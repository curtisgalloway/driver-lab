// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

use std::process::Command;

#[test]
#[ignore]
fn test_actual_harness_failures_are_valid_contracts() {
    // TODO: Port this Python logic to Rust
    /*

        for mode, group, outcome in (
            ("boot", "boot", "ERROR"),
            ("insmod", "itr", "FAIL"),
            ("before-scenario", "between scenarios", "ERROR"),
        ):
            with self.subTest(mode=mode):
                directory = self.harness_failure(mode)
                recorded = contract.read_json(directory / "verdicts.json")
                self.assertEqual(recorded["results"][0]["scenario"], group)
                self.assertEqual(recorded["results"][0]["checks"], [])
                report = self.cli("--run-dir", directory)
                self.assertEqual(report["checks"]["fixture"]["overall"], outcome)


    */
}

#[test]
#[ignore]
fn test_undeclared_scenario_rejected_for_both_identity_shapes() {
    // TODO: Port this Python logic to Rust
    /*

        for native in (True, False):
            with self.subTest(native=native):
                directory = stub.write_run(self.root / str(native))
                if native:
                    (directory / "identities.json").write_bytes(
                        (FIXTURES / "qemu-run/identities.json").read_bytes()
                    )
                path = directory / "verdicts.json"
                document = contract.read_json(path)
                document["results"].append(
                    {
                        "scenario": "smoke",
                        "verdict": "PASS",
                        "checks": [{"check": "extra", "ok": True}],
                    }
                )
                path.write_text(json.dumps(document))
                self.cli("--run-dir", directory, expected=1)


    */
}

#[test]
#[ignore]
fn test_error_groups_cannot_hide_missing_scenario_or_execution() {
    // TODO: Port this Python logic to Rust
    /*

        directory = stub.write_run(self.root / "error-groups")
        path = directory / "verdicts.json"
        for group in ("boot", "between scenarios", "trace", "capture"):
            for outcome in ("PASS", "ERROR"):
                with self.subTest(group=group, outcome=outcome):
                    checks = (
                        [] if outcome == "ERROR" else [{"check": "extra", "ok": True}]
                    )
                    path.write_text(
                        json.dumps(
                            {
                                "overall": outcome,
                                "results": [
                                    {
                                        "scenario": group,
                                        "verdict": outcome,
                                        "checks": checks,
                                    }
                                ],
                            }
                        )
                    )
                    valid = (
                        group in {"boot", "between scenarios"} and outcome == "ERROR"
                    )
                    self.cli("--run-dir", directory, expected=0 if valid else 1)
        document = contract.read_json(FIXTURES / "qemu-run/verdicts.json")
        document["overall"] = "ERROR"
        document["results"].append(
            {"scenario": "boot", "verdict": "ERROR", "checks": []}
        )
        path.write_text(json.dumps(document))
        self.cli("--run-dir", directory, expected=1)


    */
}

#[test]
#[ignore]
fn test_manifest_constructor_errors_return_json() {
    // TODO: Port this Python logic to Rust
    /*

        path = self.root / "invalid.yaml"
        for content in ("version: 2026-99-99\nplugins: []\n", "version: [\n"):
            path.write_text(content)
            self.cli("--deployment", path, expected=1)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "sweep.py"),
                    str(ROOT / "evals/e1000"),
                    "--deployment",
                    str(path),
                    "--json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(proc.stderr, "")
            self.assertFalse(json.loads(proc.stdout)["ok"])


    */
}

#[test]
#[ignore]
fn test_capture_is_limited_to_documented_context() {
    // TODO: Port this Python logic to Rust
    /*

        for native in (True, False):
            for scenario in ("itr", "smoke"):
                with self.subTest(native=native, scenario=scenario):
                    directory = stub.write_run(
                        self.root / f"capture-{native}-{scenario}"
                    )
                    identity = (
                        contract.read_json(FIXTURES / "qemu-run/identities.json")
                        if native
                        else stub.identity()
                    )
                    conditions = identity if native else identity["conditions"]
                    conditions["scenarios"] = [scenario]
                    (directory / "identities.json").write_text(json.dumps(identity))
                    path = directory / "verdicts.json"
                    document = contract.read_json(path)
                    document["results"][0]["scenario"] = scenario
                    document["results"].append(
                        {
                            "scenario": "capture",
                            "verdict": "PASS",
                            "checks": [{"check": "captured", "ok": True}],
                        }
                    )
                    path.write_text(json.dumps(document))
                    self.cli(
                        "--run-dir",
                        directory,
                        expected=1 if native and scenario == "itr" else 0,
                    )


    */
}

#[test]
#[ignore]
fn test_json_usage_errors() {
    // TODO: Port this Python logic to Rust
    /*

        for args in (("--run-dir",), ("--unknown",), ("--deployment",)):
            with self.subTest(args=args):
                report = self.cli(*args, expected=2)
                self.assertEqual(report["version"], 1)
                self.assertEqual(report["checks"], {})
                self.assertTrue(report["findings"])
        for args in (("--deployment",), ("--unknown",), ()):
            with self.subTest(sweep_args=args):
                proc = subprocess.run(
                    [sys.executable, str(SCRIPTS / "sweep.py"), "--json", *args],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(proc.stderr, "")
                self.assertFalse(json.loads(proc.stdout)["ok"])


    */
}

#[test]
#[ignore]
fn test_reference_adapter_and_native_qemu() {
    // TODO: Port this Python logic to Rust
    /*

        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "pinned_file_adapter.py"),
                str(ROOT / "evals/e1000/sources.yaml"),
                "harness",
                "--root",
                str(ROOT),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = self.cli(
            "--source-json",
            self.source_file(json.loads(proc.stdout)),
            "--run-dir",
            FIXTURES / "qemu-run",
        )
        self.assertEqual(report["checks"]["fixture"]["verdicts"], {"PASS": 19})


    */
}

#[test]
#[ignore]
fn test_successful_stub_processes() {
    // TODO: Port this Python logic to Rust
    /*

        proc = subprocess.run(
            [sys.executable, str(FIXTURES / "contract_stub.py")],
            capture_output=True,
            text=True,
            check=True,
        )
        path = self.source_file(json.loads(proc.stdout))
        proc = subprocess.run(
            [
                sys.executable,
                str(FIXTURES / "contract_stub.py"),
                "--run-dir",
                str(self.root / "run"),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        directory = json.loads(proc.stdout)["run_dir"]
        self.cli("--source-json", path, "--run-dir", directory)


    */
}

#[test]
#[ignore]
fn test_each_missing_source_provenance_field() {
    // TODO: Port this Python logic to Rust
    /*

        for field in stub.SOURCE_FIELDS:
            with self.subTest(field=field):
                path = self.source_file(stub.omit(stub.source(), field))
                report = self.cli("--source-json", path, expected=1)
                self.assertTrue(report["findings"])


    */
}

#[test]
#[ignore]
fn test_each_missing_backend_provenance_field() {
    // TODO: Port this Python logic to Rust
    /*

        for number, field in enumerate(stub.FIXTURE_FIELDS):
            with self.subTest(field=field):
                directory = stub.write_run(self.root / str(number), field)
                self.cli("--run-dir", directory, expected=1)


    */
}

#[test]
#[ignore]
fn test_each_missing_native_qemu_provenance_field() {
    // TODO: Port this Python logic to Rust
    /*

        identity = contract.read_json(FIXTURES / "qemu-run/identities.json")
        paths = [
            (key,)
            for key in (
                "qemu_version",
                "sha256",
                "driver",
                "accel",
                "scenarios",
                "dut_mem",
                "host_kernel",
                "python",
            )
        ]
        paths += [
            ("sha256", key)
            for key in (
                "qemu",
                "harness:l02harness.py",
                "harness:guest-init.sh",
                "kernel",
                "initramfs",
                "busybox",
            )
        ]
        for parts in paths:
            with self.subTest(field=parts):
                value = copy.deepcopy(identity)
                parent = value if len(parts) == 1 else value[parts[0]]
                del parent[parts[-1]]
                with self.assertRaises(check.Invalid):
                    contract.fixture_identity(value)


    */
}

#[test]
#[ignore]
fn test_malformed_source_data_and_null_hash() {
    // TODO: Port this Python logic to Rust
    /*

        for field, value in [
            ("sha256", None),
            ("sha256", "abc"),
            ("status", []),
            ("checked", "yesterday"),
            ("version", ""),
            ("provenance", None),
        ]:
            data = stub.source()
            data[field] = value
            with self.subTest(field=field):
                self.cli("--source-json", self.source_file(data), expected=1)
        for state in ("blocked", "unknown"):
            data = stub.source()
            data.update(status=state, sha256=None)
            report = self.cli("--source-json", self.source_file(data))
            self.assertEqual(report["checks"]["source"]["status"], state)


    */
}

#[test]
#[ignore]
fn test_fail_error_are_valid_contracts_but_not_passes() {
    // TODO: Port this Python logic to Rust
    /*

        directory = stub.write_run(self.root / "run")
        path = directory / "verdicts.json"
        for outcome in ("FAIL", "ERROR"):
            path.write_text(
                json.dumps(
                    {
                        "overall": outcome,
                        "results": [
                            {
                                "scenario": "itr",
                                "verdict": outcome,
                                "checks": [{"check": "insmod", "verdict": outcome}],
                            }
                        ],
                    }
                )
            )
            report = self.cli("--run-dir", directory)
            self.assertEqual(report["checks"]["fixture"]["overall"], outcome)
            self.assertEqual(report["checks"]["fixture"]["verdicts"], {outcome: 1})


    */
}

#[test]
#[ignore]
fn test_invalid_hash_conditions_and_multiple_requested_scenarios() {
    // TODO: Port this Python logic to Rust
    /*

        for field, value in (
            ("harness_sha256", None),
            ("kernel_sha256", "short"),
            ("image_sha256", True),
            ("conditions", {}),
            ("conditions", {"scenarios": ["itr", "smoke"]}),
        ):
            with self.subTest(field=field, value=value):
                identity = stub.identity()
                identity[field] = value
                with self.assertRaises(check.Invalid):
                    contract.fixture_identity(identity)
        native = contract.read_json(FIXTURES / "qemu-run/identities.json")
        native["scenarios"] = ["itr", "smoke"]
        with self.assertRaisesRegex(check.Invalid, "one scenario"):
            contract.fixture_identity(native)


    */
}

