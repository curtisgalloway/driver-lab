#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for skills/site-cache/scripts/site_cache.py.

Run:
  python3 -m unittest discover -s skills/site-cache/tests -v
"""

from __future__ import annotations

import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "site_cache.py"
sys.path.insert(0, str(SCRIPT.parent))
import site_cache  # noqa: E402


TRAC_ROBOTS_TXT = (
    "User-agent: *\n"
    "Disallow: /browser/\n"
    "Disallow: /*?format=txt\n"
)

TRAC_CATALINA_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>catalina – Gateworks</title>
  <link rel="alternate" href="/wiki/catalina?format=txt" title="Plain Text" type="text/x-trac-wiki" />
</head>
<body>
  <div id="content" class="wiki narrow">
    <p>See also <a href="/wiki/otherpage?version=2">otherpage v2</a>.</p>
    <h1 id="GateworksCatalina">Gateworks Catalina</h1>
    <div class="titleindex">
      <ul>
        <li><a href="/wiki/catalina/boot">catalina/boot</a></li>
        <li><a href="/wiki/catalina/PCIe">catalina/PCIe</a></li>
      </ul>
    </div>
    <h2 id="Bootloader">Bootloader</h2>
    <div class="trac-modifiedby">
      <span><a href="/wiki/catalina?action=diff&amp;version=6" title="Version 6 by author">Last modified</a> <a class="timeline" href="/timeline">4 weeks ago</a></span>
    </div>
  </div>
</body>
</html>
""".encode("utf-8")

# Deliberate CRLF (\r\n) line endings and Trac heading without trailing '='.
TRAC_CATALINA_TXT = (
    "= Gateworks Catalina =\r\n"
    "{{{#!html\r\n"
    "<div class=\"notice\">Custom HTML block</div>\r\n"
    "}}}\r\n"
    "== Note\r\n"
    "See [wiki:catalina/boot Boot page] and [[Image(gw9200_block.png)]].\r\n"
    "[[TitleIndex(catalina)]]\r\n"
    "== Bootloader ==\r\n"
    "Bootloader details.\r\n"
).encode("utf-8")

TRAC_CATALINA_TXT_SHA256 = hashlib.sha256(TRAC_CATALINA_TXT).hexdigest()


class _MockServerState:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.fail_mode: str | None = None
        self.etag = '"v1-etag"'
        self.dynamic_body = b"hello world\r\n"


