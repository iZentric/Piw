#!/usr/bin/env python3
"""Fallback downloader for a public Google Drive folder.

Usage: drive_fallback.py <folder_url> <output_dir>

Only used when `gdown --folder` fails inside the GitHub Actions runner.
"""
from __future__ import annotations

import os
import re
import sys
import urllib.request

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
CHUNK = 1 << 20


def fetch(url: str, timeout: int = 300) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def parse_folder(html: str) -> list[tuple[str, str]]:
    """Return a list of (file_id, file_name) found in a Drive folder page."""
    blob = html
    match = re.search(r"window\['_DRIVE_ivd'\]\s*=\s*'(.*?)';", html, re.S)
    if match:
        escaped = match.group(1)
        try:
            blob = escaped.encode("utf-8").decode("unicode_escape")
        except Exception:  # noqa: BLE001
            blob = escaped.replace("\\x22", '"').replace("\\/", "/")
    pairs = re.findall(r'"([A-Za-z0-9_-]{28,44})"\s*,\s*"([^"]{1,200}\.zip)"', blob)
    if not pairs:
        ids = re.findall(r'data-id="([A-Za-z0-9_-]{28,44})"', html)
        names = re.findall(r'"(FS22[A-Za-z0-9_.\-]*\.zip|[A-Za-z0-9_.\-]+\.zip)"', blob)
        pairs = list(zip(ids, names))
    seen, out = set(), []
    for fid, name in pairs:
        if fid in seen:
            continue
        seen.add(fid)
        out.append((fid, name))
    return out


def download(fid: str, name: str, out_dir: str) -> None:
    url = (
        "https://drive.usercontent.google.com/download"
        f"?id={fid}&export=download&confirm=t"
    )
    target = os.path.join(out_dir, name)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=600) as resp, open(target, "wb") as fh:  # noqa: S310
        while True:
            chunk = resp.read(CHUNK)
            if not chunk:
                break
            fh.write(chunk)
    size = os.path.getsize(target)
    with open(target, "rb") as fh:
        head = fh.read(4)
    if size < 1024 * 1024 or head[:2] != b"PK":
        raise RuntimeError(f"download of {name} looks wrong (size={size}, head={head!r})")
    print(f"downloaded {name} ({size} bytes)")


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    folder_url, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    match = re.search(r"/folders/([A-Za-z0-9_-]+)", folder_url)
    if not match:
        raise SystemExit(f"no folder id in {folder_url}")
    folder_id = match.group(1)
    html = fetch(f"https://drive.google.com/drive/folders/{folder_id}").decode("utf-8", "replace")
    files = parse_folder(html)
    if not files:
        raise SystemExit("could not find any file inside the Drive folder page")
    for fid, name in files:
        download(fid, name, out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