#[test]
#[ignore]
fn test_malformed_or_contradictory_verdicts() {
    // TODO: Port this Python logic to Rust
    /*

        directory = stub.write_run(self.root / "run")
        path = directory / "verdicts.json"
        baseline = contract.read_json(path)
        mutations = [
            lambda d: d.update(overall="SKIP"),
            lambda d: d.update(results=[]),
            lambda d: d["results"].append(copy.deepcopy(d["results"][0])),
            lambda d: d["results"][0].update(checks=[]),
            lambda d: d["results"][0]["checks"][0].update(verdict="FAIL"),
            lambda d: d["results"][0]["checks"][0].update(ok="yes"),
            lambda d: d["results"][0]["checks"].append(
                copy.deepcopy(d["results"][0]["checks"][0])
            ),
            lambda d: d["results"][0]["checks"][0].pop("check"),
        ]
        for number, mutate in enumerate(mutations):
            with self.subTest(case=number):
                document = copy.deepcopy(baseline)
                mutate(document)
                path.write_text(json.dumps(document))
                self.cli("--run-dir", directory, expected=1)


    */
}

#[test]
#[ignore]
fn test_missing_files_bad_json_duplicate_keys_and_skill() {
    // TODO: Port this Python logic to Rust
    /*

        self.cli("--source-json", self.root / "absent", expected=3)
        self.cli("--run-dir", self.root, expected=3)
        path = self.root / "source.json"
        for text in ("{", '{"id": 1, "id": 2}'):
            path.write_text(text)
            self.cli("--source-json", path, expected=1)
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "contract_check.py"), "--skill"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertTrue(proc.stdout.startswith("---\nname:"))


    */
}

#[test]
#[ignore]
fn test_contract_reads_only_and_never_executes_manifest_commands() {
    // TODO: Port this Python logic to Rust
    /*

        manifest = check.read_yaml(deployment.REFERENCE)
        marker = self.root / "should-not-exist"
        for entry in manifest["plugins"]:
            if entry["kind"] in {"source", "fixture"}:
                entry["command"] = ["touch", str(marker)]
        path = self.root / "manifest.yaml"
        path.write_text(check.yaml.safe_dump(manifest))
        fixture = FIXTURES / "qemu-run"
        before = {p.name: p.read_bytes() for p in fixture.iterdir()}
        self.cli("--deployment", path, "--run-dir", fixture)
        self.assertEqual(before, {p.name: p.read_bytes() for p in fixture.iterdir()})
        self.assertFalse(marker.exists())



    */
}

#[test]
#[ignore]
fn test_reference_and_default() {
    // TODO: Port this Python logic to Rust
    /*

        reference = check.read_yaml(deployment.REFERENCE)
        reader = next(p for p in reference["plugins"] if p["id"] == "reader")
        self.assertEqual(deployment.load(), deployment.validate(reference))
        self.assertEqual(deployment.load()["reader"], reader["model"])


    */
}

#[test]
#[ignore]
fn test_user_config_and_explicit_override_preserve_run_store() {
    // TODO: Port this Python logic to Rust
    /*

        settings = deployment.module_at(
            "settings_test", ROOT / "utilities/run-store.py"
        )
        cfg = self.root / "driver-lab"
        cfg.mkdir()
        self.document["plugins"][3]["model"]["name"] = uuid.uuid4().hex
        (cfg / "selected.yaml").write_text(check.yaml.safe_dump(self.document))
        (cfg / "config.toml").write_text(
            'run_store = "runs"\ndeployment = "selected.yaml"\n'
        )
        self.assertEqual(deployment.load(), deployment.validate(self.document))
        self.assertEqual(
            deployment.load(deployment.REFERENCE),
            deployment.validate(check.read_yaml(deployment.REFERENCE)),
        )
        with mock.patch.dict(os.environ, {"DRIVER_LAB_RUNS": ""}):
            self.assertEqual(settings.run_store()[0], Path("runs"))
        (cfg / "config.toml").write_text('deployment = "absent.yaml"\n')
        with self.assertRaises(OSError):
            deployment.load()


    */
}

#[test]
#[ignore]
fn test_bad_manifest_fields() {
    // TODO: Port this Python logic to Rust
    /*

        mutations = [
            (lambda d: d.update(version=True)),
            (lambda d: d.update(plugins={})),
            (lambda d: d["plugins"].append(copy.deepcopy(d["plugins"][0]))),
            (lambda d: d["plugins"][0].update(kind=[])),
            (lambda d: d["plugins"][0].update(via="shell:command")),
            (lambda d: d["plugins"][0].update(command="python3 tool.py")),
            (lambda d: d["plugins"][0].pop("command")),
            (lambda d: d["plugins"][2].update({"class": "unregistered"})),
            (lambda d: d["plugins"][2].update({"class": []})),
            (lambda d: d["plugins"][3].update(model={"name": "x"})),
            (lambda d: d["plugins"].pop()),
        ]
        for number, mutate in enumerate(mutations):
            with self.subTest(case=number):
                document = copy.deepcopy(self.document)
                mutate(document)
                with self.assertRaises(check.Invalid):
                    deployment.validate(document)


    */
}

#[test]
#[ignore]
fn test_producer_class_requires_definition_not_mention() {
    // TODO: Port this Python logic to Rust
    /*

        self.document["plugins"][2]["class"] = "kernel"
        spec = self.root / "spec.md"
        spec.write_text("Mentioning `[kernel]` is not a definition.\n")
        with self.assertRaisesRegex(check.Invalid, "unknown producer class"):
            deployment.validate(self.document, spec)
        spec.write_text(
            "| Tag | Meaning |\n| --- | --- |\n| `[kernel]` | Kernel interface. |\n"
        )
        deployment.validate(self.document, spec)


    */
}

#[test]
#[ignore]
fn test_producer_classes_follow_schema_enum_not_prose() {
    // TODO: Port this Python logic to Rust
    /*

        schema = self.root / "schema.json"
        schema.write_text(json.dumps({
            "$comment": "Mentioning [invented] is not a definition.",
            "$defs": {"support": {"properties": {"class": {"enum": ["doc"]}}}},
        }))
        with mock.patch.object(deployment, "SCHEMA", schema):
            self.assertEqual(deployment.evidence_classes(), {"doc"})
            self.document["plugins"][2]["class"] = "invented"
            with self.assertRaisesRegex(check.Invalid, "unknown producer class"):
                deployment.validate(self.document)
            self.document["plugins"][2]["class"] = "doc"
            deployment.validate(self.document)


    */
}

#[test]
#[ignore]
fn test_empty_schema_classes_refused() {
    // TODO: Port this Python logic to Rust
    /*

        schema = self.root / "schema.json"
        schema.write_text(json.dumps({
            "$defs": {"support": {"properties": {"class": {"enum": []}}}},
        }))
        with mock.patch.object(deployment, "SCHEMA", schema):
            with self.assertRaisesRegex(check.Invalid, "provenance definitions missing"):
                deployment.evidence_classes()


    */
}

#[test]
#[ignore]
fn test_reader_changes_queue_even_when_sufficient_and_never_verdicts() {
    // TODO: Port this Python logic to Rust
    /*

        claims, status, registry = inputs()
        complete_readings(status)
        for eid in ("AF-1-reading-coverage", "SR-8-independent-reading"):
            entry(status, eid)["impact"] = dict(claims=[], changes_status=False)
        before = copy.deepcopy(status)
        original = sweep.sweep(
            claims, status, registry, roles=deployment.load(BASELINE_DEPLOYMENT)
        )
        self.assertTrue(original["stopping"]["sufficient"])
        model = {"name": uuid.uuid4().hex, "version": "2"}
        self.document["plugins"][3]["model"] = model
        roles = deployment.load(self.save())
        changed = sweep.sweep(claims, status, registry, roles=roles)
        units = [
            u for u in changed["stopping"]["queue"] if u["kind"] == "comparison-reading"
        ]
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["model"], model)
        self.assertEqual(units[0]["role"], "reader")
        self.assertEqual(original["entries"], changed["entries"])
        self.assertEqual(status, before)


    */
}

#[test]
#[ignore]
fn test_cli_routes_models_from_config_without_code_changes() {
    // TODO: Port this Python logic to Rust
    /*

        for plugin in self.document["plugins"]:
            if plugin["kind"] == "role":
                plugin["model"]["name"] = uuid.uuid4().hex
        manifest = self.save()
        cfg = self.root / "driver-lab"
        cfg.mkdir()
        (cfg / "config.toml").write_text(
            "deployment = " + json.dumps(str(manifest)) + "\n"
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "sweep.py"),
                str(ROOT / "evals/e1000"),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        queue = json.loads(proc.stdout)["stopping"]["queue"]
        roles = deployment.load(manifest)
        for unit in queue:
            self.assertEqual(unit["model"], roles[unit["role"]])


    */
}

#[test]
#[ignore]
fn test_cli_without_deployment_key_names_reference_models() {
    // TODO: Port this Python logic to Rust
    /*

        """CR-G cross-milestone check: no config key means the reference roles."""
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "sweep.py"),
                str(ROOT / "evals/e1000"),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        queue = json.loads(proc.stdout)["stopping"]["queue"]
        roles = deployment.validate(check.read_yaml(deployment.REFERENCE))
        for unit in queue:
            self.assertEqual(unit["model"], roles[unit["role"]])


    */
}

#[test]
#[ignore]
fn test_implementer_role_does_not_bypass_authorization() {
    // TODO: Port this Python logic to Rust
    /*

        claims, status, registry = inputs()
        item = entry(status, "A-RR-4")
        item["action"] = "implementation"
        item.pop("decision", None)
        self.document["plugins"][4]["model"]["name"] = uuid.uuid4().hex
        roles = deployment.load(self.save())
        report = sweep.sweep(claims, status, registry, roles=roles)["stopping"]
        unit = next(u for u in report["queue"] if "A-RR-4" in u["entries"])
        self.assertEqual(unit["model"], roles["implementer"])
        self.assertEqual(unit["role"], "implementer")
        self.assertEqual(unit["state"], "awaiting decision")
        self.assertNotIn(unit["id"], report["batch"])



    */
}

#[test]
#[ignore]
fn test_good_fixture() {
    // TODO: Port this Python logic to Rust
    /*

        proc = self.run_cli(self.root, "--root", self.root, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertEqual(
            json.loads(proc.stdout)["counts"],
            {"claims": 1, "qualification": 1, "verification": 1},
        )


    */
}

