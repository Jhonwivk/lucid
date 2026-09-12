#!/usr/bin/env python3
"""Generate deterministic binary fixtures using only the Python stdlib.

The generated files are demo evidence assets. Their semantic interpretation is
specified independently in each template.json/expected.json; this script does
not parse or infer business rules.
"""

from __future__ import annotations

import html
import struct
import zlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "templates"


def write_pdf(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text_ops = ["BT", "/F1 11 Tf", "72 740 Td"]
    for index, line in enumerate(lines):
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if index:
            text_ops.append("0 -18 Td")
        text_ops.append(f"({safe}) Tj")
    text_ops.append("ET")
    stream = "\n".join(text_ops).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{number} 0 obj\n".encode())
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objects)+1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(out)


def col_name(index: int) -> str:
    result = ""
    while index:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result


def write_xlsx(path: Path, sheet_name: str, rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet_rows = []
    for r_idx, row in enumerate(rows, start=1):
        cells = []
        for c_idx, value in enumerate(row, start=1):
            ref = f"{col_name(c_idx)}{r_idx}"
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{html.escape(str(value))}</t></is></c>')
        sheet_rows.append(f'<row r="{r_idx}">' + "".join(cells) + "</row>")
    worksheet = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' \
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' \
        + "".join(sheet_rows) + '</sheetData></worksheet>'
    workbook = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' \
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">' \
        f'<sheets><sheet name="{html.escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets></workbook>'
    content_types = '<?xml version="1.0" encoding="UTF-8"?>' \
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' \
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' \
        '<Default Extension="xml" ContentType="application/xml"/>' \
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' \
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'
    root_rels = '<?xml version="1.0" encoding="UTF-8"?>' \
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' \
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    wb_rels = '<?xml version="1.0" encoding="UTF-8"?>' \
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' \
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    with ZipFile(path, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        zf.writestr("xl/worksheets/sheet1.xml", worksheet)


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def write_png(path: Path, width: int, height: int, zones: list[tuple[int, int, int, int, tuple[int, int, int]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            rgb = (232, 236, 233)
            for x0, y0, x1, y1, color in zones:
                if x0 <= x < x1 and y0 <= y < y1:
                    rgb = color
            row.extend(rgb)
        rows.append(bytes(row))
    raw = b"".join(rows)
    data = bytearray(b"\x89PNG\r\n\x1a\n")
    data.extend(png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))
    data.extend(png_chunk(b"IDAT", zlib.compress(raw, 9)))
    data.extend(png_chunk(b"IEND", b""))
    path.write_bytes(data)


def main() -> None:
    write_pdf(ROOT / "training-schedule" / "leadership-memo.pdf", [
        "Northstar Learning - leadership memo (fictional fixture)",
        "Urgent cohorts may use evening sessions when necessary.",
        "The approving owner for overtime has not yet been specified.",
    ])
    write_xlsx(ROOT / "vehicle-validation-bench" / "validation-plan.xlsx", "Plan", [
        ["job", "vehicle", "voltage", "bench", "preferred_day", "availability_note"],
        ["V-201", "V12", "400V", "B1", "Mon", "available"],
        ["V-202", "V17", "800V", "HV-2", "Thu", "vehicle unavailable Thu"],
        ["V-203", "V18", "800V", "HV-2", "Wed", "available"],
        ["V-204", "V21", "400V", "B2", "Fri", "available"],
        ["V-205", "V24", "400V", "B1", "Tue", "available"],
    ])
    write_pdf(ROOT / "vehicle-validation-bench" / "bench-requirements.pdf", [
        "Vehicle validation bench requirements (fictional fixture)",
        "800 V validation requires HV-2 qualification.",
        "Bench B2 is reserved for calibration on Friday morning.",
        "Shared thermal-zone concurrency approval is not documented.",
    ])
    write_png(ROOT / "vehicle-validation-bench" / "bench-layout.png", 640, 360, [
        (40, 55, 220, 185, (181, 205, 214)),
        (260, 55, 440, 185, (173, 194, 205)),
        (360, 65, 590, 250, (224, 201, 145)),
    ])
    write_png(ROOT / "factory-maintenance-window" / "line-layout.png", 640, 360, [
        (45, 75, 285, 155, (181, 205, 214)),
        (45, 205, 285, 285, (190, 211, 197)),
        (220, 120, 510, 235, (224, 201, 145)),
    ])
    write_xlsx(ROOT / "supplier-capacity-allocation" / "supplier-capacity.xlsx", "Capacity", [
        ["supplier", "monthly_capacity", "status", "region", "qualified_flag"],
        ["Alpha", 1200, "active", "CN-East", "yes"],
        ["Beta", 900, "active", "CN-South", "pending"],
        ["Gamma", 800, "active", "CN-East", "yes"],
        ["Delta", 600, "active", "CN-North", "yes"],
    ])
    write_pdf(ROOT / "supplier-capacity-allocation" / "quality-note.pdf", [
        "Supplier quality note (fictional fixture)",
        "Supplier Beta remains under qualification review.",
        "Production release authority is not yet recorded.",
    ])
    print("generated template binary fixtures")


if __name__ == "__main__":
    main()
