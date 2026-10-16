# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""speceval.py: shared library for the spec-eval skill (no command line).

Loads an item bank, validates it against the bank schema with a small draft 2020-12
interpreter, normalizes the legacy field names, materializes the Rust prelude into an
item's preamble, and compiles and runs Rust test programs with rustc.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
DEFAULT_PRELUDE = SKILL_DIR / "rust" / "hw_eval_prelude.rs"
DEFAULT_SCHEMA = SKILL_DIR / "schema" / "code_bank.schema.json"
PRELUDE_MARKER = "// ---- end of prelude: test module below is not prepended ----"

RUSTC_FLAGS = [
    "--edition", "2021",
    "-A", "dead_code",
    "-A", "unused_variables",
    "-A", "unused_imports",
]

COMPILE_TIMEOUT = 180

# Fields that may be spelled two ways. The first name is canonical.
ALIAS_PAIRS = [
    ("fn_signature", "signature"),
    ("reference_rust", "ref_rs"),
    ("trap_rust", "trap_rs"),
    ("test_harness", "tests_rs"),
    ("preamble", "preamble_rs"),
    ("chapter_or_block", "domain"),
    ("doc_pages_primary", "pdf_pages"),
    ("doc_pages_secondary", "pdf_pages_secondary"),
]


# ---------------------------------------------------------------------------- bank loading