#[test]
#[ignore]
fn test_bad_fixtures() {
    // TODO: Port this Python logic to Rust
    /*

        cases = [
            (
                "missing basis field",
                ("bases", "frozen", "spec_sha256"),
                None,
                "missing fields",
                True,
            ),
            (
                "truncated hash",
                ("bases", "frozen", "spec_sha256"),
                "abcdef12",
                "full SHA-256",
                False,
            ),
            (
                "unknown kind",
                ("entries", 0, "kind"),
                "unknown",
                "invalid entry kind",
                False,
            ),
            (
                "bad status",
                ("entries", 0, "status", "state"),
                "green",
                "invalid status",
                False,
            ),
            (
                "stale without cause",
                ("entries", 0, "status", "state"),
                "stale",
                "nonempty string",
                False,
            ),
            (
                "unknown basis",
                ("entries", 0, "basis"),
                "missing",
                "unknown basis",
                False,
            ),
            ("unknown claim", ("entries", 0, "claim"), "Q99", "unknown claim", False),
            ("empty rule", ("entries", 0, "rule"), "", "nonempty string", False),
            ("unknown field", ("entries", 0, "surprise"), 1, "unknown fields", False),
            ("empty runs", ("entries", 0, "run_ids"), [], "nonempty list", False),
            (
                "broken link",
                ("entries", 0, "evidence"),
                ["missing.md"],
                "does not resolve",
                False,
            ),
            (
                "directory link",
                ("entries", 0, "evidence"),
                ["."],
                "does not resolve",
                False,
            ),
            (
                "external link",
                ("entries", 0, "evidence"),
                ["https://example.invalid/report"],
                "does not resolve",
                False,
            ),
            (
                "escaped link",
                ("entries", 0, "evidence"),
                ["../outside.md"],
                "escapes repository",
                False,
            ),
            (
                "missing supersedes",
                ("entries", 0, "supersedes"),
                ["missing"],
                "target missing",
                False,
            ),
            (
                "self supersedes",
                ("entries", 0, "supersedes"),
                ["q-Q01"],
                "self supersession",
                False,
            ),
            (
                "invalid verdict",
                ("entries", 0, "verdict"),
                "PASS",
                "invalid qualification verdict",
                False,
            ),
            (
                "negative cost",
                ("entries", 0, "cost"),
                {"seconds": -1},
                "invalid cost",
                False,
            ),
            (
                "nonfinite cost",
                ("entries", 0, "cost"),
                {"usd": float("nan")},
                "invalid cost",
                False,
            ),
            (
                "bad date",
                ("entries", 0, "decision"),
                {"who": "user", "date": "tomorrow", "link": "evidence.md"},
                "ISO date",
                False,
            ),
        ]
        original = copy.deepcopy(self.status)
        for title, path, value, expected, remove in cases:
            with self.subTest(title=title):
                self.status = copy.deepcopy(original)
                node = self.status
                for key in path[:-1]:
                    node = node[key]
                if remove:
                    del node[path[-1]]
                else:
                    node[path[-1]] = value
                self.reject(expected)


    */
}

#[test]
#[ignore]
fn test_bad_claim_fixtures() {
    // TODO: Port this Python logic to Rust
    /*

        original = copy.deepcopy(self.claims)
        for field, value, expected in [
            ("cites", [], "nonempty list"),
            ("cites", ["SDM 6"], "invalid value"),
            ("checks", ["packet arrive"], "unknown harness check"),
            ("mandatory", "yes", "mandatory flag"),
            ("evidence", ["absent.md"], "does not resolve"),
            ("defects", [], "lacks detected defect"),
        ]:
            with self.subTest(field=field, value=value):
                self.claims = copy.deepcopy(original)
                self.claims["claims"][0][field] = value
                self.reject(expected)


    */
}

#[test]
#[ignore]
fn test_duplicate_ids_and_missing_qualification() {
    // TODO: Port this Python logic to Rust
    /*

        self.status["entries"].append(copy.deepcopy(self.status["entries"][0]))
        self.reject("duplicate entry ID")
        self.status["entries"] = []
        self.reject("expected one nonsuperseded qualification")


    */
}

#[test]
#[ignore]
fn test_duplicate_claim() {
    // TODO: Port this Python logic to Rust
    /*

        self.claims["claims"].append(copy.deepcopy(self.claims["claims"][0]))
        self.reject("duplicate claim ID")


    */
}

#[test]
#[ignore]
fn test_duplicate_yaml_key() {
    // TODO: Port this Python logic to Rust
    /*

        with (self.root / "claims.yaml").open("a") as out:
            out.write("version: 1\n")
        proc = self.run_cli(self.root, "--root", self.root, "--json")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("duplicate YAML key", proc.stdout)


    */
}

#[test]
#[ignore]
fn test_bad_yaml() {
    // TODO: Port this Python logic to Rust
    /*

        (self.root / "claims.yaml").write_text("claims: [")
        proc = self.run_cli(self.root, "--root", self.root, "--json")
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(json.loads(proc.stdout)["ok"])


    */
}

#[test]
#[ignore]
fn test_supersedes_current_then_history() {
    // TODO: Port this Python logic to Rust
    /*

        old = copy.deepcopy(self.status["entries"][0])
        old["id"] = "old"
        self.status["entries"].append(old)
        self.status["entries"][0]["supersedes"] = ["old"]
        self.reject("target must be superseded")
        old["status"]["state"] = "superseded"
        self.assertEqual(
            checker.validate(self.claims, self.status, self.root)["qualification"], 2
        )


    */
}

#[test]
#[ignore]
fn test_supersedes_cycle() {
    // TODO: Port this Python logic to Rust
    /*

        for name, target in [("old", "older"), ("older", "old")]:
            e = copy.deepcopy(self.status["entries"][0])
            e.update(id=name, supersedes=[target])
            e["status"]["state"] = "superseded"
            self.status["entries"].append(e)
        self.reject("supersedes cycle")


    */
}

#[test]
#[ignore]
fn test_shortfall_requires_approval_and_reopening() {
    // TODO: Port this Python logic to Rust
    /*

        e = self.status["entries"][0]
        e.update(
            verdict="shortfall",
            shortfall={"reason": "unobservable", "reopen": "New tool."},
        )
        self.reject("requires user decision")
        e["decision"] = {"who": "user", "date": "2026-09-25", "link": "evidence.md"}
        checker.validate(self.claims, self.status, self.root)
        e["shortfall"]["reason"] = "difficult"
        self.reject("invalid shortfall reason")
        e["shortfall"] = {"reason": "unobservable", "reopen": ""}
        self.reject("nonempty string")


    */
}

#[test]
#[ignore]
fn test_items() {
    // TODO: Port this Python logic to Rust
    /*

        item = copy.deepcopy(self.status["entries"][0])
        for key in ["claim", "validated_harness_sha256"]:
            del item[key]
        item.update(
            id="item",
            kind="item",
            verdict="Clarify wording.",
            rule="C6-item-classification-2026-09-26",
            target="records",
            source=3,
            disposition={"state": "queued", "destination": "Next records pass."},
        )
        item["class"] = "W"
        self.status["entries"].append(item)
        checker.validate(self.claims, self.status, self.root)
        original = copy.deepcopy(item)
        for field, value, expected in [
            ("class", "", "nonempty string"),
            ("source", True, "invalid item source"),
            ("target", "driver", "invalid item target"),
            ("disposition", {"state": "applied"}, "needs revision"),
            ("disposition", {"state": "queued"}, "nonempty string"),
            ("disposition", {"state": "rejected"}, "nonempty string"),
            (
                "disposition",
                {"state": "shortfall", "reason": "blocked"},
                "nonempty string",
            ),
            ("aliases", ["q-Q01"], "duplicate entry ID or alias"),
        ]:
            with self.subTest(field=field):
                self.status["entries"][-1] = copy.deepcopy(original)
                self.status["entries"][-1][field] = value
                self.reject(expected)


    */
}

#[test]
#[ignore]
fn test_result_cannot_claim_shortfall_as_qualified() {
    // TODO: Port this Python logic to Rust
    /*

        e = self.status["entries"][0]
        e.update(verdict="unqualified")
        result = copy.deepcopy(e)
        del result["validated_harness_sha256"]
        result.update(
            id="result",
            kind="result",
            verdict="PASS",
            round="a2",
            qualification=e["id"],
            qualified_evidence=True,
        )
        self.status["entries"].append(result)
        self.reject("unqualified result labeled qualified")
        result["qualified_evidence"] = False
        checker.validate(self.claims, self.status, self.root)


    */
}

#[test]
#[ignore]
fn test_disposition_fields_match_state() {
    // TODO: Port this Python logic to Rust
    /*

        item = self.add_item({"state": "queued", "destination": "Next brief."})
        states = [
            {"state": "queued", "destination": "Next brief."},
            {"state": "applied", "revision": 1},
            {"state": "shortfall", "reason": "blocked", "reopen": "New tool."},
            {"state": "rejected", "reason": "Already addressed."},
        ]
        extras = {
            "revision": False,
            "reason": ["bad"],
            "reopen": ["bad"],
            "destination": {"nonsense": True},
        }
        for disposition in states:
            item["disposition"] = disposition
            checker.validate(self.claims, self.status, self.root)
            for field, value in extras.items():
                if field in disposition or (
                    disposition["state"] == "shortfall" and field == "destination"
                ):
                    continue
                with self.subTest(state=disposition["state"], field=field):
                    item["disposition"] = {**disposition, field: value}
                    self.reject("unknown fields")
        item["disposition"] = {
            "state": "queued",
            "destination": "Next brief.",
            "revision": False,
            "reopen": ["bad"],
        }
        self.reject("unknown fields")


    */
}

#[test]
#[ignore]
fn test_optional_shortfall_destination() {
    // TODO: Port this Python logic to Rust
    /*

        disposition = {
            "state": "shortfall",
            "reason": "out of scope",
            "reopen": "Hardware fixture available.",
        }
        self.add_item(disposition)
        checker.validate(self.claims, self.status, self.root)
        disposition["destination"] = "HF-1"
        checker.validate(self.claims, self.status, self.root)
        for value in [{"nonsense": True}, ["bad"], False, None, ""]:
            with self.subTest(value=value):
                disposition["destination"] = value
                self.reject("nonempty string")


    */
}

#[test]
#[ignore]
fn test_static_and_formatted_renames() {
    // TODO: Port this Python logic to Rust
    /*

        self.claims["claims"][0]["checks"] = ["interface up (load 2)"]
        checker.validate(self.claims, self.status, self.root)
        p = self.root / "harness.py"
        p.write_text(p.read_text().replace("interface up", "interface ready"))
        self.reject("unknown harness check")


    */
}

#[test]
#[ignore]
fn test_runtime_conditional_handler_and_loop_names() {
    // TODO: Port this Python logic to Rust
    /*

        with (self.root / "harness.py").open("a") as out:
            out.write(
                "\n\ndef scenario_extra(c, mode=None):\n"
                '    c.check("fast path" if mode else "slow path", True)\n'
                "    c.check(f\"link {'up' if mode else 'down'}\", True)\n"
                "    try:\n"
                "        pass\n"
                "    except OSError:\n"
                '        c.check("recovered after error", True)\n'
                "    for item in c.items():\n"
                '        c.check("each item seen", True)\n'
            )
        for name in (
            "fast path",
            "slow path",
            "link up",
            "link down",
            "recovered after error",
            "each item seen",
        ):
            with self.subTest(name=name):
                self.claims["claims"][0]["checks"] = [name]
                checker.validate(self.claims, self.status, self.root)


    */
}

