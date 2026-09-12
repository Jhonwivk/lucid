#!/usr/bin/env python3
"""Focused T08 proof: PNG/JPEG bytes, metadata, and honest full-image provenance.

Uses a temporary SQLite database, a temporary data directory, and a real
FastAPI process. Image intake must not call or require any vision provider.
Never prints credential values.
"""

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
VISION_MACOS = API_ROOT / "app" / "importers" / "vision_macos.py"
VISION_SWIFT = API_ROOT / "app" / "importers" / "macos_vision.swift"


def _reexec_with_venv() -> None:
    """Pillow's C extension is installed for the API venv, not system python3."""
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
    timeout: float = 60,
) -> tuple[int, dict | list]:
    boundary = "----LucidT08Boundary"
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
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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


def _venv_site() -> Path | None:
    lib = API_ROOT / ".venv" / "lib"
    if not lib.is_dir():
        return None
    for child in sorted(lib.iterdir()):
        site = child / "site-packages"
        if site.is_dir():
            return site
    return None


def build_labeled_png() -> bytes:
    site = _venv_site()
    if site is not None and str(site) not in sys.path:
        sys.path.insert(0, str(site))
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (640, 360), (232, 236, 233))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 50, 250, 180), fill=(181, 205, 214), outline=(30, 44, 50), width=3)
    draw.text((55, 90), "Line A", fill=(30, 44, 50))
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def png_to_jpeg(png_bytes: bytes) -> bytes:
    site = _venv_site()
    if site is not None and str(site) not in sys.path:
        sys.path.insert(0, str(site))
    from PIL import Image

    image = Image.open(BytesIO(png_bytes)).convert("RGB")
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def stored_file(data_dir: Path, material: dict) -> Path:
    metadata = material.get("metadata") or {}
    stored = metadata.get("stored_path")
    expect(isinstance(stored, str) and stored, "stored_path in metadata")
    path = data_dir / stored
    expect(path.is_file(), f"stored file exists: {path}")
    return path


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
    status, body = json_request(base, "GET", "/api/projects/{0}/materials".format(project_id))
    expect(status == 200 and isinstance(body, list), f"list materials {status}")
    return body  # type: ignore[return-value]


def assert_no_secret_leak(payload: object) -> None:
    dumped = json.dumps(payload)
    expect("sk-" not in dumped, "response must not contain sk- token prefix")
    expect("Bearer " not in dumped, "response must not contain Bearer credentials")
    expect("AIza" not in dumped, "response must not contain Google-style key prefix")


def assert_honest_image_intake(material: dict, spans: list[dict]) -> None:
    metadata = material.get("metadata") or {}
    expect("vision" not in metadata, f"image metadata must not include vision: {metadata.keys()}")
    expect("vision_observations" not in metadata, "image metadata must not include vision_observations")
    expect(metadata.get("semantic_understanding") == "not_performed", f"semantic_understanding {metadata}")
    expect(metadata.get("semantic_extraction") == "not_performed", "semantic_extraction")
    expect(isinstance(metadata.get("pixel_width"), int) and metadata["pixel_width"] > 0, "pixel_width")
    expect(isinstance(metadata.get("pixel_height"), int) and metadata["pixel_height"] > 0, "pixel_height")
    expect(metadata.get("image_format") in {"PNG", "JPEG"}, f"image_format {metadata.get('image_format')}")
    dumped = json.dumps(material)
    expect("macos_vision" not in dumped, "macos_vision must not appear in image material")
    expect('"provider": "grok"' not in dumped, "grok provider must not appear in image material")
    region_spans = [span for span in spans if span.get("locator_kind") == "region"]
    expect(len(region_spans) == 1, f"exactly one region span, got {len(region_spans)}")
    region = region_spans[0].get("region") or {}
    expect(region.get("coordinate_space") == "normalized_top_left", f"coordinate_space {region}")
    expect(region.get("region_state") == "full_image", f"region_state {region}")
    expect(region.get("x") == 0.0, f"x {region}")
    expect(region.get("y") == 0.0, f"y {region}")
    expect(region.get("width") == 1.0, f"width {region}")
    expect(region.get("height") == 1.0, f"height {region}")


