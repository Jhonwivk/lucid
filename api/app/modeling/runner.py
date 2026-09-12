"""Start, resume, cancel, and poll modeling runs. UI refresh must not cancel work.

Public product execution never constructs the scripted test double. Tests inject
a model explicitly. Missing live configuration returns a failed/unavailable run.

Process restart recovers live runs that still have a LangGraph checkpoint.
Injected doubles and overdue heartbeats fail with a visible worker_lost/timeout.
"""

from __future__ import annotations

import contextvars
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from langgraph.errors import GraphInterrupt
from langgraph.types import Command

from .. import store
from ..db import utc_now
from ..runtime_config import snapshot
from . import persistence
from .agent import build_agent, build_live_model, live_model_available
from .checkpointer import get_checkpointer
from .context import CURRENT_RUN, RunContext

_lock = threading.Lock()
_threads: dict[str, threading.Thread] = {}
_models: dict[str, Any] = {}
_recovered = False


def start_run(
    project_id: str,
    question: str,
    *,
    model: Any | None = None,
    max_tool_calls: int = 24,
    max_wall_seconds: int = 180,
) -> dict[str, Any]:
    store.get_project(project_id)
    if not question.strip():
        raise ValueError("a decision question is required")
    question_material = persistence.ensure_question_material(project_id, question)
    materials = store.list_materials(project_id)
    if not materials:
        raise ValueError("meaningful analysis needs a non-empty evidence set")
    snap = snapshot()
    if model is None and not live_model_available():
        run = persistence.create_run(
            project_id,
            question=question.strip(),
            live_execution=False,
            model_configured=False,
            azure_configured=bool(snap["live_azure_possible"]),
            max_tool_calls=max_tool_calls,
            max_wall_seconds=max_wall_seconds,
            question_material_id=question_material["id"],
        )
        persistence.mark_run_failed(
            run["id"],
            error_code="model_not_configured",
            error_message=(
                "Live Agent execution is blocked. Set LUCID_MODEL_NAME, "
                "LUCID_MODEL_BASE_URL, and LUCID_MODEL_API_KEY in lucid/.env. "
                "This is not a successful modeling run."
            ),
            event_title="Live model is not configured",
        )
        return persistence.get_run(run["id"])
    live_execution = model is None
    if live_execution:
        model = build_live_model()
    run = persistence.create_run(
        project_id,
        question=question.strip(),
        live_execution=live_execution,
        model_configured=bool(snap["live_agent_possible"]) or not live_execution,
        azure_configured=bool(snap["live_azure_possible"]),
        max_tool_calls=max_tool_calls,
        max_wall_seconds=max_wall_seconds,
        question_material_id=question_material["id"],
    )
    _models[run["id"]] = model
    _spawn(run["id"], resume=None)
    return persistence.get_run(run["id"])


def resume_run(run_id: str, answer: str) -> dict[str, Any]:
    claimed = persistence.claim_resume(run_id, answer)
    claim_id = claimed.get("resume_claim_id")
    try:
        _spawn(run_id, resume=answer.strip())
    except store.ConflictError:
        if _worker_alive(run_id):
            return persistence.get_run(run_id)
        persistence.rollback_resume(run_id, claim_id)
        raise
    except Exception:
        persistence.rollback_resume(run_id, claim_id)
        raise
    return persistence.get_run(run_id)


def cancel_run(run_id: str) -> dict[str, Any]:
    return persistence.request_cancel(run_id)


def has_checkpoint(thread_id: str) -> bool:
    try:
        saver = get_checkpointer()
        config = {"configurable": {"thread_id": thread_id}}
        getter = getattr(saver, "get_tuple", None) or getattr(saver, "get", None)
        if getter is None:
            return False
        state = getter(config)
        return state is not None
    except Exception:  # noqa: BLE001
        return False


def _worker_alive(run_id: str) -> bool:
    thread = _threads.get(run_id)
    return thread is not None and thread.is_alive()