#[test]
#[ignore]
fn test_usage_errors_are_json() {
    // TODO: Port this Python logic to Rust
    /*

        for args in (["--json"], ["--json", "--bogus"], ["--json=1"]):
            with self.subTest(args=args):
                proc = self.run_cli(*args)
                self.assertEqual(proc.returncode, 2)
                payload = json.loads(proc.stdout)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["counts"], {})
                self.assertEqual(len(payload["findings"]), 1)
        proc = self.run_cli(self.root, "--js")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unrecognized arguments: --js", proc.stderr)


    */
}

#[test]
#[ignore]
fn test_formatted_name_is_exact() {
    // TODO: Port this Python logic to Rust
    /*

        self.claims["claims"][0]["checks"] = ["interface up (load 999)"]
        self.reject("unknown harness check")


    */
}

#[test]
#[ignore]
fn test_real_http_conversion_and_format_renames() {
    // TODO: Port this Python logic to Rust
    /*

        harness = (ROOT / "evals/e1000/harness/l02harness.py").read_text()
        original = "{what} over HTTP{via} {label} arrives intact"
        self.assertIn(original, harness)
        self.claims["claims"][0]["checks"] = [
            "4 MiB over HTTP peer to DUT arrives intact"
        ]
        path = self.root / "harness.py"
        path.write_text(harness)
        checker.validate(self.claims, self.status, self.root)
        for suffix in ["!r", "!s", "!a", ":>20", ":"]:
            with self.subTest(suffix=suffix):
                changed = original.replace("{label}", "{label" + suffix + "}")
                path.write_text(harness.replace(original, changed))
                self.reject("unknown harness check")


    */
}

#[test]
#[ignore]
fn test_documentation_is_not_a_check() {
    // TODO: Port this Python logic to Rust
    /*

        with (self.root / "harness.py").open("a") as out:
            out.write('\n"phantom check"\n')
        self.claims["claims"][0]["checks"] = ["phantom check"]
        self.reject("unknown harness check")


    */
}

#[test]
#[ignore]
fn test_harness_is_not_executed() {
    // TODO: Port this Python logic to Rust
    /*

        with (self.root / "harness.py").open("a") as out:
            out.write('\nraise RuntimeError("must never execute")\n')
        checker.validate(self.claims, self.status, self.root)


    */
}

#[test]
#[ignore]
fn test_symlink_escape() {
    // TODO: Port this Python logic to Rust
    /*

        (self.root / "outside").symlink_to(SCRIPT)
        self.status["entries"][0]["evidence"] = ["outside"]
        self.reject("escapes repository")


    */
}

#[test]
#[ignore]
fn test_missing_precondition_usage_and_skill() {
    // TODO: Port this Python logic to Rust
    /*

        (self.root / "status.yaml").unlink()
        proc = self.run_cli(self.root, "--root", self.root, "--json")
        self.assertEqual(proc.returncode, 3)
        self.assertFalse(json.loads(proc.stdout)["ok"])
        self.assertEqual(self.run_cli().returncode, 2)
        proc = self.run_cli("--skill")
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(proc.stdout.startswith("---\n"))


    */
}

#[test]
#[ignore]
fn test_unknown_applied_class_is_a_requirement_in_history() {
    // TODO: Port this Python logic to Rust
    /*

        claims = checker.read_yaml(ROOT / "evals/e1000/claims.yaml")
        status = checker.read_yaml(BASELINE)
        item = next(e for e in status["entries"] if e["id"] == "CF-1-TNCRS")
        item["class"] = "unknown"
        checker.validate(claims, status, ROOT)
        status["revisions"]["8"]["requirement_change"] = False
        with self.assertRaisesRegex(checker.Invalid, "matching R item chain"):
            checker.validate(claims, status, ROOT)


    */
}

#[test]
#[ignore]
fn test_real_campaign() {
    // TODO: Port this Python logic to Rust
    /*

        claims = checker.read_yaml(ROOT / "evals/e1000/claims.yaml")
        status = checker.read_yaml(BASELINE)
        counts = checker.validate(claims, status, ROOT)
        self.assertEqual(
            counts,
            {
                "claims": 28,
                "qualification": 28,
                "result": 28,
                "observation": 8,
                "item": 31,
                "verification": 95,
                "candidate_round": 3,
            },
        )
        self.assertEqual(
            {c["id"] for c in claims["claims"]}, {f"Q{i:02}" for i in range(1, 29)}
        )
        entries = {e["id"]: e for e in status["entries"]}
        self.assertEqual(entries["qualification-Q18"]["verdict"], "shortfall")
        self.assertFalse(entries["result-Q18"]["qualified_evidence"])
        self.assertEqual(entries["SR-8-4"]["target"], "records")
        self.assertEqual(entries["A-RR-1"]["class"], "W")
        self.assertEqual(entries["SR-8-2"]["aliases"], ["A-RR-5"])
        self.assertIn(
            "Next implementer brief", entries["A-RR-7"]["disposition"]["destination"]
        )
        rlec = entries["CF-2-RLEC-comment"]
        self.assertEqual((rlec["class"], rlec["target"]), ("W", "candidate"))
        self.assertEqual(rlec["disposition"], entries["A-RR-7"]["disposition"])
        basis = status["bases"][entries["CF-2-AR-10"]["basis"]]
        self.assertEqual(
            basis["candidate_module_sha256"],
            "df37c7ad143d7a04bf6655ce4e6f8770788677049e6973e6e1a4d294c88eee65",
        )
        self.assertEqual(
            basis["harness_sha256"],
            "884e771c655d627a4b4af11d0526e1445579dad674146b5db8c8121b99e8c03d",
        )
        self.assertEqual(
            basis["emulator"]["sha256"],
            "0cd4112a8f0cb891eb7c10e8df38c9dfeec8c7389bb22db6aa425f0d6fe733dc",
        )
        self.assertIn(
            "evidence/L02f2b.md#requalification",
            entries["qualification-Q15"]["evidence"],
        )
        q15 = next(c for c in claims["claims"] if c["id"] == "Q15")
        self.assertIn(
            "evidence/L02f2b.md#requalification", q15["defects"][0]["evidence"]
        )
        self.assertEqual(
            {e["id"] for e in status["entries"] if e["kind"] == "observation"},
            {f"EM{i}" for i in range(1, 9)},
        )
        self.assertEqual(status["revision_range"], [3, 8])
        self.assertEqual(set(status["revisions"]), {str(r) for r in range(3, 9)})
        readings = [e for e in entries.values() if e["kind"] == "verification"]
        self.assertEqual(len({e["reading_id"] for e in readings}), 22)
        self.assertEqual(
            {e["reading_id"] for e in readings if e["status"]["state"] == "current"},
            {"verify-r8-round2"},
        )
        self.assertEqual(entries["verify-r8-round2"]["independence"], "sequential")
        self.assertEqual(
            entries["CF-1-TNCRS"]["disposition"], {"state": "applied", "revision": 8}
        )
        self.assertIn("CF-1-TNCRS", status["revisions"]["8"]["items"])
        self.assertEqual(
            entries["candidate-CF2-a1"]["supersedes"], ["candidate-CF1-a1"]
        )
        self.assertEqual(
            entries["candidate-CF2-a2"]["supersedes"], ["candidate-CF2-a1"]
        )
        self.assertEqual(
            set(entries["candidate-CF2-a2"]["results"]),
            {f"result-Q{i:02}" for i in range(1, 29)},
        )


    */
}

#[test]
#[ignore]
fn test_history_mutations() {
    // TODO: Port this Python logic to Rust
    /*

        original = copy.deepcopy(self.status)
        cases = [
            (("revisions",), {}, "missing or unexpected revision"),
            (("revision_range",), [True, 8], "invalid revision range"),
            (("revision_range",), [7, 8], "missing or unexpected revision"),
            (("revisions", "8", "spec_sha256"), "b" * 64, "spec_sha256 does not match"),
            (("entries", 1, "text"), "unknown", "spec_sha256 does not match"),
            (("entries", 1, "covers_revisions"), [7, 8], "covered revision"),
            (("entries", 1, "evidence_classes"), ["unknown"], "evidence class"),
            (("entries", 1, "evidence_classes"), [], "nonempty list"),
            (("entries", 1, "sections"), ["2"], "outside reading basis"),
            (("entries", 1, "independence"), "gate", "gate cannot count as accuracy"),
            (("bases", "reading", "model"), None, "requires reader model"),
            (("revisions", "8", "requirement_change"), True, "matching R item chain"),
            (("revisions", "8", "items"), ["missing"], "applied to this spec revision"),
        ]
        for path, value, expected in cases:
            with self.subTest(path=path, value=value):
                self.status = copy.deepcopy(original)
                node = self.status
                for key in path[:-1]:
                    node = node[key]
                node[path[-1]] = value
                self.reject(expected)
        self.status = copy.deepcopy(original)
        self.status["entries"].pop()
        self.reject("missing verification")


    */
}

#[test]
#[ignore]
fn test_draft_hash_and_state() {
    // TODO: Port this Python logic to Rust
    /*

        reading = self.status["entries"][1]
        self.status["revisions"]["8"]["drafts"] = {"round1": "b" * 64}
        reading["text"] = "round1"
        self.reject("spec_sha256 does not match")
        self.status["bases"]["reading"]["spec_sha256"] = "b" * 64
        self.reject("draft reading must remain superseded")
        reading["status"]["state"] = "superseded"
        checker.validate(self.claims, self.status, self.root)


    */
}

#[test]
#[ignore]
fn test_verification_rejects_undefined_optional_fields() {
    // TODO: Port this Python logic to Rust
    /*

        reading = self.status["entries"][1]
        for key, value in [
            ("aliases", ["unexpected-alias"]),
            ("shortfall", {"reason": "blocked", "reopen": "New evidence."}),
        ]:
            with self.subTest(field=key):
                reading[key] = value
                self.reject("unknown fields")
                del reading[key]


    */
}

