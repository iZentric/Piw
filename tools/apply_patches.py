#!/usr/bin/env python3
"""Build the converted FS25 mods.

Usage: apply_patches.py <downloads_dir> <patch_dir> <out_dir> [original_info_dir]

For every mod .zip found in <downloads_dir>:
  * the whole archive is extracted,
  * everything from <patch_dir>/<zip stem>/ is copied on top of it
    (files that do not exist in the archive are reported),
  * a file called "_remove.txt" inside the patch folder may list paths that must
    be deleted from the archive (one path per line, '#' comments allowed),
  * a CONVERSIE_FS25_INFO.txt is added at the archive root,
  * the archive is re-created as FS25_<name>.zip inside <out_dir>.

If <original_info_dir> is given, the sha256 of each input zip is compared with
the one recorded during the extraction run (paranoia check: make sure the same
file is being patched).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile


def sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            data = fh.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def expected_sha(info_dir: str, stem: str) -> str | None:
    path = os.path.join(info_dir, f"_info_{stem}.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get("sha256")


INFO_TXT = """Conversie FS22 -> FS25
=======================

Acest mod a fost convertit automat pentru Farming Simulator 25
(modDesc descVersion, fisiere XML/i3d actualizate pentru FS25).

Instalare: copiaza acest fisier .zip in folderul de mods al jocului:
    Documents/My Games/FarmingSimulator2025/mods
si activeaza-l cand incarci salvarea.

Daca apar erori in joc, trimite continutul fisierului:
    Documents/My Games/FarmingSimulator2025/log.txt
