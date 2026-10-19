#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyyaml",
# ]
# ///
"""Demand-driven pinned document store and polite HTTP read-through cache.

CLI subcommands:
  get          Fetch or read a URL in latest mode, or by immutable --sha256 pin.
  pin          Discover current wiki/page revision, pin immutable bytes, and
               print a suggested Spec Format 2 resources.documents YAML entry.
  links        List outbound links and attachment references from a cached page
               without crawling them.
  headings     Extract document headings (Trac wikitext, Markdown, or HTML) as a
               reading and locator-authoring aid.
  info         Show recorded snapshot history or blob metadata.
  prefetch     Politely fetch and verify all pinned documents declared in one or
               more Spec Format 2 YAML files.
  materialize  Populate a --docs-dir directory (for spec.py resolve --docs-dir)
               with hash-verified hardlinks or copies, adopting any existing
               valid files into the blob store by copy.
  verify       Re-hash stored blobs (and optional --docs-dir files) to detect
               corruption.
  gc           Remove unreferenced blobs not pinned by the given --spec files.

Exit codes:
  0  Success.
  1  Operational, network, policy, soft-error, or hash verification failure.
  2  Usage error.
  3  Missing precondition (such as PyYAML for YAML spec commands).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import email.utils
import fcntl
import gzip
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
import urllib.request
import zlib

DEFAULT_USER_AGENT = (
    "driver-lab-site-cache/1.0 "
    "(+https://github.com/curtisgalloway/driver-lab; "
    "polite demand-driven document cache)"
)
DEFAULT_MIN_INTERVAL = 2.0
DEFAULT_MAX_AGE = 86400.0
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_SIZE_MB = 200.0
DEFAULT_MAX_RETRIES = 2
EXTRACTOR_VERSION = "v2"
SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")
CHUNK_SIZE = 65536


class CacheError(Exception):
    """Operational, policy, soft-error, or verification failure (exit 1)."""

    def __init__(self, message: str, fetch_status: str = "failed") -> None:
        super().__init__(message)
        self.fetch_status = fetch_status


class UsageError(Exception):
    """Command-line or input usage error (exit 2)."""


class PreconditionError(Exception):
    """Missing runtime dependency or environment precondition (exit 3)."""


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_timestamp(value: str) -> float:
    """Parse an ISO-8601 UTC timestamp into epoch seconds."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).timestamp()


def parse_duration(value: str) -> float:
    """Parse a duration like '3600', '30s', '15m', '24h', or '7d' into seconds."""
    text = str(value).strip().lower()
    if not text:
        raise UsageError("empty duration")
    multipliers = {"s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}
    suffix = text[-1]
    if suffix in multipliers:
        num_text = text[:-1].strip()
        scale = multipliers[suffix]
    else:
        num_text = text
        scale = 1.0
    try:
        seconds = float(num_text) * scale
    except ValueError as exc:
        raise UsageError(f"invalid duration: {value!r}") from exc
    if seconds < 0:
        raise UsageError("duration must be non-negative")
    return seconds


def default_cache_dir() -> Path:
    """Resolve the default cache directory outside the workspace and /tmp."""
    env_dir = os.environ.get("SITE_CACHE_DIR")
    if env_dir:
        return Path(env_dir).expanduser()
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg).expanduser() if xdg else (Path.home() / ".cache")
    return base / "site-cache"


def validate_cache_dir(cache_dir: Path, allow_ephemeral: bool = False) -> Path:
    """Ensure the cache directory is not inside /tmp or a spec root."""
    resolved = cache_dir.expanduser().resolve()
    tmp_root = Path(tempfile.gettempdir()).resolve()
    if not allow_ephemeral and (resolved == tmp_root or tmp_root in resolved.parents):
        raise UsageError(
            f"refusing ephemeral cache directory under {tmp_root}; "
            "use ~/.cache/site-cache or pass --allow-ephemeral-cache for tests"
        )
    for check_dir in (resolved, *resolved.parents):
        if (check_dir / "board-specs.yaml").is_file():
            raise UsageError(
                f"refusing cache directory inside a spec root ({check_dir})"
            )
    return resolved


def normalize_url(url: str, allow_loopback_http: bool = False) -> str:
    """Normalize a URL: lowercase scheme/host, strip fragment, preserve query."""
    if not isinstance(url, str) or not url.strip():
        raise UsageError("URL must be a non-empty string")
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in ("https", "http"):
        raise UsageError(f"unsupported URL scheme {scheme!r} in {url!r}")
    if not parts.hostname:
        raise UsageError(f"URL is missing a hostname: {url!r}")
    host = parts.hostname.lower()
    if scheme == "http":
        if not (allow_loopback_http and host in ("127.0.0.1", "localhost", "::1")):
            raise UsageError(
                f"URL must use https:// (got {url!r})"
            )
    try:
        port = parts.port
    except ValueError as exc:
        raise UsageError(f"invalid port in URL {url!r}") from exc
    if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
        netloc = host
    elif port is not None:
        netloc = f"{host}:{port}"
    else:
        netloc = host
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def strip_alternate_format_query(url: str) -> tuple[str, bool]:
    """Return (canonical_url_without_raw_format_param, had_alternate_format)."""
    parts = urlsplit(url)
    if not parts.query:
        return url, False
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    filtered = []
    removed = False
    for key, val in pairs:
        if (key == "format" and val == "txt") or (key == "action" and val == "raw"):
            removed = True
        else:
            filtered.append((key, val))
    new_query = urlencode(filtered)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, "")), removed