#[test]
#[ignore]
fn test_real_applied_spec_item_requires_destination() {
    // TODO: Port this Python logic to Rust
    /*

        claims = checker.read_yaml(ROOT / "evals/e1000/claims.yaml")
        original = checker.read_yaml(BASELINE)
        for new_item in (False, True):
            with self.subTest(new_item=new_item):
                status = copy.deepcopy(original)
                if new_item:
                    item = copy.deepcopy(
                        next(e for e in status["entries"] if e["id"] == "CF-1-TNCRS")
                    )
                    item.update(id="new-applied-R")
                    del item["aliases"]
                    status["entries"].append(item)
                else:
                    item = next(e for e in status["entries"] if e["id"] == "SR-8-1")
                item["disposition"] = {"state": "applied", "revision": 999}
                with self.assertRaisesRegex(checker.Invalid, "destination is missing"):
                    checker.validate(claims, status, ROOT)
                item["disposition"]["revision"] = 8
                with self.assertRaisesRegex(
                    checker.Invalid, "missing from destination header"
                ):
                    checker.validate(claims, status, ROOT)


    */
}

#[test]
#[ignore]
fn test_real_public_provenance() {
    // TODO: Port this Python logic to Rust
    /*

        # A live consistency check, not a pinned report: read the current index.
        status = checker.read_yaml(ROOT / "evals/e1000/status.yaml")
        entries = {e["id"]: e for e in status["entries"]}
        link = "evidence/CR2-provenance.md"
        rows = {}
        for line in (ROOT / link).read_text().splitlines():
            if line.startswith("| `verify-"):
                rows[line.split("|")[1].strip().strip("`")] = line
        cited = {
            e["id"]
            for e in entries.values()
            if e["kind"] == "verification" and link in e["evidence"]
        }
        self.assertEqual(len(rows), 43)
        self.assertEqual(set(rows), cited)
        for entry_id, row in rows.items():
            entry = entries[entry_id]
            basis = status["bases"][entry["basis"]]
            self.assertIn(basis["spec_sha256"], row)
            self.assertIn(basis["model"]["name"], row)
            self.assertIn(basis["model"]["version"], row)
            self.assertIn(", ".join(entry["sections"]), row)
            self.assertIn(", ".join(entry["evidence_classes"]), row)
            self.assertIn(entry["run_ids"][0], row)
            self.assertIsNone(basis["dependencies"])
            self.assertIn("dependencies: null", row)
        self.assertEqual(
            entries["verify-r3-adjudication"]["evidence_classes"], ["databook"]
        )
        self.assertEqual(
            status["bases"]["cf1-a1"]["model"], status["bases"]["cf2-a2"]["model"]
        )


    */
}

#[test]
#[ignore]
fn test_reading_slice_coverage() {
    // TODO: Port this Python logic to Rust
    /*

        self.status["bases"]["reading"]["sections_read"] = ["1", "2"]
        self.reject("missing reading section slice")
        reading = copy.deepcopy(self.status["entries"][1])
        reading.update(id="slice2", sections=["2"])
        self.status["entries"].append(reading)
        checker.validate(self.claims, self.status, self.root)
        reading["sections"] = ["1"]
        self.reject("overlapping reading slices")
        reading["sections"] = ["2"]
        reading["verdict"] = "FAIL"
        self.reject("inconsistent reading slices")


    */
}

#[test]
#[ignore]
fn test_requirement_and_candidate_chain() {
    // TODO: Port this Python logic to Rust
    /*

        item = self.add_item({"state": "applied", "revision": 8})
        item.update(target="spec")
        item["class"] = "R"
        revision = self.status["revisions"]["8"]
        revision.update(requirement_change=True, items=["item"])
        candidate = copy.deepcopy(self.status["entries"][0])
        del candidate["claim"]
        del candidate["validated_harness_sha256"]
        candidate.update(
            id="candidate",
            kind="candidate_round",
            round="a1",
            applied_items=["item"],
            verification=["verification"],
            results=[],
            scope="Synthetic acceptance round.",
        )
        self.status["entries"].append(candidate)
        checker.validate(self.claims, self.status, self.root)
        original = copy.deepcopy(candidate)
        for field, value, expected in [
            ("applied_items", ["missing"], "matching applied R item"),
            ("verification", ["q-Q01"], "landed verification link"),
            ("results", ["q-Q01"], "result basis or round mismatch"),
        ]:
            with self.subTest(field=field):
                candidate[field] = value
                self.reject(expected)
                candidate[field] = original[field]
        item["disposition"]["revision"] = 7
        self.reject("applied to this spec revision")


    */
}

#[test]
#[ignore]
fn test_old_unscoped_reading_cannot_remain_current() {
    // TODO: Port this Python logic to Rust
    /*

        self.status["revision_range"] = [8, 9]
        self.status["revisions"]["9"] = copy.deepcopy(self.status["revisions"]["8"])
        reading = copy.deepcopy(self.status["entries"][1])
        reading.update(id="new", reading_id="new", basis="new", covers_revisions=[9])
        self.status["bases"]["new"] = copy.deepcopy(self.status["bases"]["reading"])
        self.status["bases"]["new"]["spec_revision"] = 9
        self.status["entries"].append(reading)
        self.reject("must widen, not stay current")



    */
}

#[test]
#[ignore]
fn test_real_blockers_and_first_batch() {
    // TODO: Port this Python logic to Rust
    /*

        self.status = check.read_yaml(BASELINE)
        report = self.report()
        self.assertFalse(report["sufficient"])
        self.assertEqual(
            [s for s, v in report["conditions"].items() if not v["met"]],
            ["S2", "S3", "S4"],
        )
        self.assertEqual(len(report["conditions"]["S2"]["blockers"]), 13)
        self.assertEqual(
            report["batch"],
            [
                "e1000:second-reading:current",
                "e1000:re-verification:AF-1-reading-coverage",
                "e1000:re-verification:SR-8-independent-reading",
            ],
        )
        self.assertEqual(len(report["waiting"]), 14)
        self.assertEqual(
            report["conditions"]["S3"]["blockers"],
            [
                "AF-1-reading-coverage: impact unrecorded",
                "SR-8-independent-reading: impact unrecorded",
            ],
        )
        self.assertEqual(len(report["open_items"]), 14)
        self.assertTrue(all(r["state"] == "historical" for r in report["round_cap"]))


    */
}

#[test]
#[ignore]
fn test_sufficient_then_new_reader_even_when_sufficient() {
    // TODO: Port this Python logic to Rust
    /*

        complete_readings(self.status)
        original = self.report()
        self.assertTrue(original["sufficient"], original["conditions"])
        self.assertEqual(original["batch"], [])
        for campaign in ("e1000", "second-campaign"):
            self.claims["campaign"] = self.status["campaign"] = self.registry[
                "campaign"
            ] = campaign
            result = sweep.sweep(
                self.claims,
                self.status,
                self.registry,
                reader=dict(name="new reader", version="2"),
                roles=ROLES,
            )["stopping"]
            self.assertTrue(result["sufficient"])
            units = [u for u in result["queue"] if u["kind"] == "comparison-reading"]
            self.assertEqual(len(units), 1)
            self.assertEqual(units[0]["id"], campaign + ":comparison-reading:current")
            self.assertEqual(units[0]["model"]["version"], "2")


    */
}

#[test]
#[ignore]
fn test_sequential_reads_are_one_lineage() {
    // TODO: Port this Python logic to Rust
    /*

        complete_readings(self.status)
        for rid in ("synthetic-full-1", "synthetic-full-2"):
            entry(self.status, rid)["independence"] = "sequential"
        self.assertFalse(self.report()["conditions"]["S4"]["met"])


    */
}

#[test]
#[ignore]
fn test_gate_adjudication_draft_and_partial_reads_cannot_fill_s4() {
    // TODO: Port this Python logic to Rust
    /*

        for mutation in ("adjudication", "gate", "partial", "draft"):
            with self.subTest(mutation=mutation):
                self.setUp()
                complete_readings(self.status)
                for rid in ("synthetic-full-1", "synthetic-full-2"):
                    value = entry(self.status, rid)
                    if mutation == "gate":
                        value.update(independence="gate", purpose="acceptance")
                    elif mutation == "partial":
                        value["sections"] = ["5.5"]
                        self.status["bases"][rid]["sections_read"] = ["5.5"]
                    elif mutation == "draft":
                        value["text"] = "verify-r8-round1"
                        self.status["bases"][rid]["spec_sha256"] = self.status[
                            "revisions"
                        ]["8"]["drafts"]["verify-r8-round1"]
                        value["status"].update(state="superseded", stale_since=None)
                    else:
                        value["independence"] = mutation
                self.assertFalse(self.report()["conditions"]["S4"]["met"])


    */
}

#[test]
#[ignore]
fn test_no_scope_no_batch() {
    // TODO: Port this Python logic to Rust
    /*

        del self.status["scope"]
        report = self.report()
        self.assertFalse(report["conditions"]["S1"]["met"])
        self.assertEqual(report["batch"], [])


    */
}

#[test]
#[ignore]
fn test_unaccepted_evidence_blocks_s2() {
    // TODO: Port this Python logic to Rust
    /*

        self.status["scope"]["accepted_classes"]["Q01"] = ["databook"]
        self.assertIn("Q01", self.report()["conditions"]["S2"]["blockers"][0])


    */
}

#[test]
#[ignore]
fn test_shortfall_needs_user_and_reopening_reason() {
    // TODO: Port this Python logic to Rust
    /*

        for change in ("operator", "missing-reopen", "bad-reason"):
            with self.subTest(change=change):
                self.setUp()
                value = self.item("qualification-Q18")
                if change == "operator":
                    value["decision"]["who"] = "operator"
                elif change == "missing-reopen":
                    value["shortfall"]["reopen"] = ""
                else:
                    value["shortfall"]["reason"] = "too hard"
                with self.assertRaises(check.Invalid):
                    self.report()


    */
}

#[test]
#[ignore]
fn test_w_and_records_do_not_start_revisions() {
    // TODO: Port this Python logic to Rust
    /*

        report = self.report()
        wording_items = {"SR-8-1", "SR-8-2", "SR-8-3", "A-RR-1"}
        self.assertTrue(report["conditions"]["S3"]["met"])
        self.assertTrue(
            all(not wording_items.intersection(u["entries"]) for u in report["queue"])
        )
        self.item("SR-8-4")["class"] = "R"
        report = self.report()
        self.assertTrue(report["conditions"]["S3"]["met"])
        self.assertFalse(any("SR-8-4" in u["entries"] for u in report["queue"]))


    */
}

#[test]
#[ignore]
fn test_unknown_class_is_r_and_requires_decision() {
    // TODO: Port this Python logic to Rust
    /*

        self.item()["class"] = "uncertain"
        report = self.report()
        self.assertFalse(report["conditions"]["S3"]["met"])
        row = next(i for i in report["open_items"] if i["id"] == "SR-8-1")
        self.assertEqual(row["effective_class"], "R")
        unit = next(u for u in report["queue"] if u["kind"] == "requirement-change")
        self.assertEqual(unit["tier"], 2)
        self.assertEqual(unit["state"], "awaiting decision")
        self.assertNotIn(unit["id"], report["batch"])


    */
}

