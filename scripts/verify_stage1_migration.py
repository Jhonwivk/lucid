#!/usr/bin/env python3
"""Safe migration check: existing DB snapshots upgrade without wiping rows."""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "api"
sys.path.insert(0, str(API_ROOT))

PRE_V2 = ROOT / "data" / "backups" / "lucid-20260912-pre-stage1.db"
PRE_V3 = ROOT / "data" / "backups" / "stage1-20260912" / "lucid.db"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def migrate_copy(src: Path, label: str) -> None:
    expect(src.is_file(), f"missing snapshot {src}")
    tmp = Path(tempfile.mkdtemp(prefix=f"lucid-mig-{label}-"))
    dest = tmp / "lucid.db"
    shutil.copy2(src, dest)
    before = sqlite3.connect(dest)
    before_projects = before.execute("SELECT COUNT(*) FROM analysis_project").fetchone()[0]
    before_materials = before.execute("SELECT COUNT(*) FROM material").fetchone()[0]
    before.close()
    os.environ["LUCID_DB_PATH"] = str(dest)
    os.environ["LUCID_DATA_DIR"] = str(tmp)
    from app.db import SCHEMA_VERSION, ensure_database

    ensure_database(dest)
    after = sqlite3.connect(dest)
    version = int(after.execute("SELECT value FROM app_meta WHERE key='schema_version'").fetchone()[0])
    projects = after.execute("SELECT COUNT(*) FROM analysis_project").fetchone()[0]
    materials = after.execute("SELECT COUNT(*) FROM material").fetchone()[0]
    cols = {row[1] for row in after.execute("PRAGMA table_info(modeling_run)")}
    after.close()
    expect(version == SCHEMA_VERSION, f"{label} schema {version} != {SCHEMA_VERSION}")
    expect(projects == before_projects, f"{label} project count changed {before_projects}->{projects}")
    expect(materials == before_materials, f"{label} material count changed {before_materials}->{materials}")
    expect("snapshot_json" in cols, f"{label} missing snapshot_json")
    print(f"PASS migration {label}: version={version} projects={projects} materials={materials}")
    shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    migrate_copy(PRE_V2, "schema2")
    if PRE_V3.is_file():
        migrate_copy(PRE_V3, "schema3")
    print("PASS: existing snapshots migrate without wiping rows")


if __name__ == "__main__":
    main()