def recover_orphaned_runs() -> list[dict[str, Any]]:
    """Scan queued/running rows on process start. Do not use in-memory maps as truth."""
    recovered: list[dict[str, Any]] = []
    for run in persistence.list_runs_in_statuses(("queued", "running")):
        expired = persistence.maybe_expire_run(run["id"])
        if expired["status"] not in {"queued", "running"}:
            recovered.append(expired)
            continue
        if not expired["live_execution"]:
            persistence.mark_run_failed(
                expired["id"],
                error_code="worker_lost",
                error_message=(
                    "This run used an injected test double that is no longer in process. "
                    "It is not a live model run."
                ),
                event_title="Worker lost after restart",
            )
            recovered.append(persistence.get_run(expired["id"]))
            continue
        if not live_model_available():
            persistence.mark_run_failed(
                expired["id"],
                error_code="model_not_configured",
                error_message="Live model is not configured; the interrupted run cannot be recovered.",
                event_title="Live model is not configured",
            )
            recovered.append(persistence.get_run(expired["id"]))
            continue
        continue_from_checkpoint = expired["status"] == "running" and has_checkpoint(expired["thread_id"])
        if expired["status"] == "running" and not continue_from_checkpoint:
            persistence.mark_run_failed(
                expired["id"],
                error_code="worker_lost",
                error_message="No LangGraph checkpoint remains for this live run after restart.",
                event_title="Worker lost after restart",
            )
            recovered.append(persistence.get_run(expired["id"]))
            continue
        try:
            _models[expired["id"]] = build_live_model()
            _spawn(expired["id"], resume="__continue__" if continue_from_checkpoint else None)
            persistence.append_event(expired["id"], kind="status", title="Recovered modeling worker after restart")
        except Exception as exc:  # noqa: BLE001
            persistence.mark_run_failed(
                expired["id"],
                error_code="worker_lost",
                error_message=f"Could not recover worker ({type(exc).__name__}).",
                event_title="Worker lost after restart",
            )
        recovered.append(persistence.get_run(expired["id"]))
    return recovered


def recover_on_startup() -> None:
    global _recovered
    if _recovered:
        return
    _recovered = True
    recover_orphaned_runs()


def _spawn(run_id: str, resume: str | None) -> None:
    with _lock:
        existing = _threads.get(run_id)
        if existing is not None and existing.is_alive():
            raise store.ConflictError("run already has an active worker")
        thread = threading.Thread(target=_execute, args=(run_id, resume), daemon=True)
        _threads[run_id] = thread
    thread.start()


def _deadline_iso(seconds: int) -> str:
    return persistence.execution_deadline_iso(seconds)


def _seconds_remaining(deadline_iso: str | None) -> float:
    if not deadline_iso:
        return 180.0
    try:
        stamp = datetime.fromisoformat(str(deadline_iso).replace("Z", "+00:00"))
    except ValueError:
        return 180.0
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (stamp - datetime.now(timezone.utc)).total_seconds()


