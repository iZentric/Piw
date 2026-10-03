#!/usr/bin/env python3
"""Print diagnostics as GitHub Actions workflow annotations.

Annotations are readable through the API from outside, which makes them the
only usable log channel for this setup.

Usage: report_diag.py <file> [max_chars] [chunk_chars]
"""
from __future__ import annotations

import os
import sys


def emit(path: str, limit: int, chunk: int = 1100) -> None:
    if not os.path.isfile(path):
        print(f"::error::DIAG missing file {path}")
        return
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    text = text[-limit:]
    for index in range(0, max(len(text), 1), chunk):
        part = text[index:index + chunk]
        part = part.replace("\r", " ").replace("\n", " | ")
        print(f"::error::DIAG[{os.path.basename(path)}#{index // chunk}] {part}")


def main() -> int:
    for arg in sys.argv[1:]:
        bits = arg.split(":")
        path = bits[0]
        limit = int(bits[1]) if len(bits) > 1 else 4000
        emit(path, limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
