"""SQLite connection, bootstrap, and explicit schema migrations."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .states import (
    CONDITION_KIND_SQL,
    EVIDENCE_STATUS_SQL,
    LOCATOR_KIND_SQL,
    MATERIAL_KIND_SQL,
    OWNER_KIND_SQL,
    PREMISE_STATUS_SQL,
    REVIEW_STATUS_SQL,
    RULE_KIND_SQL,
    SOLVE_RUN_STATE_SQL,
    VERSION_STATE_SQL,
    WORKFLOW_MATURITY_SQL,
)

SCHEMA_VERSION = 6
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent
_DOTENV_LOADED = False


def load_optional_dotenv() -> None:
    """Load local LUCID .env files without logging or returning secret values."""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    for path in (PROJECT_ROOT / ".env", PACKAGE_ROOT / ".env"):
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ[key] = value


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_data_dir() -> Path:
    load_optional_dotenv()
    raw = os.environ.get("LUCID_DATA_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return PROJECT_ROOT / "data"


def get_db_path() -> Path:
    load_optional_dotenv()
    raw = os.environ.get("LUCID_DB_PATH")
    if raw:
        return Path(raw).expanduser().resolve()
    return get_data_dir() / "lucid.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_file = path or get_db_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='app_meta'"
    ).fetchone()
    if row is None:
        return 0
    value = conn.execute(
        "SELECT value FROM app_meta WHERE key = 'schema_version'"
    ).fetchone()
    if value is None:
        return 0
    return int(value["value"])


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO app_meta (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (key, value, utc_now()),
    )


MIGRATION_1_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS app_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS analysis_project (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        summary TEXT,
        workflow_maturity TEXT NOT NULL
            CHECK (workflow_maturity IN {WORKFLOW_MATURITY_SQL}),
        is_demo INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0, 1)),
        latest_understanding_revision_id TEXT,
        latest_scenario_id TEXT,
        latest_scenario_revision_id TEXT,
        latest_formal_model_id TEXT,
        latest_solve_run_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_analysis_project_single_demo
        ON analysis_project(is_demo) WHERE is_demo = 1
    """,
    f"""
    CREATE TABLE IF NOT EXISTS material (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES analysis_project(id),
        filename TEXT NOT NULL,
        media_type TEXT,
        kind TEXT NOT NULL CHECK (kind IN {MATERIAL_KIND_SQL}),
        byte_size INTEGER,
        checksum TEXT,
        notes TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_material_project
        ON material(project_id, created_at)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS source_span (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES analysis_project(id),
        material_id TEXT NOT NULL REFERENCES material(id),
        locator_kind TEXT NOT NULL CHECK (locator_kind IN {LOCATOR_KIND_SQL}),
        page INTEGER,
        start_offset INTEGER,
        end_offset INTEGER,
        sheet TEXT,
        cell_ref TEXT,
        region_json TEXT,
        excerpt TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_source_span_project
        ON source_span(project_id, material_id)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS understanding_revision (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES analysis_project(id),
        revision_no INTEGER NOT NULL,
        parent_revision_id TEXT REFERENCES understanding_revision(id),
        version_state TEXT NOT NULL CHECK (version_state IN {VERSION_STATE_SQL}),
        summary TEXT,
        assumptions_json TEXT NOT NULL DEFAULT '[]',
        unknowns_json TEXT NOT NULL DEFAULT '[]',
        conflicts_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        UNIQUE (project_id, revision_no)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_understanding_project
        ON understanding_revision(project_id, revision_no)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS scenario (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES analysis_project(id),
        name TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_scenario_project
        ON scenario(project_id, created_at)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS formal_model (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES analysis_project(id),
        scenario_revision_id TEXT,
        name TEXT NOT NULL,
        version_state TEXT NOT NULL CHECK (version_state IN {VERSION_STATE_SQL}),
        variable_count INTEGER,
        constraint_count INTEGER,
        objective_text TEXT,
        notes TEXT,
        created_at TEXT NOT NULL
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS scenario_revision (
        id TEXT PRIMARY KEY,
        scenario_id TEXT NOT NULL REFERENCES scenario(id),
        project_id TEXT NOT NULL REFERENCES analysis_project(id),
        revision_no INTEGER NOT NULL,
        parent_revision_id TEXT REFERENCES scenario_revision(id),
        version_state TEXT NOT NULL CHECK (version_state IN {VERSION_STATE_SQL}),
        based_on_understanding_id TEXT REFERENCES understanding_revision(id),
        formal_model_id TEXT REFERENCES formal_model(id),
        notes TEXT,
        created_at TEXT NOT NULL,
        UNIQUE (scenario_id, revision_no)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_scenario_revision_scenario
        ON scenario_revision(scenario_id, revision_no)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS rule (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES analysis_project(id),
        owner_kind TEXT NOT NULL CHECK (owner_kind IN {OWNER_KIND_SQL}),
        understanding_revision_id TEXT REFERENCES understanding_revision(id),
        scenario_revision_id TEXT REFERENCES scenario_revision(id),
        rule_kind TEXT NOT NULL CHECK (rule_kind IN {RULE_KIND_SQL}),
        statement TEXT NOT NULL,
        review_status TEXT NOT NULL CHECK (review_status IN {REVIEW_STATUS_SQL}),
        evidence_status TEXT NOT NULL CHECK (evidence_status IN {EVIDENCE_STATUS_SQL}),
        source_span_id TEXT REFERENCES source_span(id),
        condition_kind TEXT CHECK (condition_kind IS NULL OR condition_kind IN {CONDITION_KIND_SQL}),
        premise_status TEXT CHECK (premise_status IS NULL OR premise_status IN {PREMISE_STATUS_SQL}),
        premise_text TEXT,
        cost REAL,
        capacity REAL,
        permission INTEGER CHECK (permission IS NULL OR permission IN (0, 1)),
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rule_understanding
        ON rule(understanding_revision_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rule_scenario
        ON rule(scenario_revision_id)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS solve_run (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES analysis_project(id),
        scenario_revision_id TEXT NOT NULL REFERENCES scenario_revision(id),
        formal_model_id TEXT REFERENCES formal_model(id),
        run_state TEXT NOT NULL CHECK (run_state IN {SOLVE_RUN_STATE_SQL}),
        claimed_execution INTEGER NOT NULL DEFAULT 0 CHECK (claimed_execution = 0),
        execution TEXT NOT NULL DEFAULT 'not_executed',
        solver_name TEXT,
        started_at TEXT,
        finished_at TEXT,
        message TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_solve_run_project
        ON solve_run(project_id, created_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS result_candidate (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES analysis_project(id),
        solve_run_id TEXT NOT NULL REFERENCES solve_run(id),
        label TEXT,
        objective_value REAL,
        is_selected INTEGER CHECK (is_selected IS NULL OR is_selected IN (0, 1)),
        notes TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_result_candidate_run
        ON result_candidate(solve_run_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS change_event (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES analysis_project(id),
        event_type TEXT NOT NULL,
        entity_kind TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        summary TEXT NOT NULL,
        payload_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_change_event_project
        ON change_event(project_id, created_at)
    """,
)