#[test]
#[ignore]
fn test_review_e_without_impact_is_unresolved() {
    // TODO: Port this Python logic to Rust
    /*

        for eid in ("AF-1-reading-coverage", "SR-8-independent-reading"):
            with self.subTest(item=eid):
                self.setUp()
                del self.item(eid)["impact"]
                report = self.report()
                self.assertFalse(report["conditions"]["S3"]["met"])
                self.assertIn(
                    f"{eid}: impact unrecorded", report["conditions"]["S3"]["blockers"]
                )
                row = next(i for i in report["open_items"] if i["id"] == eid)
                self.assertIn("impact unrecorded", row["action"])
                self.assertNotIn("no change", row["action"])
                self.assertTrue(any(eid in u["entries"] for u in report["queue"]))


    */
}

#[test]
#[ignore]
fn test_version_two_preserves_freshness_independently_of_ok() {
    // TODO: Port this Python logic to Rust
    /*

        complete_readings(self.status)
        result = sweep.sweep(self.claims, self.status, self.registry, roles=ROLES)
        self.assertEqual(result["version"], 2)
        self.assertTrue(result["ok"])
        self.assertTrue(result["entries"])
        self.assertFalse(result["fresh"])
        self.assertEqual(
            result["fresh"],
            not result["entries"]
            and not result["stale_controls"]
            and not result["unavailable"],
        )
        self.assertIn("version 2", sweep.SKILL)
        self.assertIn("fresh", sweep.SKILL)
        for value in self.status["entries"]:
            if value["status"]["state"] == "stale":
                value["status"].update(state="superseded", stale_since=None)
        result = sweep.sweep(self.claims, self.status, self.registry, roles=ROLES)
        self.assertFalse(result["entries"])
        self.assertTrue(result["fresh"])
        source(self.registry, "candidate")["status"] = "unknown"
        result = sweep.sweep(self.claims, self.status, self.registry, roles=ROLES)
        self.assertFalse(result["fresh"])
        self.assertFalse(result["ok"])


    */
}

#[test]
#[ignore]
fn test_e_only_reopens_when_claim_status_changes_in_scope() {
    // TODO: Port this Python logic to Rust
    /*

        value = self.item()
        value["class"] = "E"
        for claims, changed, expected in [
            ([], True, False),
            (["Q01"], False, False),
            (["Q01"], True, True),
        ]:
            value["impact"] = dict(claims=claims, changes_status=changed)
            report = self.report()
            self.assertEqual(
                any(u["kind"] == "evidence-revision" for u in report["queue"]), expected
            )
            self.assertEqual(report["conditions"]["S3"]["met"], not expected)
        del value["impact"]
        self.assertFalse(self.report()["conditions"]["S3"]["met"])


    */
}

#[test]
#[ignore]
fn test_all_tier_two_actions_require_their_own_user_decision() {
    // TODO: Port this Python logic to Rust
    /*

        complete_readings(self.status)
        value = self.item("A-RR-4")
        for action in (
            "requirement-change",
            "implementation",
            "hardware-run",
            "recall",
            "adopt-source",
            "accept-shortfall",
            "outward-report",
        ):
            for who in (None, "operator", "user"):
                with self.subTest(action=action, who=who):
                    value["action"] = action
                    value.pop("decision", None)
                    if who:
                        value["decision"] = dict(
                            who=who, date="2026-09-27", link="evidence/CR4.md"
                        )
                    report = self.report()
                    unit = next(u for u in report["queue"] if "A-RR-4" in u["entries"])
                    self.assertEqual(unit["tier"], 2)
                    self.assertEqual(unit["id"] in report["batch"], who == "user")
                    self.assertNotIn(
                        "e1000:outward-report:QF-1-F1-upstream", report["batch"]
                    )


    */
}

#[test]
#[ignore]
fn test_fourth_unit_waits_and_forged_ready_tier_two_is_excluded() {
    // TODO: Port this Python logic to Rust
    /*

        queue = [dict(id=str(i), tier=1, state="ready") for i in range(4)]
        queue.insert(0, dict(id="unauthorized", tier=2, state="ready"))
        self.assertEqual(stopping.select_batch(queue), (["0", "1", "2"], ["3"]))


    */
}

#[test]
#[ignore]
fn test_rule_changes_flagged_and_excluded_not_compared() {
    // TODO: Port this Python logic to Rust
    /*

        complete_readings(self.status)
        self.item("qualification-Q01")["rule"] = "different-A6"
        for rid in ("synthetic-full-1", "synthetic-full-2"):
            self.item(rid)["rule"] = "different-A1"
        report = self.report()
        self.assertFalse(report["sufficient"])
        self.assertFalse(report["conditions"]["S2"]["met"])
        self.assertFalse(report["conditions"]["S4"]["met"])
        self.assertEqual(len(report["policy_changes"]), 3)
        self.assertTrue(all(not r["compared"] for r in report["policy_changes"]))


    */
}

#[test]
#[ignore]
fn test_latest_reading_r_item_blocks_s5_even_after_disposition() {
    // TODO: Port this Python logic to Rust
    /*

        complete_readings(self.status)
        self.item("synthetic-full-2")["assessment"]["r_items"] = ["CF-1-TNCRS"]
        self.assertFalse(self.report()["conditions"]["S5"]["met"])
        self.item("synthetic-full-2")["assessment"]["r_items"] = []
        self.assertTrue(self.report()["conditions"]["S5"]["met"])


    */
}

#[test]
#[ignore]
fn test_unclassified_and_accuracy_failures_block_s3() {
    // TODO: Port this Python logic to Rust
    /*

        complete_readings(self.status)
        self.item("synthetic-full-2")["assessment"]["accuracy_failures"] = 1
        self.assertFalse(self.report()["conditions"]["S3"]["met"])
        del self.item("synthetic-full-2")["assessment"]
        self.assertFalse(self.report()["conditions"]["S3"]["met"])


    */
}

#[test]
#[ignore]
fn test_post_cap_and_unknown_date_overrun_blocks_reading_batch() {
    // TODO: Port this Python logic to Rust
    /*

        for started in ("2026-09-27", None):
            self.status["revisions"]["7"].pop("started", None)
            if started:
                self.status["revisions"]["7"]["started"] = started
            report = self.report()
            row = next(r for r in report["round_cap"] if r["revision"] == 7)
            self.assertEqual(row["state"], "awaiting decision")
            self.assertNotIn("e1000:second-reading:current", report["batch"])
            self.assertFalse(report["sufficient"])


    */
}

#[test]
#[ignore]
fn test_unavailable_identity_cannot_be_sufficient() {
    // TODO: Port this Python logic to Rust
    /*

        complete_readings(self.status)
        source(self.registry, "candidate")["status"] = "unknown"
        self.assertFalse(self.report()["sufficient"])


    */
}

#[test]
#[ignore]
fn test_reached_cap_holds_no_queued_reading() {
    // TODO: Port this Python logic to Rust
    /*

        """A capped revision's findings go to the user; later readings still run.

        Revision 8 stands in for a capped revision (CR8's revision 9): its third
        round reaches the cap, and the independent second reading that the next
        text needs, a comparison reading and re-verification all stay ready.
        """
        complete_readings(self.status)
        self.status["entries"] = [
            e for e in self.status["entries"] if e["id"] != "synthetic-full-2"
        ]
        self.status["revisions"]["8"]["started"] = "2026-09-27"
        roles = copy.deepcopy(ROLES)
        roles["reader"] = {"name": "another reader", "version": "1"}
        report = sweep.sweep(self.claims, self.status, self.registry, roles=roles)[
            "stopping"
        ]
        self.assertEqual(report["round_cap"][-1]["state"], "limit reached")
        self.assertFalse(report["sufficient"])
        units = {u["id"]: u for u in report["queue"]}
        for kind in ("second-reading", "comparison-reading"):
            with self.subTest(kind=kind):
                self.assertEqual(units[f"e1000:{kind}:current"]["state"], "ready")
        self.assertEqual(report["batch"][0], "e1000:second-reading:current")
        self.assertTrue(
            all(
                u["state"] == "ready"
                for u in report["queue"]
                if u["kind"] == "re-verification"
            )
        )


    */
}

#[test]
#[ignore]
fn test_adjudication_is_not_a_round() {
    // TODO: Port this Python logic to Rust
    /*

        self.status["revisions"]["8"]["started"] = "2026-09-27"
        adjudication = copy.deepcopy(entry(self.status, "verify-r8-round2"))
        adjudication.update(
            id="synthetic-adjudication",
            reading_id="synthetic-adjudication",
            independence="adjudication",
            round="adjudication",
            sequence=23,
            supersedes=[],
        )
        self.status["entries"].append(adjudication)
        report = self.report()
        self.assertNotIn(8, [r["revision"] for r in report["round_cap"]])
        adjudication["independence"] = "independent"
        report = self.report()
        row = next(r for r in report["round_cap"] if r["revision"] == 8)
        self.assertEqual(row["state"], "limit reached")


    */
}

#[test]
#[ignore]
fn test_mandatory_item_shortfall_needs_its_own_user_decision() {
    // TODO: Port this Python logic to Rust
    /*

        value = self.item()
        value["class"] = "E"
        value["disposition"] = dict(
            state="shortfall", reason="unobservable", reopen="new instrument"
        )
        with self.assertRaisesRegex(check.Invalid, "explicit claim impact"):
            self.report()
        value["impact"] = dict(claims=["Q01"], changes_status=True)
        with self.assertRaisesRegex(check.Invalid, "user decision"):
            self.report()
        value["decision"] = dict(who="user", date="2026-09-27", link="evidence/CR4.md")
        self.report()


    */
}

#[test]
#[ignore]
fn test_sequences_and_impact_types_fail_closed() {
    // TODO: Port this Python logic to Rust
    /*

        self.item("verify-r8-round2")["sequence"] = 1
        with self.assertRaisesRegex(check.Invalid, "duplicate reading sequence"):
            self.report()
        self.setUp()
        for value in (
            dict(claims=["Q99"], changes_status=True),
            dict(claims=["Q01"], changes_status="yes"),
        ):
            self.item()["impact"] = value
            with self.assertRaises(check.Invalid):
                self.report()


    */
}

