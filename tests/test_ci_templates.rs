// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Integration and security tests for downstream CI templates (`skills/spec-format/ci/*`),
//! active workflows (`.github/workflows/*`), `install.sh`, `rust-toolchain.toml`, and
//! repository-wide hollow-test prevention.
//!
//! Port of `dc21263:skills/spec-format/tests/test_ci_templates.py` plus consensus CI/release
//! hardening gates.

use driver_lab::yaml_strict;
use regex::Regex;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::os::unix::fs::{symlink, PermissionsExt};
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use tempfile::TempDir;

#[derive(Clone, Copy, Debug)]
struct Profile {
    name: &'static str,
    fit: &'static str,
    misfit: &'static str,
    board_fit: &'static str,
    board_misfit: &'static str,
    extra_fit_licenses: &'static str,
    require_further: usize,
    src_fit: usize,
}

const PROFILES: &[Profile] = &[
    Profile {
        name: "docs",
        fit: "docs-named",
        misfit: "gpl-only",
        board_fit: "",
        board_misfit: "widgetchip-bsd-overlay",
        extra_fit_licenses: "",
        require_further: 0,
        src_fit: 0,
    },
    Profile {
        name: "permissive",
        fit: "bsd",
        misfit: "gpl-only",
        board_fit: "widgetchip-bsd-overlay",
        board_misfit: "widgetchip-gpl3-overlay",
        extra_fit_licenses: "ISC 0BSD",
        require_further: 1,
        src_fit: 1,
    },
    Profile {
        name: "gpl",
        fit: "gpl-only",
        misfit: "gpl3-only",
        board_fit: "widgetchip-bsd-overlay",
        board_misfit: "widgetchip-gpl3-overlay",
        extra_fit_licenses: "ISC 0BSD",
        require_further: 2,
        src_fit: 1,
    },
];

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn ci_dir() -> PathBuf {
    repo_root().join("skills/spec-format/ci")
}

fn fixtures_dir() -> PathBuf {
    repo_root().join("skills/spec-format/tests/fixtures/license-gate")
}

fn driver_lab_bin() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_driver-lab"))
}

struct CiHarness {
    _temp: TempDir,
    root: PathBuf,
    bin: PathBuf,
    fixture_temp: PathBuf,
    roots: Vec<PathBuf>,
}

impl CiHarness {
    fn new() -> Self {
        let temp = tempfile::tempdir().expect("create tempdir");
        let root = temp.path().canonicalize().expect("canonicalize tempdir");
        let bin = root.join("bin");
        fs::create_dir_all(&bin).unwrap();
        let physical = root.join("physical temp");
        fs::create_dir_all(&physical).unwrap();
        let alias = root.join("temp alias");
        symlink(&physical, &alias).unwrap();
        let fixture_temp = alias.join("fixtures");

        let mut roots = Vec::new();
        for p in PROFILES {
            let r = root.join(p.name).join("specs");
            fs::create_dir_all(&r).unwrap();
            fs::copy(
                fixtures_dir()
                    .join("roots")
                    .join(p.name)
                    .join("board-specs.yaml"),
                r.join("board-specs.yaml"),
            )
            .unwrap();
            roots.push(r);
        }

        let harness = Self {
            _temp: temp,
            root,
            bin,
            fixture_temp,
            roots,
        };
        harness.set_mktemp("mkdir -p \"$FIXTURE_TEMP\"\nprintf \"%s\\n\" \"$FIXTURE_TEMP\"\n");
        harness
    }

    fn set_mktemp(&self, body: &str) {
        let path = self.bin.join("mktemp");
        fs::write(&path, format!("#!/usr/bin/env bash\nset -eu\n{body}")).unwrap();
        let mut perms = fs::metadata(&path).unwrap().permissions();
        perms.set_mode(0o755);
        fs::set_permissions(&path, perms).unwrap();
    }

    fn profile(&self, name: &str) -> Profile {
        *PROFILES
            .iter()
            .find(|p| p.name == name)
            .expect("known profile")
    }