def main() -> None:
    expect(not VISION_MODULE.is_file(), "obsolete importers/vision.py must be removed")
    expect(not VISION_MACOS.is_file(), "obsolete importers/vision_macos.py must be removed")
    expect(not VISION_SWIFT.is_file(), "obsolete macos_vision.swift must be removed")

    tmp = tempfile.TemporaryDirectory(prefix="lucid-t08-")
    tmp_path = Path(tmp.name)
    db_path = tmp_path / "lucid.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    port = find_port()
    base = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env["LUCID_DB_PATH"] = str(db_path)
    env["LUCID_DATA_DIR"] = str(data_dir)
    env["XAI_API_KEY"] = "not-a-real-key-intake-must-not-call"
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
        expect("vision" not in caps, f"shell must not expose a Materials vision runtime: {caps}")
        expect(caps.get("png_jpeg") == "implemented", "png_jpeg capability")
        expect(caps.get("ocr") == "not_implemented", "ocr not claimed")
        expect(caps.get("understanding") in {"implemented", "implemented_awaiting_model_config"}, "understanding agent present")
        expect(caps.get("solver") == "not_yet_implemented", "solver still unimplemented")

        status, project = json_request(
            base,
            "POST",
            "/api/projects",
            {"title": "T08 image intake proof", "summary": "png/jpeg bytes + full-image provenance"},
        )
        expect(status == 200 and isinstance(project, dict), f"create project {status}")
        project_id = project["id"]

        png_bytes = build_labeled_png()
        jpeg_bytes = png_to_jpeg(png_bytes)

        status, png_import = import_file(base, project_id, "plant-layout.png", png_bytes, "image/png")
        expect(status == 200 and isinstance(png_import, dict), f"png import {status} {png_import}")
        png_material = png_import["material"]
        expect(png_material["kind"] == "image", "png kind")
        expect(png_material["media_type"] == "image/png", "png media")
        expect(png_material["byte_size"] == len(png_bytes), "png byte_size")
        expect(png_material["checksum"] == sha256_label(png_bytes), "png sha256")
        expect(stored_file(data_dir, png_material).read_bytes() == png_bytes, "stored png bytes")
        expect(png_material["metadata"]["ocr"] == "not_implemented", "ocr flag")
        assert_honest_image_intake(png_material, png_import["spans"])
        assert_no_secret_leak(png_import)
        db_spans = reopen_spans(db_path, png_material["id"])
        expect(len(db_spans) == 1, "sqlite exactly one image span")
        region = json.loads(db_spans[0]["region_json"])
        expect(region.get("region_state") == "full_image", f"sqlite region_state {region}")
        expect(region.get("x") == 0.0 and region.get("width") == 1.0, f"sqlite full-image box {region}")

        status, jpeg_import = import_file(base, project_id, "plant-layout.jpg", jpeg_bytes, "image/jpeg")
        expect(status == 200 and isinstance(jpeg_import, dict), f"jpeg import {status}")
        expect(jpeg_import["material"]["checksum"] == sha256_label(jpeg_bytes), "jpeg sha256")
        expect(stored_file(data_dir, jpeg_import["material"]).read_bytes() == jpeg_bytes, "stored jpeg bytes")
        assert_honest_image_intake(jpeg_import["material"], jpeg_import["spans"])
        assert_no_secret_leak(jpeg_import)

        first_png = build_labeled_png()
        status, first_import = import_file(base, project_id, "layout.png", first_png, "image/png")
        expect(status == 200, f"first png {status}")
        status, second_import = import_file(base, project_id, "layout.png", png_bytes, "image/png")
        expect(status == 200, f"second png {status}")
        expect(first_import["material"]["id"] != second_import["material"]["id"], "duplicate png rows")
        expect(stored_file(data_dir, first_import["material"]).read_bytes() == first_png, "first png intact")

        before_reject = len(list_materials(base, project_id))
        status, bad_png = import_file(base, project_id, "broken.png", b"not-a-png", "image/png")
        expect(status == 422, f"malformed png 422, got {status} {bad_png}")
        status, gif_body = import_file(base, project_id, "anim.gif", b"GIF89a", "image/gif")
        expect(status == 415, f"gif 415, got {status} {gif_body}")
        huge = b"\x89PNG\r\n\x1a\n" + (b"x" * (12 * 1024 * 1024))
        status, big_body = import_file(base, project_id, "huge.png", huge, "image/png")
        expect(status == 413, f"oversize 413, got {status} {big_body}")
        expect(len(list_materials(base, project_id)) == before_reject, "image rejects did not persist")

        print("PASS: T08 PNG/JPEG persistence + metadata + full-image provenance (no vision)")
        print(
            json.dumps(
                {
                    "project_id": project_id,
                    "png_material": png_material["id"],
                    "jpeg_material": jpeg_import["material"]["id"],
                    "semantic_understanding": png_material["metadata"]["semantic_understanding"],
                    "region_state": "full_image",
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
