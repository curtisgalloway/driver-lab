# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Deployment declarations and model roles; never execute declared commands."""

from pathlib import Path
import re

import index_check as check
from pinned_file_adapter import module_at

# YAML booleans must not be accepted as integer schema versions.
# pylint: disable=unidiomatic-typecheck

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / "evals/deployment.yaml"
FORMAT = ROOT / "skills/board-expert/SPEC-FORMAT.md"
ROLES = {"reader", "implementer", "reviewer"}


def evidence_classes(target_spec=None):
    """Read class definitions, never accept a mere tag mention in prose."""
    text = FORMAT.read_text(encoding="utf-8")
    tags = set(re.findall(r"^  - `\[([\w-]+)\]` —", text, re.MULTILINE))
    check.require(bool(tags), "SPEC-FORMAT provenance definitions missing")
    if target_spec is not None:
        text = Path(target_spec).read_text(encoding="utf-8")
        tags.update(re.findall(r"^\| `\[([\w-]+)\]` \|", text, re.MULTILINE))
    return tags


def validate(document, target_spec=None):
    """Validate version 1 and return models keyed by their declared role."""
    check.mapping(document, {"version", "plugins"})
    check.require(
        type(document["version"]) is int and document["version"] == 1,
        "unsupported deployment version",
    )
    check.require(isinstance(document["plugins"], list), "plugins must be a list")
    classes = evidence_classes(target_spec)
    ids, roles = set(), {}
    for entry in document["plugins"]:
        check.require(isinstance(entry, dict), "plugin must be a mapping")
        kind = entry.get("kind")
        check.string(kind)
        check.require(
            kind in {"source", "producer", "role", "fixture"}, "unknown plugin kind"
        )
        extra = (
            {"class"}
            if kind == "producer"
            else {"model", "agent"}
            if kind == "role"
            else {"command"}
        )
        check.mapping(entry, {"id", "kind", "via"} | extra)
        check.string(entry["id"])
        check.require(check.ID.fullmatch(entry["id"]), "invalid plugin ID")
        check.require(entry["id"] not in ids, "duplicate plugin ID")
        ids.add(entry["id"])
        check.string(entry["via"])
        check.require(
            re.fullmatch(r"skill:[A-Za-z0-9][A-Za-z0-9_.-]*", entry["via"]),
            "via must name a skill",
        )
        if kind in {"source", "fixture"}:
            command = entry["command"]
            check.require(
                isinstance(command, list) and bool(command),
                "command must be a nonempty argv list",
            )
            for arg in command:
                check.string(arg)
        elif kind == "producer":
            check.string(entry["class"])
            check.require(entry["class"] in classes, "unknown producer class")
        else:
            check.require(entry["id"] in ROLES, "unknown model role")
            check.string(entry["agent"])
            check.mapping(entry["model"], {"name", "version"})
            for value in entry["model"].values():
                check.string(value)
            roles[entry["id"]] = dict(entry["model"])
    check.require(
        roles.keys() == ROLES, "reader, implementer and reviewer roles required"
    )
    return roles


def load(path=None, target_spec=None):
    """Prefer an explicit manifest, then user config, then the reference."""
    if path is None:
        settings = module_at("driver_lab_settings", ROOT / "utilities/run-store.py")
        value = settings.read_config().get("deployment")
        if value is not None:
            check.string(value)
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = settings.config_path().parent / path
    try:
        document = check.read_yaml(Path(path) if path is not None else REFERENCE)
    except check.Invalid:
        raise
    except (ValueError, check.yaml.YAMLError) as exc:
        raise check.Invalid("invalid deployment YAML") from exc
    return validate(document, target_spec)
