#!/usr/bin/env python3
"""Fetch reference pages / files on behalf of the sandbox.

Usage:
  fetch_urls.py <urls_file> <out_root>

<out_root>/pages/<slug>.html      raw HTML of every page URL (with candidate links)
<out_root>/files/<name>           downloaded files (.zip, images, ...)
<out_root>/_fetch_report.txt      what happened

Rules for classifying an URL:
  * ends with a known archive/image extension -> download as file
  * everything else -> download as page (HTML) and list candidate download
    links found inside it
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import http.cookiejar

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
FILE_EXT = (".zip", ".rar", ".7z", ".png", ".jpg", ".jpeg", ".webp", ".dds", ".xml", ".i3d", ".lua")
CANDIDATE_RE = re.compile(
    r'(?:href|src|data-url|data-href|data-download|action)\s*=\s*["\']([^"\']{5,500})["\']',
    re.I,
)
KEYWORDS = (
    "download", "/dl/", ".zip", "modsfire", "sharemods", "modsfile", "modsbase",
    "uploadfiles", "drive.google", "dropbox", "mediafire", "mega.nz", "onedrive",
    "1drv.ms", "file.io", "gofile", "workupload", "clicknupload", "filedownload",
)


def slug(url: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    name = urllib.parse.urlparse(url).path.strip("/").replace("/", "_").replace(".html", "")
    name = re.sub(r"[^A-Za-z0-9_.\-]", "_", name)[-60:]
    return f"{name or 'page'}_{digest}"


def fetch(op, url: str, timeout: int = 300) -> tuple[bytes, dict]:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with op.open(req, timeout=timeout) as resp:  # noqa: S310
        data = resp.read()
        return data, dict(resp.headers)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    urls_file, out_root = sys.argv[1], sys.argv[2]
    pages_dir = os.path.join(out_root, "pages")
    files_dir = os.path.join(out_root, "files")
    os.makedirs(pages_dir, exist_ok=True)
    os.makedirs(files_dir, exist_ok=True)

    with open(urls_file, encoding="utf-8") as fh:
        urls = [
            line.strip() for line in fh
            if line.strip() and not line.strip().startswith("#")
        ]

    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    report = []
    for url in urls:
        path = urllib.parse.urlparse(url).path.lower()
        is_file = path.endswith(FILE_EXT)
        report.append(f"=== {url}")
        try:
            t0 = time.time()
            data, headers = fetch(op, url, timeout=300)
            secs = time.time() - t0
            ctype = headers.get("Content-Type", "?")
            report.append(f"    {len(data)} bytes, {ctype}, {secs:.1f}s")
            if is_file or not ctype.startswith("text"):
                name = os.path.basename(path) or slug(url)
                if not name.lower().endswith(FILE_EXT):
                    name += ".bin"
                target = os.path.join(files_dir, name)
                with open(target, "wb") as fh:
                    fh.write(data)
                head = data[:4]
                report.append(f"    saved as files/{name} (head={head!r})")
            else:
                html = data.decode("utf-8", "replace")
                target = os.path.join(pages_dir, slug(url) + ".html")
                with open(target, "w", encoding="utf-8") as fh:
                    fh.write(html)
                report.append(f"    saved as pages/{os.path.basename(target)}")
                seen = set()
                for match in CANDIDATE_RE.finditer(html):
                    link = match.group(1).strip()
                    if link.startswith("//"):
                        link = "https:" + link
                    elif link.startswith("/"):
                        link = urllib.parse.urljoin(url, link)
                    if not link.startswith("http") or link in seen:
                        continue
                    low = link.lower()
                    if any(key in low for key in KEYWORDS) and "javascript" not in low:
                        seen.add(link)
                        report.append(f"    -> {link}")
        except Exception as exc:  # noqa: BLE001
            report.append(f"    ERROR: {exc}")
        report.append("")

    text = "\n".join(report)
    with open(os.path.join(out_root, "_fetch_report.txt"), "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