def _invoke_with_deadline(graph: Any, payload: Any, config: dict[str, Any], run_id: str, deadline_iso: str | None) -> Any:
    remaining = _seconds_remaining(deadline_iso)
    if remaining <= 0:
        persistence.mark_run_failed(
            run_id,
            error_code="timeout",
            error_message="Wall time exhausted before the model call. This is not a successful modeling run.",
            event_title="Wall time exhausted",
            event_payload={"error_code": "timeout"},
        )
        raise persistence.StaleRunError("wall time exhausted")
    pool = ThreadPoolExecutor(max_workers=1)
    copied = contextvars.copy_context()
    future = pool.submit(copied.run, graph.invoke, payload, config)
    try:
        while True:
            try:
                return future.result(timeout=min(2.0, max(0.1, remaining)))
            except TimeoutError:
                remaining = _seconds_remaining(deadline_iso)
                current = persistence.get_run(run_id)
                if current["status"] in persistence.TERMINAL_STATUSES:
                    raise persistence.StaleRunError(f"{current['status']} run cannot accept further model output")
                if current["cancel_requested"] or current["status"] == "cancelled":
                    raise persistence.StaleRunError("run cancelled")
                if remaining <= 0:
                    persistence.mark_run_failed(
                        run_id,
                        error_code="timeout",
                        error_message="graph.invoke() exceeded max_wall_seconds. This is not a successful modeling run.",
                        event_title="Model call timed out",
                        event_payload={"error_code": "timeout"},
                    )
                    raise persistence.StaleRunError("wall time exhausted")
                persistence.touch_heartbeat(run_id)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _finish(run_id: str, **fields: Any) -> None:
    try:
        persistence.update_run(run_id, **fields)
    except persistence.StaleRunError:
        return