    fn write_configured_script(&self, profile_name: &str) -> PathBuf {
        let p = self.profile(profile_name);
        let script = self.root.join(p.name).join("scripts/checks.sh");
        fs::create_dir_all(script.parent().unwrap()).unwrap();
        let mut text = fs::read_to_string(ci_dir().join("checks.sh")).unwrap();

        let with_ext = |s: &str| -> String {
            if s.is_empty() {
                String::new()
            } else {
                format!("{s}.spec.yaml")
            }
        };

        let replacements = [
            ("REPO", format!("hardware-specs-{}", p.name)),
            ("FIT", with_ext(p.fit)),
            ("MISFIT", with_ext(p.misfit)),
            ("BOARD_FIT", with_ext(p.board_fit)),
            ("BOARD_MISFIT", with_ext(p.board_misfit)),
            ("EXTRA_FIT_LICENSES", p.extra_fit_licenses.to_string()),
            ("REQUIRE_FURTHER", p.require_further.to_string()),
            ("SRC_FIT", p.src_fit.to_string()),
        ];

        for (key, val) in replacements {
            let re = Regex::new(&format!(r"(?m)^{key}=.*$")).unwrap();
            assert_eq!(
                re.find_iter(&text).count(),
                1,
                "expected exactly one {key}= assignment in checks.sh"
            );
            text = re.replace(&text, format!("{key}=\"{val}\"")).into_owned();
        }
        fs::write(&script, text).unwrap();
        let mut perms = fs::metadata(&script).unwrap().permissions();
        perms.set_mode(0o755);
        fs::set_permissions(&script, perms).unwrap();
        script
    }

    fn invoke(
        &self,
        profile_name: &str,
        step: &str,
        contexts: Option<&[PathBuf]>,
        ci: &str,
        resolve: &str,
        extra_env: &[(&str, &str)],
    ) -> (i32, String) {
        let p = self.profile(profile_name);
        let script = self.write_configured_script(profile_name);
        let default_contexts = &self.roots[..p.require_further];
        let ctx_slice = contexts.unwrap_or(default_contexts);

        let orig_path = std::env::var("PATH").unwrap_or_default();
        let new_path = format!("{}:{orig_path}", self.bin.display());

        let mut cmd = Command::new("bash");
        cmd.arg(&script)
            .arg("--mode")
            .arg("pr")
            .arg(step)
            .arg(repo_root());
        for c in ctx_slice {
            cmd.arg(c);
        }
        cmd.current_dir(script.parent().unwrap().parent().unwrap())
            .env("PATH", new_path)
            .env("FIXTURE_TEMP", &self.fixture_temp)
            .env("DRIVER_LAB_BIN", driver_lab_bin())
            .env("RESOLVE_SRC", resolve)
            .env("CI", ci)
            .env_remove("TOOL_COMMIT");
        for &(k, v) in extra_env {
            cmd.env(k, v);
        }
        let out: Output = cmd.output().expect("spawn bash checks.sh");
        let combined = format!(
            "{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr)
        );
        (out.status.code().unwrap_or(1), combined)
    }
}

#[test]
fn test_all_profiles_through_symlinked_temp_directory() {
    let h = CiHarness::new();
    for p in PROFILES {
        let (code, out) = h.invoke(p.name, "self-test", None, "", "0", &[]);
        assert_eq!(code, 0, "profile {} failed:\n{out}", p.name);
        assert!(out.contains("self-test: passed"), "{out}");
        assert!(out.contains("is not accepted by root"), "{out}");
        assert!(!out.contains("reached through, a symbolic link"), "{out}");
        assert!(
            !h.fixture_temp.exists(),
            "temporary root leaked for profile {}",
            p.name
        );
    }
}

#[test]
fn test_required_context_cannot_be_omitted() {
    let h = CiHarness::new();
    for profile in ["permissive", "gpl"] {
        let (code, out) = h.invoke(profile, "self-test", Some(&[]), "", "0", &[]);
        assert_eq!(code, 2, "{out}");
        assert!(out.contains("further root(s)"), "{out}");
    }
}

#[test]
fn test_ci_requires_resolution() {
    let h = CiHarness::new();
    let (code, out) = h.invoke("docs", "self-test", None, "true", "0", &[]);
    assert_eq!(code, 1, "{out}");
    assert!(out.contains("running in CI without RESOLVE_SRC=1"), "{out}");
}

