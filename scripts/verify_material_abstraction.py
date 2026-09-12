#!/usr/bin/env python3
"""Focused Materials abstraction proof: direct text, no-vision images, mixed Evidence Set."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "api"
VENV_PYTHON = API_ROOT / ".venv" / "bin" / "python"
VISION_MODULE = API_ROOT / "app" / "importers" / "vision.py"


def _reexec_with_venv() -> None:
    if not VENV_PYTHON.exists():
        return
    current = Path(sys.executable).resolve()
    target = VENV_PYTHON.resolve()
    if current == target:
        return
    os.execv(str(target), [str(target), *sys.argv])


_reexec_with_venv()


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def find_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def json_request(base: str, method: str, path: str, payload: dict | None = None) -> tuple[int, dict | list]:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None or method in {"POST", "PATCH"}:
        data = json.dumps(payload or {}).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed: dict | list = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return exc.code, parsed


def import_file(
    base: str,
    project_id: str,
    filename: str,
    content: bytes,
    content_type: str = "application/octet-stream",
) -> tuple[int, dict | list]:
    boundary = "----LucidMaterialBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        base + f"/api/projects/{project_id}/materials/import",
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed: dict | list = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return exc.code, parsed


def wait_health(base: str) -> None:
    deadline = time.time() + 15
    last_error = "timeout"
    while time.time() < deadline:
        try:
            status, body = json_request(base, "GET", "/api/health")
            if status == 200 and isinstance(body, dict) and body.get("status") == "ok":
                return
            last_error = f"status={status} body={body}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(0.1)
    raise SystemExit(f"FAIL: API did not become healthy: {last_error}")


def sha256_label(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def stored_file(data_dir: Path, material: dict) -> Path:
    metadata = material.get("metadata") or {}
    stored = metadata.get("stored_path")
    expect(isinstance(stored, str) and stored, "stored_path in metadata")
    path = data_dir / stored
    expect(path.is_file(), f"stored file exists: {path}")
    return path


def reopen_material(db_path: Path, material_id: str) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM material WHERE id = ?", (material_id,)).fetchone()
        expect(row is not None, f"material {material_id} in sqlite")
        return dict(row)
    finally:
        conn.close()


def reopen_spans(db_path: Path, material_id: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM source_span WHERE material_id = ? ORDER BY created_at, id",
            (material_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def list_materials(base: str, project_id: str) -> list[dict]:
    status, body = json_request(base, "GET", f"/api/projects/{project_id}/materials")
    expect(status == 200 and isinstance(body, list), f"list materials {status}")
    return body  # type: ignore[return-value]


def _venv_site() -> Path | None:
    lib = API_ROOT / ".venv" / "lib"
    if not lib.is_dir():
        return None
    for child in sorted(lib.iterdir()):
        site = child / "site-packages"
        if site.is_dir():
            return site
    return None


def tiny_png() -> bytes:
    site = _venv_site()
    if site is not None and str(site) not in sys.path:
        sys.path.insert(0, str(site))
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (32, 24), (40, 80, 90)).save(buf, format="PNG")
    return buf.getvalue()


def main() -> None:
    expect(not VISION_MODULE.is_file(), "importers/vision.py must not exist")

    tmp = tempfile.TemporaryDirectory(prefix="lucid-materials-")
    tmp_path = Path(tmp.name)
    db_path = tmp_path / "lucid.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    port = find_port()
    base = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env["LUCID_DB_PATH"] = str(db_path)
    env["LUCID_DATA_DIR"] = str(data_dir)
    python = str(VENV_PYTHON if VENV_PYTHON.exists() else sys.executable)
    proc = subprocess.Popen(
        [
            python,
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            str(API_ROOT),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(API_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        wait_health(base)
        status, shell = json_request(base, "GET", "/api/shell")
        expect(status == 200 and isinstance(shell, dict), "shell")
        caps = shell["capabilities"]
        expect("vision" not in caps, f"no Materials vision capability: {caps}")
        expect(caps.get("direct_text") == "implemented", "direct_text capability")
        expect(caps.get("understanding") in {"implemented", "implemented_awaiting_model_config"}, "T09 modeling agent present")
        expect(caps.get("solver") == "not_yet_implemented", "solver still unimplemented")

        status, missing = json_request(
            base,
            "POST",
            "/api/projects/does-not-exist/materials/text",
            {"text": "hello"},
        )
        expect(status == 404, f"unknown project text 404, got {status} {missing}")

        # 1. Direct-text-only analysis is a valid Materials state.
        status, text_only = json_request(
            base,
            "POST",
            "/api/projects",
            {"title": "Direct-text-only evidence", "summary": "no files required"},
        )
        expect(status == 200 and isinstance(text_only, dict), f"text-only project {status}")
        text_project_id = text_only["id"]
        entered = "HARD RULE: rooms cannot overlap on the same day.\nThis is typed evidence, not a prompt."
        status, blank = json_request(
            base,
            "POST",
            f"/api/projects/{text_project_id}/materials/text",
            {"text": "   "},
        )
        expect(status == 422, f"blank direct text 422, got {status} {blank}")
        expect(len(list_materials(base, text_project_id)) == 0, "blank text did not persist")

        status, text_import = json_request(
            base,
            "POST",
            f"/api/projects/{text_project_id}/materials/text",
            {"text": entered, "label": "Meeting notes"},
        )
        expect(status == 200 and isinstance(text_import, dict), f"direct text {status} {text_import}")
        material = text_import["material"]
        spans = text_import["spans"]
        raw = entered.encode("utf-8")
        expect(material["filename"] == "Meeting notes", "label stored in compatibility filename field")
        expect(material["kind"] == "document", "direct text kind=document")
        expect(material["media_type"] == "text/plain", "direct text media_type")
        expect(material["byte_size"] == len(raw), "direct text byte_size")
        expect(material["checksum"] == sha256_label(raw), "direct text checksum")
        meta = material["metadata"]
        expect(meta["source_origin"] == "direct_text", "source_origin")
        expect(meta["display_label"] == "Meeting notes", "display_label")
        expect(meta["filename_field"] == "compatibility_source_label", "filename compatibility flag")
        expect(meta["evidence_role"] == "evidence_not_instruction", "evidence boundary")
        expect(meta["semantic_understanding"] == "not_performed", "no semantic intake")
        expect(stored_file(data_dir, material).read_bytes() == raw, "stored raw text bytes")
        db_row = reopen_material(db_path, material["id"])
        expect(db_row["checksum"] == sha256_label(raw), "sqlite checksum")
        expect(db_row["filename"] == "Meeting notes", "sqlite filename compatibility field")
        expect(len(spans) == 1, f"one text_range span, got {len(spans)}")
        span = spans[0]
        expect(span["locator_kind"] == "text_range", "locator_kind")
        expect(span["start_offset"] == 0, "start_offset")
        expect(span["end_offset"] == len(entered), "end_offset")
        expect("HARD RULE" in (span.get("excerpt") or ""), "excerpt preserves source")
        db_spans = reopen_spans(db_path, material["id"])
        expect(len(db_spans) == 1 and db_spans[0]["end_offset"] == len(entered), "sqlite text span")
        expect(len(list_materials(base, text_project_id)) == 1, "text-only evidence set has one material")

        default_status, default_import = json_request(
            base,
            "POST",
            f"/api/projects/{text_project_id}/materials/text",
            {"text": "Second note without a custom label."},
        )
        expect(default_status == 200 and isinstance(default_import, dict), "default label")
        expect(default_import["material"]["filename"] == "Direct text", "default source label")

        # 2. Mixed Evidence Set: direct text + TXT + CSV + PNG, no required modality.
        status, mixed = json_request(
            base,
            "POST",
            "/api/projects",
            {"title": "Mixed evidence set", "summary": "peers"},
        )
        expect(status == 200 and isinstance(mixed, dict), "mixed project")
        mixed_id = mixed["id"]
        status, mixed_text = json_request(
            base,
            "POST",
            f"/api/projects/{mixed_id}/materials/text",
            {"text": "Typed policy: do not double-book rooms."},
        )
        expect(status == 200, f"mixed direct text {status}")
        status, mixed_txt = import_file(
            base, mixed_id, "policy.txt", b"File policy: capacity stays unknown when blank.\n", "text/plain"
        )
        expect(status == 200, f"mixed txt {status}")
        csv_bytes = b"Room,Capacity (people)\nA,12\nB,\n"
        status, mixed_csv = import_file(base, mixed_id, "rooms.csv", csv_bytes, "text/csv")
        expect(status == 200, f"mixed csv {status}")
        png_bytes = tiny_png()
        status, mixed_png = import_file(base, mixed_id, "layout.png", png_bytes, "image/png")
        expect(status == 200 and isinstance(mixed_png, dict), f"mixed png {status}")
        png_meta = mixed_png["material"]["metadata"]
        expect("vision" not in png_meta, "mixed png has no vision metadata")
        expect(png_meta.get("semantic_understanding") == "not_performed", "mixed png no semantics")
        listed = list_materials(base, mixed_id)
        kinds = sorted(item["kind"] for item in listed)
        expect(len(listed) == 4, f"four peer materials, got {len(listed)}")
        expect(kinds == ["document", "document", "image", "table"], f"mixed kinds {kinds}")
        origins = {item["id"]: (item.get("metadata") or {}).get("source_origin") for item in listed}
        expect("direct_text" in origins.values(), "mixed set includes direct text")

        print("PASS: direct-text-only + mixed Evidence Set; image intake has no vision runtime")
        print(
            json.dumps(
                {
                    "text_only_project": text_project_id,
                    "direct_text_material": material["id"],
                    "mixed_project": mixed_id,
                    "mixed_materials": len(listed),
                    "vision_runtime_present": False,
                },
                sort_keys=True,
            )
        )
        print(f"temp_db={db_path}")
        print(f"temp_data={data_dir}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        tmp.cleanup()


if __name__ == "__main__":
    main()
