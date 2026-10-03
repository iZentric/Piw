#!/usr/bin/env python3
"""Extract every text file (xml / i3d / lua / ...) from the mod zips.

Usage: extract_text.py <downloads_dir> <output_dir>

For each *.zip found under <downloads_dir> a folder <output_dir>/<zip stem>/ is
created that mirrors the zip structure but contains only small text files.  In
addition two metadata files are written next to it:

    _filelist_<zip stem>.txt   every entry of the zip with size and CRC
    _info_<zip stem>.json      size, sha256, entry count ...
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import zipfile

# Only files that really are text (the .i3d.shapes / .dds / .ogg files are
# binary assets and must never end up in the repository).
TEXT_EXT = {
    ".xml", ".i3d", ".lua", ".txt", ".md", ".json", ".cfg", ".conf", ".ini",
    ".materials", ".csv", ".xsd", ".shader", ".glsl", ".xml.bak",
}

MAX_TEXT_SIZE = 8 * 1024 * 1024  # per file safety limit


def sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            data = fh.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def process(zip_path: str, out_dir: str) -> None:
    stem = os.path.splitext(os.path.basename(zip_path))[0]
    dest = os.path.join(out_dir, stem)
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)

    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        listing = []
        total = 0
        for info in infos:
            total += info.file_size
            listing.append(f"{info.file_size:12d}  {info.CRC:08x}  {info.filename}")
            if info.is_dir():
                continue
            ext = os.path.splitext(info.filename)[1].lower()
            if ext not in TEXT_EXT or info.file_size > MAX_TEXT_SIZE:
                continue
            target = os.path.join(dest, info.filename.replace("\\", "/"))
            os.makedirs(os.path.dirname(target) or dest, exist_ok=True)
            try:
                with zf.open(info) as src, open(target, "wb") as dst:
                    dst.write(src.read())
            except Exception as exc:  # noqa: BLE001
                print(f"  ! could not extract {info.filename}: {exc}")

    listing.sort(key=lambda line: line.split("  ", 2)[-1])
    with open(os.path.join(out_dir, f"_filelist_{stem}.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"# contents of {os.path.basename(zip_path)}\n")
        fh.write("# " + "\n# ".join(["size bytes  crc32  path"]) + "\n")
        fh.write("\n".join(listing) + "\n")

    info_doc = {
        "zip": os.path.basename(zip_path),
        "sha256": sha256(zip_path),
        "size": os.path.getsize(zip_path),
        "entries": len(infos),
        "uncompressed_size": total,
    }
    with open(os.path.join(out_dir, f"_info_{stem}.json"), "w", encoding="utf-8") as fh:
        json.dump(info_doc, fh, indent=2)
        fh.write("\n")
    print(f"{os.path.basename(zip_path)}: {len(infos)} entries, sha256={info_doc['sha256']}")


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    dl_dir, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    zips = []
    for root, _dirs, files in os.walk(dl_dir):
        for name in files:
            if name.lower().endswith(".zip"):
                zips.append(os.path.join(root, name))
    if not zips:
        print("no .zip files found in", dl_dir)
        return 1
    for path in sorted(zips):
        process(path, out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
