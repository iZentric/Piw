#!/usr/bin/env python3
"""Download a file behind a simple web form (XFileSharing-style host).

Usage:
  grab_file.py <list_file> <out_dir>

<list_file> lines:  <page_url> [output_name]
Lines starting with '#' are ignored.

Handles the usual flow of hosts like modsfile.com / moddingfile.com:
  GET page -> <form op=download1 ...> -> POST -> <form op=download2 ...> -> POST
  -> direct link.  Also follows plain "click here to download" links that point
  at a .zip / /d/ URL.
"""
from __future__ import annotations

import http.cookiejar
import os
import re
import sys
import time
import urllib.parse
import urllib.request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
FORM_RE = re.compile(r"<form[^>]*>(.*?)</form>", re.S | re.I)
FORM_TAG_RE = re.compile(r"<form([^>]*)>", re.I)
INPUT_RE = re.compile(r"<(?:input|button)[^>]*>", re.I)
ATTR_RE = re.compile(r'(\w+)\s*=\s*["\']([^"\']*)["\']')
LINK_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.I)
DIRECT_HINT = (".zip", ".rar", ".7z", "/d/", "downloadfile", "getfile")


def log(msg: str = "") -> None:
    print(msg, flush=True)


def save_page(out_dir: str, name: str, html: str) -> str:
    """Keep the fetched page so we can inspect the host's form/JS flow later."""
    parent = os.path.dirname(os.path.abspath(out_dir.rstrip("/"))) or "."
    pages = os.path.join(parent, "pages")
    os.makedirs(pages, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:80] or "page"
    path = os.path.join(pages, slug + ".html")
    with open(path, "w", encoding="utf-8", errors="replace") as fh:
        fh.write(html)
    return path


def candidate_links(html: str) -> list:
    """Any href/data-* that looks like a download endpoint (for diagnosis + retry)."""
    out, seen = [], set()
    for attr, value in re.findall(r'(href|action|data-href|data-url|data-link)\s*=\s*["\']([^"\']+)["\']', html, re.I):
        if value in seen:
            continue
        low = value.lower()
        if any(h in low for h in (".zip", "/d/", "download", "getfile", "downloadfile")):
            seen.add(value)
            out.append(value)
    return out[:15]


def build_opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def request(op, url: str, data: bytes | None = None, referer: str | None = None,
            timeout: int = 600):
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, headers=headers)
    return op.open(req, timeout=timeout)  # noqa: S310


def parse_form(html: str, idx: int = 0) -> tuple[str | None, dict[str, str]] | None:
    forms = FORM_RE.findall(html)
    if not forms:
        return None
    if idx >= len(forms):
        return None
    body = forms[idx]
    tags = FORM_TAG_RE.findall(html)
    attrs = dict(ATTR_RE.findall(tags[idx])) if idx < len(tags) else {}
    action = attrs.get("action") or None
    fields: dict[str, str] = {}
    for tag in INPUT_RE.findall(body):
        a = dict(ATTR_RE.findall(tag))
        name = a.get("name")
        if not name:
            continue
        if a.get("type", "text").lower() in ("checkbox", "radio") and "checked" not in tag:
            continue
        fields[name] = a.get("value", "submit" if a.get("type") == "submit" else "")
    return action, fields


def pick_form(html: str) -> tuple[int, str | None, dict[str, str]] | None:
    """Prefer the form that looks like a download form, else the first one."""
    tags = FORM_TAG_RE.findall(html)
    best = None
    for idx in range(len(FORM_RE.findall(html))):
        step = parse_form(html, idx)
        if not step:
            continue
        _action, fields = step
        attrs = dict(ATTR_RE.findall(tags[idx])) if idx < len(tags) else {}
        score = 0
        if "download" in (attrs.get("action") or "").lower():
            score += 3
        if str(fields.get("op", "")).startswith("download"):
            score += 3
        if "method_free" in fields or "method_premium" in fields:
            score += 2
        if any(k in fields for k in ("_token", "upload_id", "id", "fname")):
            score += 1
        if best is None or score > best[0]:
            best = (score, idx, step[0], step[1])
    if not best:
        return None
    return best[1], best[2], best[3]


