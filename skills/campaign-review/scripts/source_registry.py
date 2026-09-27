#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Validate identity metadata without opening any source files."""

from pathlib import PurePosixPath

import index_check as check

# Booleans must not pass as integer revisions or version numbers.
# pylint: disable=unidiomatic-typecheck

KINDS = {
    "spec",
    "document",
    "kernel",
    "reference",
    "harness",
    "guest_init",
    "emulator",
    "guest_kernel",
    "guest_image",
    "guest_busybox",
    "candidate",
    "toolchain",
    "model",
    "fixture",
}


def relative(value):
    """Reject absolute paths and traversal before any filesystem operation."""
    check.string(value)
    path = PurePosixPath(value)
    check.require(
        not path.is_absolute()
        and ".." not in path.parts
        and "\\" not in value
        and ":" not in value,
        "expected a relative path without traversal",
    )


def validate(registry, claims=None, status=None):
    """Validate the registry and optional references into an already checked index."""
    check.mapping(
        registry,
        {"version", "campaign", "sources", "citations", "premises", "contradictions"},
    )
    check.require(
        type(registry["version"]) is int and registry["version"] == 1,
        "unsupported registry version",
    )
    check.string(registry["campaign"])
    check.require(isinstance(registry["sources"], list), "sources must be a list")
    ids = set()
    for source in registry["sources"]:
        check.mapping(
            source,
            {
                "id",
                "kind",
                "version",
                "sha256",
                "status",
                "checked",
                "provenance",
                "file",
                "expected_sha256",
            },
            {"pin", "commit", "revision", "changes", "bindings", "requirement_change"},
        )
        check.string(source["id"])
        check.require(source["id"] not in ids, "duplicate source ID")
        ids.add(source["id"])
        check.string(source["kind"])
        check.require(source["kind"] in KINDS, "unknown source kind")
        check.string(source["version"])
        check.sha(source["sha256"])
        check.sha(source["expected_sha256"])
        check.string(source["status"])
        check.require(
            source["status"] in {"ok", "blocked", "unknown"}, "invalid adapter status"
        )
        if source["status"] == "ok" and source["kind"] not in {
            "toolchain",
            "model",
            "fixture",
        }:
            check.sha(source["sha256"], nullable=False)
        check.date(source["checked"])
        check.mapping(source["provenance"], {"adapter", "version", "version_method"})
        for value in source["provenance"].values():
            check.string(value)
        if source["file"] is not None:
            check.mapping(source["file"], {"root", "path"})
            check.string(source["file"]["root"])
            check.require(
                source["file"]["root"] in {"repository", "run_store"},
                "unknown file root",
            )
            relative(source["file"]["path"])
        if "pin" in source:
            check.string(source["pin"])
        if "commit" in source:
            check.require(
                isinstance(source["commit"], str)
                and len(source["commit"]) == 40
                and all(c in "0123456789abcdef" for c in source["commit"]),
                "invalid commit",
            )
        if source["kind"] == "spec":
            check.require(
                type(source.get("revision")) is int and source["revision"] > 0,
                "spec needs revision",
            )
        if "requirement_change" in source:
            check.require(
                type(source["requirement_change"]) is bool,
                "requirement_change must be boolean",
            )
        if "bindings" in source:
            check.strings(source["bindings"], nonempty=True)
        changes = source.get("changes", [])
        check.require(isinstance(changes, list), "changes must be a list")
        seen = set()
        for change in changes:
            check.mapping(
                change,
                {
                    "from_sha256",
                    "to_sha256",
                    "since",
                    "reviewed",
                    "sections",
                    "checks",
                    "scenarios",
                    "evidence",
                },
            )
            check.sha(change["from_sha256"], nullable=False)
            check.sha(change["to_sha256"], nullable=False)
            check.require(change["from_sha256"] not in seen, "duplicate change origin")
            seen.add(change["from_sha256"])
            check.require(
                change["to_sha256"] == source["sha256"],
                "change map is not for current hash",
            )
            check.string(change["since"])
            check.require(type(change["reviewed"]) is bool, "reviewed must be boolean")
            for key in ("sections", "checks", "scenarios"):
                if change[key] is not None:
                    check.strings(change[key])
            check.strings(change["evidence"], nonempty=True)
    for key in ("citations", "premises"):
        check.require(isinstance(registry[key], dict), f"{key} must be a mapping")
    for citations in registry["citations"].values():
        check.require(isinstance(citations, dict), "citations must be a mapping")
        for source_id, sections in citations.items():
            check.require(source_id in ids, "citation source missing")
            check.strings(sections, nonempty=True)
    for observations in registry["premises"].values():
        check.strings(observations, nonempty=True)
    check.require(
        isinstance(registry["contradictions"], list), "contradictions must be a list"
    )
    for conflict in registry["contradictions"]:
        check.mapping(conflict, {"observation", "since", "conflict"})
        check.string(conflict["observation"])
        check.string(conflict["since"])
        relative(conflict["conflict"])
    if status is not None:
        check.require(
            registry["campaign"] == status["campaign"] == claims["campaign"],
            "campaign mismatch",
        )
        entries = {e["id"]: e for e in status["entries"]}
        observations = {
            e["id"] for e in status["entries"] if e["kind"] == "observation"
        }
        check.require(
            registry["citations"].keys() <= entries.keys(), "citation entry missing"
        )
        claim_ids = {c["id"] for c in claims["claims"]}
        check.require(registry["premises"].keys() <= claim_ids, "premise claim missing")
        for values in registry["premises"].values():
            check.require(set(values) <= observations, "premise observation missing")
        for conflict in registry["contradictions"]:
            check.require(
                conflict["observation"] in observations, "conflict observation missing"
            )
        for source in registry["sources"]:
            check.require(
                set(source.get("bindings", [])) <= status["bases"].keys(),
                "unknown basis binding",
            )