"""


REF_ATTR = re.compile(r'(?P<pre>\b(?:filename|image|xmlFilename|iconFilename|img)=")(?P<path>[^"]+)(?P<post>")')
REF_ELEM = re.compile(r'(?P<pre><(?:image|iconFilename|filename)>)(?P<path>[^<]+)(?P<post></(?:image|iconFilename|filename)>)')


def scan_broken(root: str) -> set:
    """Return the set of local file references (xml/i3d) that do not resolve."""
    files = set()
    for r, _dirs, fs in os.walk(root):
        for nm in fs:
            files.add(os.path.relpath(os.path.join(r, nm), root).replace("\\", "/"))
    low = {f.lower() for f in files}
    broken = set()
    for r, _dirs, fs in os.walk(root):
        for nm in sorted(fs):
            if not nm.lower().endswith((".xml", ".i3d")):
                continue
            full = os.path.join(r, nm)
            rel = os.path.relpath(full, root).replace("\\", "/")
            basedir = os.path.dirname(rel)
            with open(full, "rb") as fh:
                text = fh.read().decode("utf-8-sig", errors="replace")
            for pat in (REF_ATTR, REF_ELEM):
                for m in pat.finditer(text):
                    ref = m.group("path").strip().replace("\\", "/")
                    if not ref or ref.startswith(("$", "/")) or re.match(r"^[A-Za-z]:", ref):
                        continue
                    cands = (os.path.normpath(os.path.join(basedir, ref)).replace("\\", "/"),
                             os.path.normpath(ref).replace("\\", "/"))
                    if any(c in files or c.lower() in low for c in cands):
                        continue
                    broken.add((rel, ref))
    return broken


def build_zip(src_zip: str, patch_root: str, out_dir: str, info_dir: str | None) -> str:
    stem = os.path.splitext(os.path.basename(src_zip))[0]
    patched = os.path.join(patch_root, stem)

    if info_dir:
        want = expected_sha(info_dir, stem)
        if want:
            got = sha256(src_zip)
            if got != want:
                print(f"  !! sha256 mismatch for {stem}: {got} != {want} (continuing)")

    with tempfile.TemporaryDirectory() as tmp:
        work = os.path.join(tmp, stem)
        os.makedirs(work, exist_ok=True)
        with zipfile.ZipFile(src_zip) as zf:
            zf.extractall(work)

        broken_before = scan_broken(work)

        removed, added, replaced, missing = [], [], [], []
        if os.path.isdir(patched):
            remove_list = os.path.join(patched, "_remove.txt")
            if os.path.isfile(remove_list):
                with open(remove_list, encoding="utf-8") as fh:
                    for line in fh:
                        entry = line.strip()
                        if not entry or entry.startswith("#"):
                            continue
                        target = os.path.join(work, entry)
                        if os.path.isfile(target):
                            os.remove(target)
                            removed.append(entry)
                        else:
                            missing.append(entry)

            for root, _dirs, files in os.walk(patched):
                for name in files:
                    if name == "_remove.txt":
                        continue
                    src = os.path.join(root, name)
                    rel = os.path.relpath(src, patched)
                    dst = os.path.join(work, rel)
                    os.makedirs(os.path.dirname(dst) or work, exist_ok=True)
                    if os.path.isfile(dst):
                        replaced.append(rel)
                    else:
                        added.append(rel)
                    shutil.copy2(src, dst)

        with open(os.path.join(work, "CONVERSIE_FS25_INFO.txt"), "w", encoding="utf-8") as fh:
            fh.write(INFO_TXT)

        # --- verification -------------------------------------------------
        # (a) no FS22-era shader file left (they use tex2D() and cannot load on FS25)
        fs22_shaders = []
        for root, _dirs, files in os.walk(work):
            for name in sorted(files):
                if not name.lower().endswith(".xml"):
                    continue
                full = os.path.join(root, name)
                with open(full, "rb") as fh:
                    blob = fh.read()
                if b"<CustomShader" in blob[:4096] and b"tex2D(" in blob:
                    fs22_shaders.append(os.path.relpath(full, work))

        # (b) every local file reference (xml/i3d) must resolve inside the archive;
        #     only references that were fine before the patches count as regressions
        broken_after = scan_broken(work)
        regressions = sorted(broken_after - broken_before)

        print(f"  check: FS22-era shader files left : {len(fs22_shaders)}")
        for item in fs22_shaders:
            print(f"    ! {item}")
        print(f"  check: unresolved local refs      : {len(broken_after)} "
              f"(pre-existing in the FS22 archive: {len(broken_before)})")
        for item, ref in sorted(broken_after):
            print(f"    ? {item} -> {ref}")
        print(f"  check: refs broken by this build  : {len(regressions)}")
        for item, ref in regressions:
            print(f"    x {item} -> {ref}")

        out_name = f"FS25_{stem[5:]}" if stem.upper().startswith("FS22_") else f"FS25_{stem}"
        out_path = os.path.join(out_dir, out_name + ".zip")
        os.makedirs(out_dir, exist_ok=True)
        if os.path.exists(out_path):
            os.remove(out_path)
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for root, _dirs, files in os.walk(work):
                for name in sorted(files):
                    full = os.path.join(root, name)
                    rel = os.path.relpath(full, work).replace("\\", "/")
                    zf.write(full, rel)

    print(f"built {out_path}")
    print(f"  replaced files : {len(replaced)}")
    for item in sorted(replaced):
        print(f"    ~ {item}")
    print(f"  added files    : {len(added)}")
    for item in sorted(added):
        print(f"    + {item}")
    if removed:
        print(f"  deleted files  : {len(removed)}")
        for item in sorted(removed):
            print(f"    - {item}")
    if missing:
        print(f"  WARNING: patched/removed files that are NOT in the archive ({len(missing)}):")
        for item in sorted(missing):
            print(f"    ? {item}")
    return out_path


def main() -> int:
    if len(sys.argv) not in (4, 5):
        print(__doc__)
        return 2
    dl_dir, patch_dir, out_dir = sys.argv[1:4]
    info_dir = sys.argv[4] if len(sys.argv) == 5 else None
    zips = []
    for root, _dirs, files in os.walk(dl_dir):
        for name in files:
            if name.lower().endswith(".zip"):
                zips.append(os.path.join(root, name))
    if not zips:
        print("no .zip files found in", dl_dir)
        return 1
    for path in sorted(zips):
        print(f"=== {os.path.basename(path)}")
        build_zip(path, patch_dir, out_dir, info_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
