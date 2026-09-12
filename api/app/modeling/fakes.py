"""Labeled test double: adaptive tool use without a live model. Not a live Agent run."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr


class AdaptiveScriptModel(BaseChatModel):
    """Scripted tool-calling model for contract tests. live_execution must stay false."""

    clarify_once: bool = False
    model_name: str = "lucid-scripted-double"
    _submitted: bool = PrivateAttr(default=False)

    @property
    def _llm_type(self) -> str:
        return "lucid-scripted-double"

    def bind_tools(self, tools: Any, **kwargs: Any) -> AdaptiveScriptModel:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        tool_messages = [item for item in messages if isinstance(item, ToolMessage)]
        names = [item.name for item in tool_messages]
        if not any(name == "inspect_evidence" for name in names):
            return _call("inspect_evidence", {}, "inspect")
        inspect_payload = _latest_json(tool_messages, "inspect_evidence") or {}
        materials = inspect_payload.get("materials") or []
        read_ids = _tool_arg_ids(messages, "read_source")
        understood_ids = _tool_arg_ids(messages, "understand_material")
        readable = []
        azure_needed = []
        for item in materials:
            media = item.get("media_type") or ""
            origin = item.get("source_origin")
            if origin == "direct_text" or str(media).startswith("text/") or media == "application/json":
                readable.append(item)
            elif item.get("kind") == "table":
                readable.append(item)
            else:
                azure_needed.append(item)
        for item in readable:
            if item["id"] not in read_ids:
                return _call("read_source", {"material_id": item["id"]}, f"read-{item['id'][:8]}")
        for item in azure_needed:
            if item["id"] not in understood_ids:
                return _call(
                    "understand_material",
                    {"material_id": item["id"]},
                    f"cu-{item['id'][:8]}",
                )
        if self.clarify_once and "ask_clarification" not in names:
            return _call(
                "ask_clarification",
                {
                    "question": "Which overtime / exception owner should be treated as authoritative?",
                    "reason": "Sources leave an approval or exception owner unknown.",
                    "affected_claim_keys": ["unknown-1"],
                },
                "clarify",
            )
        if self.clarify_once and names.count("inspect_evidence") < 2:
            return _call("inspect_evidence", {}, "inspect-after-clarify")
        if self._submitted:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Draft already submitted."))])
        self._submitted = True
        excerpts = []
        for item in tool_messages:
            if item.name in {"read_source", "understand_material", "inspect_evidence", "ask_clarification"}:
                excerpts.append(str(item.content)[:1200])
        unknown_needed = self.clarify_once
        coverage = []
        for item in materials:
            state = "analyzed"
            if item.get("needs_azure") and item["id"] in understood_ids:
                blob = _latest_json(tool_messages, "understand_material") or {}
                if blob.get("status") in {"unavailable", "failed"}:
                    state = "unavailable"
            coverage.append(
                {
                    "material_id": item["id"],
                    "filename": item.get("filename") or "",
                    "state": state,
                    "detail": "Scripted double coverage",
                    "needs_azure": bool(item.get("needs_azure")),
                }
            )
        draft = {
            "completeness": "partial" if unknown_needed or any(c["state"] != "analyzed" for c in coverage) else "complete",
            "decision_brief": {
                "what_to_decide": "Produce a source-grounded business baseline for the user's question.",
                "scope": "Evidence supplied in this analysis only",
                "time_horizon": None,
                "ambiguities": ["Approval owner is not named"] if unknown_needed else [],
            },
            "entities": [
                {
                    "claim_key": "entity-1",
                    "claim_kind": "entity",
                    "original_statement": "Decision entities mentioned in supplied evidence",
                    "proposed_interpretation": "Treat named resources as candidate entities",
                    "grounding": "inferred",
                    "evidence_refs": _refs(readable),
                }
            ],
            "parameters": [],
            "decision_variables": [
                {
                    "claim_key": "var-1",
                    "name": "assignment_or_selection",
                    "domain": "finite set implied by evidence; unknown if not stated",
                    "evidence_refs": _refs(readable),
                }
            ],
            "constraints": _constraints_from_excerpts(excerpts, readable),
            "objectives": [
                {
                    "claim_key": "obj-1",
                    "original_statement": "Prefer stated objectives only; do not invent weights",
                    "proposed_interpretation": None,
                    "direction": "unknown",
                    "weight": None,
                    "weight_stated": False,
                    "grounding": "assumed",
                    "evidence_refs": [],
                }
            ],
            "assumptions": [],
            "unknowns": [
                {
                    "claim_key": "unknown-1",
                    "claim_kind": "unknown",
                    "original_statement": "At least one required approval/capacity value is not stated",
                    "grounding": "inferred",
                    "evidence_refs": _refs(readable),
                    "modelability_status": "blocked",
                }
            ]
            if unknown_needed
            else [],
            "conflicts": [],
            "clarification_questions": [],
            "readiness_issues": [
                "Partial coverage: Azure was unavailable for one or more non-text sources"
                if any(c["state"] == "unavailable" for c in coverage)
                else "Ready only for families that tolerate remaining unknowns"
            ],
            "coverage": coverage,
            "notes": "Produced by a labeled scripted test double, not a live model.",
        }
        return _call("submit_modeling_draft", {"draft": draft}, "submit")


def _call(name: str, args: dict[str, Any], call_id: str) -> ChatResult:
    message = AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )
    return ChatResult(generations=[ChatGeneration(message=message)])


def _latest_json(messages: list[ToolMessage], name: str) -> dict[str, Any] | None:
    for item in reversed(messages):
        if item.name != name:
            continue
        try:
            payload = json.loads(item.content)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _tool_arg_ids(messages: list[BaseMessage], tool_name: str) -> set[str]:
    found: set[str] = set()
    for item in messages:
        if not isinstance(item, AIMessage):
            continue
        for call in item.tool_calls or []:
            if call.get("name") == tool_name:
                args = call.get("args") or {}
                if isinstance(args, dict) and args.get("material_id"):
                    found.add(str(args["material_id"]))
    return found


def _refs(materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs = []
    for item in materials[:3]:
        span_id = (item.get("span_ids") or [None])[0]
        refs.append(
            {
                "material_id": item["id"],
                "source_span_id": span_id,
                "material_checksum": item.get("checksum"),
                "precision": "approximate" if span_id else "whole_source",
                "coordinate_system": "source_span_excerpt" if span_id else "whole_source",
                "quote": None,
            }
        )
    return refs


def _constraints_from_excerpts(
    excerpts: list[str],
    materials: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    blob = "\n".join(excerpts).lower()
    statement = "Use only constraints that appear in supplied evidence; unknowns stay unknown."
    for marker in ("must", "不得", "at most", "最多", "require", "capacity"):
        if marker in blob:
            statement = "A capacity or prohibition constraint is stated in the evidence."
            break
    return [
        {
            "claim_key": "c-1",
            "strength": "hard",
            "original_statement": statement,
            "proposed_interpretation": statement,
            "grounding": "inferred",
            "evidence_refs": _refs(materials),
            "review_status": "unreviewed",
            "modelability_status": "unknown",
        }
    ]


class ScriptedAzure:
    """Labeled Azure double. Continuation tokens stay private to the client."""

    def __init__(
        self,
        *,
        markdown: str = "Derived markdown from a labeled Azure double.",
        operation_id: str = "op-azure-real-id",
        token: str = "PRIVATE_CONTINUATION_TOKEN_OPAQUE_SECRET_VALUE_NOT_AN_ID",
        timeout: bool = False,
    ) -> None:
        self.markdown = markdown
        self.operation_id = operation_id
        self.token = token
        self.timeout = timeout

    def configured(self) -> bool:
        return True

    def start_job(self, content: bytes, *, media_type: str | None = None, continuation_token: str | None = None):
        from .azure_cu import AzureJob

        return AzureJob(
            analyzer_id="prebuilt-document",
            api_version="2025-11-01",
            status="running",
            operation_id=self.operation_id,
            continuation_token=continuation_token or self.token,
            poller=self,
        )

    def continuation_token(self) -> str:
        return self.token

    def result(self, timeout: int | None = None) -> dict[str, Any]:
        if self.timeout:
            raise TimeoutError("polling timed out")
        return {"markdown": self.markdown, "contents": [{"markdown": self.markdown}]}

    def wait(self, job, *, timeout_seconds: int = 60):
        from .azure_cu import derive_representation

        if self.timeout:
            job.status = "timeout"
            job.error_code = "timeout"
            job.error_message = "Azure Content Understanding job timed out while still running."
            return job
        job.status = "succeeded"
        job.raw = {"markdown": self.markdown, "contents": [{"markdown": self.markdown}]}
        job.derived = derive_representation(job.raw)
        job.continuation_token = self.token
        job.operation_id = self.operation_id
        return job