#[test]
#[ignore]
fn test_review_evidence_impact_reopens_and_unknown_review_is_r() {
    // TODO: Port this Python logic to Rust
    /*

        value = self.item("AF-1-reading-coverage")
        value["impact"] = dict(claims=["Q01"], changes_status=True)
        report = self.report()
        self.assertFalse(report["conditions"]["S3"]["met"])
        self.assertTrue(any(value["id"] in u["entries"] for u in report["queue"]))
        value["class"] = "unknown"
        report = self.report()
        self.assertFalse(report["conditions"]["S3"]["met"])
        unit = next(u for u in report["queue"] if value["id"] in u["entries"])
        self.assertEqual(unit["tier"], 2)


    */
}

#[test]
#[ignore]
fn test_tier_two_action_cannot_hide_spec_evidence_impact() {
    // TODO: Port this Python logic to Rust
    /*

        value = self.item()
        value["class"] = "E"
        value["impact"] = dict(claims=["Q01"], changes_status=True)
        value["action"] = "adopt-source"
        report = self.report()
        self.assertFalse(report["conditions"]["S3"]["met"])
        unit = next(u for u in report["queue"] if value["id"] in u["entries"])
        self.assertEqual(unit["tier"], 2)
        self.assertNotIn(unit["id"], report["batch"])



    */
}

#[test]
#[ignore]
fn test_matrix() {
    // TODO: Port this Python logic to Rust
    /*

        for row in matrix():
            with self.subTest(row=row["row"]):
                self.assertEqual(row["stale"], row["expected_stale"])
                self.assertEqual(row["contested"], row["expected_contested"])
                self.assertTrue(row["queue_ok"], row)


    */
}

#[test]
#[ignore]
fn test_baseline_and_no_source_access_or_mutation() {
    // TODO: Port this Python logic to Rust
    /*

        before = copy.deepcopy((self.claims, self.status, self.registry))
        with mock.patch.object(
            Path, "open", side_effect=AssertionError("source read")
        ), mock.patch.object(
            Path, "read_bytes", side_effect=AssertionError("source read")
        ), mock.patch.object(
            check, "harness_check_names", side_effect=AssertionError("source parsed")
        ):
            result = self.run_sweep()
        self.assertEqual(newly_affected(result), [])
        self.assertEqual(before, (self.claims, self.status, self.registry))
        self.assertTrue(
            all(e["id"] not in result["eligible"] for e in result["entries"])
        )
        self.assertEqual(len(result["entries"]), 83)


    */
}

#[test]
#[ignore]
fn test_real_index() {
    // TODO: Port this Python logic to Rust
    /*

        self.status = check.read_yaml(BASELINE)
        result = self.run_sweep()
        self.assertEqual(
            newly_affected(result),
            [
                "qualification-" + c
                for c in [
                    "Q01",
                    "Q02",
                    "Q03",
                    "Q11",
                    "Q12",
                    "Q13",
                    "Q14",
                    "Q15",
                    "Q16",
                    "Q17",
                    "Q18",
                    "Q24",
                    "Q26",
                ]
            ],
        )
        self.assertEqual(result["counts"], dict(current=84, stale=96, superseded=13))
        self.assertEqual(result["unmapped_harness"], [])
        by_id = {e["id"]: e for e in result["entries"]}
        self.assertEqual(by_id["qualification-Q01"]["stale_since"], "spec-r6")
        self.assertEqual(by_id["qualification-Q02"]["stale_since"], "spec-r7")


    */
}

#[test]
#[ignore]
fn test_spec_wording_and_declared_dependencies() {
    // TODO: Port this Python logic to Rust
    /*

        row = mutate(self.registry, "spec", sections=["5.3"])
        row.update(revision=9, requirement_change=False)
        basis = self.status["bases"]["verify-r8-round2"]
        basis["dependencies"] = []
        self.assertEqual(newly_affected(self.run_sweep()), ["qualification-Q01"])
        basis["dependencies"] = ["5"]
        self.assertEqual(
            newly_affected(self.run_sweep()), ["qualification-Q01", "verify-r8-round2"]
        )
        self.assertFalse(sweep.overlap(["5.1"], ["5.10"]))
        self.assertTrue(sweep.overlap(["5"], ["5.10"]))


    */
}

#[test]
#[ignore]
fn test_spec_unknown_header_widens() {
    // TODO: Port this Python logic to Rust
    /*

        row = source(self.registry, "spec")
        row.update(revision=9, sha256="a" * 64)
        expected = [f"qualification-Q{i:02}" for i in range(1, 29)]
        expected += [f"result-Q{i:02}" for i in range(1, 29)]
        expected += ["candidate-CF2-a2", "verify-r8-round2"]
        self.assertEqual(newly_affected(self.run_sweep()), sorted(expected))


    */
}

#[test]
#[ignore]
fn test_document_mapping_and_missing_citations() {
    // TODO: Port this Python logic to Rust
    /*

        mutate(self.registry, "8254x-sdm", sections=["13.4"])
        self.registry["citations"] = {"verify-r8-round2": {"8254x-sdm": ["14"]}}
        self.assertEqual(newly_affected(self.run_sweep()), [])
        self.registry["citations"]["verify-r8-round2"]["8254x-sdm"] = ["13"]
        self.assertEqual(newly_affected(self.run_sweep()), ["verify-r8-round2"])
        self.registry["citations"] = {}
        self.assertEqual(newly_affected(self.run_sweep()), ["verify-r8-round2"])


    */
}

#[test]
#[ignore]
fn test_kernel_leaves_manual_verdicts_current() {
    // TODO: Port this Python logic to Rust
    /*

        mutate(self.registry, "linux-e1000_main-c")
        entry = next(e for e in self.status["entries"] if e["id"] == "verify-r8-round2")
        entry["evidence_classes"] = ["databook"]
        self.assertEqual(newly_affected(self.run_sweep()), [])


    */
}

#[test]
#[ignore]
fn test_reference_control_runs() {
    // TODO: Port this Python logic to Rust
    /*

        mutate(self.registry, "reference")
        result = self.run_sweep()
        expected = {
            run
            for c in self.claims["claims"]
            for d in c["defects"]
            for run in d["control_runs"]
        }
        self.assertEqual({c["id"] for c in result["stale_controls"]}, expected)
        self.assertEqual(newly_affected(result), [])


    */
}

#[test]
#[ignore]
fn test_harness_widening_and_bad_names() {
    // TODO: Port this Python logic to Rust
    /*

        row = mutate(
            self.registry, "harness", checks=["not a check"], scenarios=["itr"]
        )
        result = self.run_sweep()
        expected = sorted(
            "qualification-" + c["id"]
            for c in self.claims["claims"]
            if "itr" in c["scenarios"]
        )
        self.assertEqual(newly_affected(result), expected)
        self.assertEqual(result["unmapped_harness"], [])
        reviewed = copy.deepcopy(row["changes"][0])
        for mapping in [
            dict(checks=None, scenarios=None),
            dict(checks=["MAC matches QEMU's"], scenarios=None, reviewed=False),
            dict(checks=["unknown check"], scenarios=["unknown scenario"]),
        ]:
            with self.subTest(mapping=mapping):
                row["changes"][0] = dict(copy.deepcopy(reviewed), **mapping)
                result = self.run_sweep()
                self.assertEqual(
                    newly_affected(result),
                    [f"qualification-Q{i:02}" for i in range(1, 29)],
                )
                self.assertEqual(result["unmapped_harness"], ["harness"])


    */
}

#[test]
#[ignore]
fn test_mapping_must_cover_exact_old_hash() {
    // TODO: Port this Python logic to Rust
    /*

        row = mutate(self.registry, "harness", checks=["MAC matches QEMU's"])
        row["changes"][0]["from_sha256"] = "b" * 64
        self.assertEqual(len(newly_affected(self.run_sweep())), 28)
        row["changes"][0]["to_sha256"] = "b" * 64
        with self.assertRaisesRegex(check.Invalid, "current hash"):
            self.run_sweep()


    */
}

#[test]
#[ignore]
fn test_guest_kernel_and_image() {
    // TODO: Port this Python logic to Rust
    /*

        mutate(self.registry, "guest-kernel")
        self.assertEqual(len(newly_affected(self.run_sweep())), 65)
        self.claims, self.status, self.registry = inputs()
        mutate(self.registry, "guest-image-candidate")
        self.assertEqual(len(newly_affected(self.run_sweep())), 29)


    */
}

#[test]
#[ignore]
fn test_emulated_reading_follows_observation_dependency() {
    // TODO: Port this Python logic to Rust
    /*

        entry = next(e for e in self.status["entries"] if e["id"] == "verify-r8-round2")
        entry["evidence_classes"] = ["emulated"]
        mutate(self.registry, "qemu-e1000")
        self.assertIn("verify-r8-round2", newly_affected(self.run_sweep()))
        entry["evidence_classes"] = ["databook"]
        self.assertNotIn("verify-r8-round2", newly_affected(self.run_sweep()))


    */
}

#[test]
#[ignore]
fn test_unrecorded_compiler_does_not_trigger() {
    // TODO: Port this Python logic to Rust
    /*

        self.registry["sources"] = [
            s for s in self.registry["sources"] if s["kind"] != "toolchain"
        ]
        self.assertEqual(newly_affected(self.run_sweep()), [])
        row = copy.deepcopy(source(self.registry, "candidate"))
        row.update(
            id="compiler",
            kind="toolchain",
            version="new compiler",
            sha256=None,
            file=None,
        )
        self.registry["sources"].append(row)
        for basis in self.status["bases"].values():
            basis["toolchain"] = None
        self.assertEqual(newly_affected(self.run_sweep()), [])


    */
}

#[test]
#[ignore]
fn test_recorded_toolchain() {
    // TODO: Port this Python logic to Rust
    /*

        source(self.registry, "toolchain")["version"] = "exact compiler build"
        result = self.run_sweep()
        self.assertEqual(len(newly_affected(result)), 57)


    */
}

#[test]
#[ignore]
fn test_hardware_widening_preserves_candidate() {
    // TODO: Port this Python logic to Rust
    /*

        self.registry["contradictions"] = [
            dict(
                observation="EM1",
                since="new-run",
                conflict="spec/section12.md#conflict-EM1",
            )
        ]
        result = self.run_sweep()
        expected = sorted(
            "qualification-" + c["id"]
            for c in self.claims["claims"]
            if sweep.overlap(
                c["cites"],
                next(e["sections"] for e in self.status["entries"] if e["id"] == "EM1"),
            )
        )
        self.assertEqual(newly_affected(result), sorted(["EM1"] + expected))
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertTrue(
            all(f"result-Q{i:02}" in result["eligible"] for i in range(1, 29))
        )


    */
}

