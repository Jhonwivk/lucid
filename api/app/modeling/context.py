"""Run-scoped context for Agent tools. Tools never take filesystem paths or URLs."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class RunContext:
    project_id: str
    run_id: str
    thread_id: str
    live_execution: bool
    max_excerpt_chars: int = 8000
    max_tool_calls: int = 24


CURRENT_RUN: ContextVar[RunContext | None] = ContextVar("lucid_modeling_run", default=None)


def require_run() -> RunContext:
    ctx = CURRENT_RUN.get()
    if ctx is None:
        raise RuntimeError("modeling tool called outside a run")
    return ctx
