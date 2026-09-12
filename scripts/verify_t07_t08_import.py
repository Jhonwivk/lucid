#!/usr/bin/env python3
"""Focused T07/T08 proof through real FastAPI + SQLite (tables + image provenance)."""

from __future__ import annotations

import io
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "api"
VENV_PYTHON = API_ROOT / ".venv" / "bin" / "python"


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
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request_json(base: str, method: str, path: str, payload: dict | None = None) -> tuple[int, dict | list]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"raw": raw}
        return exc.code, body


def import_file(base: str, project_id: str, filename: str, content: bytes, content_type: str) -> tuple[int, dict | list]:
    boundary = "----LucidT07T08Boundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        base + f"/api/projects/{project_id}/materials/import",
        data=body,
        method="POST",
        headers={"Accept": "application/json", "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"raw": raw}
        return exc.code, body


def wait_health(base: str) -> None:
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            status, body = request_json(base, "GET", "/api/health")
            if status == 200 and isinstance(body, dict) and body.get("status") == "ok":
                return
        except Exception:
            pass
        time.sleep(0.1)
    raise SystemExit("FAIL: API did not become healthy")


def sqlite_material(db: Path, material_id: str) -> dict:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM material WHERE id=?", (material_id,)).fetchone()
        expect(row is not None, f"material persisted: {material_id}")
        out = dict(row)
        out["metadata"] = json.loads(out.get("metadata_json") or "{}")
        return out
    finally:
        conn.close()


def sqlite_spans(db: Path, material_id: str) -> list[dict]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM source_span WHERE material_id=? ORDER BY created_at,id", (material_id,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["region"] = json.loads(item.get("region_json") or "null")
            result.append(item)
        return result
    finally:
        conn.close()


def stored_bytes(data_dir: Path, material: dict) -> bytes:
    path = data_dir / material["metadata"]["stored_path"]
    expect(path.is_file(), f"stored bytes exist: {path}")
    return path.read_bytes()


def make_xlsx() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Capacity"
    ws.append(["Item", "weight_kg", "Cost [USD]", "Rate %"])
    ws.append(["A", 12.5, 100, None])
    ws.append(["B", None, "=C2*2", "15%"])
    ws.column_dimensions["C"].hidden = True
    ws.row_dimensions[3].hidden = True
    notes = wb.create_sheet("HiddenRules")
    notes.sheet_state = "hidden"
    notes.append(["Duration_h", "Owner"])
    notes.append([2, "Ops"])
    buf = io.BytesIO()
    wb.save(buf)
    wb.close()
    return buf.getvalue()


def make_images() -> tuple[bytes, bytes]:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (900, 560), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((70, 80, 830, 475), outline="black", width=12)
    draw.rectangle((130, 160, 390, 355), outline="black", width=8)
    draw.rectangle((510, 160, 770, 355), outline="black", width=8)
    draw.text((245, 35), "LUCID IMAGE T08", fill="black")
    draw.text((175, 245), "RESOURCE A", fill="black")
    draw.text((555, 245), "RESOURCE B", fill="black")
    png = io.BytesIO()
    jpg = io.BytesIO()
    image.save(png, format="PNG")
    image.save(jpg, format="JPEG", quality=92)
    return png.getvalue(), jpg.getvalue()


def main() -> None:
    tmp = tempfile.TemporaryDirectory(prefix="lucid-t07-t08-")
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
        [python, "-m", "uvicorn", "app.main:app", "--app-dir", str(API_ROOT), "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(API_ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        wait_health(base)
        status, shell = request_json(base, "GET", "/api/shell")
        expect(status == 200 and isinstance(shell, dict), "shell available")
        expect(shell["capabilities"]["csv_xlsx"] == "implemented", "CSV/XLSX capability")
        expect("vision" not in shell["capabilities"], f"no Materials vision capability: {shell}")
        expect(shell["capabilities"].get("png_jpeg") == "implemented", "png_jpeg capability")

        status, project = request_json(base, "POST", "/api/projects", {"title": "T07 T08 proof"})
        expect(status == 200 and isinstance(project, dict), "project creation")
        pid = project["id"]

        csv_bytes = b"Capacity (people),Cost [USD],Duration_h,Rate %\n25,1200,2,15%\n,900,,\n"
        status, csv_import = import_file(base, pid, "capacity.csv", csv_bytes, "text/csv")
        expect(status == 200 and isinstance(csv_import, dict), f"CSV import: {status} {csv_import}")
        csv_mat = csv_import["material"]
        expect(csv_mat["kind"] == "table", "CSV material kind")
        units = csv_mat["metadata"].get("units") or []
        unit_values = {item.get("unit") for item in units if isinstance(item, dict)}
        expect({"people", "USD", "h", "%"}.issubset(unit_values), f"CSV unit hints: {units}")
        csv_spans = csv_import["spans"]
        expect(any(s.get("cell_ref") == "A3" and "blank/unknown" in (s.get("excerpt") or "") for s in csv_spans), "CSV blank remains blank/unknown")
        expect(any(s.get("cell_ref") == "B2" and "1200" in (s.get("excerpt") or "") for s in csv_spans), "CSV B2 provenance")
        reopened_csv = sqlite_material(db_path, csv_mat["id"])
        expect(stored_bytes(data_dir, reopened_csv) == csv_bytes, "CSV stored bytes exact")

        xlsx_bytes = make_xlsx()
        status, xlsx_import = import_file(base, pid, "capacity.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        expect(status == 200 and isinstance(xlsx_import, dict), f"XLSX import: {status} {xlsx_import}")
        xlsx_mat = xlsx_import["material"]
        meta = xlsx_mat["metadata"]
        expect(meta.get("sheet_names") == ["Capacity", "HiddenRules"], f"multi-sheet names: {meta.get('sheet_names')}")
        expect("HiddenRules" in (meta.get("hidden_sheet_names") or []), "hidden sheet recorded")
        expect(meta.get("formulas_recalculated") is False, "formulas not recalculated")
        xlsx_spans = xlsx_import["spans"]
        expect(any(s.get("sheet") == "Capacity" and s.get("cell_ref") == "C3" and "=C2*2" in (s.get("excerpt") or "") and "not recalculated" in (s.get("excerpt") or "") for s in xlsx_spans), "formula preserved with cell provenance")
        expect(any(s.get("sheet") == "Capacity" and s.get("cell_ref") == "B3" and "blank/unknown" in (s.get("excerpt") or "") for s in xlsx_spans), "XLSX blank remains unknown")
        expect(any(s.get("sheet") == "HiddenRules" and s.get("cell_ref") == "A2" for s in xlsx_spans), "second-sheet A1 provenance")
        reopened_xlsx = sqlite_material(db_path, xlsx_mat["id"])
        expect(stored_bytes(data_dir, reopened_xlsx) == xlsx_bytes, "XLSX stored bytes exact")

        status, duplicate = import_file(base, pid, "capacity.csv", b"A,B\n1,2\n", "text/csv")
        expect(status == 200 and isinstance(duplicate, dict), "duplicate filename imports")
        expect(duplicate["material"]["id"] != csv_mat["id"], "duplicate creates independent material")
        expect(duplicate["material"]["metadata"]["stored_path"] != csv_mat["metadata"]["stored_path"], "duplicate gets independent stored path")

        status, legacy = import_file(base, pid, "legacy.xls", b"old excel", "application/vnd.ms-excel")
        expect(status == 415, f"legacy .xls rejected: {status} {legacy}")
        status, malformed = import_file(base, pid, "bad.xlsx", b"not a zip workbook", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        expect(status == 422, f"malformed XLSX controlled: {status} {malformed}")
        status, oversized = import_file(base, pid, "huge.csv", b"x" * (12 * 1024 * 1024 + 1), "text/csv")
        expect(status == 413, f"oversize controlled: {status}")

        png_bytes, jpg_bytes = make_images()
        status, png_import = import_file(base, pid, "layout-proof.png", png_bytes, "image/png")
        expect(status == 200 and isinstance(png_import, dict), f"PNG import: {status} {png_import}")
        png_mat = png_import["material"]
        png_meta = png_mat["metadata"]
        expect("vision" not in png_meta, f"PNG must not include vision metadata: {png_meta.keys()}")
        expect(png_meta.get("semantic_understanding") == "not_performed", f"no semantic intake: {png_meta}")
        expect(isinstance(png_meta.get("pixel_width"), int), "PNG pixel_width")
        png_spans = png_import["spans"]
        expect(len(png_spans) == 1, f"exactly one PNG span, got {len(png_spans)}")
        region = png_spans[0].get("region") or {}
        expect(png_spans[0].get("locator_kind") == "region", "PNG region provenance")
        expect(region.get("region_state") == "full_image", f"full-image region: {region}")
        expect(region.get("x") == 0.0 and region.get("width") == 1.0, f"normalized full image: {region}")
        reopened_png = sqlite_material(db_path, png_mat["id"])
        reopened_spans = sqlite_spans(db_path, png_mat["id"])
        expect(stored_bytes(data_dir, reopened_png) == png_bytes, "PNG stored bytes exact")
        expect(any((s.get("region") or {}).get("region_state") == "full_image" for s in reopened_spans), "region provenance reopens from SQLite")

        status, jpg_import = import_file(base, pid, "layout-proof.jpg", jpg_bytes, "image/jpeg")
        expect(status == 200 and isinstance(jpg_import, dict), f"JPEG import: {status} {jpg_import}")
        expect(jpg_import["material"]["media_type"] == "image/jpeg", "JPEG media type")
        expect("vision" not in (jpg_import["material"].get("metadata") or {}), "JPEG has no vision metadata")
        expect(stored_bytes(data_dir, sqlite_material(db_path, jpg_import["material"]["id"])) == jpg_bytes, "JPEG stored bytes exact")

        before_bad = sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM material").fetchone()[0]
        status, bad_img = import_file(base, pid, "broken.png", b"not an image", "image/png")
        expect(status == 422, f"malformed image controlled: {status} {bad_img}")
        conn = sqlite3.connect(db_path)
        after_bad = conn.execute("SELECT COUNT(*) FROM material").fetchone()[0]
        conn.close()
        expect(after_bad == before_bad, "malformed image did not persist")

        print("PASS: T07 CSV/XLSX + T08 PNG/JPEG full-image provenance through FastAPI + SQLite")
        print(json.dumps({
            "project_id": pid,
            "csv_material": csv_mat["id"],
            "xlsx_material": xlsx_mat["id"],
            "png_material": png_mat["id"],
            "semantic_understanding": png_meta.get("semantic_understanding"),
        }, ensure_ascii=False, sort_keys=True))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        tmp.cleanup()


if __name__ == "__main__":
    main()