class FileLock:
    """Context manager for an advisory flock file."""

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        self._fd: int | None = None

    def __enter__(self) -> FileLock:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(str(self.lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(self._fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = None


class RobotsPolicy:
    """RFC 9309 robots.txt parser supporting *, $, Allow, Disallow, Crawl-delay."""

    def __init__(self, text: str, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self.rules: list[tuple[str, str, re.Pattern[str]]] = []
        self.crawl_delay: float = 0.0
        self._parse(text, user_agent)

    @staticmethod
    def _compile_pattern(pattern: str) -> re.Pattern[str]:
        anchored_end = pattern.endswith("$")
        core = pattern[:-1] if anchored_end else pattern
        pieces = [re.escape(part) for part in core.split("*")]
        body = ".*".join(pieces)
        if r"\?" in body:
            body = body.replace(r"\?", r"\?(?:[^#]*&)?", 1)
        regex = r"\A" + body
        if anchored_end:
            regex += r"\Z"
        return re.compile(regex)

    def _parse(self, text: str, user_agent: str) -> None:
        product = user_agent.split("/", 1)[0].strip().lower()
        groups: list[tuple[list[str], list[tuple[str, str]], float]] = []
        current_agents: list[str] = []
        current_rules: list[tuple[str, str]] = []
        current_delay = 0.0
        seen_rule = False

        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            field, value = line.split(":", 1)
            key = field.strip().lower()
            val = value.strip()
            if key == "user-agent":
                if seen_rule:
                    groups.append((current_agents, current_rules, current_delay))
                    current_agents = []
                    current_rules = []
                    current_delay = 0.0
                    seen_rule = False
                current_agents.append(val.lower())
            elif key in ("allow", "disallow"):
                if not current_agents:
                    continue
                seen_rule = True
                current_rules.append((key, val))
            elif key == "crawl-delay":
                if not current_agents:
                    continue
                seen_rule = True
                try:
                    delay = float(val)
                    if delay > 0:
                        current_delay = max(current_delay, delay)
                except ValueError:
                    pass
        if current_agents:
            groups.append((current_agents, current_rules, current_delay))

        matched_rules: list[tuple[str, str]] = []
        matched_delay = 0.0
        specific_matched = False
        for agents, rules, delay in groups:
            for a in agents:
                a_token = a.split("/", 1)[0].strip()
                if a_token and a_token != "*" and (product == a_token or product.startswith(a_token)):
                    matched_rules.extend(rules)
                    matched_delay = max(matched_delay, delay)
                    specific_matched = True
                    break
        if not specific_matched:
            for agents, rules, delay in groups:
                if "*" in agents:
                    matched_rules.extend(rules)
                    matched_delay = max(matched_delay, delay)

        self.crawl_delay = matched_delay
        for directive, pattern in matched_rules:
            if not pattern:
                continue
            self.rules.append((directive, pattern, self._compile_pattern(pattern)))

    def is_allowed(self, url: str) -> bool:
        """Evaluate longest-matching rule (Allow wins ties per RFC 9309)."""
        parts = urlsplit(url)
        target = parts.path or "/"
        if parts.query:
            target = f"{target}?{parts.query}"
        best_len = -1
        best_directive = "allow"
        for directive, raw_pattern, compiled in self.rules:
            if compiled.search(target):
                plen = len(raw_pattern)
                if plen > best_len or (plen == best_len and directive == "allow"):
                    best_len = plen
                    best_directive = directive
        return best_directive == "allow"


def detect_soft_error(
    status: int,
    headers: dict[str, str],
    body: bytes,
    requested_url: str,
) -> tuple[str, str | None]:
    """Inspect a 200 OK payload for truncation, bot challenges, login walls, or stubs.

    Returns (fetch_status, error_message). fetch_status is one of:
    'ok', 'blocked', 'truncated', 'partial'.
    """
    if status != 200:
        return "failed", f"HTTP status {status}"
    declared_len = headers.get("content-length")
    if declared_len is not None and declared_len.strip().isdigit():
        expected = int(declared_len.strip())
        if len(body) != expected:
            return (
                "truncated",
                f"Content-Length mismatch: expected {expected} bytes, got {len(body)}",
            )
    if not body:
        return "blocked", "empty 200 OK response body"

    ctype = headers.get("content-type", "").lower()
    if body.startswith(b"%PDF-"):
        if b"%%EOF" not in body[-2048:]:
            return "truncated", "PDF response is missing trailing %%EOF marker"
        return "ok", None

    if any(t in ctype for t in ("text/html", "text/plain", "application/xhtml")) or (
        not ctype and body[:64].lstrip().startswith((b"<!", b"<html", b"<HTML"))
    ):
        sample = body[:32768].decode("utf-8", errors="replace")
        lower = sample.lower()
        if (
            "cf-browser-verification" in lower
            or "cdn-cgi/challenge-platform" in lower
            or ("<title>just a moment...</title>" in lower and "cloudflare" in lower)
            or ("<title>attention required!" in lower and "cloudflare" in lower)
        ):
            return "blocked", "bot challenge or interstitial page detected in 200 OK response"

        if (
            re.search(r"<title>\s*(?:sign\s*in|log\s*in)\b", lower)
            and re.search(r'<input[^>]+type=["\']?password', lower)
        ):
            return "blocked", "login wall detected in 200 OK response"

        if (
            "the page" in lower
            and "does not exist. you can create it here" in lower
            and 'id="content" class="wiki' in lower
        ):
            return "blocked", "Trac non-existent wiki page stub detected in 200 OK response"

    return "ok", None


class _HtmlExtractor(HTMLParser):
    """Extract title, headings, outbound links, and readable text from HTML."""

    SKIP_TAGS = frozenset({"script", "style", "noscript", "svg"})
    BLOCK_TAGS = frozenset(
        {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote", "br", "hr"}
    )

    def __init__(self, base_url: str = "") -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.in_title = False
        self._skip_depth = 0
        self._heading_level: int | None = None
        self._heading_id: str = ""
        self._heading_parts: list[str] = []
        self.headings: list[dict[str, Any]] = []
        self.links: list[dict[str, str]] = []
        self._link_href: str | None = None
        self._link_rel: str = ""
        self._link_parts: list[str] = []
        self.alternate_links: list[dict[str, str]] = []
        self.text_lines: list[str] = []
        self._current_line: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_l = tag.lower()
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        if tag_l in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag_l == "title":
            self.in_title = True
        elif tag_l == "link":
            href = attr_map.get("href", "").strip()
            if href:
                full = urljoin(self.base_url, href) if self.base_url else href
                self.alternate_links.append(
                    {
                        "rel": attr_map.get("rel", ""),
                        "type": attr_map.get("type", ""),
                        "title": attr_map.get("title", ""),
                        "url": full,
                    }
                )
        elif re.fullmatch(r"h[1-6]", tag_l):
            self._flush_line()
            self._heading_level = int(tag_l[1])
            self._heading_id = attr_map.get("id", "")
            self._heading_parts = []
        elif tag_l == "a":
            href = attr_map.get("href", "").strip()
            if href and not href.startswith(("javascript:", "mailto:")):
                self._link_href = urljoin(self.base_url, href) if self.base_url else href
                self._link_rel = attr_map.get("rel", "")
                self._link_parts = []
        elif tag_l == "img":
            src = attr_map.get("src", "").strip()
            if src:
                full = urljoin(self.base_url, src) if self.base_url else src
                self.links.append(
                    {
                        "url": full,
                        "text": attr_map.get("alt", "") or Path(urlsplit(src).path).name,
                        "kind": "image",
                    }
                )
        elif tag_l in self.BLOCK_TAGS:
            self._flush_line()

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()
        if tag_l in self.SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag_l == "title":
            self.in_title = False
        elif self._heading_level is not None and re.fullmatch(r"h[1-6]", tag_l):
            raw_heading = re.sub(r"\s+", " ", "".join(self._heading_parts)).strip().rstrip("¶").strip()
            if raw_heading:
                self.headings.append(
                    {
                        "level": self._heading_level,
                        "heading": raw_heading,
                        "anchor": self._heading_id,
                    }
                )
                prefix = "#" * self._heading_level
                self.text_lines.append(f"{prefix} {raw_heading}")
            self._heading_level = None
            self._heading_id = ""
            self._heading_parts = []
            self._current_line = []
        elif tag_l == "a" and self._link_href is not None:
            label = re.sub(r"\s+", " ", "".join(self._link_parts)).strip()
            self.links.append(
                {
                    "url": self._link_href,
                    "text": label,
                    "kind": "link",
                    "rel": self._link_rel,
                }
            )
            self._link_href = None
            self._link_rel = ""
            self._link_parts = []
        elif tag_l in self.BLOCK_TAGS:
            self._flush_line()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
        if self._heading_level is not None:
            self._heading_parts.append(data)
        if self._link_href is not None:
            self._link_parts.append(data)
        self._current_line.append(data)

    def _flush_line(self) -> None:
        if not self._current_line:
            return
        line = re.sub(r"\s+", " ", "".join(self._current_line)).strip()
        self._current_line = []
        if line:
            self.text_lines.append(line)

    def close(self) -> None:
        self._flush_line()
        super().close()


def extract_wikitext_info(text: str, page_url: str = "") -> dict[str, Any]:
    """Extract headings, links, attachment references, and html-block warnings from wikitext."""
    headings: list[dict[str, Any]] = []
    links: list[dict[str, str]] = []
    attachments: list[dict[str, str]] = []
    has_html_processor = False
    in_code_block = False

    parts = urlsplit(page_url) if page_url else None
    base_root = f"{parts.scheme}://{parts.netloc}" if parts and parts.scheme else ""
    wiki_page = ""
    if parts and "/wiki/" in parts.path:
        wiki_page = parts.path.split("/wiki/", 1)[1].strip("/")

    trac_heading_re = re.compile(r"^\s*(=+)\s+(.+?)\s*=*(?:\s+#([A-Za-z0-9_.-]+))?\s*$")
    md_heading_re = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")
    image_macro_re = re.compile(r"\[\[Image\(([^),\s]+)(?:,[^\]]*)?\)\]\]")
    wiki_link_re = re.compile(r"\[wiki:([^\s\]]+)(?:\s+([^\]]+))?\]")
    http_link_re = re.compile(r"\[(https?://[^\s\]]+)(?:\s+([^\]]+))?\]")
    title_index_re = re.compile(r"\[\[TitleIndex\(([^)]*)\)\]\]")

    macros: list[str] = []

    for line_no, raw_line in enumerate(text.splitlines(), 1):
        stripped = raw_line.strip()
        if stripped.startswith("{{{"):
            if "#!html" in stripped.lower():
                has_html_processor = True
            in_code_block = True
            continue
        if stripped == "}}}":
            in_code_block = False
            continue
        if "#!html" in stripped.lower():
            has_html_processor = True

        for m in title_index_re.finditer(raw_line):
            macros.append(f"TitleIndex({m.group(1)})")

        for m in image_macro_re.finditer(raw_line):
            target = m.group(1).strip()
            if target.startswith(("http://", "https://")):
                att_url = target
            elif ":" in target and not target.startswith("wiki:"):
                # e.g. wiki:page:file.png
                segs = target.split(":")
                att_url = (
                    f"{base_root}/raw-attachment/wiki/{'/'.join(segs[-2:])}"
                    if base_root and len(segs) >= 2
                    else target
                )
            elif base_root and wiki_page:
                att_url = f"{base_root}/raw-attachment/wiki/{wiki_page}/{target}"
            else:
                att_url = target
            item = {"target": target, "url": att_url, "line": str(line_no)}
            attachments.append(item)
            links.append({"url": att_url, "text": target, "kind": "attachment"})

        for m in wiki_link_re.finditer(raw_line):
            wtarget = m.group(1).strip()
            wlabel = (m.group(2) or wtarget).strip()
            wurl = f"{base_root}/wiki/{wtarget.lstrip('/')}" if base_root else f"wiki:{wtarget}"
            links.append({"url": wurl, "text": wlabel, "kind": "wiki"})

        for m in http_link_re.finditer(raw_line):
            hurl = m.group(1).strip()
            hlabel = (m.group(2) or hurl).strip()
            links.append({"url": hurl, "text": hlabel, "kind": "external"})

        if in_code_block:
            continue

        m_trac = trac_heading_re.match(raw_line)
        if m_trac:
            level = len(m_trac.group(1))
            htext = m_trac.group(2).strip()
            # Strip trailing = if any remained before anchor
            htext = re.sub(r"\s*=+\s*$", "", htext).strip()
            headings.append(
                {
                    "level": level,
                    "heading": htext,
                    "anchor": m_trac.group(3) or "",
                    "line": line_no,
                }
            )
            continue

        m_md = md_heading_re.match(raw_line)
        if m_md:
            headings.append(
                {
                    "level": len(m_md.group(1)),
                    "heading": m_md.group(2).strip(),
                    "anchor": "",
                    "line": line_no,
                }
            )

    return {
        "headings": headings,
        "links": links,
        "attachments": attachments,
        "has_html_processor": has_html_processor,
        "dynamic_macros": macros,
    }


def detect_trac_version(html_text: str, page_url: str) -> tuple[int | None, str]:
    """Detect current Trac page revision number and title from rendered HTML."""
    extractor = _HtmlExtractor(base_url=page_url)
    extractor.feed(html_text)
    extractor.close()
    title = re.sub(r"\s+", " ", "".join(extractor.title_parts)).strip()
    page_path = urlsplit(page_url).path
    escaped_path = re.escape(page_path)

    for alt in extractor.alternate_links:
        if "x-trac-wiki" in alt.get("type", "").lower() or "format=txt" in alt.get("url", ""):
            alt_parts = urlsplit(alt["url"])
            if not alt_parts.path or alt_parts.path == page_path:
                q = dict(parse_qsl(alt_parts.query))
                if "version" in q and q["version"].isdigit():
                    return int(q["version"]), title

    patterns = [
        rf"{escaped_path}\?(?:[^\"'\s>]*&(?:amp;)?)?action=diff&(?:amp;)?version=(\d+)",
        r"\bVersion\s+(\d+)\s+\(modified\s+by\b",
        rf"{escaped_path}\?(?:format=txt&(?:amp;)?version=|version=)(\d+)",
        r"[?&]action=diff&(?:amp;)?version=(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, html_text, re.IGNORECASE)
        if m:
            return int(m.group(1)), title
    return None, title


def detect_mediawiki_revision(html_text: str) -> int | None:
    """Detect MediaWiki revision ID (wgCurRevisionId or oldid=) from rendered HTML."""
    patterns = [
        r'"wgCurRevisionId"\s*:\s*(\d+)',
        r'"wgRevisionId"\s*:\s*(\d+)',
        r"[?&]oldid=(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, html_text)
        if m and int(m.group(1)) > 0:
            return int(m.group(1))
    return None


class _RedirectTracker(urllib.request.HTTPRedirectHandler):
    """Record every redirect hop while preserving safe header policies."""

    def __init__(self, allow_loopback_http: bool = False) -> None:
        super().__init__()
        self.allow_loopback_http = allow_loopback_http
        self.chain: list[str] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if req.full_url.lower().startswith("https://") and newurl.lower().startswith("http://"):
            raise URLError(f"refusing HTTPS to HTTP downgrade redirect: {newurl}")
        try:
            norm = normalize_url(newurl, allow_loopback_http=self.allow_loopback_http)
        except UsageError as exc:
            raise URLError(str(exc)) from exc
        self.chain.append(norm)
        return super().redirect_request(req, fp, code, msg, headers, norm)


class SiteCache:
    """Content-addressed blob store + append-only URL snapshot log + polite HTTP fetcher."""

    def __init__(
        self,
        cache_dir: Path,
        namespace: str = "public",
        user_agent: str = DEFAULT_USER_AGENT,
        min_interval: float = DEFAULT_MIN_INTERVAL,
        timeout: float = DEFAULT_TIMEOUT,
        max_size_mb: float = DEFAULT_MAX_SIZE_MB,
        max_retries: int = DEFAULT_MAX_RETRIES,
        strict_robots: bool = False,
        allow_loopback_http: bool = False,
        allow_ephemeral_cache: bool = False,
    ) -> None:
        if namespace not in ("public", "private"):
            raise UsageError(f"invalid cache namespace {namespace!r} (expected 'public' or 'private')")
        self.base_dir = validate_cache_dir(cache_dir, allow_ephemeral=allow_ephemeral_cache)
        self.namespace = namespace
        self.root = self.base_dir / namespace
        self.blobs_dir = self.root / "blobs" / "sha256"
        self.snapshots_dir = self.root / "snapshots"
        self.derived_dir = self.root / "derived"
        self.locks_dir = self.root / "locks"
        self.tmp_dir = self.root / "tmp"
        self.user_agent = user_agent
        self.min_interval = max(0.0, float(min_interval))
        self.timeout = float(timeout)
        self.max_size_bytes = int(float(max_size_mb) * (1024 * 1024))
        self.max_retries = max(0, int(max_retries))
        self.strict_robots = strict_robots
        self.allow_loopback_http = allow_loopback_http

    def with_namespace(self, namespace: str) -> SiteCache:
        """Return a view of the cache rooted in the specified namespace ('public' or 'private')."""
        if namespace == self.namespace:
            return self
        return SiteCache(
            cache_dir=self.base_dir,
            namespace=namespace,
            user_agent=self.user_agent,
            min_interval=self.min_interval,
            timeout=self.timeout,
            max_size_mb=self.max_size_bytes / (1024 * 1024),
            max_retries=self.max_retries,
            strict_robots=self.strict_robots,
            allow_loopback_http=self.allow_loopback_http,
            allow_ephemeral_cache=True,
        )

    def blob_path(self, sha256: str) -> Path:
        digest = sha256.lower()
        if not SHA256_RE.match(digest):
            raise UsageError(f"invalid sha256 hex digest: {sha256!r}")
        return self.blobs_dir / digest[:2] / digest

    def has_blob(self, sha256: str) -> bool:
        path = self.blob_path(sha256)
        return not path.is_symlink() and path.is_file()

    def read_blob(self, sha256: str) -> bytes:
        path = self.blob_path(sha256)
        if path.is_symlink() or not path.is_file():
            raise CacheError(f"blob not found in {self.namespace} cache: {sha256}")
        return path.read_bytes()

    def store_blob_bytes(self, data: bytes, expected_sha256: str | None = None) -> tuple[str, Path]:
        """Write raw bytes atomically to the blob store as mode 0444."""
        digest = hashlib.sha256(data).hexdigest()
        if expected_sha256 is not None and digest != expected_sha256.lower():
            raise CacheError(
                f"sha256 mismatch: expected {expected_sha256.lower()}, got {digest}",
                fetch_status="failed",
            )
        dest = self.blob_path(digest)
        if not dest.is_symlink() and dest.is_file():
            return digest, dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix="blob-", dir=str(self.tmp_dir))
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(tmp_path, 0o444)
            os.replace(tmp_path, dest)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
        return digest, dest

    def import_file_by_copy(self, source_file: Path, expected_sha256: str | None = None) -> tuple[str, Path, int]:
        """Stream-copy a regular file into the 0444 blob store without mutating source_file's inode."""
        if source_file.is_symlink() or not source_file.is_file():
            raise CacheError(f"{source_file}: expected a regular non-symlink file")
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix="import-", dir=str(self.tmp_dir))
        tmp_path = Path(tmp_name)
        hasher = hashlib.sha256()
        total = 0
        try:
            with source_file.open("rb") as src, os.fdopen(fd, "wb") as dst:
                while True:
                    chunk = src.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    total += len(chunk)
                    hasher.update(chunk)
                    dst.write(chunk)
                dst.flush()
                os.fsync(dst.fileno())
            digest = hasher.hexdigest()
            if expected_sha256 is not None and digest != expected_sha256.lower():
                raise CacheError(
                    f"{source_file}: sha256 mismatch (expected {expected_sha256.lower()}, got {digest})"
                )
            dest = self.blob_path(digest)
            if not dest.is_symlink() and dest.is_file():
                tmp_path.unlink(missing_ok=True)
                return digest, dest, total
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(tmp_path, 0o444)
            os.replace(tmp_path, dest)
            return digest, dest, total
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    @staticmethod
    def _url_key(normalized_url: str) -> str:
        return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()

    def snapshot_log_path(self, normalized_url: str) -> Path:
        return self.snapshots_dir / f"{self._url_key(normalized_url)}.jsonl"

    def url_lock(self, normalized_url: str) -> FileLock:
        return FileLock(self.locks_dir / f"url-{self._url_key(normalized_url)}.lock")

    def host_lock_and_state(self, netloc: str) -> tuple[FileLock, Path]:
        host_key = hashlib.sha256(netloc.lower().encode("utf-8")).hexdigest()[:24]
        return (
            FileLock(self.locks_dir / f"host-{host_key}.lock"),
            self.locks_dir / f"host-{host_key}.state.json",
        )

    def read_snapshots(self, normalized_url: str) -> list[dict[str, Any]]:
        path = self.snapshot_log_path(normalized_url)
        if not path.is_file():
            return []
        records: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    def latest_ok_snapshot(self, normalized_url: str) -> dict[str, Any] | None:
        for record in reversed(self.read_snapshots(normalized_url)):
            if record.get("fetch_status") == "ok" and record.get("sha256"):
                if self.has_blob(record["sha256"]):
                    return record
        return None

    def append_snapshot(self, normalized_url: str, record: dict[str, Any]) -> None:
        path = self.snapshot_log_path(normalized_url)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, sort_keys=True) + "\n"
        with path.open("a", encoding="utf-8") as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())

    def _load_host_state(self, state_path: Path) -> dict[str, Any]:
        if not state_path.is_file():
            return {}
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_host_state(self, state_path: Path, state: dict[str, Any]) -> None:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
        os.replace(tmp, state_path)

    def _wait_for_host_slot(self, state_path: Path, extra_delay: float = 0.0) -> None:
        state = self._load_host_state(state_path)
        last_req = float(state.get("last_request_at", 0.0))
        interval = max(self.min_interval, float(state.get("crawl_delay", 0.0)), extra_delay)
        now = time.time()
        wait = (last_req + interval) - now
        if wait > 0:
            time.sleep(wait)
        state["last_request_at"] = time.time()
        self._save_host_state(state_path, state)

    def _check_robots_locked(self, normalized_url: str, state_path: Path) -> str | None:
        """Check robots.txt under the host lock. Return an optional robots_note or raise CacheError."""
        parts = urlsplit(normalized_url)
        robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
        state = self._load_host_state(state_path)
        now = time.time()
        robots_text = state.get("robots_text")
        robots_fetched_at = float(state.get("robots_fetched_at", 0.0))

        if robots_text is None or (now - robots_fetched_at) > 86400.0:
            self._wait_for_host_slot(state_path)
            req = urllib.request.Request(
                robots_url,
                headers={"User-Agent": self.user_agent, "Accept": "text/plain, */*"},
            )
            try:
                with urllib.request.urlopen(req, timeout=min(self.timeout, 15.0)) as resp:
                    raw = resp.read(512 * 1024)
                    robots_text = raw.decode("utf-8", errors="replace")
            except HTTPError as exc:
                if exc.code in (404, 410):
                    robots_text = ""
                elif exc.code in (401, 403):
                    robots_text = "User-agent: *\nDisallow: /\n"
                else:
                    robots_text = state.get("robots_text") or ""
            except (URLError, TimeoutError, OSError):
                robots_text = state.get("robots_text") or ""

            policy = RobotsPolicy(robots_text, self.user_agent)
            state = self._load_host_state(state_path)
            state["robots_text"] = robots_text
            state["robots_fetched_at"] = time.time()
            state["crawl_delay"] = policy.crawl_delay
            self._save_host_state(state_path, state)
        else:
            policy = RobotsPolicy(robots_text, self.user_agent)

        if policy.is_allowed(normalized_url):
            return None

        canonical_url, had_alt_format = strip_alternate_format_query(normalized_url)
        if had_alt_format and not self.strict_robots and policy.is_allowed(canonical_url):
            return (
                "canonical page path is allowed by robots.txt; "
                "query disallow matched raw-text alternate format"
            )

        raise CacheError(
            f"blocked by robots.txt on {parts.netloc}: {normalized_url}",
            fetch_status="blocked",
        )

    @staticmethod
    def _parse_retry_after(value: str | None, max_wait: float) -> float:
        if not value:
            return 0.0
        text = value.strip()
        if text.isdigit():
            return min(float(text), max_wait)
        try:
            dt = email.utils.parsedate_to_datetime(text)
            wait = dt.timestamp() - time.time()
            return max(0.0, min(wait, max_wait))
        except (TypeError, ValueError):
            return 0.0

    def _http_fetch_locked(
        self,
        normalized_url: str,
        state_path: Path,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> dict[str, Any]:
        """Perform a polite HTTP GET under the per-host lock, streaming bytes to a temp file."""
        robots_note = self._check_robots_locked(normalized_url, state_path)

        headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, identity",
        }
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        attempt = 0
        extra_delay = 0.0
        while True:
            self._wait_for_host_slot(state_path, extra_delay=extra_delay)
            tracker = _RedirectTracker(allow_loopback_http=self.allow_loopback_http)
            opener = urllib.request.build_opener(tracker)
            req = urllib.request.Request(normalized_url, headers=headers)
            try:
                with opener.open(req, timeout=self.timeout) as resp:
                    status = getattr(resp, "status", 200)
                    resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                    body = self._read_bounded_stream(resp, resp_headers)
                    final_url = normalize_url(
                        resp.geturl(), allow_loopback_http=self.allow_loopback_http
                    )
                    return {
                        "status": status,
                        "headers": resp_headers,
                        "body": body,
                        "final_url": final_url,
                        "redirects": tracker.chain,
                        "robots_note": robots_note,
                    }
            except HTTPError as exc:
                if exc.code == 304:
                    return {
                        "status": 304,
                        "headers": {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {},
                        "body": b"",
                        "final_url": normalized_url,
                        "redirects": tracker.chain,
                        "robots_note": robots_note,
                    }
                if exc.code in (429, 503) and attempt < self.max_retries:
                    attempt += 1
                    retry_header = exc.headers.get("Retry-After") if exc.headers else None
                    backoff = self._parse_retry_after(retry_header, self.timeout)
                    if backoff <= 0:
                        backoff = min(self.timeout, self.min_interval * (2 ** attempt))
                    extra_delay = backoff
                    continue
                raise CacheError(
                    f"HTTP {exc.code} fetching {normalized_url}: {exc.reason}",
                    fetch_status="blocked" if exc.code in (401, 403) else "failed",
                ) from exc
            except (URLError, TimeoutError, OSError) as exc:
                if attempt < self.max_retries:
                    attempt += 1
                    extra_delay = min(self.timeout, self.min_interval * (2 ** attempt))
                    continue
                raise CacheError(
                    f"network error fetching {normalized_url}: {exc}",
                    fetch_status="failed",
                ) from exc

    def _read_bounded_stream(self, resp: Any, headers: dict[str, str]) -> bytes:
        """Stream response body up to max_size_bytes and decode transport Content-Encoding."""
        declared = headers.get("content-length")
        if declared and declared.strip().isdigit() and int(declared.strip()) > self.max_size_bytes:
            raise CacheError(
                f"response Content-Length ({declared} bytes) exceeds limit ({self.max_size_bytes} bytes)",
                fetch_status="truncated",
            )
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = resp.read(CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > self.max_size_bytes:
                raise CacheError(
                    f"response body exceeds size limit ({self.max_size_bytes} bytes)",
                    fetch_status="truncated",
                )
            chunks.append(chunk)
        raw = b"".join(chunks)
        encoding = headers.get("content-encoding", "").strip().lower()
        if encoding in ("gzip", "x-gzip", "deflate"):
            headers.pop("content-length", None)
            return self._decompress_bounded(raw, encoding)
        return raw

    def _decompress_bounded(self, raw: bytes, encoding: str) -> bytes:
        """Decompress gzip or deflate stream with a strict output cap of max_size_bytes."""
        wbits_candidates = (
            [16 + zlib.MAX_WBITS]
            if encoding in ("gzip", "x-gzip")
            else [zlib.MAX_WBITS, -zlib.MAX_WBITS]
        )
        last_err: Exception | None = None
        for wbits in wbits_candidates:
            try:
                decomp = zlib.decompressobj(wbits)
                out = decomp.decompress(raw, self.max_size_bytes + 1)
                if len(out) > self.max_size_bytes or decomp.unconsumed_tail:
                    raise CacheError(
                        f"decompressed response body exceeds size limit ({self.max_size_bytes} bytes)",
                        fetch_status="truncated",
                    )
                tail = decomp.flush()
                if len(out) + len(tail) > self.max_size_bytes:
                    raise CacheError(
                        f"decompressed response body exceeds size limit ({self.max_size_bytes} bytes)",
                        fetch_status="truncated",
                    )
                return out + tail
            except CacheError:
                raise
            except (zlib.error, OSError) as exc:
                last_err = exc
        raise CacheError(
            f"invalid {encoding} response stream: {last_err}",
            fetch_status="truncated",
        ) from last_err

    def _verify_cached_blob(self, expected: str) -> Path:
        """Verify that a cached blob on disk still matches its expected SHA-256 digest."""
        bpath = self.blob_path(expected)
        with bpath.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise CacheError(
                f"corrupted cached blob at {bpath}: expected {expected}, got {actual}",
                fetch_status="failed",
            )
        return bpath

    @staticmethod
    def _safe_headers(headers: dict[str, str]) -> dict[str, str]:
        keep = ("content-type", "etag", "last-modified", "cache-control", "content-length")
        return {k: headers[k] for k in keep if k in headers}

    def get(
        self,
        url: str | None = None,
        *,
        sha256: str | None = None,
        max_age: float = DEFAULT_MAX_AGE,
        offline: bool = False,
        refresh: bool = False,
    ) -> dict[str, Any]:
        """Fetch or read a document in Pinned Mode (--sha256) or Latest Mode (url)."""
        if sha256 is not None:
            expected = sha256.lower()
            if not SHA256_RE.match(expected):
                raise UsageError(f"invalid --sha256 digest: {sha256!r}")
            if self.has_blob(expected):
                bpath = self._verify_cached_blob(expected)
                return {
                    "mode": "pinned",
                    "source": "cache",
                    "stale": False,
                    "sha256": expected,
                    "size": bpath.stat().st_size,
                    "blob_path": str(bpath),
                    "url": normalize_url(url, self.allow_loopback_http) if url else None,
                    "fetch_status": "ok",
                }
            if offline or not url:
                raise CacheError(
                    f"pinned blob {expected} is not in local cache"
                    + (" (--offline)" if offline else " and no retrieval URL was provided")
                )
            norm_url = normalize_url(url, self.allow_loopback_http)
            with self.url_lock(norm_url):
                if self.has_blob(expected):
                    bpath = self._verify_cached_blob(expected)
                    return {
                        "mode": "pinned",
                        "source": "cache",
                        "stale": False,
                        "sha256": expected,
                        "size": bpath.stat().st_size,
                        "blob_path": str(bpath),
                        "url": norm_url,
                        "fetch_status": "ok",
                    }
                fetched = self._fetch_and_record(norm_url, expected_sha256=expected)
                fetched["mode"] = "pinned"
                return fetched

        if not url:
            raise UsageError("either a URL or --sha256 is required")
        norm_url = normalize_url(url, self.allow_loopback_http)
        with self.url_lock(norm_url):
            latest = self.latest_ok_snapshot(norm_url)
            now = time.time()
            if latest is not None and not refresh:
                verified_ts = parse_iso_timestamp(
                    latest.get("verified_at") or latest["fetched_at"]
                )
                age = max(0.0, now - verified_ts)
                if offline or age <= max_age:
                    bpath = self.blob_path(latest["sha256"])
                    return {
                        "mode": "latest",
                        "source": "cache",
                        "stale": age > max_age,
                        "age_seconds": round(age, 1),
                        "fetched_at": latest["fetched_at"],
                        "verified_at": latest.get("verified_at", latest["fetched_at"]),
                        "sha256": latest["sha256"],
                        "size": latest["size"],
                        "blob_path": str(bpath),
                        "url": norm_url,
                        "final_url": latest.get("final_url", norm_url),
                        "headers": latest.get("headers", {}),
                        "fetch_status": "ok",
                    }
            if offline:
                raise CacheError(f"no cached snapshot for {norm_url} (--offline)")

            etag = latest.get("headers", {}).get("etag") if latest else None
            last_mod = latest.get("headers", {}).get("last-modified") if latest else None
            try:
                fetched = self._fetch_and_record(
                    norm_url, etag=etag, last_modified=last_mod, previous=latest
                )
                fetched["mode"] = "latest"
                return fetched
            except CacheError as exc:
                if latest is not None and exc.fetch_status == "failed":
                    verified_ts = parse_iso_timestamp(
                        latest.get("verified_at") or latest["fetched_at"]
                    )
                    age = max(0.0, time.time() - verified_ts)
                    bpath = self.blob_path(latest["sha256"])
                    return {
                        "mode": "latest",
                        "source": "cache-fallback",
                        "stale": True,
                        "stale_reason": str(exc),
                        "age_seconds": round(age, 1),
                        "fetched_at": latest["fetched_at"],
                        "verified_at": latest.get("verified_at", latest["fetched_at"]),
                        "sha256": latest["sha256"],
                        "size": latest["size"],
                        "blob_path": str(bpath),
                        "url": norm_url,
                        "final_url": latest.get("final_url", norm_url),
                        "headers": latest.get("headers", {}),
                        "fetch_status": "ok",
                    }
                raise

    def _fetch_and_record(
        self,
        norm_url: str,
        *,
        expected_sha256: str | None = None,
        etag: str | None = None,
        last_modified: str | None = None,
        previous: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        parts = urlsplit(norm_url)
        host_lock, state_path = self.host_lock_and_state(parts.netloc)
        with host_lock:
            resp = self._http_fetch_locked(
                norm_url, state_path, etag=etag, last_modified=last_modified
            )

        now_iso = utc_now_iso()
        if resp["status"] == 304 and previous is not None:
            merged_headers = dict(previous.get("headers", {}))
            merged_headers.update(self._safe_headers(resp["headers"]))
            record = {
                "requested_url": norm_url,
                "normalized_url": norm_url,
                "final_url": previous.get("final_url", norm_url),
                "redirects": previous.get("redirects", []),
                "status": 304,
                "fetch_status": "ok",
                "headers": merged_headers,
                "fetched_at": previous["fetched_at"],
                "verified_at": now_iso,
                "sha256": previous["sha256"],
                "size": previous["size"],
            }
            if resp.get("robots_note"):
                record["robots_note"] = resp["robots_note"]
            self.append_snapshot(norm_url, record)
            bpath = self.blob_path(previous["sha256"])
            return {
                "source": "revalidated-304",
                "stale": False,
                "age_seconds": 0.0,
                "fetched_at": previous["fetched_at"],
                "verified_at": now_iso,
                "sha256": previous["sha256"],
                "size": previous["size"],
                "blob_path": str(bpath),
                "url": norm_url,
                "final_url": record["final_url"],
                "headers": merged_headers,
                "fetch_status": "ok",
                "robots_note": resp.get("robots_note"),
            }

        body: bytes = resp["body"]
        f_status, err_msg = detect_soft_error(
            resp["status"], resp["headers"], body, norm_url
        )
        if f_status != "ok":
            bad_record = {
                "requested_url": norm_url,
                "normalized_url": norm_url,
                "final_url": resp["final_url"],
                "redirects": resp["redirects"],
                "status": resp["status"],
                "fetch_status": f_status,
                "error": err_msg,
                "headers": self._safe_headers(resp["headers"]),
                "fetched_at": now_iso,
                "size": len(body),
            }
            self.append_snapshot(norm_url, bad_record)
            raise CacheError(
                f"soft error ({f_status}) from {norm_url}: {err_msg}",
                fetch_status=f_status,
            )

        actual_sha = hashlib.sha256(body).hexdigest()
        if expected_sha256 is not None and actual_sha != expected_sha256.lower():
            bad_record = {
                "requested_url": norm_url,
                "normalized_url": norm_url,
                "final_url": resp["final_url"],
                "redirects": resp["redirects"],
                "status": resp["status"],
                "fetch_status": "failed",
                "error": f"sha256 mismatch: expected {expected_sha256.lower()}, got {actual_sha}",
                "headers": self._safe_headers(resp["headers"]),
                "fetched_at": now_iso,
                "sha256": actual_sha,
                "size": len(body),
            }
            self.append_snapshot(norm_url, bad_record)
            raise CacheError(
                f"sha256 mismatch for {norm_url}: expected {expected_sha256.lower()}, got {actual_sha}",
                fetch_status="failed",
            )

        digest, bpath = self.store_blob_bytes(body, expected_sha256=expected_sha256)
        safe_hdrs = self._safe_headers(resp["headers"])
        record = {
            "requested_url": norm_url,
            "normalized_url": norm_url,
            "final_url": resp["final_url"],
            "redirects": resp["redirects"],
            "status": resp["status"],
            "fetch_status": "ok",
            "headers": safe_hdrs,
            "fetched_at": now_iso,
            "verified_at": now_iso,
            "sha256": digest,
            "size": len(body),
        }
        if resp.get("robots_note"):
            record["robots_note"] = resp["robots_note"]
        self.append_snapshot(norm_url, record)
        return {
            "source": "network",
            "stale": False,
            "age_seconds": 0.0,
            "fetched_at": now_iso,
            "verified_at": now_iso,
            "sha256": digest,
            "size": len(body),
            "blob_path": str(bpath),
            "url": norm_url,
            "final_url": resp["final_url"],
            "headers": safe_hdrs,
            "fetch_status": "ok",
            "robots_note": resp.get("robots_note"),
        }

    def derive_view(self, sha256: str, context_url: str = "") -> dict[str, Any]:
        """Return or lazily compute derived reader view (text, headings, links, attachments)."""
        digest = sha256.lower()
        out_dir = self.derived_dir / digest / EXTRACTOR_VERSION
        meta_path = out_dir / "meta.json"
        view_path = out_dir / "view.md"
        if meta_path.is_file() and view_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["text"] = view_path.read_text(encoding="utf-8")
            return meta

        raw = self.read_blob(digest)
        if raw.startswith(b"%PDF-"):
            meta = {
                "sha256": digest,
                "kind": "pdf",
                "headings": [],
                "links": [],
                "attachments": [],
                "has_html_processor": False,
                "dynamic_macros": [],
            }
            text = f"[PDF document blob {digest} ({len(raw)} bytes)]"
        else:
            decoded = raw.decode("utf-8", errors="replace")
            sample = decoded[:2048].lstrip().lower()
            is_html = sample.startswith(("<!doctype html", "<html", "<?xml")) or (
                "<body" in sample or "<head" in sample
            )
            if is_html:
                ext = _HtmlExtractor(base_url=context_url)
                ext.feed(decoded)
                ext.close()
                title = re.sub(r"\s+", " ", "".join(ext.title_parts)).strip()
                meta = {
                    "sha256": digest,
                    "kind": "html",
                    "title": title,
                    "headings": ext.headings,
                    "links": ext.links,
                    "alternate_links": ext.alternate_links,
                    "attachments": [l for l in ext.links if l.get("kind") == "image"],
                    "has_html_processor": False,
                    "dynamic_macros": [],
                }
                text = "\n".join(ext.text_lines)
            else:
                info = extract_wikitext_info(decoded, page_url=context_url)
                meta = {
                    "sha256": digest,
                    "kind": "wikitext",
                    "title": info["headings"][0]["heading"] if info["headings"] else "",
                    "headings": info["headings"],
                    "links": info["links"],
                    "attachments": info["attachments"],
                    "has_html_processor": info["has_html_processor"],
                    "dynamic_macros": info["dynamic_macros"],
                }
                text = decoded.replace("\r\n", "\n")

        out_dir.mkdir(parents=True, exist_ok=True)
        view_path.write_text(text, encoding="utf-8")
        meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
        result = dict(meta)
        result["text"] = text
        return result

    def pin(
        self,
        url: str,
        *,
        name: str | None = None,
        title: str | None = None,
        doc_class: str = "doc",
        offline: bool = False,
        max_age: float = DEFAULT_MAX_AGE,
    ) -> dict[str, Any]:
        """Discover immutable revision (Trac, MediaWiki, or static HTTP), pin raw bytes, and emit YAML."""
        norm_url = normalize_url(url, self.allow_loopback_http)
        parts = urlsplit(norm_url)
        query_map = dict(parse_qsl(parts.query, keep_blank_values=True))

        # Case 1: Trac wiki URL (/wiki/<page>)
        if "/wiki/" in parts.path:
            page_slug = parts.path.split("/wiki/", 1)[1].strip("/")
            base_page_url = urlunsplit((parts.scheme, parts.netloc, f"/wiki/{page_slug}", "", ""))
            version_num: int | None = None
            discovered_title = ""
            html_discovery_sha: str | None = None
            expanded_links: list[dict[str, str]] = []

            if "version" in query_map and query_map["version"].isdigit():
                version_num = int(query_map["version"])

            if version_num is None or query_map.get("format") != "txt":
                html_target = (
                    f"{base_page_url}?version={version_num}"
                    if version_num is not None
                    else base_page_url
                )
                html_res = self.get(html_target, max_age=max_age, offline=offline)
                html_discovery_sha = html_res["sha256"]
                html_text = self.read_blob(html_discovery_sha).decode("utf-8", errors="replace")
                detected_ver, discovered_title = detect_trac_version(html_text, html_target)
                if version_num is None:
                    version_num = detected_ver
                html_view = self.derive_view(html_discovery_sha, context_url=html_target)
                expanded_links = html_view.get("links", [])

            if version_num is None:
                raise CacheError(
                    f"could not determine immutable Trac page revision from {base_page_url}; "
                    "pass an explicit ?version=N URL"
                )
            canonical_url = f"{base_page_url}?version={version_num}"
            retrieval_url = f"{base_page_url}?version={version_num}&format=txt"
            revision_str = f"version {version_num}"
            txt_res = self.get(retrieval_url, max_age=max_age, offline=offline)
            pinned_sha = txt_res["sha256"]
            txt_view = self.derive_view(pinned_sha, context_url=canonical_url)

            doc_name = name or ("wiki-" + re.sub(r"[^a-z0-9]+", "-", page_slug.lower()).strip("-"))
            doc_title = title or f"Wiki page {page_slug}"
            yaml_entry = self._format_document_yaml(
                name=doc_name,
                doc_class=doc_class,
                title=doc_title,
                revision=revision_str,
                url=canonical_url,
                retrieval_url=retrieval_url,
                sha256=pinned_sha,
            )
            return {
                "adapter": "trac",
                "name": doc_name,
                "class": doc_class,
                "title": doc_title,
                "discovered_html_title": discovered_title,
                "revision": revision_str,
                "url": canonical_url,
                "retrieval_url": retrieval_url,
                "sha256": pinned_sha,
                "size": txt_res["size"],
                "discovery_html_sha256": html_discovery_sha,
                "headings": txt_view["headings"],
                "attachments": txt_view["attachments"],
                "has_html_processor": txt_view["has_html_processor"],
                "dynamic_macros": txt_view["dynamic_macros"],
                "expanded_html_links_count": len(expanded_links),
                "yaml": yaml_entry,
            }

        # Case 2: MediaWiki or generic HTTP resource
        res = self.get(norm_url, max_age=max_age, offline=offline)
        raw_bytes = self.read_blob(res["sha256"])
        if not raw_bytes.startswith(b"%PDF-"):
            sample_text = raw_bytes[:65536].decode("utf-8", errors="replace")
            mw_rev = detect_mediawiki_revision(sample_text)
            if mw_rev is not None and query_map.get("action") != "raw":
                base_mw = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
                canonical_url = f"{base_mw}?oldid={mw_rev}"
                retrieval_url = f"{base_mw}?oldid={mw_rev}&action=raw"
                raw_res = self.get(retrieval_url, max_age=max_age, offline=offline)
                doc_name = name or re.sub(
                    r"[^a-z0-9]+", "-", Path(parts.path).name.lower() or "wiki-page"
                ).strip("-")
                doc_title = title or f"Wiki page {Path(parts.path).name}"
                revision_str = f"oldid {mw_rev}"
                yaml_entry = self._format_document_yaml(
                    name=doc_name,
                    doc_class=doc_class,
                    title=doc_title,
                    revision=revision_str,
                    url=canonical_url,
                    retrieval_url=retrieval_url,
                    sha256=raw_res["sha256"],
                )
                view = self.derive_view(raw_res["sha256"], context_url=canonical_url)
                return {
                    "adapter": "mediawiki",
                    "name": doc_name,
                    "class": doc_class,
                    "title": doc_title,
                    "revision": revision_str,
                    "url": canonical_url,
                    "retrieval_url": retrieval_url,
                    "sha256": raw_res["sha256"],
                    "size": raw_res["size"],
                    "headings": view["headings"],
                    "attachments": view["attachments"],
                    "yaml": yaml_entry,
                }

        view = self.derive_view(res["sha256"], context_url=norm_url)
        slug = Path(parts.path).stem.lower() or parts.hostname or "document"
        doc_name = name or re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
        doc_title = title or view.get("title") or doc_name
        yaml_entry = self._format_document_yaml(
            name=doc_name,
            doc_class=doc_class,
            title=doc_title,
            revision=None,
            url=norm_url,
            retrieval_url=None,
            sha256=res["sha256"],
        )
        return {
            "adapter": "generic",
            "name": doc_name,
            "class": doc_class,
            "title": doc_title,
            "revision": None,
            "url": norm_url,
            "retrieval_url": None,
            "sha256": res["sha256"],
            "size": res["size"],
            "headings": view["headings"],
            "attachments": view["attachments"],
            "yaml": yaml_entry,
        }

    @staticmethod
    def _format_document_yaml(
        *,
        name: str,
        doc_class: str,
        title: str,
        revision: str | None,
        url: str,
        retrieval_url: str | None,
        sha256: str,
    ) -> str:
        lines = [
            f"- name: {name}",
            f"  class: {doc_class}",
            f"  title: {title}",
        ]
        if revision:
            lines.append(f"  revision: {revision}")
        lines.append(f"  url: {url}")
        if retrieval_url:
            lines.append("  retrieval:")
            lines.append(f"  - url: {retrieval_url}")
        lines.append(f"  sha256: {sha256}")
        return "\n".join(lines)

    def resolve_target_to_blob(
        self, target: str, *, offline: bool = False, max_age: float = DEFAULT_MAX_AGE
    ) -> tuple[str, str]:
        """Resolve a sha256 digest or URL to (sha256, context_url)."""
        if SHA256_RE.match(target.lower()):
            digest = target.lower()
            if not self.has_blob(digest):
                raise CacheError(f"blob {digest} is not in local cache")
            return digest, ""
        res = self.get(target, max_age=max_age, offline=offline)
        return res["sha256"], res.get("final_url") or res.get("url") or ""

    def info(self, target: str) -> dict[str, Any]:
        """Return snapshot history for a URL or blob info for a sha256 digest."""
        if SHA256_RE.match(target.lower()):
            digest = target.lower()
            exists = self.has_blob(digest)
            bpath = self.blob_path(digest)
            size = bpath.stat().st_size if exists else None
            referencing_urls: list[str] = []
            if self.snapshots_dir.is_dir():
                for snap_file in sorted(self.snapshots_dir.glob("*.jsonl")):
                    for line in snap_file.read_text(encoding="utf-8").splitlines():
                        if not line.strip():
                            continue
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if rec.get("sha256") == digest:
                            u = rec.get("normalized_url") or rec.get("requested_url")
                            if u and u not in referencing_urls:
                                referencing_urls.append(u)
            return {
                "kind": "blob",
                "namespace": self.namespace,
                "sha256": digest,
                "exists": exists,
                "size": size,
                "blob_path": str(bpath) if exists else None,
                "referencing_urls": referencing_urls,
            }

        norm_url = normalize_url(target, self.allow_loopback_http)
        snapshots = self.read_snapshots(norm_url)
        latest = self.latest_ok_snapshot(norm_url)
        age = None
        if latest:
            verified_ts = parse_iso_timestamp(latest.get("verified_at") or latest["fetched_at"])
            age = round(max(0.0, time.time() - verified_ts), 1)
        return {
            "kind": "url",
            "namespace": self.namespace,
            "url": norm_url,
            "snapshots_count": len(snapshots),
            "latest_ok": latest,
            "latest_age_seconds": age,
            "snapshots": snapshots,
        }

    def verify_store(self) -> dict[str, Any]:
        """Re-hash every blob in blobs/sha256/ to detect corruption."""
        checked = 0
        corrupted: list[dict[str, str]] = []
        if self.blobs_dir.is_dir():
            for path in sorted(self.blobs_dir.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                checked += 1
                expected = path.name.lower()
                with path.open("rb") as stream:
                    actual = hashlib.file_digest(stream, "sha256").hexdigest()
                if actual != expected:
                    corrupted.append(
                        {"path": str(path), "expected": expected, "actual": actual}
                    )
        return {
            "ok": not corrupted,
            "namespace": self.namespace,
            "blobs_checked": checked,
            "corrupted": corrupted,
        }


def load_yaml_file(path: Path) -> dict[str, Any]:
    """Load a YAML file using sibling specload if available, else PyYAML."""
    if not path.is_file():
        raise UsageError(f"{path}: file not found")
    spec_scripts = Path(__file__).resolve().parents[2] / "spec-format" / "scripts"
    if (spec_scripts / "specload.py").is_file():
        if str(spec_scripts) not in sys.path:
            sys.path.insert(0, str(spec_scripts))
        try:
            import specload  # type: ignore

            loaded = specload.load_strict(path)
            data = loaded.data if hasattr(loaded, "data") else loaded
            if not isinstance(data, dict):
                raise CacheError(f"{path}: expected a YAML mapping at top level")
            return data
        except ImportError:
            pass
        except Exception as exc:
            if exc.__class__.__name__ == "LoadError":
                raise CacheError(f"{path}: invalid YAML: {exc}") from exc
            raise
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise PreconditionError(
            f"missing precondition: PyYAML is required to read {path} ({exc})"
        ) from exc
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CacheError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise CacheError(f"{path}: expected a YAML mapping at top level")
    return data


def detect_root_layer(spec_files: list[Path], explicit_root: Path | None) -> str | None:
    """Detect the spec root's layer ('public', etc.) from board-specs.yaml if present."""
    candidates: list[Path] = []
    if explicit_root is not None:
        candidates.append(explicit_root)
    for f in spec_files:
        for parent in (f.resolve().parent, *f.resolve().parents):
            if (parent / "board-specs.yaml").is_file():
                candidates.append(parent)
                break
    for root in candidates:
        marker_path = root / "board-specs.yaml"
        if marker_path.is_file():
            data = load_yaml_file(marker_path)
            layer = data.get("layer")
            if isinstance(layer, str):
                return layer
    return None


def iter_spec_documents(spec_files: list[Path]) -> list[tuple[Path, dict[str, Any]]]:
    """Extract document entries from spec.yaml or corpus.yaml files."""
    entries: list[tuple[Path, dict[str, Any]]] = []
    for path in spec_files:
        data = load_yaml_file(path)
        docs = data.get("resources", {}).get("documents")
        if docs is None and "documents" in data:
            docs = data.get("documents")
        if not isinstance(docs, list):
            continue
        for doc in docs:
            if isinstance(doc, dict) and isinstance(doc.get("name"), str):
                entries.append((path, doc))
    return entries


def pick_fetch_url(doc: dict[str, Any]) -> str | None:
    """Select the primary retrieval URL (or canonical url fallback) for a document entry."""
    retrieval = doc.get("retrieval")
    if isinstance(retrieval, list):
        for item in retrieval:
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                return item["url"]
    url = doc.get("url")
    return url if isinstance(url, str) else None


def materialize_documents(
    cache: SiteCache,
    spec_files: list[Path],
    docs_dir: Path,
    *,
    root: Path | None = None,
    offline: bool = False,
    allow_private: bool = False,
) -> dict[str, Any]:
    """Populate docs_dir/<doc-name> from spec resources.documents[], adopting valid existing files by copy."""
    if docs_dir.exists() and not docs_dir.is_dir():
        raise UsageError(f"--docs-dir {docs_dir}: not a directory")
    layer = detect_root_layer(spec_files, root)
    entries = iter_spec_documents(spec_files)

    results: list[dict[str, Any]] = []
    errors: list[str] = []
    adopted = 0
    materialized = 0
    skipped = 0

    by_name: dict[str, tuple[Path, dict[str, Any]]] = {}
    for spec_path, doc in entries:
        name = doc["name"]
        if "/" in name or name in (".", ".."):
            errors.append(f"{spec_path}: invalid document name {name!r}")
            continue
        if name in by_name:
            prev_sha = by_name[name][1].get("sha256")
            cur_sha = doc.get("sha256")
            if prev_sha and cur_sha and prev_sha != cur_sha:
                errors.append(
                    f"conflicting sha256 pins for document {name!r}: {prev_sha} vs {cur_sha}"
                )
                continue
        if "sha256" in doc or name not in by_name:
            by_name[name] = (spec_path, doc)

    docs_dir.mkdir(parents=True, exist_ok=True)

    for name, (spec_path, doc) in by_name.items():
        access = doc.get("access", "public")
        is_private = access in ("private", "nda", "restricted")
        if is_private and layer == "public" and not allow_private:
            msg = (
                f"{spec_path}: document {name!r} has access={access!r} "
                "and cannot be materialized in a public spec root"
            )
            errors.append(msg)
            results.append({"name": name, "status": "error", "error": msg})
            continue

        expected_sha = doc.get("sha256")
        if not expected_sha:
            skipped += 1
            results.append(
                {"name": name, "status": "skipped", "reason": "document has no sha256 pin"}
            )
            continue
        expected_sha = str(expected_sha).lower()
        if not SHA256_RE.match(expected_sha):
            msg = f"{spec_path}: document {name!r} has invalid sha256 {expected_sha!r}"
            errors.append(msg)
            results.append({"name": name, "status": "error", "error": msg})
            continue

        ns_cache = cache.with_namespace("private" if is_private else "public")
        target_path = docs_dir / name

        if target_path.exists() or target_path.is_symlink():
            if target_path.is_dir() and not target_path.is_symlink():
                msg = f"{target_path}: target is a directory, expected a regular file"
                errors.append(msg)
                results.append({"name": name, "status": "error", "error": msg})
                continue
            if not target_path.is_symlink() and target_path.is_file():
                with target_path.open("rb") as stream:
                    current_digest = hashlib.file_digest(stream, "sha256").hexdigest()
                if current_digest == expected_sha:
                    # Adopt valid existing file into the blob store by copy so we do not
                    # chmod 0444 an external inode shared with another repository.
                    if not ns_cache.has_blob(expected_sha):
                        ns_cache.import_file_by_copy(target_path, expected_sha256=expected_sha)
                        action = "adopted-into-cache"
                        adopted += 1
                    else:
                        action = "already-valid"
                    materialized += 1
                    results.append(
                        {
                            "name": name,
                            "status": "ok",
                            "action": action,
                            "sha256": expected_sha,
                            "path": str(target_path),
                            "namespace": ns_cache.namespace,
                        }
                    )
                    continue

        fetch_url = pick_fetch_url(doc)
        try:
            res = ns_cache.get(
                fetch_url,
                sha256=expected_sha,
                offline=offline,
            )
            blob_file = Path(res["blob_path"])
            if target_path.exists() or target_path.is_symlink():
                target_path.unlink()
            link_mode = "hardlink"
            try:
                os.link(blob_file, target_path)
            except OSError:
                shutil.copyfile(blob_file, target_path)
                link_mode = "copy"

            with target_path.open("rb") as stream:
                verify_digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if verify_digest != expected_sha:
                raise CacheError(
                    f"{target_path}: post-materialization sha256 mismatch "
                    f"(expected {expected_sha}, got {verify_digest})"
                )
            materialized += 1
            results.append(
                {
                    "name": name,
                    "status": "ok",
                    "action": f"materialized-{link_mode}",
                    "source": res["source"],
                    "sha256": expected_sha,
                    "path": str(target_path),
                    "namespace": ns_cache.namespace,
                }
            )
        except (CacheError, UsageError) as exc:
            msg = f"{name}: {exc}"
            errors.append(msg)
            results.append({"name": name, "status": "error", "error": str(exc)})

    return {
        "ok": not errors,
        "docs_dir": str(docs_dir),
        "materialized": materialized,
        "adopted": adopted,
        "skipped": skipped,
        "errors": errors,
        "documents": results,
    }


def prefetch_documents(
    cache: SiteCache,
    spec_files: list[Path],
    *,
    offline: bool = False,
) -> dict[str, Any]:
    """Fetch and verify all sha256-pinned documents in spec_files into the blob store."""
    entries = iter_spec_documents(spec_files)
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    fetched = 0
    skipped = 0

    seen: set[tuple[str, str]] = set()
    for spec_path, doc in entries:
        name = doc["name"]
        expected_sha = doc.get("sha256")
        if not expected_sha:
            skipped += 1
            results.append(
                {"name": name, "status": "skipped", "reason": "document has no sha256 pin"}
            )
            continue
        expected_sha = str(expected_sha).lower()
        access = doc.get("access", "public")
        ns = "private" if access in ("private", "nda", "restricted") else "public"
        if (ns, expected_sha) in seen:
            continue
        seen.add((ns, expected_sha))
        ns_cache = cache.with_namespace(ns)
        fetch_url = pick_fetch_url(doc)
        try:
            res = ns_cache.get(fetch_url, sha256=expected_sha, offline=offline)
            fetched += 1
            results.append(
                {
                    "name": name,
                    "status": "ok",
                    "source": res["source"],
                    "sha256": expected_sha,
                    "size": res["size"],
                    "namespace": ns,
                }
            )
        except (CacheError, UsageError) as exc:
            msg = f"{spec_path}:{name}: {exc}"
            errors.append(msg)
            results.append({"name": name, "status": "error", "error": str(exc)})

    return {
        "ok": not errors,
        "prefetched": fetched,
        "skipped": skipped,
        "errors": errors,
        "documents": results,
    }


def gc_blobs(
    cache: SiteCache,
    spec_files: list[Path],
    *,
    keep_latest_snapshots: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Evict blobs not referenced by the given spec files (and optional latest snapshots)."""
    if not spec_files:
        raise UsageError("gc requires at least one --spec file or --root directory")

    pinned_hashes: set[str] = set()
    for _, doc in iter_spec_documents(spec_files):
        sha = doc.get("sha256")
        if isinstance(sha, str) and SHA256_RE.match(sha.lower()):
            pinned_hashes.add(sha.lower())

    if keep_latest_snapshots and cache.snapshots_dir.is_dir():
        for snap_file in cache.snapshots_dir.glob("*.jsonl"):
            lines = [l for l in snap_file.read_text(encoding="utf-8").splitlines() if l.strip()]
            for line in reversed(lines):
                rec = json.loads(line)
                if rec.get("fetch_status") == "ok" and rec.get("sha256"):
                    pinned_hashes.add(rec["sha256"].lower())
                    break

    kept: list[str] = []
    removed: list[str] = []
    bytes_freed = 0

    if cache.blobs_dir.is_dir():
        for path in sorted(cache.blobs_dir.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            digest = path.name.lower()
            if digest in pinned_hashes:
                kept.append(digest)
            else:
                size = path.stat().st_size
                bytes_freed += size
                removed.append(digest)
                if not dry_run:
                    try:
                        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
                    except OSError:
                        pass
                    path.unlink(missing_ok=True)
                    derived_sub = cache.derived_dir / digest
                    if derived_sub.is_dir():
                        shutil.rmtree(derived_sub, ignore_errors=True)

    return {
        "ok": True,
        "namespace": cache.namespace,
        "dry_run": dry_run,
        "pinned_roots_count": len(pinned_hashes),
        "kept_count": len(kept),
        "removed_count": len(removed),
        "bytes_freed": bytes_freed,
        "removed": removed,
    }


def collect_specs_from_args(specs: list[Path], roots: list[Path]) -> list[Path]:
    """Expand --spec files and --root directories into a list of YAML files."""
    files: list[Path] = list(specs)
    for root in roots:
        if not root.is_dir():
            raise UsageError(f"--root {root}: not a directory")
        files.extend(sorted(root.rglob("*.spec.yaml")))
        files.extend(sorted(root.rglob("*.facts.yaml")))
        corpus = root / "corpus.yaml"
        if corpus.is_file():
            files.append(corpus)
    if not files:
        raise UsageError("no spec or corpus YAML files supplied")
    return files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="site_cache.py",
        description=__doc__.splitlines()[0],
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="cache root directory (default: $SITE_CACHE_DIR or ~/.cache/site-cache)",
    )
    common.add_argument(
        "--namespace",
        choices=("public", "private"),
        default="public",
        help="cache namespace (default: public)",
    )
    common.add_argument(
        "--user-agent",
        default=os.environ.get("SITE_CACHE_USER_AGENT", DEFAULT_USER_AGENT),
        help="HTTP User-Agent string",
    )
    common.add_argument(
        "--min-interval",
        type=float,
        default=DEFAULT_MIN_INTERVAL,
        help="minimum seconds between requests to the same host (default: 2.0)",
    )
    common.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="per-request HTTP timeout in seconds (default: 30.0)",
    )
    common.add_argument(
        "--max-size-mb",
        type=float,
        default=DEFAULT_MAX_SIZE_MB,
        help="maximum response body size in MiB (default: 200.0)",
    )
    common.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="retries on 429/503 or transient network error (default: 2)",
    )
    common.add_argument(
        "--strict-robots",
        action="store_true",
        help="enforce robots.txt query-string disallows even on raw-text alternate formats",
    )
    common.add_argument(
        "--allow-loopback-http",
        action="store_true",
        help="allow http://127.0.0.1 and http://localhost for local test servers",
    )
    common.add_argument(
        "--allow-ephemeral-cache",
        action="store_true",
        help="allow --cache-dir inside the system temp directory (for tests)",
    )
    common.add_argument(
        "--json",
        action="store_true",
        help="emit structured JSON output",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_get = sub.add_parser(
        "get",
        parents=[common],
        help="fetch or read a URL in latest mode, or by immutable --sha256 pin",
    )
    p_get.add_argument("url", nargs="?", help="HTTPS URL to fetch or read")
    p_get.add_argument("--sha256", help="expected 64-hex SHA-256 digest (Pinned Mode)")
    p_get.add_argument(
        "--max-age",
        default="24h",
        help="maximum snapshot age in Latest Mode, e.g. 3600, 30m, 24h, 7d (default: 24h)",
    )
    p_get.add_argument("--offline", action="store_true", help="serve from local cache only")
    p_get.add_argument("--refresh", action="store_true", help="force conditional revalidation")
    mode_group = p_get.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--raw",
        action="store_true",
        help="write exact cached bytes to stdout (or --out)",
    )
    mode_group.add_argument(
        "--text",
        action="store_true",
        help="print derived clean Markdown/text view to stdout",
    )
    p_get.add_argument("--out", type=Path, help="write raw bytes to this file path")

    p_pin = sub.add_parser(
        "pin",
        parents=[common],
        help="discover immutable page revision, pin bytes, and print Spec Format 2 YAML",
    )
    p_pin.add_argument("url", help="HTTPS URL of the wiki page or document")
    p_pin.add_argument("--name", help="document name for resources.documents[].name")
    p_pin.add_argument("--title", help="document title override")
    p_pin.add_argument("--class", dest="doc_class", default="doc", help="document class (default: doc)")
    p_pin.add_argument("--max-age", default="24h", help="maximum discovery snapshot age (default: 24h)")
    p_pin.add_argument("--offline", action="store_true", help="use local cache only")

    p_links = sub.add_parser(
        "links",
        parents=[common],
        help="list outbound links and attachment references from a cached page",
    )
    p_links.add_argument("target", help="cached URL or 64-hex SHA-256 digest")
    p_links.add_argument("--filter", help="case-insensitive substring or regex filter on URL/text")
    p_links.add_argument("--max-age", default="24h", help="maximum snapshot age (default: 24h)")
    p_links.add_argument("--offline", action="store_true", help="use local cache only")

    p_headings = sub.add_parser(
        "headings",
        parents=[common],
        help="extract headings from a cached document as a reading and locator aid",
    )
    p_headings.add_argument("target", help="cached URL or 64-hex SHA-256 digest")
    p_headings.add_argument("--max-age", default="24h", help="maximum snapshot age (default: 24h)")
    p_headings.add_argument("--offline", action="store_true", help="use local cache only")

    p_info = sub.add_parser(
        "info",
        parents=[common],
        help="display snapshot history for a URL or metadata for a blob SHA-256",
    )
    p_info.add_argument("target", help="URL or 64-hex SHA-256 digest")

    p_prefetch = sub.add_parser(
        "prefetch",
        parents=[common],
        help="politely fetch and verify all pinned documents in Spec Format 2 YAML files",
    )
    p_prefetch.add_argument("files", nargs="+", type=Path, help="spec or corpus YAML files")
    p_prefetch.add_argument("--offline", action="store_true", help="verify local cache only")

    p_mat = sub.add_parser(
        "materialize",
        parents=[common],
        help="populate --docs-dir with hash-verified hardlinks/copies for spec.py resolve",
    )
    p_mat.add_argument("files", nargs="+", type=Path, help="spec or corpus YAML files")
    p_mat.add_argument(
        "--docs-dir",
        type=Path,
        required=True,
        help="target directory for materialized DIR/<doc-name> files",
    )
    p_mat.add_argument("--root", type=Path, help="optional spec root directory")
    p_mat.add_argument("--offline", action="store_true", help="use local cache and existing files only")
    p_mat.add_argument(
        "--allow-private",
        action="store_true",
        help="allow materializing private/nda/restricted documents in a public root",
    )

    p_verify = sub.add_parser(
        "verify",
        parents=[common],
        help="re-hash cached blobs (and optional --docs-dir files) to detect corruption",
    )
    p_verify.add_argument("--docs-dir", type=Path, help="optional docs-dir to verify against --spec")
    p_verify.add_argument("--spec", action="append", type=Path, default=[], help="spec YAML file(s)")

    p_gc = sub.add_parser(
        "gc",
        parents=[common],
        help="remove blobs not referenced by the given --spec files or --root directories",
    )
    p_gc.add_argument("--spec", action="append", type=Path, default=[], help="spec or corpus YAML file")
    p_gc.add_argument("--root", action="append", type=Path, default=[], help="spec root directory")
    p_gc.add_argument(
        "--no-keep-latest",
        action="store_true",
        help="also evict unpinned blobs even if they are the latest snapshot of a URL",
    )
    p_gc.add_argument("--dry-run", action="store_true", help="report blobs that would be removed")

    return parser


def make_cache(args: argparse.Namespace) -> SiteCache:
    cdir = args.cache_dir if args.cache_dir is not None else default_cache_dir()
    return SiteCache(
        cache_dir=cdir,
        namespace=args.namespace,
        user_agent=args.user_agent,
        min_interval=args.min_interval,
        timeout=args.timeout,
        max_size_mb=args.max_size_mb,
        max_retries=args.max_retries,
        strict_robots=args.strict_robots,
        allow_loopback_http=args.allow_loopback_http,
        allow_ephemeral_cache=args.allow_ephemeral_cache,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2

    try:
        cache = make_cache(args)
        cmd = args.command

        if cmd == "get":
            max_age = parse_duration(args.max_age)
            res = cache.get(
                args.url,
                sha256=args.sha256,
                max_age=max_age,
                offline=args.offline,
                refresh=args.refresh,
            )
            if args.out is not None:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(res["blob_path"], args.out)
                res["out"] = str(args.out)
            if args.json:
                if args.text:
                    view = cache.derive_view(res["sha256"], context_url=res.get("url") or "")
                    res["text"] = view["text"]
                print(json.dumps(res, indent=2, sort_keys=True))
            elif args.raw:
                if args.out is None:
                    sys.stdout.buffer.write(cache.read_blob(res["sha256"]))
                    sys.stdout.buffer.flush()
            elif args.text:
                if res.get("stale"):
                    print(
                        f"warning: serving stale snapshot from {res.get('fetched_at')} "
                        f"({res.get('stale_reason', 'expired')})",
                        file=sys.stderr,
                    )
                view = cache.derive_view(res["sha256"], context_url=res.get("url") or "")
                print(view["text"])
            else:
                stale_tag = " [STALE]" if res.get("stale") else ""
                print(
                    f"sha256: {res['sha256']} ({res['size']} bytes, "
                    f"source={res['source']}{stale_tag})"
                )
                if res.get("fetched_at"):
                    print(
                        f"fetched_at: {res['fetched_at']} "
                        f"(age={res.get('age_seconds', 0.0)}s)"
                    )
                print(f"blob: {res['blob_path']}")
            return 0

        if cmd == "pin":
            max_age = parse_duration(args.max_age)
            res = cache.pin(
                args.url,
                name=args.name,
                title=args.title,
                doc_class=args.doc_class,
                offline=args.offline,
                max_age=max_age,
            )
            if args.json:
                print(json.dumps(res, indent=2, sort_keys=True))
            else:
                print(res["yaml"])
                if res.get("has_html_processor"):
                    print(
                        "# note: wikitext contains {{{#!html blocks; headings inside raw HTML "
                        "blocks are not visible in wikitext.",
                        file=sys.stderr,
                    )
                for att in res.get("attachments", []):
                    print(
                        f"# attachment (unversioned in Trac; pin separately if cited): "
                        f"{att['url']}",
                        file=sys.stderr,
                    )
            return 0

        if cmd == "links":
            max_age = parse_duration(args.max_age)
            digest, ctx_url = cache.resolve_target_to_blob(
                args.target, offline=args.offline, max_age=max_age
            )
            view = cache.derive_view(digest, context_url=ctx_url)
            links = list(view.get("links", []))
            if args.filter:
                try:
                    pat = re.compile(args.filter, re.IGNORECASE)
                except re.error as exc:
                    raise UsageError(f"invalid --filter regex {args.filter!r}: {exc}") from exc
                links = [
                    l
                    for l in links
                    if pat.search(l.get("url", "")) or pat.search(l.get("text", ""))
                ]
            payload = {
                "sha256": digest,
                "url": ctx_url or None,
                "kind": view.get("kind"),
                "dynamic_macros": view.get("dynamic_macros", []),
                "links_count": len(links),
                "links": links,
            }
            if args.json:
                print(json.dumps(payload, indent=2, sort_keys=True))
            else:
                if view.get("dynamic_macros"):
                    print(
                        f"# note: wikitext contains unexpanded macros {view['dynamic_macros']}; "
                        "inspect the HTML discovery snapshot for expanded macro links.",
                        file=sys.stderr,
                    )
                for item in links:
                    kind = item.get("kind", "link")
                    text = item.get("text", "")
                    suffix = f" ({text})" if text and text != item["url"] else ""
                    print(f"[{kind}] {item['url']}{suffix}")
            return 0

        if cmd == "headings":
            max_age = parse_duration(args.max_age)
            digest, ctx_url = cache.resolve_target_to_blob(
                args.target, offline=args.offline, max_age=max_age
            )
            view = cache.derive_view(digest, context_url=ctx_url)
            headings = view.get("headings", [])
            payload = {
                "sha256": digest,
                "url": ctx_url or None,
                "kind": view.get("kind"),
                "has_html_processor": view.get("has_html_processor", False),
                "headings_count": len(headings),
                "headings": headings,
            }
            if args.json:
                print(json.dumps(payload, indent=2, sort_keys=True))
            else:
                if view.get("has_html_processor"):
                    print(
                        "# note: wikitext contains {{{#!html blocks; check raw content if a "
                        "heading lives inside an embedded HTML block.",
                        file=sys.stderr,
                    )
                for h in headings:
                    indent = "  " * max(0, int(h["level"]) - 1)
                    line_info = f" (line {h['line']})" if "line" in h else ""
                    print(f"{indent}H{h['level']}: {h['heading']}{line_info}")
            return 0

        if cmd == "info":
            res = cache.info(args.target)
            if args.json:
                print(json.dumps(res, indent=2, sort_keys=True))
            elif res["kind"] == "blob":
                print(f"blob: {res['sha256']} (exists={res['exists']}, size={res['size']})")
                for u in res["referencing_urls"]:
                    print(f"  url: {u}")
            else:
                print(f"url: {res['url']} ({res['snapshots_count']} snapshot(s))")
                for snap in res["snapshots"]:
                    print(
                        f"  [{snap.get('fetched_at')}] status={snap.get('status')} "
                        f"fetch={snap.get('fetch_status')} sha256={snap.get('sha256', '-')} "
                        f"size={snap.get('size', '-')}"
                    )
            return 0

        if cmd == "prefetch":
            res = prefetch_documents(cache, args.files, offline=args.offline)
            if args.json:
                print(json.dumps(res, indent=2, sort_keys=True))
            else:
                for err in res["errors"]:
                    print(f"error: {err}", file=sys.stderr)
                print(
                    f"{res['prefetched']} document(s) prefetched, {res['skipped']} skipped"
                )
            return 0 if res["ok"] else 1

        if cmd == "materialize":
            res = materialize_documents(
                cache,
                args.files,
                args.docs_dir,
                root=args.root,
                offline=args.offline,
                allow_private=args.allow_private,
            )
            if args.json:
                print(json.dumps(res, indent=2, sort_keys=True))
            else:
                for err in res["errors"]:
                    print(f"error: {err}", file=sys.stderr)
                print(
                    f"{res['materialized']} document(s) materialized "
                    f"({res['adopted']} adopted from existing files), "
                    f"{res['skipped']} skipped"
                )
            return 0 if res["ok"] else 1

        if cmd == "verify":
            res = cache.verify_store()
            docs_errors: list[str] = []
            docs_checked = 0
            if args.docs_dir is not None:
                if not args.spec:
                    raise UsageError("--docs-dir verification requires at least one --spec file")
                for spec_path, doc in iter_spec_documents(args.spec):
                    sha = doc.get("sha256")
                    if not sha:
                        continue
                    name = doc["name"]
                    if "/" in name or name in (".", ".."):
                        docs_errors.append(f"{spec_path}: invalid document name {name!r}")
                        continue
                    docs_checked += 1
                    p = args.docs_dir / name
                    if p.is_symlink() or not p.is_file():
                        docs_errors.append(f"{p}: missing regular file")
                        continue
                    with p.open("rb") as stream:
                        digest = hashlib.file_digest(stream, "sha256").hexdigest()
                    if digest != str(sha).lower():
                        docs_errors.append(
                            f"{p}: sha256 mismatch (expected {str(sha).lower()}, got {digest})"
                        )
            res["docs_checked"] = docs_checked
            res["docs_errors"] = docs_errors
            res["ok"] = res["ok"] and not docs_errors
            if args.json:
                print(json.dumps(res, indent=2, sort_keys=True))
            else:
                for item in res["corrupted"]:
                    print(
                        f"corrupted blob: {item['path']} "
                        f"(expected {item['expected']}, got {item['actual']})",
                        file=sys.stderr,
                    )
                for err in docs_errors:
                    print(f"error: {err}", file=sys.stderr)
                print(
                    f"{res['blobs_checked']} blob(s) verified, "
                    f"{docs_checked} materialized doc(s) verified"
                )
            return 0 if res["ok"] else 1

        if cmd == "gc":
            spec_files = collect_specs_from_args(args.spec, args.root)
            res = gc_blobs(
                cache,
                spec_files,
                keep_latest_snapshots=not args.no_keep_latest,
                dry_run=args.dry_run,
            )
            if args.json:
                print(json.dumps(res, indent=2, sort_keys=True))
            else:
                action = "would remove" if args.dry_run else "removed"
                print(
                    f"gc: {res['kept_count']} blob(s) kept, "
                    f"{res['removed_count']} {action} ({res['bytes_freed']} bytes)"
                )
            return 0

        raise UsageError(f"unknown subcommand: {cmd}")

    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except PreconditionError as exc:
        print(f"{exc}", file=sys.stderr)
        return 3
    except CacheError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