#[test]
fn test_mktemp_failure_stops_before_creating_fixtures() {
    let h = CiHarness::new();
    h.set_mktemp("exit 1\n");
    let (code, out) = h.invoke("docs", "self-test", None, "", "0", &[]);
    assert_eq!(code, 1, "{out}");
    assert!(!out.contains("fit docs-named.spec.yaml"), "{out}");
    assert!(!h.fixture_temp.exists());
}

#[test]
fn test_canonicalization_failure_stops_before_creating_fixtures() {
    let h = CiHarness::new();
    h.set_mktemp("printf \"%s\\n\" \"$FIXTURE_TEMP\"\n");
    let (code, out) = h.invoke("docs", "self-test", None, "", "0", &[]);
    assert_eq!(code, 1, "{out}");
    assert!(!out.contains("fit docs-named.spec.yaml"), "{out}");
    assert!(!h.fixture_temp.exists());
}

#[test]
fn test_discovery_failure_cannot_report_success() {
    let h = CiHarness::new();
    h.set_mktemp("printf \"%s\\n\" \"$FIXTURE_TEMP\"\n");
    let find_bin = h.bin.join("find");
    fs::write(&find_bin, "#!/usr/bin/env bash\nexit 1\n").unwrap();
    let mut perms = fs::metadata(&find_bin).unwrap().permissions();
    perms.set_mode(0o755);
    fs::set_permissions(&find_bin, perms).unwrap();

    let (code, out) = h.invoke("docs", "resolve", None, "", "1", &[]);
    assert_eq!(code, 1, "{out}");
    assert!(out.contains("error: cannot discover spec files"), "{out}");
    assert!(!out.contains("resolve: no specs"), "{out}");
    assert!(!h.fixture_temp.exists(), "discovery file leaked");
}

#[test]
fn test_docs_profile_with_context_root_passes_cross_root_overlay_self_test() {
    let h = CiHarness::new();
    let ctx = vec![h.roots[1].clone()];
    let (code, out) = h.invoke("docs", "self-test", Some(&ctx), "", "0", &[]);
    assert_eq!(code, 0, "{out}");
    assert!(out.contains("overlay with the second root"), "{out}");
    assert!(out.contains("self-test: passed"), "{out}");
}

#[test]
fn test_check_step_runs_stubs_from_and_stubgen_check() {
    let h = CiHarness::new();
    let repo_dir = h.root.join("docs");
    let raw_spec = fs::read_to_string(fixtures_dir().join("board/widgetchip.spec.yaml")).unwrap();
    let facts_pos = raw_spec
        .find("facts:\n")
        .expect("facts: in widgetchip.spec.yaml");
    let spec_text = format!("{}facts: []\n", &raw_spec[..facts_pos]);
    fs::write(repo_dir.join("specs/widgetchip.spec.yaml"), spec_text).unwrap();

    let domains = repo_dir.join("domains.yaml");
    fs::write(
        &domains,
        "# SPDX-FileCopyrightText: 2026 contributors\n\
         # SPDX-License-Identifier: CC-BY-4.0\n\
         format: 2\n\
         board: widgetchip\n\
         copyright: 2026 contributors\n\
         license: CC-BY-4.0\n\
         domains:\n\
         \x20 - name: widgetchip-usb-expert\n\
         \x20   title: WidgetChip USB\n\
         \x20   description: USB host questions on WidgetChip\n\
         \x20   entry: [widgetchip]\n\
         \x20   preload: [board-expert]\n",
    )
    .unwrap();

    let gen = Command::new(driver_lab_bin())
        .arg("stubgen")
        .arg(&domains)
        .arg("--out")
        .arg(repo_dir.join("skills"))
        .output()
        .unwrap();
    assert!(
        gen.status.success(),
        "stubgen failed: {}",
        String::from_utf8_lossy(&gen.stderr)
    );

    let (code, out) = h.invoke("docs", "check", None, "", "0", &[]);
    assert_eq!(code, 0, "{out}");
    assert!(out.contains("--stubs-from skills"), "{out}");
    assert!(
        out.contains("== stubgen domains.yaml --out skills --check"),
        "{out}"
    );

    let stub_file = repo_dir.join("skills/widgetchip-usb-expert/SKILL.md");
    let mut stub_txt = fs::read_to_string(&stub_file).unwrap();
    stub_txt.push_str("\ndrift\n");
    fs::write(&stub_file, stub_txt).unwrap();

    let (d_code, d_out) = h.invoke("docs", "check", None, "", "0", &[]);
    assert_eq!(d_code, 1, "{d_out}");
    assert!(d_out.contains("stale"), "{d_out}");
}