#[test]
#[ignore]
fn test_invalid_registry_and_missing_identity() {
    // TODO: Port this Python logic to Rust
    /*

        source(self.registry, "harness")["status"] = "blocked"
        result = self.run_sweep()
        self.assertEqual(result["unavailable"], ["harness"])
        self.assertFalse(result["ok"])
        for path in ["/private/file", "../escape", "sub/../../escape", "C:\\file"]:
            with self.subTest(path=path):
                source(self.registry, "harness")["file"]["path"] = path
                with self.assertRaises(check.Invalid):
                    self.run_sweep()


    */
}

#[test]
#[ignore]
fn test_index_contested_observation_invalidates_dependents() {
    // TODO: Port this Python logic to Rust
    /*

        entries = {entry["id"]: entry for entry in self.status["entries"]}
        entries["EM1"]["status"].update(
            state="contested", reason="Hardware contradicts this observation."
        )
        self.registry["premises"] = {"Q01": ["EM1"]}
        entries["verify-r8-round2"]["evidence_classes"] = ["emulated"]
        self.assertEqual(self.registry["contradictions"], [])
        result = self.run_sweep()
        affected = {entry["id"]: entry for entry in result["entries"]}
        self.assertEqual(affected["EM1"]["state"], "contested")
        for entry_id in ("qualification-Q01", "verify-r8-round2"):
            self.assertEqual(affected[entry_id]["state"], "stale")
            self.assertNotIn(entry_id, result["eligible"])
            self.assertEqual(affected[entry_id]["stale_since"], "index:EM1")
        self.assertEqual(result["conflicts"], [])
        self.assertIn("candidate-CF2-a2", result["eligible"])


    */
}

#[test]
#[ignore]
fn test_null_ok_hash_rejected_per_kind() {
    // TODO: Port this Python logic to Rust
    /*

        for kind in sorted(source_registry.KINDS):
            registry = copy.deepcopy(self.registry)
            row = source(registry, "candidate")
            row.update(kind=kind, sha256=None, version="new candidate")
            if kind == "spec":
                row["revision"] = 9
            with self.subTest(kind=kind):
                if kind in {"toolchain", "model", "fixture"}:
                    source_registry.validate(registry)
                else:
                    with self.assertRaisesRegex(check.Invalid, "full SHA-256"):
                        source_registry.validate(registry)
                    row["status"] = "unknown"
                    source_registry.validate(registry)


    */
}

#[test]
#[ignore]
fn test_null_candidate_hash_json_error() {
    // TODO: Port this Python logic to Rust
    /*

        source(self.registry, "candidate").update(sha256=None, version="new candidate")
        for script, proc in self.registry_clis(self.registry):
            with self.subTest(script=script):
                self.assertEqual(proc.returncode, 1)
                payload = json.loads(proc.stdout)
                self.assertFalse(payload["ok"])
                self.assertIn("full SHA-256", payload["findings"][0])
                self.assertEqual(proc.stderr, "")


    */
}

#[test]
#[ignore]
fn test_malformed_registry_types_json_error() {
    // TODO: Port this Python logic to Rust
    /*

        for field, value in (("kind", []), ("status", {}), ("file.root", [])):
            registry = copy.deepcopy(self.registry)
            row = source(registry, "candidate")
            if field == "file.root":
                row["file"]["root"] = value
            else:
                row[field] = value
            for script, proc in self.registry_clis(registry):
                with self.subTest(field=field, script=script):
                    self.assertEqual(proc.returncode, 1)
                    payload = json.loads(proc.stdout)
                    self.assertFalse(payload["ok"])
                    self.assertIn("nonempty string", payload["findings"][0])
                    self.assertEqual(proc.stderr, "")


    */
}

#[test]
#[ignore]
fn test_cli_json_skill_and_errors() {
    // TODO: Port this Python logic to Rust
    /*

        with tempfile.TemporaryDirectory() as temp:
            # No user config or run store: the reference manifest applies.
            env = dict(os.environ, XDG_CONFIG_HOME=temp)
            env.pop("DRIVER_LAB_RUNS", None)
            campaign = Path(temp) / "campaign"
            campaign.mkdir()
            shutil.copy(ROOT / "evals/e1000/claims.yaml", campaign / "claims.yaml")
            shutil.copy(BASELINE, campaign / "status.yaml")
            shutil.copy(BASELINE_SOURCES, campaign / "sources.yaml")


    */
}

#[test]
#[ignore]
fn test_hash_pin_match_and_provenance() {
    // TODO: Port this Python logic to Rust
    /*

        result = adapter.inspect(self.source, self.root)
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["matches_pin"])
        self.assertNotIn("opaque bytes", json.dumps(result))
        self.source["expected_sha256"] = result["sha256"]
        self.assertTrue(adapter.inspect(self.source, self.root)["matches_pin"])
        self.assertEqual(result["provenance"]["adapter"], "pinned-file")


    */
}

#[test]
#[ignore]
fn test_absent_blocked_and_symlink_escape() {
    // TODO: Port this Python logic to Rust
    /*

        self.source["file"] = None
        self.assertEqual(adapter.inspect(self.source, self.root)["status"], "unknown")
        self.source["file"] = dict(root="repository", path="absent")
        self.assertEqual(adapter.inspect(self.source, self.root)["status"], "blocked")
        (self.root / "escape").symlink_to(ROOT / "README.md")
        self.source["file"]["path"] = "escape"
        self.assertEqual(adapter.inspect(self.source, self.root)["status"], "blocked")


    */
}

#[test]
#[ignore]
fn test_write_dry_run_and_idempotence() {
    // TODO: Port this Python logic to Rust
    /*

        original = self.path.read_bytes()
        proc = self.cli("--write", "--dry-run")
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(json.loads(proc.stdout)["would_update"])
        self.assertEqual(self.path.read_bytes(), original)
        proc = self.cli("--write")
        self.assertTrue(json.loads(proc.stdout)["updated"])
        updated = self.path.read_bytes()
        self.assertNotEqual(updated, original)
        self.cli("--write")
        self.assertEqual(self.path.read_bytes(), updated)
        row = source(check.read_yaml(self.path), "candidate")
        self.assertEqual(row["expected_sha256"], self.source["expected_sha256"])
        self.assertNotEqual(row["sha256"], row["expected_sha256"])


    */
}

#[test]
#[ignore]
fn test_run_store_and_missing_dependency() {
    // TODO: Port this Python logic to Rust
    /*

        self.source["file"] = dict(root="run_store", path="opaque")
        self.assertEqual(adapter.inspect(self.source, ROOT, self.root)["status"], "ok")
        self.source["file"]["path"] = "absent"
        self.assertEqual(
            adapter.inspect(self.source, ROOT, self.root)["status"], "blocked"
        )
        with mock.patch.object(check, "yaml", None), mock.patch(
            "builtins.print"
        ) as output:
            self.assertEqual(adapter.main([str(self.path), "candidate", "--json"]), 3)
            self.assertFalse(json.loads(output.call_args.args[0])["ok"])


    */
}

#[test]
#[ignore]
fn test_blocked_write_leaves_registry_unchanged() {
    // TODO: Port this Python logic to Rust
    /*

        self.source["sha256"] = "c" * 64
        self.source["changes"] = [
            dict(
                from_sha256="d" * 64,
                to_sha256="c" * 64,
                since="reviewed change",
                reviewed=True,
                sections=None,
                checks=None,
                scenarios=None,
                evidence=["synthetic reviewed diff"],
            )
        ]
        self.path.write_text(check.yaml.safe_dump(self.registry))
        self.file.unlink()
        original = self.path.read_bytes()
        for args in (("--write",), ("--write", "--dry-run")):
            with self.subTest(args=args):
                proc = self.cli(*args)
                self.assertEqual(proc.returncode, 3)
                payload = json.loads(proc.stdout)
                self.assertEqual(payload["result"]["status"], "blocked")
                self.assertFalse(payload["updated"])
                self.assertFalse(payload["would_update"])
                self.assertIn("registry is unchanged", payload["findings"][0])
                self.assertEqual(self.path.read_bytes(), original)


    */
}

#[test]
#[ignore]
fn test_failed_write_keeps_registry_whole() {
    // TODO: Port this Python logic to Rust
    /*

        original = self.path.read_bytes()
        with mock.patch.object(adapter.os, "replace", side_effect=OSError), mock.patch(
            "builtins.print"
        ) as output:
            code = adapter.main(
                [str(self.path), "candidate", "--root", str(self.root), "--json"]
                + ["--write"]
            )
        self.assertEqual(code, 3)
        self.assertFalse(json.loads(output.call_args.args[0])["updated"])
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(
            sorted(p.name for p in self.root.iterdir()), ["opaque", "sources.yaml"]
        )


    */
}

#[test]
#[ignore]
fn test_invalid_date_and_usage_errors_are_json() {
    // TODO: Port this Python logic to Rust
    /*

        text = self.path.read_text()
        self.assertIn("checked: '2026-09-23'", text)
        self.path.write_text(
            text.replace("checked: '2026-09-23'", "checked: 2026-13-45", 1)
        )
        proc = self.cli()
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertFalse(json.loads(proc.stdout)["ok"])
        self.assertEqual(proc.stderr, "")
        for args in (["--json"], ["--json", "--bogus"], ["--json=1"]):
            with self.subTest(args=args):
                proc = subprocess.run(
                    [sys.executable, str(SCRIPTS / "pinned_file_adapter.py"), *args],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(proc.returncode, 2)
                payload = json.loads(proc.stdout)
                self.assertFalse(payload["ok"])
                self.assertIsNone(payload["result"])


    */
}

#[test]
#[ignore]
fn test_duplicate_keys_and_unknown_id() {
    // TODO: Port this Python logic to Rust
    /*

        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "pinned_file_adapter.py"),
                str(self.path),
                "not-registered",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not registered", json.loads(proc.stdout)["findings"][0])
        with self.path.open("a") as out:
            out.write("version: 1\n")
        self.assertEqual(self.cli().returncode, 1)
        self.source["file"]["path"] = "../outside"
        with self.assertRaises(check.Invalid):
            source_registry.validate(self.registry)



    */
}

#[test]
fn test_cli_help() {
    let output = Command::new(env!("CARGO_BIN_EXE_driver-lab"))
        .args(["campaign", "--help"])
        .output()
        .expect("Failed to execute");
    assert!(!output.stdout.is_empty() || !output.stderr.is_empty());
}

#[test]
fn test_index_check_e1000() {
    let output = Command::new(env!("CARGO_BIN_EXE_driver-lab"))
        .args(["campaign", "index-check", "evals/e1000"])
        .output()
        .expect("Failed to execute");
    assert!(
        output.status.success(),
        "Command failed: {:?}",
        String::from_utf8_lossy(&output.stdout)
    );
}
