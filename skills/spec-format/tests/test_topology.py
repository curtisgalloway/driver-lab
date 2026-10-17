# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Topology acceptance through real checker/CLI, contexts, renders and fact-v1 status.

All hardware and sources below are synthetic. No source adapters or live inference.
Run with isolated Python and the pinned spec-format requirements.
"""

import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

import yaml

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
# The isolated test fixture must add the scripts directory before these imports.
import spec  # pylint: disable=wrong-import-position
import topology  # pylint: disable=wrong-import-position

HDR = (
    "# SPDX-FileCopyrightText: 2026 contributors\n"
    "# SPDX-License-Identifier: Apache-2.0\n"
)
SUPPORT = [{"class": "doc", "doc": "manual", "at": [{"heading": "Synthetic topology"}]}]
KINDS = ("clock", "interrupt", "power", "reset")


def fact(fid, name, value):
    return dict(
        id=fid,
        section="topology",
        title=fid,
        claim=f"Synthetic claim {fid}.",
        support=copy.deepcopy(SUPPORT),
        data={name: value},
    )


def port(name, kind, role, **kw):
    return dict(name=name, kind=kind, role=role, **kw)


def node(fid, ports, kind="device", **kw):
    return fact(fid, "topologyNode", dict(kind=kind, ports=ports, **kw))


def connection(fid, kind, provider, consumer, mode="fixed", **kw):
    return fact(
        fid,
        "connection",
        dict(kind=kind, provider=provider, consumer=consumer, mode=mode, **kw),
    )


def end(node_ref, port_name, **kw):
    return dict(node=node_ref, port=port_name, **kw)


def document(sid, kind="chip", facts=None, **kw):
    return dict(
        format=2,
        kind=kind,
        id=sid,
        name=sid,
        triggers=[sid],
        resources={
            "documents": [
                dict(
                    name="manual",
                    title="Synthetic manual",
                    **{"class": "doc"},
                    url="https://example.invalid/manual",
                )
            ]
        },
        facts=facts or [],
        **kw,
    )


def fixture():
    providers = [
        port(k, k, "provider", **({"cells": c} if c is not None else {}))
        for k, c in zip(KINDS, (0, 2, None, 1))
    ]
    socfacts = [
        node("services", providers, kind="clock-pll"),
        node(
            "mux",
            [
                port("parent", "clock", "consumer"),
                port("out", "clock", "provider", cells=0),
            ],
            kind="clock-mux",
        ),
        node(
            "cascade",
            [
                port("upstream", "interrupt", "consumer"),
                port("irq", "interrupt", "provider", cells=2),
            ],
            kind="interrupt-controller",
        ),
    ]
    for suffix in ("a", "b"):
        socfacts.append(
            node(
                "dev-" + suffix,
                [port(k, k, "consumer") for k in KINDS],
                instance="#inst-" + suffix,
            )
        )
        for k in KINDS:
            provider = end("#mux", "out") if k == "clock" else end("#services", k)
            attrs = {}
            if k == "interrupt":
                provider = end("#cascade", "irq", cells=[1, 4])
                attrs = dict(
                    space="controller-local", number=1, trigger="IRQ_TYPE_LEVEL_HIGH"
                )
            if k == "reset":
                provider["cells"] = [3]
                attrs = dict(resetId=3, polarity="active-low")
            if k == "power":
                attrs = dict(domainId=0, supplyName="core")
            socfacts.append(
                connection(
                    k + "-" + suffix, k, provider, end("#dev-" + suffix, k), **attrs
                )
            )
    socfacts.append(
        connection(
            "cascade-link",
            "interrupt",
            end("#services", "interrupt", cells=[2, 4]),
            end("#cascade", "upstream"),
        )
    )
    soc = document(
        "soc",
        "soc",
        socfacts,
        instances=[
            dict(
                id="inst-" + s,
                name="same-ip-" + s,
                ip="ip",
                reg="0x" + v,
                irq={"kind": "SPI", "number": 1},
                clocks=["unlinked-legacy"],
                support=copy.deepcopy(SUPPORT),
            )
            for s, v in [("a", "1000"), ("b", "2000")]
        ],
    )
    boardfacts = [
        node(
            "osc",
            [port("out", "clock", "provider", cells=0)],
            kind="clock-source",
            rate="metadata#rate",
            voltage="metadata#voltage",
        ),
        connection(
            "slow",
            "clock",
            end("#osc", "out"),
            end("soc#mux", "parent"),
            "selectable",
            selectorValue=0,
            fixedRatio={"mul": 1, "div": 2},
        ),
        connection(
            "fast",
            "clock",
            end("soc#services", "clock", cells=[]),
            end("soc#mux", "parent"),
            "selectable",
            selectorValue=1,
        ),
        fact("normal", "topologyConfiguration", dict(board="board", name="Normal")),
        fact("choose", "selection", dict(configuration="#normal", selects="#slow")),
    ]
    quantities = [
        dict(
            id=fid,
            section="identity",
            title=fid,
            claim="Synthetic quantity.",
            support=copy.deepcopy(SUPPORT),
            data={"quantity": dict(unit=u, nom=n)},
        )
        for fid, u, n in [("rate", "MHz", 24), ("voltage", "mV", 1800)]
    ]
    return {
        "board": document(
            "board", "board", boardfacts, parts=["soc"], cache="synthetic"
        ),
        "soc": soc,
        "ip": document("ip", "ip"),
        "metadata": document("metadata", "peripheral", quantities, describes=["soc"]),
    }


class Topology(unittest.TestCase):
    """Exercise topology contracts and freshness through the real checker and CLI."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.docs = fixture()
        self.marker(self.root, "test")
        self.write()

    def marker(self, root, name, layer="public", accepts=()):
        root.mkdir(parents=True, exist_ok=True)
        (root / "board-specs.yaml").write_text(
            HDR
            + yaml.safe_dump(
                dict(
                    format=2,
                    name=name,
                    layer=layer,
                    license="Apache-2.0",
                    accepts=list(accepts),
                )
            )
        )

    def write(self):
        for name, data in self.docs.items():
            (self.root / (name + ".spec.yaml")).write_text(
                HDR + yaml.safe_dump(data, sort_keys=False)
            )

    # Keep the command first so calls read in the same order as the real CLI.
    # pylint: disable-next=keyword-arg-before-vararg
    def run_cli(self, command="check", *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = spec.main([command, str(self.root), "--json", *map(str, args)])
        self.assertEqual(err.getvalue(), "", err.getvalue())
        return code, json.loads(out.getvalue())

    def accepted(self):
        self.write()
        code, result = self.run_cli()
        self.assertEqual(code, 0, result)

    def rejected(self, text=None):
        self.write()
        code, result = self.run_cli()
        self.assertEqual(code, 1, result)
        errors = [f for f in result["findings"] if f["level"] == "error"]
        self.assertTrue(errors, result)
        if text:
            self.assertTrue(any(text in f["message"] for f in errors), errors)
        return result

    def f(self, owner, fid):
        return next(f for f in self.docs[owner]["facts"] if f["id"] == fid)

    def data(self, owner, fid):
        return next(iter(self.f(owner, fid)["data"].values()))

    def checker(self, context=()):
        # Inspect context records through the same private check entry point as the CLI.
        # pylint: disable=protected-access
        return spec._run_check(
            SimpleNamespace(
                roots=[self.root],
                context_root=list(context),
                require_license=False,
                public_skill=[],
            )
        )

    def test_complete_fixture_cli_and_renders(self):
        self.accepted()
        # Exercise the actual executable under isolated Python as well as main().
        proc = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                str(SCRIPTS / "spec.py"),
                "check",
                str(self.root),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for fmt, key in [("md", "markdown"), ("html", "html"), ("atlas", "html")]:
            code, result = self.run_cli("render", "--format", fmt, "--spec", "board")
            self.assertEqual(code, 0, result)
            self.assertIn("Synthetic claim osc.", result[key])
        code, result = self.run_cli("render", "--format", "html", "--spec", "soc")
        self.assertEqual(code, 0, result)
        self.assertIn("unlinked-legacy", result["html"])
        check = self.checker()
        ctx = topology.context(
            check, next(f for f in check.files if f.spec_id == "board")
        )
        self.assertEqual(len(ctx.of_kind("selection")), 1)
        self.assertEqual(len(ctx.of_kind("topologyNode")), 6)
        self.assertEqual(len(ctx.of_kind("connection")), 11)

    def test_placement_closed_shapes_and_kinds(self):
        original = copy.deepcopy(self.docs)
        cases = [
            lambda: self.f("board", "osc").update(section="quick-facts"),
            lambda: self.f("board", "osc").pop("data"),
            lambda: self.f("board", "osc").update(
                data={"quantity": {"unit": "Hz", "nom": 1}}
            ),
            lambda: self.docs["metadata"]["facts"].append(
                fact("wrong", "topologyNode", {"kind": "device", "ports": []})
            ),
            lambda: self.docs["ip"]["facts"].append(
                fact("wrong", "topologyNode", {"kind": "device", "ports": []})
            ),
            lambda: self.data("board", "osc").update(kind="unknown-kind"),
            lambda: self.data("board", "slow").update(resetId=1),
            lambda: self.data("soc", "reset-a")["consumer"].update(cells=[]),
            lambda: self.data("soc", "dev-a")["ports"][0].update(cells=0),
            lambda: self.data("board", "slow").update(fixedRatio={"mul": 0, "div": 1}),
            lambda: self.data("soc", "interrupt-a").update(trigger="level-high"),
            lambda: self.data("board", "osc").update(extra=True),
        ]
        for i, change in enumerate(cases):
            with self.subTest(case=i):
                self.docs = copy.deepcopy(original)
                change()
                self.rejected()
        for kind, section in [
            ("review", "findings"),
            ("facts", "facts"),
            ("peripheral", "identity"),
            ("ip", "gotchas"),
        ]:
            self.docs = copy.deepcopy(original)
            wrong = fact("wrong", "topologyNode", dict(kind="device", ports=[]))
            wrong["section"] = section
            self.docs["other"] = document("other", kind, [wrong])
            if kind == "review":
                self.docs["other"].pop("triggers")
            if kind == "facts":
                self.docs["other"].pop("triggers")
                self.write()
                (self.root / "other.spec.yaml").rename(self.root / "other.facts.yaml")
                self.docs.pop("other")
            with self.subTest(kind=kind):
                self.rejected()
            (
                self.root
                / ("other.facts.yaml" if kind == "facts" else "other.spec.yaml")
            ).unlink()

    def test_overlay_resolves_real_target_kind(self):
        for sid in ("soc", "metadata", "ip", "missing"):
            self.docs["overlay"] = dict(
                format=2,
                kind="overlay",
                overlays=sid,
                facts=[node("overlay-node", [])],
                resources=copy.deepcopy(self.docs["soc"]["resources"]),
            )
            if sid == "soc":
                self.accepted()
            else:
                self.rejected()

    def test_board_overlay_configuration_and_selection(self):
        self.docs["overlay"] = dict(
            format=2,
            kind="overlay",
            overlays="board",
            resources=copy.deepcopy(self.docs["board"]["resources"]),
            facts=[
                fact(
                    "overlay-config",
                    "topologyConfiguration",
                    dict(board="board", name="Normal"),
                ),
                fact(
                    "overlay-choice",
                    "selection",
                    dict(configuration="#overlay-config", selects="board#fast"),
                ),
            ],
        )
        self.accepted()
        for fmt, key in [("md", "markdown"), ("html", "html")]:
            code, result = self.run_cli(
                "render", "--format", fmt, "--spec", "board", "--merged"
            )
            self.assertEqual(code, 0, result)
            self.assertIn("Synthetic claim overlay-choice.", result[key])
        # An overlay is owned by its target board, regardless of boards in its prose.
        self.docs["other"] = document(
            "other", "board", parts=["soc"], cache="synthetic"
        )
        self.docs["overlay"]["facts"][0]["data"]["topologyConfiguration"][
            "board"
        ] = "other"
        self.rejected("belong to its configured board")

    def test_unresolved_and_wrong_reference_types_have_unknown_bases(self):
        original = copy.deepcopy(self.docs)
        for owner, fid, field, value in [
            ("board", "osc", "rate", "metadata#missing"),
            ("board", "osc", "rate", "soc#dev-a"),
            ("board", "osc", "voltage", "soc#dev-a"),
            ("soc", "dev-a", "instance", "#dev-b"),
            ("board", "choose", "configuration", "#slow"),
            ("board", "choose", "selects", "#osc"),
        ]:
            with self.subTest(field=field, value=value):
                self.docs = copy.deepcopy(original)
                self.data(owner, fid)[field] = value
                self.rejected()
                _, result = self.run_cli("status")
                row = next(
                    r
                    for s in result["specs"]
                    for r in s["facts"]
                    if r["ref"] == f"{owner}@test#{fid}"
                )
                self.assertIsNone(row["basis"])
        self.docs = copy.deepcopy(original)
        self.data("board", "slow")["provider"]["node"] = "metadata#rate"
        self.rejected("must reference a topologyNode")
        self.data("board", "slow")["provider"]["node"] = "missing@absent#node"
        self.rejected("no root named")

    def test_port_names_roles_and_kinds(self):
        original = copy.deepcopy(self.docs)
        for change, message in [
            (
                lambda: self.data("board", "osc")["ports"].append(
                    port("out", "clock", "provider")
                ),
                "duplicated",
            ),
            (
                lambda: self.data("board", "slow")["provider"].update(port="missing"),
                "missing or ambiguous",
            ),
            (
                lambda: self.data("soc", "dev-a")["ports"][0].update(role="provider"),
                "role/kind",
            ),
            (
                lambda: self.data("board", "osc")["ports"][0].update(kind="reset"),
                "role/kind",
            ),
            (
                lambda: self.data("board", "slow")["consumer"].update(port="out"),
                "role/kind",
            ),
        ]:
            with self.subTest(message=message):
                self.docs = copy.deepcopy(original)
                change()
                self.rejected(message)

    def test_cell_bounds_and_zero_known_unknown_arity(self):
        self.data("board", "slow")["provider"]["cells"] = []
        self.data("soc", "power-a")["provider"]["cells"] = [0, 4294967295]
        self.accepted()
        original = copy.deepcopy(self.docs)
        for owner, fid, cells in [
            ("board", "slow", [1]),
            ("soc", "reset-a", []),
            ("soc", "interrupt-a", [1]),
            ("soc", "power-a", [-1]),
            ("soc", "power-a", [4294967296]),
            ("soc", "power-a", [True]),
            ("soc", "power-a", [1.5]),
        ]:
            with self.subTest(fid=fid, cells=cells):
                self.docs = copy.deepcopy(original)
                self.data(owner, fid)["provider"]["cells"] = cells
                self.rejected()
        self.docs = copy.deepcopy(original)
        self.data("soc", "reset-a")["provider"].pop("cells")
        self.rejected("exactly 1")

    def test_incomplete_kinds_requires_document_todo_even_with_edges(self):
        n = self.data("soc", "dev-a")
        n["incompleteKinds"] = ["clock"]
        self.rejected("document TODO")
        self.f("soc", "dev-a")["todo"] = dict(
            check="hardware", text="Missing clock ports."
        )
        self.rejected("document TODO")
        self.f("soc", "dev-a")["todo"]["check"] = "document"
        self.accepted()
        code, result = self.run_cli("todo", "--check", "document")
        self.assertEqual(code, 0, result)
        self.assertIn("Missing clock ports.", json.dumps(result))
        n["incompleteKinds"] = ["clock", "clock"]
        self.rejected()
        n["incompleteKinds"] = []
        self.rejected()

    def test_same_node_distinct_ports_are_not_duplicate_references(self):
        self.docs["soc"]["facts"].append(
            connection(
                "feedback",
                "clock",
                end("#services", "clock"),
                end("#services", "feedback"),
            )
        )
        self.data("soc", "services")["ports"].append(
            port("feedback", "clock", "consumer")
        )
        self.accepted()

    def test_slot_conflicts_and_conflicts_metadata_cannot_waive_them(self):
        for mode in ("fixed", "selectable"):
            self.docs = fixture()
            conn = copy.deepcopy(self.f("soc", "clock-a"))
            conn["id"] = "duplicate"
            conn["data"]["connection"]["mode"] = mode
            conn["conflicts"] = [
                dict(reading="Conflicting claim.", support=copy.deepcopy(SUPPORT))
            ]
            self.docs["soc"]["facts"].append(conn)
            self.rejected("consumer slot")

    def test_selection_fixed_conflict_duplicate_and_configuration_identity(self):
        self.data("board", "choose")["selects"] = "soc#clock-a"
        self.rejected("never fixed")
        self.data("board", "choose")["selects"] = "#slow"
        duplicate = copy.deepcopy(self.f("board", "choose"))
        duplicate["id"] = "same-choice"
        self.docs["board"]["facts"].append(duplicate)
        self.accepted()
        duplicate["data"]["selection"]["selects"] = "#fast"
        self.rejected("different candidates")
        self.docs["board"]["facts"].append(
            fact(
                "other-config",
                "topologyConfiguration",
                dict(board="board", name="Normal"),
            )
        )
        duplicate["data"]["selection"]["configuration"] = "#other-config"
        self.accepted()

    def test_competing_selections_have_unknown_freshness_with_pass_records(self):
        for candidates in [
            ("slow", "fast"),
            ("slow", "slow", "fast"),
            ("slow", "fast", "fast"),
            ("slow", "slow"),
        ]:
            for reverse in (False, True):
                with self.subTest(candidates=candidates, reverse=reverse):
                    self.docs = fixture()
                    choices = [self.f("board", "choose")]
                    for index in range(1, len(candidates)):
                        choice = copy.deepcopy(choices[0])
                        choice["id"] = f"choice-{index}"
                        choices.append(choice)
                        self.docs["board"]["facts"].append(choice)
                    resources = self.root / "resources"
                    resources.mkdir(exist_ok=True)
                    record_path = resources / "board.verify.yaml"
                    record_path.unlink(missing_ok=True)
                    verdicts = {}
                    # Establish real current/PASS records with each candidate alone in
                    # the slot, then combine their independently valid selections.
                    for candidate in dict.fromkeys(candidates):
                        for choice in choices:
                            choice["data"]["selection"]["selects"] = "#" + candidate
                        self.accepted()
                        bases = self.bases()
                        current = {
                            choice["id"]: dict(
                                basis=bases["board@test#" + choice["id"]],
                                verdict="PASS",
                                date="2026-10-08",
                                verifier="Synthetic topology verifier",
                                contrary_evidence="none-found",
                                citation_precision="exact",
                            )
                            for choice in choices
                        }
                        record = dict(
                            format=2,
                            spec="board",
                            spec_file="board.spec.yaml",
                            spec_sha256="0" * 64,
                            canonical="fact-v1",
                            sources=[],
                            summary={
                                "pass": len(choices),
                                "fail": 0,
                                "unverifiable": 0,
                                "gap": 0,
                                "adjudicate": 0,
                            },
                            verdicts=current,
                        )
                        record_path.write_text(HDR + yaml.safe_dump(record))
                        code, result = self.run_cli("status")
                        self.assertEqual(code, 0, result)
                        rows = {
                            row["ref"]: row
                            for item in result["specs"]
                            for row in item["facts"]
                        }
                        for choice, selected in zip(choices, candidates):
                            row = rows["board@test#" + choice["id"]]
                            self.assertEqual(row["status"], "current", row)
                            self.assertEqual(row["verdict"], "PASS", row)
                            if selected == candidate:
                                verdicts[choice["id"]] = current[choice["id"]]
                    record["verdicts"] = verdicts
                    record_path.write_text(HDR + yaml.safe_dump(record))
                    for choice, candidate in zip(choices, candidates):
                        choice["data"]["selection"]["selects"] = "#" + candidate
                    if reverse:
                        self.docs["board"]["facts"].reverse()
                    conflict = len(set(candidates)) > 1
                    if conflict:
                        self.rejected("different candidates")
                    else:
                        self.accepted()
                    code, result = self.run_cli("status")
                    self.assertEqual(code, int(conflict), result)
                    rows = {
                        row["ref"]: row
                        for item in result["specs"]
                        for row in item["facts"]
                    }
                    for choice in choices:
                        row = rows["board@test#" + choice["id"]]
                        self.assertEqual(row["verdict"], "PASS", row)
                        self.assertEqual(
                            row["status"], "unknown" if conflict else "current", row
                        )
                        if conflict:
                            self.assertIsNone(row["basis"], row)
                        else:
                            self.assertEqual(
                                row["basis"], verdicts[choice["id"]]["basis"]
                            )

    def test_configuration_and_selection_board_ownership(self):
        original = copy.deepcopy(self.docs)
        for owner in ("soc", "missing"):
            self.data("board", "normal")["board"] = owner
            self.rejected("real board")
        self.docs = copy.deepcopy(original)
        self.docs["soc"]["facts"].append(
            fact("illegal", "topologyConfiguration", dict(board="board", name="Normal"))
        )
        self.rejected("belong to its configured board")
        self.docs = copy.deepcopy(original)
        self.docs["soc"]["facts"].append(
            fact(
                "illegal",
                "selection",
                dict(configuration="board#normal", selects="board#slow"),
            )
        )
        self.rejected("selection must belong")
        self.docs = copy.deepcopy(original)
        self.docs["elsewhere"] = document(
            "elsewhere",
            facts=[
                node("osc", [port("out", "clock", "provider")]),
                node("sink", [port("in", "clock", "consumer")]),
                connection(
                    "route",
                    "clock",
                    end("#osc", "out"),
                    end("#sink", "in"),
                    "selectable",
                ),
            ],
        )
        self.data("board", "choose")["selects"] = "elsewhere#route"
        self.rejected("not admitted")

    def test_shared_soc_boards_and_unrelated_reverse_edges_are_isolated(self):
        other = copy.deepcopy(self.docs["board"])
        other.update(id="other", name="other", triggers=["other"])
        self.data("board", "normal")["name"] = "Same display name"
        next(f for f in other["facts"] if f["id"] == "normal")["data"][
            "topologyConfiguration"
        ].update(board="other", name="Same display name")
        next(f for f in other["facts"] if f["id"] == "choose")["data"]["selection"][
            "selects"
        ] = "#fast"
        self.docs["other"] = other
        self.docs["unrelated"] = document(
            "unrelated",
            facts=[
                node("osc", [port("out", "clock", "provider")]),
                connection(
                    "reverse", "clock", end("#osc", "out"), end("soc#mux", "parent")
                ),
            ],
        )
        self.accepted()
        check = self.checker()
        for sid in ("board", "other", "soc"):
            ctx = topology.context(
                check, next(f for f in check.files if f.spec_id == sid)
            )
            self.assertNotIn("unrelated", ctx.owners)
            self.assertNotIn("other" if sid == "board" else "board", ctx.owners)
            self.assertEqual(len(ctx.of_kind("selection")), 0 if sid == "soc" else 1)
        # A valid reference to another board is still an inapplicable hardware endpoint.
        self.data("board", "slow")["provider"]["node"] = "other#osc"
        self.rejected("outside topology context")

    def test_two_boards_can_each_fix_the_same_soc_slot_differently(self):
        # Each board has one fixed parent. Combining loaded board claims globally would
        # spuriously report duplicate fixed connections on soc#mux.parent.
        self.docs["board"]["facts"] = [
            f
            for f in self.docs["board"]["facts"]
            if f["id"] not in ("fast", "normal", "choose")
        ]
        self.data("board", "slow")["mode"] = "fixed"
        self.docs["other"] = copy.deepcopy(self.docs["board"])
        self.docs["other"].update(id="other", name="other", triggers=["other"])
        self.data("other", "slow")["selectorValue"] = 1
        self.accepted()
        duplicate = copy.deepcopy(self.f("board", "slow"))
        duplicate["id"] = "duplicate"
        self.docs["board"]["facts"].append(duplicate)
        self.rejected("consumer slot")

    def test_explicit_companion_multi_hop_and_hardware_cycles(self):
        self.docs["companion"] = document(
            "companion",
            facts=[
                node(
                    "one",
                    [port("in", "clock", "consumer"), port("out", "clock", "provider")],
                ),
                connection("hop", "clock", end("#one", "out"), end("leaf#two", "in")),
            ],
        )
        self.docs["leaf"] = document(
            "leaf",
            facts=[
                node(
                    "two",
                    [port("in", "clock", "consumer"), port("out", "clock", "provider")],
                ),
                connection(
                    "cycle", "clock", end("#two", "out"), end("companion#one", "in")
                ),
            ],
        )
        self.docs["board"]["facts"].append(
            connection(
                "join", "reset", end("#osc", "reset"), end("companion#one", "reset")
            )
        )
        self.data("board", "osc")["ports"].append(port("reset", "reset", "provider"))
        self.data("companion", "one")["ports"].append(
            port("reset", "reset", "consumer")
        )
        self.accepted()
        check = self.checker()
        ctx = topology.context(
            check, next(f for f in check.files if f.spec_id == "board")
        )
        self.assertTrue({"companion", "leaf"} <= ctx.owners)
        self.docs["board"]["facts"].remove(self.f("board", "join"))
        self.accepted()
        check = self.checker()
        ctx = topology.context(
            check, next(f for f in check.files if f.spec_id == "board")
        )
        self.assertFalse({"companion", "leaf"} & ctx.owners)

    def bases(self):
        code, result = self.run_cli("status")
        self.assertEqual(code, 0, result)
        return {r["ref"]: r["basis"] for s in result["specs"] for r in s["facts"]}

    def test_freshness_transitive_forward_only_and_quantity_metadata(self):
        self.accepted()
        before = self.bases()
        self.data("board", "osc")["ports"][0]["name"] = "renamed"
        self.data("board", "slow")["provider"]["port"] = "renamed"
        self.accepted()
        after = self.bases()
        for fid in ("osc", "slow", "choose"):
            self.assertNotEqual(before["board@test#" + fid], after["board@test#" + fid])
        self.assertEqual(before["soc@test#inst-a"], after["soc@test#inst-a"])
        self.f("board", "slow")["claim"] += " Revised evidence."
        self.accepted()
        last = self.bases()
        self.assertEqual(after["board@test#osc"], last["board@test#osc"])
        self.assertNotEqual(after["board@test#choose"], last["board@test#choose"])
        # A node metadata edit also propagates without editing the connection itself.
        self.f("board", "osc")["claim"] += " Source clarification."
        self.accepted()
        edited = self.bases()
        for fid in ("slow", "choose"):
            self.assertNotEqual(last["board@test#" + fid], edited["board@test#" + fid])
        self.assertEqual(last["board@test#fast"], edited["board@test#fast"])
        self.assertIsNotNone(before["soc@test#inst-a"])
        self.data("metadata", "rate")["nom"] = 25
        self.accepted()
        quantity_edit = self.bases()
        for fid in ("osc", "slow", "choose"):
            self.assertNotEqual(
                edited["board@test#" + fid], quantity_edit["board@test#" + fid]
            )

    def test_historical_legacy_fact_v1_golden(self):
        legacy = (
            Path(__file__).resolve().parent / "fixtures" / "records" / "verify_root"
        )
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            spec.main(["status", str(legacy), "--json"])
        self.assertEqual(err.getvalue(), "")
        row = next(
            r
            for s in json.loads(out.getvalue())["specs"]
            for r in s["facts"]
            if r["ref"].endswith("#reset") and r["ref"].startswith("vok@")
        )
        self.assertEqual(
            row["basis"],
            "1aa486d65b8ab1c147beedd2bdc7bcc25132ac13adab3ecc999c1dba577e2a7c",
        )
        self.assertEqual(row["status"], "current")

    def test_other_root_layer_transitive_license_and_trust(self):
        vendor = self.root.parent / (self.root.name + "-vendor")
        vendor.mkdir()
        self.addCleanup(lambda: __import__("shutil").rmtree(vendor))
        self.marker(vendor, "vendor", accepts=["GPL-2.0-only"])
        upstream = document(
            "external", facts=[node("source", [port("out", "clock", "provider")])]
        )
        (vendor / "external.spec.yaml").write_text(HDR + yaml.safe_dump(upstream))
        self.data("board", "slow")["provider"]["node"] = "external@vendor#source"
        self.write()
        code, result = self.run_cli("check", "--context-root", vendor)
        self.assertEqual(code, 0, result)
        upstream["resources"]["repos"] = [
            dict(
                name="code",
                url="https://example.invalid/code",
                commit="1" * 40,
                license="GPL-2.0-only",
                files=[dict(path="source.c", license_from="spdx-line")],
            )
        ]
        upstream["facts"][0]["support"] = [
            dict(
                **{"class": "src"},
                anchors=[
                    dict(repo="code", path="source.c", lines=[1, 2], symbol="source")
                ],
            )
        ]
        (vendor / "external.spec.yaml").write_text(HDR + yaml.safe_dump(upstream))
        code, result = self.run_cli("check", "--context-root", vendor)
        self.assertEqual(code, 1, result)
        self.assertTrue(any("license gate" in f["message"] for f in result["findings"]))
        # The selection reaches this license indirectly through connection -> node.
        self.assertTrue(
            any(
                "fact 'choose'" in f["message"] and "license gate" in f["message"]
                for f in result["findings"]
            )
        )
        upstream["facts"][0]["support"] = copy.deepcopy(SUPPORT)
        (vendor / "external.spec.yaml").write_text(HDR + yaml.safe_dump(upstream))
        self.marker(vendor, "vendor", layer="local")
        code, result = self.run_cli("check", "--context-root", vendor)
        self.assertEqual(code, 1, result)
        self.assertTrue(any("merges after" in f["message"] for f in result["findings"]))
        self.marker(vendor, "vendor")
        upstream["facts"][0]["data"]["topologyNode"]["ports"].append(
            port("out", "clock", "provider")
        )
        (vendor / "external.spec.yaml").write_text(HDR + yaml.safe_dump(upstream))
        code, result = self.run_cli("check", "--context-root", vendor)
        self.assertEqual(code, 1, result)
        self.assertTrue(any("untrusted" in f["message"] for f in result["findings"]))


if __name__ == "__main__":
    unittest.main()
