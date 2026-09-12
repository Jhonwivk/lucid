#!/usr/bin/env python3
"""Historical T08 filename. Image intake no longer includes a vision runtime."""

from __future__ import annotations

import os
import sys
from pathlib import Path

TARGET = Path(__file__).with_name("verify_t08_images.py")


def main() -> None:
    print("NOTE: T08 is PNG/JPEG bytes + metadata + full-image provenance. Vision is not a Materials capability.")
    os.execv(sys.executable, [sys.executable, str(TARGET), *sys.argv[1:]])


if __name__ == "__main__":
    main()