def load_document(path) -> Any:
    """Read a bank file as parsed JSON, without interpreting it."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def items_of(document: Any) -> list:
    """The item list of a bank document (an array, or an object's `items`); [] if neither."""
    if isinstance(document, dict):
        document = document.get("items")
    return document if isinstance(document, list) else []


def load_bank(path) -> list[dict]:
    """Read a bank file: a JSON array of items, or an object holding them under `items`."""
    document = load_document(path)
    if not isinstance(document, list) and not (
            isinstance(document, dict) and isinstance(document.get("items"), list)):
        raise ValueError(f"{path}: not an array of items or an object with an items array")
    return items_of(document)


def bank_findings(document: Any, schema: dict) -> list[str]:
    """Schema errors for the whole document, then the semantic checks on its items."""
    return validate(document, schema) + check_bank(items_of(document))


def load_schema(path=None) -> dict:
    return json.loads(Path(path or DEFAULT_SCHEMA).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------- schema interpreter

_IGNORED = {"$schema", "$id", "$comment", "title", "description", "$defs", "default"}
_IMPLEMENTED = {
    "type", "enum", "const", "required", "properties", "additionalProperties", "items",
    "anyOf", "oneOf", "allOf", "minLength", "minItems", "$ref",
}


def _type_ok(value: Any, name: str) -> bool:
    if name == "string":
        return isinstance(value, str)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "array":
        return isinstance(value, list)
    if name == "object":
        return isinstance(value, dict)
    if name == "null":
        return value is None
    raise ValueError(f"schema type not implemented: {name}")


def _json_equal(a: Any, b: Any) -> bool:
    """JSON equality: True is not 1."""
    return isinstance(a, bool) == isinstance(b, bool) and a == b


def _resolve(ref: str, root: dict) -> dict:
    if not ref.startswith("#/"):
        raise ValueError(f"only local $ref values are implemented: {ref}")
    node: Any = root
    for part in ref[2:].split("/"):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node


def _check(inst: Any, schema: Any, root: dict, path: str) -> list[str]:
    if schema is True or schema == {}:
        return []
    if not isinstance(schema, dict):
        raise ValueError(f"schema node is not an object at {path}: {schema!r}")
    for key in schema:
        if key not in _IMPLEMENTED and key not in _IGNORED:
            raise ValueError(f"schema keyword not implemented by speceval.validate: {key}")
    errors: list[str] = []
    if "$ref" in schema:
        errors += _check(inst, _resolve(schema["$ref"], root), root, path)
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(inst, n) for n in names):
            errors.append(f"{path}: expected type {'|'.join(names)}, got {type(inst).__name__}")
            return errors
    if "enum" in schema and not any(_json_equal(inst, v) for v in schema["enum"]):
        errors.append(f"{path}: {inst!r} is not one of {schema['enum']!r}")
    if "const" in schema and not _json_equal(inst, schema["const"]):
        errors.append(f"{path}: expected {schema['const']!r}")
    if isinstance(inst, str) and "minLength" in schema and len(inst) < schema["minLength"]:
        errors.append(f"{path}: shorter than {schema['minLength']} characters")
    if isinstance(inst, list):
        if "minItems" in schema and len(inst) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for i, element in enumerate(inst):
                errors += _check(element, schema["items"], root, f"{path}[{i}]")
    if isinstance(inst, dict):
        for name in schema.get("required", []):
            if name not in inst:
                errors.append(f"{path}: missing required field {name!r}")
        props = schema.get("properties", {})
        for name, sub in props.items():
            if name in inst:
                errors += _check(inst[name], sub, root, f"{path}.{name}")
        extra = schema.get("additionalProperties", True)
        if not isinstance(extra, bool):
            raise ValueError("schema keyword not implemented by speceval.validate: "
                             "additionalProperties with a schema value")
        if extra is False:
            for name in inst:
                if name not in props:
                    errors.append(f"{path}: unknown field {name!r}")
    if "allOf" in schema:
        for sub in schema["allOf"]:
            errors += _check(inst, sub, root, path)
    if "anyOf" in schema:
        results = [_check(inst, sub, root, path) for sub in schema["anyOf"]]
        if not any(not r for r in results):
            detail = "; ".join(r[0] for r in results if r)
            errors.append(f"{path}: matches none of the allowed forms ({detail})")
    if "oneOf" in schema:
        matches = sum(1 for sub in schema["oneOf"] if not _check(inst, sub, root, path))
        if matches != 1:
            errors.append(f"{path}: matches {matches} of the oneOf forms, expected exactly 1")
    return errors


def check_schema(node: Any, path: str = "#") -> None:
    """Raise on any keyword in the whole schema that `validate` does not implement."""
    if node is True:
        return
    if not isinstance(node, dict):
        raise ValueError(f"schema node is not an object at {path}")
    for key, value in node.items():
        if key not in _IMPLEMENTED and key not in _IGNORED:
            raise ValueError(f"schema keyword not implemented by speceval.validate: {key}")
        if key == "additionalProperties" and not isinstance(value, bool):
            raise ValueError("schema keyword not implemented by speceval.validate: "
                             "additionalProperties with a schema value")
        if key in ("properties", "$defs"):
            for name, sub in value.items():
                check_schema(sub, f"{path}/{key}/{name}")
        elif key == "items":
            check_schema(value, f"{path}/items")
        elif key in ("anyOf", "oneOf", "allOf"):
            for i, sub in enumerate(value):
                check_schema(sub, f"{path}/{key}/{i}")


def validate(instance: Any, schema: dict) -> list[str]:
    """Return a list of error strings (empty when valid). Raises on an unsupported keyword."""
    check_schema(schema)
    return _check(instance, schema, schema, "$")


# ---------------------------------------------------------------------------- bank semantics


def check_bank(items: list[dict]) -> list[str]:
    """Checks the schema cannot express: duplicate ids, both names of an alias pair, a body in
    the signature, and an out-of-spec item without an abstain probe."""
    errors: list[str] = []
    seen: set[str] = set()
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        label = item_id if isinstance(item_id, str) else f"#{i}"
        if isinstance(item_id, str):
            if item_id in seen:
                errors.append(f"{label}: duplicate id")
            seen.add(item_id)
        for first, second in ALIAS_PAIRS:
            if first in item and second in item:
                errors.append(f"{label}: carries both {first!r} and {second!r}; use one")
        signature = _pick(item, "fn_signature", "signature", "")
        if isinstance(signature, str) and "{" in signature:
            errors.append(f"{label}: fn_signature must be a header only; it holds a '{{'")
        if item.get("stratum") == "out-of-spec" and not item.get("abstain_probe"):
            errors.append(f"{label}: an out-of-spec item needs an abstain_probe")
    return errors


def _pick(item: dict, first: str, second: str, default: Any = None) -> Any:
    if first in item:
        return item[first]
    return item.get(second, default)


def normalize(item: dict) -> dict:
    """Return the item with canonical keys (see ALIAS_PAIRS) and defaults filled in."""
    out = dict(item)
    for first, second in ALIAS_PAIRS:
        if second in out:
            value = out.pop(second)
            out.setdefault(first, value)
    out["fn_signature"] = out.get("fn_signature", "")
    out["reference_rust"] = out.get("reference_rust", "")
    out["trap_rust"] = out.get("trap_rust", "")
    out["test_harness"] = out.get("test_harness", "")
    out["preamble"] = out.get("preamble", "")
    out["use_hw_prelude"] = bool(out.get("use_hw_prelude", False))
    tier = out.get("tier")
    if isinstance(tier, str):
        tier = int(tier.removeprefix("tier"))
    out["tier"] = tier
    out["doc_pages_primary"] = list(out.get("doc_pages_primary", []))
    out["doc_pages_secondary"] = list(out.get("doc_pages_secondary", []))
    return out


# ------------------------------------------------------------------------------- prelude


def read_prelude(path=None) -> str:
    """Return the text before the marker line of the prelude file."""
    path = Path(path or DEFAULT_PRELUDE)
    text = path.read_text(encoding="utf-8")
    index = text.find(PRELUDE_MARKER)
    if index < 0:
        raise ValueError(f"{path}: marker line missing: {PRELUDE_MARKER}")
    return text[:index].rstrip() + "\n"


def item_preamble(item: dict, prelude_text: str) -> str:
    """The code placed before an answer: prelude plus the item's preamble, if it asks for it."""
    preamble = _pick(item, "preamble", "preamble_rs", "")
    if item.get("use_hw_prelude"):
        return prelude_text + "\n\n" + preamble
    return preamble


def signature_stub(fn_signature: str) -> str:
    """The signature header with a body that returns `Err(SpecGap(..))`."""
    sig = fn_signature.strip().rstrip(";").rstrip()
    return sig + ' { Err(SpecGap("out of spec")) }'


# ------------------------------------------------------------------------------- rustc


def have_rustc() -> bool:
    return shutil.which("rustc") is not None


def _text(value) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else value


def compile_lib(source: str, workdir=None) -> tuple[bool, str]:
    """Compile `source` as a library crate. Returns (ok, diagnostics)."""
    with tempfile.TemporaryDirectory(prefix="speceval-", dir=workdir) as tmp:
        src = Path(tmp) / "item.rs"
        src.write_text(source, encoding="utf-8")
        try:
            proc = subprocess.run(
                ["rustc", *RUSTC_FLAGS, "--crate-type", "lib", "--out-dir", tmp, str(src)],
                capture_output=True, text=True, timeout=COMPILE_TIMEOUT, check=False)
        except subprocess.TimeoutExpired:
            return False, "rustc timed out"
        return proc.returncode == 0, proc.stderr.replace(tmp + "/", "")


_TEST_LINE = re.compile(r"^test (\S+) \.\.\. (ok|FAILED|ignored)\b", re.MULTILINE)
_RUNNING = re.compile(r"^running (\d+) tests?$", re.MULTILINE)
_SUMMARY = re.compile(r"^test result: ", re.MULTILINE)


def run_timeout() -> int:
    """Seconds a test binary may run: `SPEC_EVAL_RUN_TIMEOUT`, default 20.

    Raises ValueError unless the value is a positive integer.
    """
    raw = os.environ.get("SPEC_EVAL_RUN_TIMEOUT", "20")
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        raise ValueError(f"SPEC_EVAL_RUN_TIMEOUT must be a positive integer, not {raw!r}")
    return value


def compile_and_run_tests(source: str, workdir=None, timeout: int | None = None) -> SimpleNamespace:
    """Compile `source` with `--test` and run it single-threaded.

    The result has compiled, diagnostics, exit_code, timed_out, stdout and results (test name
    to "ok", "FAILED" or "ignored"). `complete` is true only when the run did not time out,
    announced `running N tests`, printed a `test result:` summary, and reported all N tests;
    a binary that aborts or exits part-way is never complete.
    """
    if timeout is None:
        timeout = run_timeout()
    res = SimpleNamespace(compiled=False, diagnostics="", exit_code=None, timed_out=False,
                          stdout="", results={}, declared=0, complete=False)
    with tempfile.TemporaryDirectory(prefix="speceval-", dir=workdir) as tmp:
        src = Path(tmp) / "item.rs"
        exe = Path(tmp) / "item_tests"
        src.write_text(source, encoding="utf-8")
        try:
            build = subprocess.run(
                ["rustc", *RUSTC_FLAGS, "--test", "-o", str(exe), str(src)],
                capture_output=True, text=True, timeout=COMPILE_TIMEOUT, check=False)
        except subprocess.TimeoutExpired:
            res.diagnostics = "rustc timed out"
            return res
        res.diagnostics = build.stderr.replace(tmp + "/", "")
        if build.returncode != 0:
            return res
        res.compiled = True
        try:
            run = subprocess.run([str(exe), "--test-threads=1"], capture_output=True,
                                 text=True, timeout=timeout, check=False, cwd=tmp)
            res.exit_code = run.returncode
            res.stdout = run.stdout + run.stderr
        except subprocess.TimeoutExpired as exc:
            res.timed_out = True
            res.stdout = _text(exc.stdout) + _text(exc.stderr)
        res.results = {name: status for name, status in _TEST_LINE.findall(res.stdout)}
        res.declared = sum(int(n) for n in _RUNNING.findall(res.stdout))
        failed = any(status == "FAILED" for status in res.results.values())
        # libtest exits 0 when every test passed and 101 when one failed; any other status
        # (a signal from abort or a stack overflow) means the binary died, whatever it printed.
        exit_ok = res.exit_code == (101 if failed else 0)
        res.complete = (not res.timed_out and exit_ok and res.declared > 0
                        and bool(_SUMMARY.search(res.stdout))
                        and len(res.results) == res.declared)
    return res
