#!/usr/bin/env python3
"""Fallback downloader for a public Google Drive folder.

Usage:
  drive_fallback.py <folder_url> <output_dir> [--log FILE] [--need name.zip ...]

Prints / logs everything it finds.  Only downloads the files listed with
--need (default: all .zip files found) that are not already present in
<output_dir>.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
ID_RE = re.compile(r"^[A-Za-z0-9_-]{25,44}$")

LOG_FH = None


def log(msg: str = "") -> None:
    print(msg, flush=True)
    if LOG_FH is not None:
        LOG_FH.write(msg + "\n")
        LOG_FH.flush()


def opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def http_get(op, url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with op.open(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def walk_pairs(node, acc) -> None:
    """Collect (file_id, name) pairs from the decoded _DRIVE_ivd structure."""
    if isinstance(node, list):
        strings = [x for x in node if isinstance(x, str)]
        ids = [s for s in strings if ID_RE.match(s)]
        names = [s for s in strings if s.lower().endswith(".zip")]
        if ids and names:
            acc.append((ids[0], names[0]))
        for item in node:
            walk_pairs(item, acc)
    elif isinstance(node, dict):
        for value in node.values():
            walk_pairs(value, acc)


def parse_folder(html: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    match = re.search(r"window\['_DRIVE_ivd'\]\s*=\s*'(.*?)';", html, re.S)
    if match:
        raw = match.group(1)
        decoded = None
        try:
            decoded = raw.encode("utf-8").decode("unicode_escape")
        except Exception:  # noqa: BLE001
            decoded = raw.replace("\\x22", '"').replace("\\/", "/")
        for candidate in (decoded, raw):
            try:
                walk_pairs(json.loads(candidate), pairs)
            except Exception as exc:  # noqa: BLE001
                log(f"    (json parse of _DRIVE_ivd failed: {exc})")
            if pairs:
                break
        if not pairs:
            for m in re.finditer(
                r'\[\s*"([A-Za-z0-9_-]{25,44})"\s*,\s*\[[^\]]*\]\s*,\s*"([^"]{1,200}\.zip)"',
                decoded or raw,
            ):
                pairs.append((m.group(1), m.group(2)))
    if not pairs:
        for m in re.finditer(r'data-id="([A-Za-z0-9_-]{25,44})"', html):
            pairs.append((m.group(1), ""))
        names = re.findall(r'"([A-Za-z0-9_.\- ]{1,200}\.zip)"', html)
        merged = []
        for i, (fid, _) in enumerate(pairs):
            merged.append((fid, names[i] if i < len(names) else ""))
        pairs = merged
    seen, out = set(), []
    for fid, name in pairs:
        if fid in seen or not name:
            continue
        seen.add(fid)
        out.append((fid, name))
    return out


def download(op, fid: str, name: str, out_dir: str) -> bool:
    url = (
        "https://drive.usercontent.google.com/download"
        f"?id={urllib.parse.quote(fid)}&export=download&confirm=t"
    )
    target = os.path.join(out_dir, name)
    for attempt in range(1, 4):
        try:
            log(f"  downloading {name} (id={fid}, attempt {attempt}) ...")
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            t0 = time.time()
            with op.open(req, timeout=900) as resp, open(target, "wb") as fh:  # noqa: S310
                size = 0
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
                    size += len(chunk)
            with open(target, "rb") as fh:
                head = fh.read(4)
            if head[:2] == b"PK" and size > 1024:
                log(f"  ok {name}: {size} bytes in {time.time() - t0:.1f}s")
                return True
            snippet = open(target, "rb").read(400).decode("utf-8", "replace")
            log(f"  NOT a zip ({size} bytes). First bytes: {snippet[:300]!r}")
        except Exception as exc:  # noqa: BLE001
            log(f"  download error: {exc}")
        time.sleep(3 * attempt)
    if os.path.exists(target):
        os.remove(target)
    return False


def main() -> int:
    global LOG_FH
    parser = argparse.ArgumentParser()
    parser.add_argument("folder_url")
    parser.add_argument("out_dir")
    parser.add_argument("--log")
    parser.add_argument("--need", nargs="*", default=None)
    args = parser.parse_args()

    if args.log:
        LOG_FH = open(args.log, "a", encoding="utf-8")
    os.makedirs(args.out_dir, exist_ok=True)

    match = re.search(r"/folders/([A-Za-z0-9_-]+)", args.folder_url)
    if not match:
        log(f"no folder id in {args.folder_url}")
        return 2
    folder_id = match.group(1)

    op = opener()
    page_url = f"https://drive.google.com/drive/folders/{folder_id}?hl=en"
    html = http_get(op, page_url).decode("utf-8", "replace")
    log(f"  folder page: {len(html)} bytes")
    files = parse_folder(html)
    log(f"  parsed {len(files)} file(s) from the folder page:")
    for fid, name in files:
        log(f"    - {name}  (id={fid})")
    if not files:
        log("  !! could not parse any file from the folder page")
        return 1

    wanted = args.need if args.need else [n for _f, n in files]
    ok = True
    for fid, name in files:
        if name not in wanted:
            continue
        if os.path.isfile(os.path.join(args.out_dir, name)):
            log(f"  already present: {name}")
            continue
        if not download(op, fid, name, args.out_dir):
            ok = False
    for name in wanted:
        if not os.path.isfile(os.path.join(args.out_dir, name)):
            log(f"  MISSING after fallback: {name}")
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
