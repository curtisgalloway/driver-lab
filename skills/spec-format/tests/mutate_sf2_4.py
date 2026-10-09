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
    ("generated-newlines", "render_md", 'str(value).replace("\\n", " ").replace("\\r", " ")', 'str(value)'),
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

MUTATIONS.extend([
    (
        'anchor-unanchored', 'specmd',
        'bool(re.match(r"^(?:https?|mailto):", url, re.IGNORECASE))',
        'bool(re.search(r"(?:https?|mailto):", url, re.IGNORECASE))',
    ),
    (
        'anchor-hash-anywhere', 'specmd',
        'url.startswith("#")',
        '"#" in url',
    ),
    (
        'heading-top-level-only', 'specmd',
        'elif token.type == "heading_open":',
        'elif token.type == "heading_open" and token.level == 0:',
    ),
    (
        'fence-top-level-only', 'specmd',
        'elif token.type == "fence" and not token.meta["closed"]:',
        'elif token.type == "fence" and not token.meta["closed"] and token.level == 0:',
    ),
    (
        'html-block-top-level-only', 'specmd',
        'if token.type == "html_block":\n            add',
        'if token.type == "html_block" and token.level == 0:\n            add',
    ),
    (
        'autolink-not-positioned', 'specmd',
        '("html_inline", html_inline), ("autolink", autolink),',
        '("html_inline", html_inline),',
    ),
    (
        'notice-exempt-anywhere', 'textcheck',
        'if key == "notices" and not path:',
        'if key == "notices":',
    ),
    (
        'skip-render-containment-context', 'render_md',
        'for file in group:\n            for path, value, _ in textcheck.fields',
        'for file in [g for g in group if not g.root.context]:\n            for path, value, _ in textcheck.fields',
    ),
    (
        'render-containment-html-only', 'render_md',
        'bad = [f for f in specmd.findings(value) if f.level == "error"]',
        'bad = [f for f in specmd.findings(value) if f.level == "error" and f.kind == "html"]',
    ),
    (
        'escape-no-pipe', 'render_md',
        're.escape(string.punctuation)',
        're.escape(string.punctuation.replace("|", ""))',
    ),
    (
        'escape-no-backtick', 'render_md',
        're.escape(string.punctuation)',
        're.escape(string.punctuation.replace("`", ""))',
    ),
    (
        'citation-ext-unescaped', 'render_md',
        'bits.append(escape(key + ": " + _value(value)))',
        'bits.append(key + ": " + _value(value))',
    ),
    (
        'premise-uses-unescaped', 'render_md',
        'text += ": " + escape(premise["uses"])',
        'text += ": " + premise["uses"]',
    ),
    (
        'assumption-text-unescaped', 'render_md',
        '"- assumes " + code(aid) + ": " + escape(assumption["text"])',
        '"- assumes " + code(aid) + ": " + assumption["text"]',
    ),
    (
        'todo-unescaped', 'render_md',
        'escape(todo["check"]) + "): " + escape(todo["text"])',
        'escape(todo["check"]) + "): " + todo["text"]',
    ),
    (
        'scope-unescaped', 'render_md',
        '", ".join(escape(v) for v in vals)',
        '", ".join(v for v in vals)',
    ),
    (
        'conflict-reading-unescaped', 'render_md',
        '": " + escape(conflict["reading"]))',
        '": " + conflict["reading"])',
    ),
    (
        'derivation-unescaped', 'render_md',
        '"derivation: " + escape(entry["derivation"])',
        '"derivation: " + entry["derivation"]',
    ),
    (
        'table-key-unescaped', 'render_md',
        '" | ".join(escape(k) for k in keys)',
        '" | ".join(k for k in keys)',
    ),
    (
        'banner-sha-dropped', 'render_md',
        '"; SHA256 " + code(digest) + "."',
        '"."',
    ),
    (
        'overlay-heading-dropped', 'render_md',
        'if facts and file.is_overlay:',
        'if False:',
    ),
    (
        'relates-dropped', 'render_md',
        'for relation in data.get("relates", []):',
        'for relation in []:',
    ),
    (
        'assumes-dropped', 'render_md',
        'for aid in data.get("assumes", []):',
        'for aid in []:',
    ),
    (
        'gap-dropped', 'render_md',
        'out.append("- Gap")',
        'pass',
    ),
    (
        'critical-dropped', 'render_md',
        'text += " · bring-up critical"',
        'pass',
    ),
    (
        'second-reader-dropped', 'render_md',
        'status_notes.append("second reader missing")',
        'pass',
    ),
    (
        'spec-filter-ignored', 'render_md',
        'and (spec_id is None or f.spec_id == spec_id)]',
        ']',
    ),
    (
        'instances-dropped', 'render_md',
        'for kind in ("instances", "variants"):',
        'for kind in ():',
    ),
    (
        'support-note-dropped', 'render_md',
        'notes.append(entry["note"])',
        'pass',
    ),
    (
        'resource-note-dropped', 'render_md',
        '_author(out, entry["note"])',
        'pass',
    ),
    (
        'reference-definition', 'specmd',
        'for ref in list(env.get("references", {}).values()) + env.get("duplicate_refs", []):',
        'for ref in []:',
    ),
    (
        'assembled-containment', 'render_md',
        'specmd.check_view(view, out.expected)',
        'pass',
    ),
    (
        'source-hash-second-read', 'render_md',
        'hashlib.sha256(file.loaded.source_bytes)',
        'hashlib.sha256(file.path.read_bytes())',
    ),
    (
        'filename-refusal', 'specload',
        'if any(unicodedata.category(c) in NAME_CATEGORIES for c in str(path)):',
        'if any(unicodedata.category(c) in () for c in str(path)):',
    ),
    (
        'filename-visible', 'specload',
        'if unicodedata.category(c) in NAME_CATEGORIES else c',
        'if False else c',
    ),
    (
        'record-textcheck', 'records',
        'textcheck.check_data(checker, where, loaded.data)',
        'pass',
    ),
    (
        'note-collection', 'render_md',
        'notes.append(entry["note"])',
        'out.extend(["", "Note (not evidence):", "", entry["note"], ""])',
    ),
    (
        'leading-whitespace', 'render_md',
        ').lstrip()',
        ')',
    ),
    (
        'placeholder-html-overlap', 'speccheck',
        'skip_html=path in author_paths',
        'skip_html=False',
    ),
    (
        'html-pair-duplicate', 'specmd',
        'if tag and tag[1] and tag[2].lower() in tags:',
        'if False:',
    ),
    (
        'commit-validation', 'spec',
        'if not re.fullmatch(r"[0-9a-f]{40}", value):',
        'if False:',
    ),
])

MUTATIONS.append((
    "status-drops-author-notes", "render_md", "status_notes = []",
    "notes = []\n        status_notes = []",
))

EQUIVALENT = {
    "escape-no-amp": "The semicolon is still escaped, preventing entity decoding.",
    "escape-no-lt": "The closing angle bracket is still escaped, preventing an HTML tag.",
    "escape-keep-cr": "The strict loader rejects CR in author/structured strings.",
    "code-cr-kept": "CommonMark code spans normalize CR to a space already.",
}


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
    cmd = [sys.executable, "-m", "unittest", "test_textcheck", "test_render_md", "test_sf2_4_r1"]
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
        print(name + ": " + ("assertion kill" if killed else "SURVIVED OR CRASHED"), flush=True)
    (run / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    for name, reason in EQUIVALENT.items():
        print(name + ": equivalent — " + reason)
    print("artifacts: " + str(run))
    return 0 if all(r["killed_by_assertion"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