MIGRATION_2_STATEMENTS = (
    """
    ALTER TABLE material ADD COLUMN metadata_json TEXT
    """,
)


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, spec: str) -> None:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {spec}")


def _migrate_to_3(conn: sqlite3.Connection) -> None:
    """Additive Stage 1 modeling tables; preserve existing rows and confirmed states."""
    _add_column_if_missing(conn, "analysis_project", "decision_question", "TEXT")
    _add_column_if_missing(conn, "analysis_project", "latest_modeling_run_id", "TEXT")
    _add_column_if_missing(conn, "analysis_project", "latest_modeling_draft_id", "TEXT")
    _add_column_if_missing(conn, "analysis_project", "latest_baseline_id", "TEXT")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS modeling_run (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES analysis_project(id),
            thread_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN (
                'queued','running','waiting_for_user','partial','completed','failed','cancelled'
            )),
            question TEXT NOT NULL,
            evidence_fingerprint TEXT NOT NULL,
            parent_run_id TEXT,
            coverage_json TEXT NOT NULL DEFAULT '[]',
            error_code TEXT,
            error_message TEXT,
            tool_call_count INTEGER NOT NULL DEFAULT 0,
            max_tool_calls INTEGER NOT NULL DEFAULT 24,
            started_at TEXT,
            finished_at TEXT,
            heartbeat_at TEXT,
            cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1)),
            stale_input INTEGER NOT NULL DEFAULT 0 CHECK (stale_input IN (0, 1)),
            live_execution INTEGER NOT NULL DEFAULT 0 CHECK (live_execution IN (0, 1)),
            model_configured INTEGER NOT NULL DEFAULT 0 CHECK (model_configured IN (0, 1)),
            azure_configured INTEGER NOT NULL DEFAULT 0 CHECK (azure_configured IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_modeling_run_project
            ON modeling_run(project_id, created_at);
        CREATE TABLE IF NOT EXISTS modeling_run_event (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES modeling_run(id),
            project_id TEXT NOT NULL REFERENCES analysis_project(id),
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            detail TEXT,
            payload_json TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_modeling_run_event_run
            ON modeling_run_event(run_id, created_at);
        CREATE TABLE IF NOT EXISTS material_analysis (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES analysis_project(id),
            material_id TEXT NOT NULL REFERENCES material(id),
            material_checksum TEXT,
            provider TEXT NOT NULL DEFAULT 'azure_content_understanding',
            analyzer_id TEXT,
            api_version TEXT,
            operation_id TEXT,
            operation_url TEXT,
            continuation_token TEXT,
            status TEXT NOT NULL,
            raw_response_json TEXT,
            derived_markdown TEXT,
            locator_map_json TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_material_analysis_material
            ON material_analysis(material_id, analyzer_id);
        CREATE TABLE IF NOT EXISTS modeling_draft (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES analysis_project(id),
            run_id TEXT NOT NULL REFERENCES modeling_run(id),
            revision_no INTEGER NOT NULL,
            parent_draft_id TEXT,
            version_state TEXT NOT NULL,
            completeness TEXT NOT NULL,
            understanding_revision_id TEXT,
            draft_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (project_id, revision_no)
        );
        CREATE TABLE IF NOT EXISTS modeling_claim (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES analysis_project(id),
            draft_id TEXT NOT NULL REFERENCES modeling_draft(id),
            claim_key TEXT NOT NULL,
            claim_kind TEXT NOT NULL,
            original_statement TEXT NOT NULL,
            proposed_interpretation TEXT,
            edited_statement TEXT,
            grounding TEXT NOT NULL,
            review_status TEXT NOT NULL CHECK (review_status IN (
                'unreviewed','accepted','rejected','needs_clarification','not_applicable'
            )),
            modelability_status TEXT NOT NULL DEFAULT 'unknown',
            applicability TEXT,
            evidence_refs_json TEXT NOT NULL DEFAULT '[]',
            rule_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_modeling_claim_draft
            ON modeling_claim(draft_id);
        CREATE TABLE IF NOT EXISTS modeling_clarification (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES analysis_project(id),
            run_id TEXT NOT NULL REFERENCES modeling_run(id),
            question TEXT NOT NULL,
            reason TEXT,
            affected_claim_keys_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL,
            answer_text TEXT,
            answer_material_id TEXT,
            created_at TEXT NOT NULL,
            answered_at TEXT
        );
        CREATE TABLE IF NOT EXISTS modeling_baseline (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES analysis_project(id),
            draft_id TEXT NOT NULL REFERENCES modeling_draft(id),
            understanding_revision_id TEXT,
            scenario_id TEXT,
            scenario_revision_id TEXT,
            export_json TEXT NOT NULL,
            export_markdown TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rule_v3 (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES analysis_project(id),
                owner_kind TEXT NOT NULL,
                understanding_revision_id TEXT,
                scenario_revision_id TEXT,
                rule_kind TEXT NOT NULL,
                statement TEXT NOT NULL,
                review_status TEXT NOT NULL CHECK (review_status IN (
                    'unreviewed','accepted','rejected','needs_clarification','not_applicable'
                )),
                evidence_status TEXT NOT NULL,
                source_span_id TEXT,
                condition_kind TEXT,
                premise_status TEXT,
                premise_text TEXT,
                cost REAL,
                capacity REAL,
                permission INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='rule'"
        ).fetchone()
        v3_count = conn.execute("SELECT COUNT(*) AS n FROM rule_v3").fetchone()["n"]
        if existing is not None and v3_count == 0:
            conn.execute("INSERT INTO rule_v3 SELECT * FROM rule")
            conn.execute("DROP TABLE rule")
            conn.execute("ALTER TABLE rule_v3 RENAME TO rule")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rule_understanding ON rule(understanding_revision_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rule_scenario ON rule(scenario_revision_id)"
            )
        elif existing is None:
            conn.execute("ALTER TABLE rule_v3 RENAME TO rule")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _migrate_to_4(conn: sqlite3.Connection) -> None:
    """Frozen run snapshots, resume claims, review audit, freeze uniqueness."""
    _add_column_if_missing(conn, "modeling_run", "snapshot_json", "TEXT")
    _add_column_if_missing(conn, "modeling_run", "question_material_id", "TEXT")
    _add_column_if_missing(conn, "modeling_run", "resume_claim_id", "TEXT")
    _add_column_if_missing(conn, "modeling_run", "wall_deadline_at", "TEXT")
    _add_column_if_missing(conn, "modeling_run", "max_wall_seconds", "INTEGER NOT NULL DEFAULT 180")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS modeling_claim_review_event (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES analysis_project(id),
            draft_id TEXT NOT NULL REFERENCES modeling_draft(id),
            claim_id TEXT NOT NULL REFERENCES modeling_claim(id),
            previous_status TEXT NOT NULL,
            new_status TEXT NOT NULL,
            previous_edited_statement TEXT,
            new_edited_statement TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_modeling_claim_review_claim
            ON modeling_claim_review_event(claim_id, created_at)
        """
    )
    duplicates = conn.execute(
        """
        SELECT draft_id, claim_key, COUNT(*) AS n
        FROM modeling_claim
        GROUP BY draft_id, claim_key
        HAVING n > 1
        """
    ).fetchone()
    if duplicates is None:
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_modeling_claim_unique_key
                ON modeling_claim(draft_id, claim_key)
            """
        )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_modeling_baseline_draft
            ON modeling_baseline(draft_id)
        """
    )


def _migrate_to_5(conn: sqlite3.Connection) -> None:
    """At most one queued/running/waiting_for_user modeling run per project."""
    rows = conn.execute(
        """
        SELECT id, project_id FROM modeling_run
        WHERE status IN ('queued','running','waiting_for_user')
        ORDER BY project_id, updated_at DESC, created_at DESC, id DESC
        """
    ).fetchall()
    seen: set[str] = set()
    now = utc_now()
    for row in rows:
        project_id = row["project_id"]
        if project_id in seen:
            conn.execute(
                """
                UPDATE modeling_run
                SET status = 'failed',
                    error_code = 'superseded_active_run',
                    error_message = 'Closed because another active modeling run already existed for this analysis.',
                    finished_at = ?,
                    updated_at = ?
                WHERE id = ?
                  AND status IN ('queued','running','waiting_for_user')
                """,
                (now, now, row["id"]),
            )
        else:
            seen.add(project_id)
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_modeling_run_one_active
            ON modeling_run(project_id)
            WHERE status IN ('queued','running','waiting_for_user')
        """
    )



def _migrate_to_6(conn: sqlite3.Connection) -> None:
    """Add structured formal-model payload and invalidation audit fields."""
    _add_column_if_missing(conn, "formal_model", "definition_json", "TEXT")
    _add_column_if_missing(conn, "formal_model", "definition_hash", "TEXT")
    _add_column_if_missing(conn, "formal_model", "dependency_fingerprint", "TEXT")
    _add_column_if_missing(conn, "scenario_revision", "invalidation_reason", "TEXT")
    _add_column_if_missing(conn, "scenario_revision", "invalidated_at", "TEXT")


def apply_migrations(conn: sqlite3.Connection) -> int:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    current = _schema_version(conn)
    if current < 1:
        for statement in MIGRATION_1_STATEMENTS:
            conn.execute(statement)
        _set_meta(conn, "schema_version", "1")
        current = 1
    if current < 2:
        for statement in MIGRATION_2_STATEMENTS:
            conn.execute(statement)
        _set_meta(conn, "schema_version", "2")
        current = 2
        _set_meta(conn, "bootstrap", "t07-t08-intake")
    if current < 3:
        _migrate_to_3(conn)
        _set_meta(conn, "schema_version", "3")
        current = 3
        _set_meta(conn, "bootstrap", "stage1-modeling-agent")
    if current < 4:
        _migrate_to_4(conn)
        _set_meta(conn, "schema_version", "4")
        current = 4
        _set_meta(conn, "bootstrap", "stage1-review-corrections")
    if current < 5:
        _migrate_to_5(conn)
        _set_meta(conn, "schema_version", "5")
        current = 5
        _set_meta(conn, "bootstrap", "stage1-one-active-run")
    if current < 6:
        _migrate_to_6(conn)
        _set_meta(conn, "schema_version", "6")
        current = 6
        _set_meta(conn, "bootstrap", "stage2-formalization")
    return current


def ensure_database(path: Path | None = None) -> Path:
    db_file = path or get_db_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_file)
    try:
        with conn:
            apply_migrations(conn)
    finally:
        conn.close()
    return db_file
