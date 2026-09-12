"""Start, resume, cancel, and poll modeling runs. UI refresh must not cancel work.

Public product execution never constructs the scripted test double. Tests inject
a model explicitly. Missing live configuration returns a failed/unavailable run.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from langgraph.errors import GraphInterrupt
from langgraph.types import Command

from .. import store
from ..db import utc_now
from ..runtime_config import snapshot
from . import persistence
from .agent import build_agent, build_live_model, live_model_available
from .context import CURRENT_RUN, RunContext

_lock = threading.Lock()
_threads: dict[str, threading.Thread] = {}
_models: dict[str, Any] = {}


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
        persistence.update_run(
            run["id"],
            status="failed",
            error_code="model_not_configured",
            error_message=(
                "Live Agent execution is blocked. Set LUCID_MODEL_NAME, "
                "LUCID_MODEL_BASE_URL, and LUCID_MODEL_API_KEY in lucid/.env. "
                "This is not a successful modeling run."
            ),
            finished_at=utc_now(),
        )
        persistence.append_event(
            run["id"],
            kind="status",
            title="Live model is not configured",
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
    persistence.claim_resume(run_id, answer)
    try:
        _spawn(run_id, resume=answer.strip())
    except store.ConflictError:
        raise
    except Exception:
        persistence.update_run(
            run_id,
            status="failed",
            error_code="resume_failed",
            error_message="Clarification was claimed but the worker could not start.",
            finished_at=utc_now(),
        )
        raise
    return persistence.get_run(run_id)


def cancel_run(run_id: str) -> dict[str, Any]:
    return persistence.request_cancel(run_id)


def _spawn(run_id: str, resume: str | None) -> None:
    with _lock:
        existing = _threads.get(run_id)
        if existing is not None and existing.is_alive():
            raise store.ConflictError("run already has an active worker")
        thread = threading.Thread(target=_execute, args=(run_id, resume), daemon=True)
        _threads[run_id] = thread
    thread.start()


def _deadline_iso(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=max(5, seconds))).isoformat()


def _execute(run_id: str, resume: str | None) -> None:
    run = persistence.get_run(run_id)
    token = None
    try:
        if run["cancel_requested"] or run["status"] == "cancelled":
            return
        current_materials = store.list_materials(run["project_id"])
        original_ids = set((run.get("snapshot") or {}).get("original_material_ids") or [])
        current_original = [
            item
            for item in current_materials
            if item["id"] in original_ids
        ] if original_ids else current_materials
        fingerprint = persistence.evidence_fingerprint(current_original if original_ids else current_materials)
        if fingerprint != run["evidence_fingerprint"] and resume is None:
            persistence.update_run(run_id, stale_input=True)
        wall_seconds = int(run.get("max_wall_seconds") or 180)
        persistence.update_run(
            run_id,
            status="running",
            started_at=run["started_at"] or utc_now(),
            wall_deadline_at=run.get("wall_deadline_at") or _deadline_iso(wall_seconds),
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
            title="Modeling run started" if resume is None else "Modeling run resumed",
            payload={"live_execution": bool(run["live_execution"])},
        )
        model = _models.get(run_id)
        if model is None:
            if run["live_execution"]:
                model = build_live_model()
                _models[run_id] = model
            else:
                persistence.update_run(
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
        if resume is None:
            payload: Any = {
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
        try:
            result = graph.invoke(payload, config)
        except GraphInterrupt:
            persistence.update_run(run_id, status="waiting_for_user")
            persistence.append_event(run_id, kind="status", title="Waiting for clarification")
            return
        state = graph.get_state(config)
        interrupts = []
        for task in getattr(state, "tasks", ()) or ():
            interrupts.extend(getattr(task, "interrupts", ()) or ())
        if interrupts:
            persistence.update_run(run_id, status="waiting_for_user")
            persistence.append_event(
                run_id,
                kind="status",
                title="Waiting for clarification",
            )
            return
        run_after = persistence.get_run(run_id)
        if run_after["cancel_requested"]:
            persistence.update_run(run_id, status="cancelled", finished_at=utc_now())
            return
        drafts = run_after.get("drafts") or []
        completeness = None
        if drafts:
            latest = persistence.get_draft(drafts[-1]["id"])
            completeness = latest.get("completeness")
        if completeness == "partial":
            persistence.update_run(run_id, status="partial", finished_at=utc_now())
        elif drafts:
            persistence.update_run(run_id, status="completed", finished_at=utc_now())
        else:
            structured = None
            if isinstance(result, dict):
                structured = result.get("structured_response")
            if structured is not None:
                from .draft import ModelingDraft

                saved = persistence.save_draft(run_id, ModelingDraft.model_validate(structured))
                persistence.update_run(
                    run_id,
                    status="partial" if saved["completeness"] == "partial" else "completed",
                    finished_at=utc_now(),
                )
            else:
                persistence.update_run(
                    run_id,
                    status="failed",
                    error_code="no_draft",
                    error_message="The Agent finished without submitting a modeling draft.",
                    finished_at=utc_now(),
                )
        persistence.append_event(run_id, kind="status", title="Modeling run finished")
    except persistence.StaleRunError as exc:
        message = str(exc)
        status = "partial" if "budget" in message or "wall time" in message else "failed"
        if "cancel" in message:
            status = "cancelled"
        persistence.update_run(
            run_id,
            status=status,
            error_code="budget_or_cancel",
            error_message=message,
            finished_at=utc_now(),
        )
    except Exception as exc:  # noqa: BLE001
        persistence.update_run(
            run_id,
            status="failed",
            error_code=type(exc).__name__,
            error_message=f"Modeling run failed ({type(exc).__name__}).",
            finished_at=utc_now(),
        )
        persistence.append_event(run_id, kind="status", title="Modeling run failed")
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