class _MockHandler(BaseHTTPRequestHandler):
    server_version = "MockTrac/1.0"

    def log_message(self, fmt: str, *args) -> None:
        pass

    @property
    def state(self) -> _MockServerState:
        return self.server.mock_state  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        hdrs = {k.lower(): v for k, v in self.headers.items()}
        self.state.requests.append((self.path, hdrs))

        if self.path == "/robots.txt":
            body = TRAC_ROBOTS_TXT.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.state.fail_mode == "503":
            self.send_response(503)
            self.send_header("Retry-After", "0")
            self.end_headers()
            return

        if self.path in ("/wiki/catalina", "/wiki/catalina?version=6"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(TRAC_CATALINA_HTML)))
            self.end_headers()
            self.wfile.write(TRAC_CATALINA_HTML)
            return

        if self.path == "/wiki/catalina?version=6&format=txt":
            self.send_response(200)
            self.send_header("Content-Type", "text/x-trac-wiki; charset=utf-8")
            self.send_header("Content-Length", str(len(TRAC_CATALINA_TXT)))
            self.end_headers()
            self.wfile.write(TRAC_CATALINA_TXT)
            return

        if self.path == "/doc/etag-page":
            if hdrs.get("if-none-match") == self.state.etag:
                self.send_response(304)
                self.send_header("ETag", self.state.etag)
                self.end_headers()
                return
            body = self.state.dynamic_body
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("ETag", self.state.etag)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/doc/gzipped":
            compressed = gzip.compress(TRAC_CATALINA_TXT)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(compressed)))
            self.end_headers()
            self.wfile.write(compressed)
            return

        if self.path == "/soft/cloudflare":
            body = (
                b"<html><head><title>Just a moment...</title></head>"
                b"<body>cloudflare cf-browser-verification</body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/soft/login":
            body = (
                b"<html><head><title>Sign in to Vendor Portal</title></head>"
                b'<body><form><input type="password" name="pw"></form></body></html>'
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/soft/truncated-pdf":
            body = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()


class SiteCacheTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _MockHandler)
        cls.httpd.mock_state = _MockServerState()  # type: ignore[attr-defined]
        cls.port = cls.httpd.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self) -> None:
        self.state: _MockServerState = self.httpd.mock_state  # type: ignore[attr-defined]
        self.state.requests.clear()
        self.state.fail_mode = None
        self.state.etag = '"v1-etag"'
        self.state.dynamic_body = b"hello world\r\n"
        self.tmp = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.tmp.name) / "site-cache"

    def tearDown(self) -> None:
        for root, _, files in os.walk(self.tmp.name):
            for fname in files:
                fpath = Path(root) / fname
                if not fpath.is_symlink():
                    try:
                        os.chmod(fpath, 0o644)
                    except OSError:
                        pass
        self.tmp.cleanup()

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        cmd = [
            sys.executable,
            str(SCRIPT),
            *args,
            "--cache-dir",
            str(self.cache_dir),
            "--min-interval",
            "0",
            "--max-retries",
            "0",
            "--allow-loopback-http",
            "--allow-ephemeral-cache",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return proc.returncode, proc.stdout, proc.stderr

    def test_refuses_ephemeral_tmp_cache_by_default(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "info",
                "a" * 64,
                "--cache-dir",
                str(self.cache_dir),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("refusing ephemeral cache directory", proc.stderr)

    def test_trac_pin_discovers_version_preserves_crlf_and_handles_robots(self) -> None:
        rc, out, _ = self.run_cli(
            "pin",
            f"{self.base_url}/wiki/catalina",
            "--name",
            "gw-wiki-catalina",
            "--title",
            "Gateworks wiki page catalina",
            "--json",
        )
        self.assertEqual(rc, 0, out)
        data = json.loads(out)
        self.assertEqual(data["adapter"], "trac")
        self.assertEqual(data["revision"], "version 6")
        self.assertEqual(data["url"], f"{self.base_url}/wiki/catalina?version=6")
        self.assertEqual(
            data["retrieval_url"],
            f"{self.base_url}/wiki/catalina?version=6&format=txt",
        )
        self.assertEqual(data["sha256"], TRAC_CATALINA_TXT_SHA256)
        self.assertTrue(data["has_html_processor"])
        self.assertIn("TitleIndex(catalina)", data["dynamic_macros"])
        self.assertEqual(len(data["attachments"]), 1)
        self.assertEqual(
            data["attachments"][0]["url"],
            f"{self.base_url}/raw-attachment/wiki/catalina/gw9200_block.png",
        )

        # Verify stored blob has exact CRLF bytes and 0444 permissions.
        blob_path = (
            self.cache_dir
            / "public"
            / "blobs"
            / "sha256"
            / TRAC_CATALINA_TXT_SHA256[:2]
            / TRAC_CATALINA_TXT_SHA256
        )
        self.assertTrue(blob_path.is_file())
        self.assertEqual(blob_path.read_bytes(), TRAC_CATALINA_TXT)
        self.assertEqual(stat.S_IMODE(blob_path.stat().st_mode), 0o444)

        # Verify links from the HTML discovery snapshot include expanded TitleIndex links.
        rc, links_out, _ = self.run_cli(
            "links",
            f"{self.base_url}/wiki/catalina",
            "--filter",
            "/wiki/catalina/",
            "--offline",
            "--json",
        )
        self.assertEqual(rc, 0)
        links_data = json.loads(links_out)
        urls = [item["url"] for item in links_data["links"]]
        self.assertIn(f"{self.base_url}/wiki/catalina/boot", urls)
        self.assertIn(f"{self.base_url}/wiki/catalina/PCIe", urls)

        # Verify headings extraction from the pinned wikitext blob.
        rc, head_out, _ = self.run_cli(
            "headings",
            TRAC_CATALINA_TXT_SHA256,
            "--offline",
            "--json",
        )
        self.assertEqual(rc, 0)
        head_data = json.loads(head_out)
        self.assertEqual(
            [h["heading"] for h in head_data["headings"]],
            ["Gateworks Catalina", "Note", "Bootloader"],
        )

    def test_robots_blocks_disallowed_paths_and_strict_mode_blocks_query_disallow(self) -> None:
        # /browser/ is disallowed at the canonical path level.
        rc, _, err = self.run_cli("get", f"{self.base_url}/browser/trunk")
        self.assertEqual(rc, 1)
        self.assertIn("blocked by robots.txt", err)

        # With --strict-robots, even /*?format=txt is refused.
        rc, _, err = self.run_cli(
            "get",
            f"{self.base_url}/wiki/catalina?version=6&format=txt",
            "--strict-robots",
        )
        self.assertEqual(rc, 1)
        self.assertIn("blocked by robots.txt", err)

    def test_gzip_transport_decoding_preserves_exact_payload_hash(self) -> None:
        rc, out, _ = self.run_cli(
            "get",
            f"{self.base_url}/doc/gzipped",
            "--sha256",
            TRAC_CATALINA_TXT_SHA256,
            "--json",
        )
        self.assertEqual(rc, 0, out)
        data = json.loads(out)
        self.assertEqual(data["sha256"], TRAC_CATALINA_TXT_SHA256)

    def test_pinned_mode_zero_network_on_hit_and_fails_closed_on_mismatch(self) -> None:
        rc, _, _ = self.run_cli(
            "get",
            f"{self.base_url}/wiki/catalina?version=6&format=txt",
            "--sha256",
            TRAC_CATALINA_TXT_SHA256,
        )
        self.assertEqual(rc, 0)
        count_after_first = len(self.state.requests)

        # Second pinned read hits local blob store with 0 HTTP requests.
        rc, out, _ = self.run_cli(
            "get",
            f"{self.base_url}/wiki/catalina?version=6&format=txt",
            "--sha256",
            TRAC_CATALINA_TXT_SHA256,
            "--json",
        )
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.state.requests), count_after_first)
        self.assertEqual(json.loads(out)["source"], "cache")

        # Mismatched sha256 fails closed.
        wrong_sha = "b" * 64
        rc, _, err = self.run_cli(
            "get",
            f"{self.base_url}/wiki/catalina?version=6&format=txt",
            "--sha256",
            wrong_sha,
        )
        self.assertEqual(rc, 1)
        self.assertIn("sha256 mismatch", err)

    def test_conditional_revalidation_304_and_stale_fallback_on_503(self) -> None:
        url = f"{self.base_url}/doc/etag-page"
        rc, out1, _ = self.run_cli("get", url, "--json")
        self.assertEqual(rc, 0)
        d1 = json.loads(out1)
        self.assertEqual(d1["source"], "network")

        # Refresh triggers If-None-Match -> 304 Not Modified.
        rc, out2, _ = self.run_cli("get", url, "--refresh", "--json")
        self.assertEqual(rc, 0)
        d2 = json.loads(out2)
        self.assertEqual(d2["source"], "revalidated-304")
        self.assertEqual(d2["sha256"], d1["sha256"])

        # Origin goes down (503) -> falls back to cached snapshot with stale=True.
        self.state.fail_mode = "503"
        rc, out3, _ = self.run_cli("get", url, "--refresh", "--json")
        self.assertEqual(rc, 0)
        d3 = json.loads(out3)
        self.assertEqual(d3["source"], "cache-fallback")
        self.assertTrue(d3["stale"])
        self.assertEqual(d3["sha256"], d1["sha256"])

    def test_soft_errors_are_rejected_and_not_cached_as_ok(self) -> None:
        for path, expected_word in (
            ("/soft/cloudflare", "bot challenge"),
            ("/soft/login", "login wall"),
            ("/soft/truncated-pdf", "missing trailing %%EOF"),
        ):
            with self.subTest(path=path):
                rc, _, err = self.run_cli("get", f"{self.base_url}{path}")
                self.assertEqual(rc, 1)
                self.assertIn(expected_word, err)
                rc_info, info_out, _ = self.run_cli(
                    "info", f"{self.base_url}{path}", "--json"
                )
                self.assertEqual(rc_info, 0)
                info = json.loads(info_out)
                self.assertIsNone(info["latest_ok"])
                self.assertIn(
                    info["snapshots"][-1]["fetch_status"], ("blocked", "truncated")
                )

    def test_materialize_adopts_existing_files_by_copy_and_links_missing_files(self) -> None:
        work = Path(self.tmp.name) / "project"
        specs_dir = work / "specs"
        docs_dir = work / "docs" / "by-name"
        sibling_dir = Path(self.tmp.name) / "sibling-repo"
        specs_dir.mkdir(parents=True)
        docs_dir.mkdir(parents=True)
        sibling_dir.mkdir(parents=True)

        (specs_dir / "board-specs.yaml").write_text(
            "format: 2\nlayer: public\nname: test-root\nlicense: Apache-2.0\naccepts: []\n",
            encoding="utf-8",
        )

        # Create an existing local file hardlinked to a sibling repo with mode 0644.
        local_bytes = b"pre-existing local datasheet bytes\n"
        local_sha = hashlib.sha256(local_bytes).hexdigest()
        sibling_file = sibling_dir / "datasheet.bin"
        sibling_file.write_bytes(local_bytes)
        os.chmod(sibling_file, 0o644)
        os.link(sibling_file, docs_dir / "local-doc")

        spec_file = specs_dir / "test.spec.yaml"
        spec_file.write_text(
            f"""format: 2
kind: board
id: test-board
name: Test Board
resources:
  documents:
    - name: local-doc
      class: doc
      title: Already Present Document
      url: {self.base_url}/doc/never-fetched
      sha256: {local_sha}
    - name: gw-wiki-catalina
      class: doc
      title: Gateworks wiki page catalina
      revision: version 6
      url: {self.base_url}/wiki/catalina?version=6
      retrieval:
        - url: {self.base_url}/wiki/catalina?version=6&format=txt
      sha256: {TRAC_CATALINA_TXT_SHA256}
""",
            encoding="utf-8",
        )

        rc, out, err = self.run_cli(
            "materialize",
            str(spec_file),
            "--docs-dir",
            str(docs_dir),
            "--root",
            str(specs_dir),
            "--json",
        )
        self.assertEqual(rc, 0, err + out)
        res = json.loads(out)
        self.assertTrue(res["ok"])
        self.assertEqual(res["materialized"], 2)
        self.assertEqual(res["adopted"], 1)

        # Confirm local-doc was never requested over HTTP and sibling_file kept 0644 permissions!
        requested_paths = [r[0] for r in self.state.requests]
        self.assertNotIn("/doc/never-fetched", requested_paths)
        self.assertEqual(stat.S_IMODE(sibling_file.stat().st_mode), 0o644)

        # Confirm gw-wiki-catalina was materialized as a regular non-symlink file.
        mat_wiki = docs_dir / "gw-wiki-catalina"
        self.assertFalse(mat_wiki.is_symlink())
        self.assertTrue(mat_wiki.is_file())
        self.assertEqual(mat_wiki.read_bytes(), TRAC_CATALINA_TXT)

        # Verify command checks both blob store and docs-dir.
        rc, v_out, _ = self.run_cli(
            "verify",
            "--docs-dir",
            str(docs_dir),
            "--spec",
            str(spec_file),
            "--json",
        )
        self.assertEqual(rc, 0, v_out)
        v_data = json.loads(v_out)
        self.assertTrue(v_data["ok"])
        self.assertEqual(v_data["docs_checked"], 2)

        # GC keeps pinned blobs and removes unreferenced blobs.
        orphan_bytes = b"orphan unreferenced blob"
        orphan_sha = hashlib.sha256(orphan_bytes).hexdigest()
        cache = site_cache.SiteCache(
            self.cache_dir, allow_ephemeral_cache=True
        )
        cache.store_blob_bytes(orphan_bytes)
        self.assertTrue(cache.has_blob(orphan_sha))

        rc, gc_out, _ = self.run_cli(
            "gc",
            "--spec",
            str(spec_file),
            "--no-keep-latest",
            "--json",
        )
        self.assertEqual(rc, 0, gc_out)
        gc_data = json.loads(gc_out)
        self.assertIn(orphan_sha, gc_data["removed"])
        self.assertFalse(cache.has_blob(orphan_sha))
        self.assertTrue(cache.has_blob(local_sha))
        self.assertTrue(cache.has_blob(TRAC_CATALINA_TXT_SHA256))

    def test_public_root_refuses_private_document_materialization(self) -> None:
        work = Path(self.tmp.name) / "pubroot"
        docs_dir = work / "docs"
        work.mkdir(parents=True)
        (work / "board-specs.yaml").write_text(
            "format: 2\nlayer: public\nname: pub\nlicense: Apache-2.0\naccepts: []\n",
            encoding="utf-8",
        )
        spec_file = work / "priv.spec.yaml"
        spec_file.write_text(
            f"""format: 2
kind: board
id: priv-board
name: Priv Board
resources:
  documents:
    - name: secret-doc
      class: doc
      title: Private Document
      access: private
      url: {self.base_url}/wiki/catalina?version=6&format=txt
      sha256: {TRAC_CATALINA_TXT_SHA256}
""",
            encoding="utf-8",
        )
        rc, out, _ = self.run_cli(
            "materialize",
            str(spec_file),
            "--docs-dir",
            str(docs_dir),
            "--root",
            str(work),
            "--json",
        )
        self.assertEqual(rc, 1, out)
        res = json.loads(out)
        self.assertFalse(res["ok"])
        self.assertIn("cannot be materialized in a public spec root", res["errors"][0])


if __name__ == "__main__":
    unittest.main()
