# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Reproduce SF2-4 guard mutations in temporary copies, without editing the working tree.

Run with the hash-pinned interpreter: python skills/spec-format/tests/mutate_sf2_4.py.
Logs and results.json stay under TMPDIR. A kill requires assertion failures, zero unittest
errors, and no internal-error traceback. Surviving or crashing mutations exit 1.
"""

from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

MUTATIONS = [
    ("html-inline", "specmd", 'if child.type == "html_inline":', 'if False:'),
    ("html-block", "specmd", 'if token.type == "html_block":\n            add', 'if False:\n            add'),
    ("link-scheme", "specmd", 'if not allowed_link(url):', 'if False:'),
    ("recognize-unsafe-links", "specmd", '_PARSER.validateLink = lambda url: True', '_PARSER.validateLink = lambda url: not url.lower().startswith(("javascript:", "vbscript:", "data:"))'),
    ("reject-relative-links", "specmd", 'return url.startswith("#") or bool', 'return not re.match(r"^[a-zA-Z]+:", url) or url.startswith("#") or bool'),
    ("allow-scheme-case-alias", "specmd", 'url, re.IGNORECASE)', 'url)'),
    ("image-scheme", "specmd", 'elif child.type in ("link_open", "image"):', 'elif child.type == "link_open":'),
    ("heading", "specmd", 'elif token.type == "heading_open":', 'elif False:'),
    ("fence", "specmd", 'elif token.type == "fence" and not token.meta["closed"]:', 'elif False:'),
    ("fence-parser-closure", "specmd", 'token.meta["closed"] = token.content != state.getLines(', 'token.meta["closed"] = True or token.content != state.getLines('),
    ("nested-inline", "specmd", 'if child.children:\n                inline', 'if False:\n                inline'),
    ("inline-source-position", "specmd", 'token.meta.setdefault("field_line", state.src.count("\\n", 0, start))', 'token.meta.setdefault("field_line", 0)'),
    ("lint", "specmd", 'if lint:\n                visible', 'if False:\n                visible'),
    ("lint-warning", "specmd", 'f"format 1 tag {match.group(0)!r} in author text", "warning"', 'f"format 1 tag {match.group(0)!r} in author text", "error"'),
    ("notice-exemption", "textcheck", 'if key == "notices" and not path:', 'if False:'),
    ("select-claims", "textcheck", '("claim", "title", "note", "orientation", "milestones", "notes")', '("title", "note", "orientation", "milestones", "notes")'),
    ("select-titles", "textcheck", '("claim", "title", "note", "orientation", "milestones", "notes")', '("claim", "note", "orientation", "milestones", "notes")'),
    ("select-notes", "textcheck", '("claim", "title", "note", "orientation", "milestones", "notes")', '("claim", "title", "orientation", "milestones", "notes")'),
    ("select-prose", "textcheck", '("claim", "title", "note", "orientation", "milestones", "notes")', '("claim", "title", "note")'),
    ("field-traversal", "textcheck", 'yield from fields(value, at)', 'yield from ()'),
    ("enable-field-lint", "textcheck", 'specmd.findings(value, lint=lint)', 'specmd.findings(value, lint=False)'),
    ("checker-integration", "speccheck", 'textcheck.check_file(self, f)', 'pass'),
    ("generated-escaping", "render_md", 'return re.sub(r"([" + re.escape(string.punctuation) + r"])", r"\\\\\\1", text)', 'return text'),
    ("generated-newlines", "render_md", 'text = str(value).replace("\\n", " ").replace("\\r", " ")', 'text = str(value)'),
    ("code-fence-length", "render_md", 'fence = "`" * (max((len(m[0]) for m in re.finditer(r"`+", text)), default=0) + 1)', 'fence = "`"'),
    ("code-padding", "render_md", 'pad = " " if text.startswith', 'pad = " " if False and text.startswith'),
    ("empty-code", "render_md", 'return fence + pad + text + pad + fence if text else ""', 'return fence + pad + text + pad + fence'),
    ("repeat-containment", "render_md", 'if bad:\n                    raise', 'if False:\n                    raise'),
    ("selected-spec-exists", "render_md", 'if not selected:\n        raise', 'if False:\n        raise'),
    ("check-before-view", "render_md", 'if errors:\n        return', 'if False:\n        return'),
    ("context-trust", "render_md", 'if root.context and root.untrusted:', 'if False:'),
    ("notice-fence", "render_md", 'fence = "`" * max(3, max', 'fence = "`" * max(3, 0 * max'),
    ("with-status", "render_md", 'if with_status:\n        row', 'if False:\n        row'),
    ("contested", "render_md", 'if "resolution" not in conflict else ""', 'if False else ""'),
    ("merged", "render_md", 'if merged:\n        groups', 'if False:\n        groups'),
]


def main():
    run = Path(tempfile.mkdtemp(prefix="sf2-4-mutations-", dir=os.environ["TMPDIR"]))
    tree = run / "tree"
    destination = tree / "skills/spec-format"
    shutil.copytree(HERE.parent, destination, ignore=shutil.ignore_patterns("__pycache__", ".*"))
    spdx = tree / "skills/board-expert/scripts"
    spdx.mkdir(parents=True)
    shutil.copyfile(REPO / "skills/board-expert/scripts/spdx.py", spdx / "spdx.py")
    (tree / "docs").mkdir()
    shutil.copyfile(REPO / "docs/SPEC-FORMAT-V2.md", tree / "docs/SPEC-FORMAT-V2.md")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(destination / "tests"))
    cmd = [sys.executable, "-m", "unittest", "test_textcheck", "test_render_md"]
    baseline = subprocess.run(cmd, cwd=tree, env=env, capture_output=True, text=True, check=False)
    (run / "baseline.log").write_text(baseline.stdout + baseline.stderr)
    if baseline.returncode:
        print("baseline failed: " + str(run))
        return 1
    results = []
    for name, module, before, after in MUTATIONS:
        path = destination / "scripts" / (module + ".py")
        source = path.read_text()
        if before not in source:
            raise ValueError("mutation target missing: " + name)
        changed = source.replace(before, after, 1)
        compile(changed, str(path), "exec")
        try:
            path.write_text(changed)
            result = subprocess.run(cmd, cwd=tree, env=env, capture_output=True, text=True, check=False)
        finally:
            path.write_text(source)
        log = result.stdout + result.stderr
        (run / (name + ".log")).write_text(log)
        killed = result.returncode != 0 and "FAIL:" in log and "ERROR:" not in log and (
            "internal error:" not in log and "RuntimeError: intentional" not in log and
            "AssertionError: 100 !=" not in log and "(100," not in log)
        results.append({"name": name, "killed_by_assertion": killed, "exit": result.returncode})
        print(name + ": " + ("assertion kill" if killed else "SURVIVED OR CRASHED"))
    (run / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print("artifacts: " + str(run))
    return 0 if all(r["killed_by_assertion"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