def find_direct_link(html: str, base: str) -> str | None:
    for link in LINK_RE.findall(html):
        low = link.lower()
        if any(hint in low for hint in DIRECT_HINT) and not low.startswith("javascript"):
            return urllib.parse.urljoin(base, link)
    return None


def download(op, url: str, referer: str, out_dir: str, name: str) -> bool:
    log(f"  GET (file) {url}")
    with request(op, url, referer=referer) as resp:
        ctype = resp.headers.get("Content-Type", "")
        data = resp.read()
    if "text/html" in ctype and not data[:2] == b"PK":
        log(f"    got HTML instead of a file ({len(data)} bytes), head={data[:120]!r}")
        text = data.decode("utf-8", "replace")
        link = find_direct_link(text, url)
        if link and link != url:
            log(f"    trying {link}")
            return download(op, link, url, out_dir, name)
        return False
    target = os.path.join(out_dir, name)
    with open(target, "wb") as fh:
        fh.write(data)
    log(f"    saved {name}: {len(data)} bytes, head={data[:4]!r}")
    return len(data) > 1024 and data[:2] == b"PK"


def grab(op, page_url: str, out_dir: str, name: str) -> bool:
    log(f"=== {page_url}")
    html = ""
    with request(op, page_url) as resp:
        html = resp.read().decode("utf-8", "replace")
    log(f"  page: {len(html)} bytes")

    for attempt in range(6):
        picked = pick_form(html)
        if not picked:
            log("  no form found")
            link = find_direct_link(html, page_url)
            if link and download(op, link, page_url, out_dir, name):
                return True
            break
        _idx, action, fields = picked
        opcode = fields.get("op", "?")
        target = urllib.parse.urljoin(page_url, action) if action else page_url
        log(f"  POST {opcode} -> {target} ({len(fields)} fields)")
        post = urllib.parse.urlencode(fields).encode()
        time.sleep(2 if attempt == 0 else 6)
        with request(op, target, data=post, referer=page_url) as resp:
            ctype = resp.headers.get("Content-Type", "")
            body = resp.read()
        if "text/html" not in ctype and body[:2] == b"PK":
            target_path = os.path.join(out_dir, name)
            with open(target_path, "wb") as fh:
                fh.write(body)
            log(f"    saved directly: {name} ({len(body)} bytes)")
            return True
        html = body.decode("utf-8", "replace")
        log(f"    response: {len(html)} bytes, {ctype}")
        link = find_direct_link(html, target)
        if link:
            log(f"    direct link found: {link}")
            if download(op, link, target, out_dir, name):
                return True
    path = save_page(out_dir, name, html)
    log(f"  page saved: {path}")
    links = candidate_links(html)
    if links:
        log("  candidate links: " + " | ".join(links))
        for link in links:
            target = urllib.parse.urljoin(page_url, link)
            if download(op, target, page_url, out_dir, name):
                return True
    log("  !! could not obtain the file through the form flow")
    return False


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    list_file, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    ok = True
    with open(list_file, encoding="utf-8") as fh:
        entries = [
            line.strip() for line in fh
            if line.strip() and not line.strip().startswith("#")
        ]
    op = build_opener()
    for entry in entries:
        parts = entry.split()
        url = parts[0]
        name = parts[1] if len(parts) > 1 else (os.path.basename(urllib.parse.urlparse(url).path) or "download.zip")
        if not name.lower().endswith((".zip", ".rar", ".7z")):
            name += ".zip"
        if os.path.isfile(os.path.join(out_dir, name)):
            log(f"=== {url}\n  already present: {name}")
            continue
        try:
            if not grab(op, url, out_dir, name):
                ok = False
        except Exception as exc:  # noqa: BLE001
            log(f"  !! {url} raised {type(exc).__name__}: {exc}")
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
