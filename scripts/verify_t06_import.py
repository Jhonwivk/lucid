#!/usr/bin/env python3
"""Focused T06 proof: TXT / Markdown / text-PDF import through the real API.

Uses a temporary SQLite database, a temporary data directory, and a real
FastAPI process. Exercises POST /api/projects/{id}/materials/import with
multipart uploads. This is not a broad test matrix.
"""

from __future__ import annotations

import hashlib
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

TXT_ANCHOR = "HARD RULE: rooms cannot overlap on the same day."
TXT_BODY = f"Room policy\n{TXT_ANCHOR}\nEnd of note.\n"
MD_HEADING = "# Supplier capacity rule"
MD_RULE = "Soft constraint: prefer local suppliers when lead time is known."
MD_BODY = f"{MD_HEADING}\n\n{MD_RULE}\n"
PDF_PAGE_ONE = "T06_PAGE_ONE_ANCHOR"
PDF_PAGE_TWO = "T06_PAGE_TWO_ANCHOR"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def find_port() -> int:
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
    boundary = "----LucidT06Boundary"
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
        except Exception as exc:  # noqa: BLE001 — startup race
            last_error = str(exc)
        time.sleep(0.1)
    raise SystemExit(f"FAIL: API did not become healthy: {last_error}")


def sha256_label(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def build_text_pdf(pages: list[list[str]]) -> bytes:
    """Minimal multi-page PDF with extractable Helvetica text operators."""
    font_id = 3
    objects: dict[int, bytes] = {
        font_id: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    page_ids: list[int] = []
    next_id = 4
    for lines in pages:
        text_ops = ["BT", "/F1 11 Tf", "72 740 Td"]
        for index, line in enumerate(lines):
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            if index:
                text_ops.append("0 -18 Td")
            text_ops.append(f"({safe}) Tj")
        text_ops.append("ET")
        stream = ("\n".join(text_ops) + "\n").encode("latin-1") if lines else b""
        page_id = next_id
        content_id = next_id + 1
        next_id += 2
        page_ids.append(page_id)
        objects[content_id] = (
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
        kids_ref = f"{page_id} 0 R".encode()  # placeholder unused
        objects[page_id] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 "
            + f"{font_id} 0 R".encode()
            + b" >> >> /Contents "
            + f"{content_id} 0 R".encode()
            + b" >>"
        )
        _ = kids_ref
    kids = b"[" + b" ".join(f"{pid} 0 R".encode() for pid in page_ids) + b"]"
    objects[2] = b"<< /Type /Pages /Kids " + kids + b" /Count " + str(len(page_ids)).encode() + b" >>"
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {0: 0}
    for number in sorted(objects):
        offsets[number] = len(out)
        out.extend(f"{number} 0 obj\n".encode())
        out.extend(objects[number])
        out.extend(b"\nendobj\n")
    xref = len(out)
    max_id = max(objects)
    out.extend(f"xref\n0 {max_id + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for number in range(1, max_id + 1):
        out.extend(f"{offsets[number]:010d} 00000 n \n".encode())
    out.extend(
        f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)


def _venv_site() -> Path | None:
    lib = API_ROOT / ".venv" / "lib"
    if not lib.is_dir():
        return None
    for child in sorted(lib.iterdir()):
        site = child / "site-packages"
        if site.is_dir():
            return site
    return None


def encrypt_pdf(content: bytes, password: str) -> bytes:
    site = _venv_site()
    if site is not None and str(site) not in sys.path:
        sys.path.insert(0, str(site))
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(content)))
    writer.encrypt(password)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def list_materials(base: str, project_id: str) -> list[dict]:
    status, body = json_request(base, "GET", f"/api/projects/{project_id}/materials")
    expect(status == 200 and isinstance(body, list), f"list materials {status}")
    return body  # type: ignore[return-value]


def reopen_material(db_path: Path, material_id: str) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM material WHERE id = ?", (material_id,)).fetchone()
        expect(row is not None, f"material {material_id} in sqlite")
        return dict(row)
    finally:
        conn.close()


def stored_file(data_dir: Path, material: dict) -> Path:
    metadata = material.get("metadata") or {}
    stored = metadata.get("stored_path")
    expect(isinstance(stored, str) and stored, "stored_path in metadata")
    path = data_dir / stored
    expect(path.is_file(), f"stored file exists: {path}")
    return path


def find_span_covering(text: str, spans: list[dict], needle: str) -> dict:
    start = text.find(needle)
    expect(start >= 0, f"needle present in source text: {needle}")
    end = start + len(needle)
    for span in spans:
        if span.get("locator_kind") != "text_range":
            continue
        s, e = span.get("start_offset"), span.get("end_offset")
        if s is None or e is None:
            continue
        if s <= start and e >= end and needle in (span.get("excerpt") or text[s:e]):
            sliced = text[s:e]
            expect(needle in sliced, f"offset slice contains {needle!r}")
            return span
    raise SystemExit(f"FAIL: no text_range span covers {needle!r}")


def main() -> None:
    tmp = tempfile.TemporaryDirectory(prefix="lucid-t06-")
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
        expect(shell["capabilities"]["import"].startswith("txt_md_pdf_csv_xlsx_png_jpeg"), "import capability includes T06 types")
        expect(shell["capabilities"]["ocr"] == "not_implemented", "ocr not claimed")
        expect(shell["capabilities"]["solver"] == "deterministic_training_schedule", "deterministic solver capability is advertised")

        status, project = json_request(
            base,
            "POST",
            "/api/projects",
            {"title": "T06 intake proof", "summary": "real file import"},
        )
        expect(status == 200 and isinstance(project, dict), f"create project {status} {project}")
        project_id = project["id"]

        status, missing = import_file(base, "does-not-exist", "note.txt", b"hello\n")
        expect(status == 404, f"unknown project 404, got {status} {missing}")

        # 1. TXT
        txt_bytes = TXT_BODY.encode("utf-8")
        status, txt_import = import_file(base, project_id, "room-policy.txt", txt_bytes, "text/plain")
        expect(status == 200 and isinstance(txt_import, dict), f"txt import {status} {txt_import}")
        txt_material = txt_import["material"]
        txt_spans = txt_import["spans"]
        expect(txt_material["filename"] == "room-policy.txt", "txt original filename")
        expect(txt_material["byte_size"] == len(txt_bytes), "txt byte_size")
        expect(txt_material["checksum"] == sha256_label(txt_bytes), "txt sha256")
        expect(txt_material["media_type"] == "text/plain", "txt media type")
        expect(txt_material["metadata"]["decode_status"] == "strict", "strict utf-8")
        expect(txt_material["metadata"]["evidence_role"] == "evidence_not_instruction", "evidence boundary")
        db_row = reopen_material(db_path, txt_material["id"])
        expect(db_row["byte_size"] == len(txt_bytes), "sqlite txt byte_size")
        expect(db_row["checksum"] == sha256_label(txt_bytes), "sqlite txt checksum")
        stored = stored_file(data_dir, txt_material)
        expect(stored.read_bytes() == txt_bytes, "stored txt bytes match")
        find_span_covering(TXT_BODY, txt_spans, TXT_ANCHOR)

        # 2. Markdown
        md_bytes = MD_BODY.encode("utf-8")
        status, md_import = import_file(base, project_id, "capacity.md", md_bytes, "text/markdown")
        expect(status == 200 and isinstance(md_import, dict), f"md import {status} {md_import}")
        md_material = md_import["material"]
        expect(md_material["media_type"] == "text/markdown", "markdown media type")
        expect(md_material["byte_size"] == len(md_bytes), "md byte_size")
        expect(md_material["checksum"] == sha256_label(md_bytes), "md sha256")
        expect(stored_file(data_dir, md_material).read_bytes() == md_bytes, "stored md bytes")
        excerpts = " ".join(span.get("excerpt") or "" for span in md_import["spans"])
        expect(MD_HEADING.lstrip("# ").strip() in excerpts or MD_HEADING in excerpts, "md heading in spans")
        expect(MD_RULE in excerpts, "md rule in spans")
        find_span_covering(MD_BODY, md_import["spans"], MD_RULE)

        # 3. two-page text PDF
        pdf_bytes = build_text_pdf([[PDF_PAGE_ONE, "first page body"], [PDF_PAGE_TWO, "second page body"]])
        status, pdf_import = import_file(base, project_id, "two-page.pdf", pdf_bytes, "application/pdf")
        expect(status == 200 and isinstance(pdf_import, dict), f"pdf import {status} {pdf_import}")
        pdf_material = pdf_import["material"]
        pdf_meta = pdf_material["metadata"]
        expect(pdf_material["media_type"] == "application/pdf", "pdf media type")
        expect(pdf_material["checksum"] == sha256_label(pdf_bytes), "pdf sha256")
        expect(pdf_meta["page_count"] == 2, f"page_count {pdf_meta.get('page_count')}")
        expect(pdf_meta["ocr"] == "not_implemented", "ocr flag")
        expect(pdf_meta["empty_pages"] == [], f"no empty pages {pdf_meta.get('empty_pages')}")
        page_spans = [span for span in pdf_import["spans"] if span["locator_kind"] == "page"]
        expect(len(page_spans) == 2, f"two page spans, got {len(page_spans)}")
        expect(page_spans[0]["page"] == 1 and PDF_PAGE_ONE in (page_spans[0]["excerpt"] or ""), "page 1 anchor")
        expect(page_spans[1]["page"] == 2 and PDF_PAGE_TWO in (page_spans[1]["excerpt"] or ""), "page 2 anchor")
        expect(stored_file(data_dir, pdf_material).read_bytes() == pdf_bytes, "stored pdf bytes")

        # 4. empty-text / scanned-like PDF
        empty_pdf = build_text_pdf([[]])
        status, empty_import = import_file(base, project_id, "scan-like.pdf", empty_pdf, "application/pdf")
        expect(status == 200 and isinstance(empty_import, dict), f"empty pdf import {status} {empty_import}")
        empty_meta = empty_import["material"]["metadata"]
        expect(empty_meta["page_count"] == 1, "empty pdf page_count")
        expect(empty_meta["empty_pages"] == [1], f"empty_pages {empty_meta.get('empty_pages')}")
        expect(empty_meta["ocr"] == "not_implemented", "empty pdf ocr")
        empty_excerpt = empty_import["spans"][0]["excerpt"] or ""
        expect("No extractable text" in empty_excerpt, "empty page reports no extractable text")
        expect(PDF_PAGE_ONE not in empty_excerpt, "empty pdf does not invent other page text")
        expect("T06_PAGE" not in empty_excerpt, "empty pdf does not invent anchors")

        before_reject = len(list_materials(base, project_id))

        # 5a. truly unsupported types still rejected. CSV/XLSX/PNG/JPEG are T07/T08
        # intake (no longer a T06 415); this script keeps proving TXT/MD/PDF.
        status, xls_body = import_file(base, project_id, "grid.xls", b"not-xlsx", "application/vnd.ms-excel")
        expect(status == 415, f"xls 415, got {status} {xls_body}")
        status, doc_body = import_file(base, project_id, "notes.docx", b"PK\x03\x04not-doc", "application/octet-stream")
        expect(status == 422, f"malformed docx 422, got {status} {doc_body}")
        expect(len(list_materials(base, project_id)) == before_reject, "unsupported types did not persist")

        # 5b. oversized rejected
        oversized = b"x" * (12 * 1024 * 1024 + 1)
        status, big_body = import_file(base, project_id, "huge.txt", oversized, "text/plain")
        expect(status == 413, f"oversize 413, got {status} {big_body}")
        expect(len(list_materials(base, project_id)) == before_reject, "oversize did not persist")

        # 5c. malformed PDF
        status, bad_pdf = import_file(base, project_id, "broken.pdf", b"%PDF-1.4\nnot-a-pdf", "application/pdf")
        expect(status == 422, f"malformed pdf 422, got {status} {bad_pdf}")
        expect(len(list_materials(base, project_id)) == before_reject, "malformed pdf did not persist")

        # 5d. duplicate original filename, independent storage
        first_bytes = b"first notes version one\n"
        second_bytes = b"second notes version two - different checksum\n"
        status, first_import = import_file(base, project_id, "notes.txt", first_bytes)
        expect(status == 200, f"first notes {status}")
        status, second_import = import_file(base, project_id, "notes.txt", second_bytes)
        expect(status == 200, f"second notes {status}")
        first_mat = first_import["material"]
        second_mat = second_import["material"]
        expect(first_mat["id"] != second_mat["id"], "duplicate name creates two rows")
        expect(first_mat["filename"] == second_mat["filename"] == "notes.txt", "original filename preserved")
        expect(first_mat["checksum"] == sha256_label(first_bytes), "first checksum")
        expect(second_mat["checksum"] == sha256_label(second_bytes), "second checksum")
        first_path = stored_file(data_dir, first_mat)
        second_path = stored_file(data_dir, second_mat)
        expect(first_path != second_path, "collision-safe distinct stored paths")
        expect(first_path.read_bytes() == first_bytes, "first stored bytes intact after second import")
        expect(second_path.read_bytes() == second_bytes, "second stored bytes independent")

        # encrypted PDF (cheap extra)
        encrypted = encrypt_pdf(build_text_pdf([["secret page"]]), "t06-secret")
        before_enc = len(list_materials(base, project_id))
        status, enc_body = import_file(base, project_id, "locked.pdf", encrypted, "application/pdf")
        expect(status in {415, 422}, f"encrypted pdf controlled error, got {status} {enc_body}")
        expect(len(list_materials(base, project_id)) == before_enc, "encrypted pdf did not persist")

        # empty txt still imports
        status, empty_txt = import_file(base, project_id, "empty.txt", b"")
        expect(status == 200 and isinstance(empty_txt, dict), f"empty txt {status}")
        expect(empty_txt["material"]["metadata"]["empty"] is True, "empty metadata")
        expect("(empty file" in (empty_txt["spans"][0]["excerpt"] or ""), "empty span state")

        print("PASS: T06 TXT/Markdown/text-PDF import through real FastAPI + SQLite")
        print(
            json.dumps(
                {
                    "project_id": project_id,
                    "txt_material": txt_material["id"],
                    "md_material": md_material["id"],
                    "pdf_material": pdf_material["id"],
                    "materials": len(list_materials(base, project_id)),
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