#[test]
fn test_resolve_step_auto_binds_valid_cache_repo_and_skips_partial_or_missing() {
    let h = CiHarness::new();
    h.set_mktemp(
        "if [ \"${1:-}\" = \"-d\" ]; then mkdir -p \"$FIXTURE_TEMP\"; fi\n\
         printf \"%s\\n\" \"$FIXTURE_TEMP\"\n",
    );
    let repo_dir = h.root.join("permissive");
    let cache_repo = repo_dir.join("cache/tools");
    fs::create_dir_all(&cache_repo).unwrap();

    let run_git = |args: &[&str]| -> String {
        let out = Command::new("git")
            .args(args)
            .env("GIT_AUTHOR_NAME", "Test")
            .env("GIT_AUTHOR_EMAIL", "test@users.noreply.github.com")
            .env("GIT_COMMITTER_NAME", "Test")
            .env("GIT_COMMITTER_EMAIL", "test@users.noreply.github.com")
            .output()
            .unwrap();
        assert!(
            out.status.success(),
            "git {:?} failed: {}",
            args,
            String::from_utf8_lossy(&out.stderr)
        );
        String::from_utf8_lossy(&out.stdout).trim().to_string()
    };

    run_git(&["init", "-q", cache_repo.to_str().unwrap()]);
    fs::write(
        cache_repo.join("driver.c"),
        "// SPDX-License-Identifier: BSD-3-Clause\nint stub_magic(void) { return 42; }\n",
    )
    .unwrap();
    run_git(&["-C", cache_repo.to_str().unwrap(), "add", "driver.c"]);
    run_git(&[
        "-C",
        cache_repo.to_str().unwrap(),
        "commit",
        "-q",
        "-m",
        "init",
    ]);
    let commit = run_git(&["-C", cache_repo.to_str().unwrap(), "rev-parse", "HEAD"]);

    fs::copy(
        fixtures_dir().join("board/widgetchip.spec.yaml"),
        repo_dir.join("specs/widgetchip.spec.yaml"),
    )
    .unwrap();
    let raw_overlay =
        fs::read_to_string(fixtures_dir().join("board/widgetchip-src-overlay.spec.yaml")).unwrap();
    let commit_re = Regex::new(r#"commit: "[0-9a-f]{40}""#).unwrap();
    let overlay = commit_re
        .replace(&raw_overlay, format!("commit: \"{commit}\""))
        .replace("license_from: notice", "license_from: spdx-line")
        .replace("path: armstubs/armstub8.S", "path: driver.c")
        .replace("lines: [30, 30]", "lines: [2, 2]");
    fs::write(
        repo_dir.join("specs/widgetchip-src-overlay.spec.yaml"),
        &overlay,
    )
    .unwrap();

    let (code, out) = h.invoke("permissive", "resolve", None, "", "1", &[]);
    assert_eq!(code, 0, "{out}");
    assert!(out.contains("--repo tools=cache/tools"), "{out}");
    assert!(out.contains("1 anchor(s) resolved, 0 skipped"), "{out}");

    run_git(&[
        "-C",
        cache_repo.to_str().unwrap(),
        "config",
        "extensions.partialClone",
        "origin",
    ]);
    let (_p_code, p_out) = h.invoke("permissive", "resolve", None, "", "1", &[]);
    assert!(
        p_out.contains("resolve: skipping cache/tools (partial clone)"),
        "{p_out}"
    );
    assert!(!p_out.contains("--repo tools=cache/tools"), "{p_out}");
    run_git(&[
        "-C",
        cache_repo.to_str().unwrap(),
        "config",
        "--unset",
        "extensions.partialClone",
    ]);

    let absent_commit = "f".repeat(40);
    fs::write(
        repo_dir.join("specs/widgetchip-src-overlay.spec.yaml"),
        overlay.replace(
            &format!("commit: \"{commit}\""),
            &format!("commit: \"{absent_commit}\""),
        ),
    )
    .unwrap();
    let (_m_code, m_out) = h.invoke("permissive", "resolve", None, "", "1", &[]);
    assert!(
        m_out.contains(&format!(
            "resolve: skipping cache/tools (missing commit {absent_commit})"
        )),
        "{m_out}"
    );
    assert!(!m_out.contains("--repo tools=cache/tools"), "{m_out}");
}

#[test]
fn test_checks_sh_rejects_mismatched_tool_commit_with_exit_3() {
    let h = CiHarness::new();
    let bogus_commit = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef";
    let (code, out) = h.invoke(
        "docs",
        "check",
        None,
        "",
        "0",
        &[("TOOL_COMMIT", bogus_commit)],
    );
    assert_eq!(code, 3, "expected exit 3 on TOOL_COMMIT mismatch:\n{out}");
    assert!(out.contains("does not match TOOL_COMMIT"), "{out}");
}

#[test]
fn test_self_test_live_github_resolve_when_net_tests_enabled() {
    if std::env::var("DRIVER_LAB_NET_TESTS").as_deref() != Ok("1") {
        return;
    }
    let h = CiHarness::new();
    let (code, out) = h.invoke("docs", "self-test", None, "true", "1", &[]);
    assert_eq!(code, 0, "live RESOLVE_SRC=1 self-test failed:\n{out}");
    assert!(
        out.contains("resolve-good (anchor exists at the pin) exited 0 as required"),
        "{out}"
    );
    assert!(
        out.contains("resolve-bad (no such symbol at the pin) exited 1 as required"),
        "{out}"
    );
}

fn load_yaml_file(path: &Path) -> Value {
    let raw = fs::read_to_string(path).expect("read workflow yaml");
    let normalized = raw
        .lines()
        .map(|line| {
            let trimmed = line.trim();
            if trimmed == "pull_request:" || trimmed == "workflow_dispatch:" {
                format!("{line} {{}}")
            } else {
                line.to_string()
            }
        })
        .collect::<Vec<_>>()
        .join("\n");
    let loaded = yaml_strict::load_text(&normalized, path);
    assert!(
        loaded.findings().is_empty(),
        "YAML strict findings in {}: {:?}",
        path.display(),
        loaded.findings()
    );
    loaded.data.expect("YAML data present")
}

#[test]
fn test_workflow_runs_all_checks_on_both_platforms() {
    let workflow = load_yaml_file(&ci_dir().join("checks.yml"));
    let job = &workflow["jobs"]["checks"];
    assert_eq!(
        job["strategy"]["matrix"]["os"],
        serde_json::json!(["ubuntu-latest", "macos-latest"])
    );
    assert_eq!(job["strategy"]["fail-fast"], Value::Bool(false));
    assert_eq!(job["runs-on"], Value::String("${{ matrix.os }}".into()));
    assert_eq!(
        workflow["permissions"],
        serde_json::json!({"contents": "read"})
    );
    assert_eq!(
        workflow["env"]["TOOL_COMMIT"],
        Value::String("0".repeat(40))
    );

    let steps = job["steps"].as_array().unwrap();
    assert!(steps[0]["run"]
        .as_str()
        .unwrap()
        .contains(&format!("test \"$TOOL_COMMIT\" != {}", "0".repeat(40))));

    let checks: Vec<&Value> = steps
        .iter()
        .filter(|s| {
            s.get("run")
                .and_then(Value::as_str)
                .is_some_and(|r| r.starts_with("scripts/checks.sh"))
        })
        .collect();
    assert_eq!(checks.len(), 4);
    for (command, step) in ["check", "resolve", "render", "self-test"]
        .iter()
        .zip(checks.iter())
    {
        let run_str = step["run"].as_str().unwrap();
        assert!(run_str.contains(&format!("{command} .driver-lab")));
        if *command == "resolve" || *command == "self-test" {
            assert_eq!(step["env"]["RESOLVE_SRC"], serde_json::json!(1));
        }
    }
    assert!(checks[0]["run"]
        .as_str()
        .unwrap()
        .contains("--mode \"$CHECKS_MODE\""));

    let sha_re = Regex::new(r"@[0-9a-f]{40}$").unwrap();
    for step in steps {
        if let Some(uses) = step.get("uses").and_then(Value::as_str) {
            assert!(sha_re.is_match(uses), "unpinned uses: {uses}");
        }
    }
    let tool = steps
        .iter()
        .find(|s| {
            s.get("with")
                .and_then(|w| w.get("path"))
                .and_then(Value::as_str)
                == Some(".driver-lab")
        })
        .expect(".driver-lab checkout step");
    assert_eq!(
        tool["with"]["ref"],
        Value::String("${{ env.TOOL_COMMIT }}".into())
    );
    assert_eq!(tool["with"]["persist-credentials"], Value::Bool(false));
}

#[test]
fn test_publish_workflow_uses_repo_checkout_path_and_pinned_shas() {
    let workflow = load_yaml_file(&ci_dir().join("publish.yml"));
    let sha_re = Regex::new(r"@[0-9a-f]{40}$").unwrap();
    for job_name in ["build", "deploy"] {
        let steps = workflow["jobs"][job_name]["steps"].as_array().unwrap();
        for step in steps {
            if let Some(uses) = step.get("uses").and_then(Value::as_str) {
                assert!(sha_re.is_match(uses), "unpinned uses: {uses}");
            }
        }
        let repo_checkout = steps
            .iter()
            .find(|s| {
                s.get("with")
                    .and_then(|w| w.get("path"))
                    .and_then(Value::as_str)
                    == Some("repo")
            })
            .expect("repo checkout step");
        assert_eq!(
            repo_checkout["with"]["persist-credentials"],
            Value::Bool(false)
        );
    }
    let build_steps = workflow["jobs"]["build"]["steps"].as_array().unwrap();
    let build_step = build_steps
        .iter()
        .find(|s| s.get("env").and_then(|e| e.get("SOURCE_COMMIT")).is_some())
        .expect("SOURCE_COMMIT step");
    assert_eq!(
        build_step["env"]["SOURCE_COMMIT"],
        Value::String("${{ github.sha }}".into())
    );
    let run_cmd = build_step["run"].as_str().unwrap();
    assert!(run_cmd.contains("--source-commit \"repo/specs=$SOURCE_COMMIT\""));
    assert!(run_cmd.contains("repo/specs"));
}

#[test]
fn test_release_workflow_builds_four_targets_with_tool_commit_and_publish_job() {
    let workflow = load_yaml_file(&repo_root().join(".github/workflows/release.yml"));
    let build_job = &workflow["jobs"]["build"];
    let includes = build_job["strategy"]["matrix"]["include"]
        .as_array()
        .unwrap();
    let targets: Vec<&str> = includes
        .iter()
        .map(|inc| inc["target"].as_str().unwrap())
        .collect();
    assert_eq!(
        targets,
        vec![
            "x86_64-unknown-linux-gnu",
            "aarch64-unknown-linux-gnu",
            "x86_64-apple-darwin",
            "aarch64-apple-darwin",
        ]
    );
    for inc in includes {
        let os = inc["os"].as_str().unwrap();
        assert_ne!(
            os, "macos-13",
            "deprecated macos-13 runner must not be used"
        );
    }

    let sha_re = Regex::new(r"@[0-9a-f]{40}$").unwrap();
    for (_job_name, job) in workflow["jobs"].as_object().unwrap() {
        for step in job["steps"].as_array().unwrap() {
            if let Some(uses) = step.get("uses").and_then(Value::as_str) {
                assert!(sha_re.is_match(uses), "unpinned uses: {uses}");
            }
        }
    }
    assert_eq!(
        build_job["env"]["DRIVER_LAB_TOOL_COMMIT"],
        Value::String("${{ github.sha }}".into())
    );

    let pub_job = &workflow["jobs"]["publish-release"];
    assert!(
        pub_job.is_object(),
        "release.yml must define a publish-release job"
    );
    assert_eq!(
        pub_job["permissions"],
        serde_json::json!({"contents": "write"})
    );
}

#[test]
fn test_all_github_workflows_pin_shas_and_disable_persist_credentials_and_pin_toolchain() {
    let sha_re = Regex::new(r"@[0-9a-f]{40}$").unwrap();
    let workflow_paths = [
        repo_root().join(".github/workflows/checks.yml"),
        repo_root().join(".github/workflows/release.yml"),
        ci_dir().join("checks.yml"),
        ci_dir().join("publish.yml"),
    ];
    for wf_path in &workflow_paths {
        let wf = load_yaml_file(wf_path);
        assert_eq!(
            wf["permissions"],
            serde_json::json!({"contents": "read"}),
            "top-level permissions in {} must be contents: read",
            wf_path.display()
        );
        for (job_name, job) in wf["jobs"].as_object().unwrap() {
            for step in job["steps"].as_array().unwrap() {
                if let Some(uses) = step.get("uses").and_then(Value::as_str) {
                    assert!(
                        sha_re.is_match(uses),
                        "{} (job {job_name}): uses '{uses}' is not pinned to a 40-hex SHA",
                        wf_path.display()
                    );
                    if uses.starts_with("actions/checkout@") {
                        assert_eq!(
                            step.get("with")
                                .and_then(|w| w.get("persist-credentials"))
                                .and_then(Value::as_bool),
                            Some(false),
                            "{} (job {job_name}): actions/checkout step must set persist-credentials: false",
                            wf_path.display()
                        );
                    }
                }
            }
        }
    }

    let toolchain_txt = fs::read_to_string(repo_root().join("rust-toolchain.toml")).unwrap();
    let semver_re = Regex::new(r#"(?m)^channel\s*=\s*"[0-9]+\.[0-9]+\.[0-9]+"\s*$"#).unwrap();
    assert!(
        semver_re.is_match(&toolchain_txt),
        "rust-toolchain.toml must pin an exact X.Y.Z semver channel:\n{toolchain_txt}"
    );
}

#[test]
fn test_install_sh_offline_bundle_sha256_and_commit_handshake() {
    let temp = tempfile::tempdir().unwrap();
    let dist_dir = temp.path().join("dist");
    let install_dir = temp.path().join("bin");
    fs::create_dir_all(&dist_dir).unwrap();

    let target = "x86_64-unknown-linux-gnu";
    let staging = dist_dir.join(format!("driver-lab-{target}"));
    fs::create_dir_all(&staging).unwrap();

    let commit_sha = "1234567890abcdef1234567890abcdef12345678";
    let fake_bin = staging.join("driver-lab");
    fs::write(
        &fake_bin,
        format!("#!/bin/sh\necho \"driver-lab 0.1.0 ({commit_sha})\"\n"),
    )
    .unwrap();
    let mut perms = fs::metadata(&fake_bin).unwrap().permissions();
    perms.set_mode(0o755);
    fs::set_permissions(&fake_bin, perms).unwrap();

    let archive_name = format!("driver-lab-{target}.tar.gz");
    let archive_path = dist_dir.join(&archive_name);
    let tar_status = Command::new("tar")
        .arg("-C")
        .arg(&dist_dir)
        .arg("-czf")
        .arg(&archive_path)
        .arg(format!("driver-lab-{target}"))
        .status()
        .unwrap();
    assert!(tar_status.success());

    let archive_bytes = fs::read(&archive_path).unwrap();
    let actual_sha256 = format!("{:x}", Sha256::digest(&archive_bytes));
    fs::write(
        dist_dir.join(format!("{archive_name}.sha256")),
        format!("{actual_sha256}  {archive_name}\n"),
    )
    .unwrap();

    let base_url = format!("file://{}", dist_dir.display());
    let install_sh = repo_root().join("install.sh");

    // 1. Valid SHA-256 and matching commit handshake -> exit 0.
    let ok_out = Command::new("sh")
        .arg(&install_sh)
        .args([
            "--version",
            "v0.1.0",
            "--base-url",
            &base_url,
            "--sha256",
            &actual_sha256,
            "--commit",
            commit_sha,
            "--install-dir",
            install_dir.to_str().unwrap(),
        ])
        .env("DRIVER_LAB_TARGET", target)
        .output()
        .unwrap();
    assert_eq!(
        ok_out.status.code(),
        Some(0),
        "install.sh failed: {}",
        String::from_utf8_lossy(&ok_out.stderr)
    );
    assert!(String::from_utf8_lossy(&ok_out.stdout).contains(commit_sha));
    assert!(install_dir.join("driver-lab").is_file());

    // 2. Mismatched SHA-256 -> exit 3.
    let bad_sha = "0".repeat(64);
    let bad_sha_out = Command::new("sh")
        .arg(&install_sh)
        .args([
            "--version",
            "v0.1.0",
            "--base-url",
            &base_url,
            "--sha256",
            &bad_sha,
            "--commit",
            commit_sha,
            "--install-dir",
            install_dir.to_str().unwrap(),
        ])
        .env("DRIVER_LAB_TARGET", target)
        .output()
        .unwrap();
    assert_eq!(bad_sha_out.status.code(), Some(3));
    assert!(String::from_utf8_lossy(&bad_sha_out.stderr).contains("SHA-256 mismatch"));

    // 3. Mismatched commit handshake -> exit 3.
    let wrong_commit = "abcdefabcdefabcdefabcdefabcdefabcdefabcd";
    let bad_commit_out = Command::new("sh")
        .arg(&install_sh)
        .args([
            "--version",
            "v0.1.0",
            "--base-url",
            &base_url,
            "--sha256",
            &actual_sha256,
            "--commit",
            wrong_commit,
            "--install-dir",
            install_dir.to_str().unwrap(),
        ])
        .env("DRIVER_LAB_TARGET", target)
        .output()
        .unwrap();
    assert_eq!(bad_commit_out.status.code(), Some(3));
    assert!(String::from_utf8_lossy(&bad_commit_out.stderr).contains("version handshake failed"));
}

#[test]
fn test_no_hollow_assert_true_tests_in_repository() {
    let mut rs_files = Vec::new();
    for dir_name in ["tests", "src"] {
        let mut stack = vec![repo_root().join(dir_name)];
        while let Some(dir) = stack.pop() {
            let Ok(entries) = fs::read_dir(&dir) else {
                continue;
            };
            for entry in entries.flatten() {
                let p = entry.path();
                if p.is_dir() {
                    stack.push(p);
                } else if p.extension().and_then(|e| e.to_str()) == Some("rs") {
                    rs_files.push(p);
                }
            }
        }
    }
    rs_files.sort();

    let mut violations: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let assert_true_needle = ["assert!", "(", "true"].concat();
    let assert_eq_one_needle = ["assert_eq!", "(", "1, 1)"].concat();
    let resolve_help_needle = ["\"resolve\"", ", ", "\"--help\""].concat();

    for path in rs_files {
        let rel = path
            .strip_prefix(repo_root())
            .unwrap_or(&path)
            .display()
            .to_string();
        let content = fs::read_to_string(&path).unwrap();
        for (idx, line) in content.lines().enumerate() {
            let trimmed = line.trim();
            if trimmed.starts_with("//") {
                continue;
            }
            if trimmed.contains(&assert_true_needle) || trimmed.contains(&assert_eq_one_needle) {
                violations.entry(rel.clone()).or_default().push(format!(
                    "line {}: hollow tautology assertion found",
                    idx + 1
                ));
            }
            if rel == "tests/test_resolve_inventory.rs" && trimmed.contains(&resolve_help_needle) {
                violations.entry(rel.clone()).or_default().push(format!(
                    "line {}: hollow resolve --help placeholder found",
                    idx + 1
                ));
            }
        }
    }

    assert!(
        violations.is_empty(),
        "hollow test assertions are forbidden across tests/ and src/:\n{:#?}",
        violations
    );
}