def _execute(run_id: str, resume: str | None) -> None:
    run = persistence.get_run(run_id)
    token = None
    try:
        if run["cancel_requested"] or run["status"] == "cancelled":
            return
        if run["status"] in persistence.TERMINAL_STATUSES:
            return
        current_materials = store.list_materials(run["project_id"])
        original_ids = set((run.get("snapshot") or {}).get("original_material_ids") or [])
        current_original = (
            [item for item in current_materials if item["id"] in original_ids]
            if original_ids
            else current_materials
        )
        fingerprint = persistence.evidence_fingerprint(current_original if original_ids else current_materials)
        if fingerprint != run["evidence_fingerprint"] and resume is None:
            persistence.update_run(run_id, stale_input=True)
        wall_seconds = int(run.get("max_wall_seconds") or 180)
        human_resume = resume not in {None, "__continue__"}
        existing_deadline = run.get("wall_deadline_at")
        if human_resume:
            deadline = existing_deadline if existing_deadline and str(existing_deadline) >= utc_now() else _deadline_iso(wall_seconds)
        else:
            deadline = existing_deadline or _deadline_iso(wall_seconds)
        if run["status"] != "running":
            persistence.update_run(
                run_id,
                status="running",
                started_at=run["started_at"] or utc_now(),
                wall_deadline_at=deadline,
                heartbeat_at=utc_now(),
            )
        else:
            persistence.update_run(
                run_id,
                started_at=run["started_at"] or utc_now(),
                wall_deadline_at=deadline,
                heartbeat_at=utc_now(),
            )
        ctx = RunContext(
            project_id=run["project_id"],
            run_id=run_id,
            thread_id=run["thread_id"],
            live_execution=bool(run["live_execution"]),
            max_tool_calls=int(run["max_tool_calls"]),
        )
        token = CURRENT_RUN.set(ctx)
        persistence.append_event(
            run_id,
            kind="status",
            title="Modeling run started" if resume in {None, "__continue__"} else "Modeling run resumed",
            payload={"live_execution": bool(run["live_execution"])},
        )
        model = _models.get(run_id)
        if model is None:
            if run["live_execution"]:
                model = build_live_model()
                _models[run_id] = model
            else:
                _finish(
                    run_id,
                    status="failed",
                    error_code="worker_lost",
                    error_message=(
                        "This run used an injected test double that is no longer in process. "
                        "It is not a live model run."
                    ),
                    finished_at=utc_now(),
                )
                return
        graph = build_agent(model)
        config = {
            "configurable": {"thread_id": run["thread_id"]},
            "recursion_limit": max(8, int(run["max_tool_calls"]) * 2),
        }
        if resume == "__continue__":
            payload: Any = None
        elif resume is None:
            payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Decision question:\n{run['question']}\n\n"
                            "Inspect the evidence snapshot, use tools as needed, "
                            "and submit a grounded modeling draft. Do not solve."
                        ),
                    }
                ]
            }
        else:
            payload = Command(resume=resume)
        run = persistence.get_run(run_id)
        try:
            result = _invoke_with_deadline(graph, payload, config, run_id, run.get("wall_deadline_at"))
        except GraphInterrupt:
            _finish(run_id, status="waiting_for_user", wall_deadline_at=None)
            persistence.append_event(run_id, kind="status", title="Waiting for clarification")
            return
        state = graph.get_state(config)
        interrupts = []
        for task in getattr(state, "tasks", ()) or ():
            interrupts.extend(getattr(task, "interrupts", ()) or ())
        run_after = persistence.get_run(run_id)
        if interrupts and not (run_after.get("drafts") or []):
            _finish(run_id, status="waiting_for_user", wall_deadline_at=None)
            persistence.append_event(
                run_id,
                kind="status",
                title="Waiting for clarification",
            )
            return
        if run_after["cancel_requested"] or run_after["status"] == "cancelled":
            _finish(run_id, status="cancelled", finished_at=utc_now())
            return
        if run_after["status"] in persistence.TERMINAL_STATUSES:
            return
        drafts = run_after.get("drafts") or []
        completeness = None
        if drafts:
            latest = persistence.get_draft(drafts[-1]["id"])
            completeness = latest.get("completeness")
        if completeness == "partial":
            _finish(run_id, status="partial", finished_at=utc_now())
        elif drafts:
            _finish(run_id, status="completed", finished_at=utc_now())
        else:
            structured = None
            if isinstance(result, dict):
                structured = result.get("structured_response")
            if structured is not None:
                from .draft import ModelingDraft

                saved = persistence.save_draft(run_id, ModelingDraft.model_validate(structured))
                _finish(
                    run_id,
                    status="partial" if saved["completeness"] == "partial" else "completed",
                    finished_at=utc_now(),
                )
            else:
                _finish(
                    run_id,
                    status="failed",
                    error_code="no_draft",
                    error_message="The Agent finished without submitting a modeling draft.",
                    finished_at=utc_now(),
                )
        persistence.append_event(run_id, kind="status", title="Modeling run finished", allow_terminal=True)
    except persistence.StaleRunError as exc:
        current = persistence.get_run(run_id)
        if current["status"] in persistence.TERMINAL_STATUSES:
            return
        message = str(exc)
        status = "partial" if "budget" in message or "wall time" in message else "failed"
        code = "budget_or_cancel"
        if "cancel" in message:
            status = "cancelled"
            code = "cancelled"
        if "wall time" in message or "timeout" in message:
            status = "failed"
            code = "timeout"
        _finish(
            run_id,
            status=status,
            error_code=code,
            error_message=message,
            finished_at=utc_now(),
        )
    except Exception as exc:  # noqa: BLE001
        current = persistence.get_run(run_id)
        if current["status"] in persistence.TERMINAL_STATUSES:
            return
        _finish(
            run_id,
            status="failed",
            error_code=type(exc).__name__,
            error_message=f"Modeling run failed ({type(exc).__name__}).",
            finished_at=utc_now(),
        )
        persistence.append_event(run_id, kind="status", title="Modeling run failed", allow_terminal=True)
    finally:
        if token is not None:
            CURRENT_RUN.reset(token)


def wait_for_run(run_id: str, timeout: float = 90.0) -> dict[str, Any]:
    import time

    deadline = time.time() + timeout
    terminal = {"waiting_for_user", "partial", "completed", "failed", "cancelled"}
    while time.time() < deadline:
        run = persistence.get_run(run_id)
        if run["status"] in terminal:
            thread = _threads.get(run_id)
            if thread is not None:
                thread.join(timeout=0.5)
            return persistence.get_run(run_id)
        thread = _threads.get(run_id)
        if thread is not None:
            thread.join(timeout=0.2)
        else:
            time.sleep(0.1)
    raise TimeoutError(f"modeling run {run_id} did not finish within {timeout}s")
