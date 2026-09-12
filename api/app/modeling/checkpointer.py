"""Durable LangGraph SQLite checkpointer with owned connection lifetime.

Do not reuse a global saver against a different data directory. Connections are
closed when the data dir changes or when close_checkpointer() is called.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from ..db import get_data_dir

_CONN: sqlite3.Connection | None = None
_SAVER: SqliteSaver | None = None
_PATH: Path | None = None


def checkpoint_path() -> Path:
    return get_data_dir() / "langgraph-checkpoints.db"


def close_checkpointer() -> None:
    global _CONN, _SAVER, _PATH
    saver = _SAVER
    conn = _CONN
    _SAVER = None
    _CONN = None
    _PATH = None
    if saver is not None:
        closer = getattr(saver, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:  # noqa: BLE001
                pass
    if conn is not None:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def reset_checkpointer() -> None:
    """Tests: drop the process-global saver so a new LUCID_DATA_DIR is used."""
    close_checkpointer()


def get_checkpointer() -> SqliteSaver:
    global _CONN, _SAVER, _PATH
    path = checkpoint_path()
    if _SAVER is not None and _PATH == path:
        return _SAVER
    close_checkpointer()
    path.parent.mkdir(parents=True, exist_ok=True)
    _CONN = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
    _CONN.execute("PRAGMA journal_mode = WAL")
    _CONN.execute("PRAGMA busy_timeout = 5000")
    _SAVER = SqliteSaver(_CONN)
    _SAVER.setup()
    _PATH = path
    return _SAVER
