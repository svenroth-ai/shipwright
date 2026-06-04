"""Behavioral regression test for the security-workflow critical-findings gate.

The gate step (``id: shipwright-critical-gate``) in
``shared/templates/github-actions/security.yml.template`` is what blocks a merge
on a critical security finding in every ``/shipwright-adopt``-scaffolded repo.

A prior version read ``security-severity`` from the SARIF *result* properties,
but GitHub's SARIF convention puts that field on the *rule*
(``tool.driver.rules[].properties``) — so the gate read "0" for every finding
from every scanner and was structurally unable to ever block a merge (a false
green shipped to every adopted repo, empirically confirmed against real
semgrep/trivy/gitleaks SARIF). This test pins the ACTUAL shipped gate shell
(extracted from the template) against synthetic SARIF fixtures so the bug
cannot silently return — the sibling ``test_security_workflow_convention.py``
only checks the step's *shape*, never its *behaviour*.

Blocking policy (ratified 2026-06-04): a merge is blocked iff
  - any finding's rule-level ``security-severity`` >= 9.0 (GitHub "critical"), OR
  - any Gitleaks result exists                           (a committed secret), OR
  - ``sarif/`` is empty / a SARIF file is invalid JSON   (fail closed).
Scanners that emit no ``security-severity`` (e.g. Semgrep ``--config auto``) do
NOT block on their own — a critical gate that fired on 130 auto-findings would
be unusable.

Executes the real ``bash``+``jq`` the workflow uses; per ADR-044 CI-discipline
the missing-binary guard hard-fails in CI (ubuntu ships both) and skips locally.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")  # PyYAML — root + adopt + compliance dep

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.security_workflow import (  # noqa: E402  (deferred so importorskip wins)
    CRITICAL_GATE_STEP_ID,
    TEMPLATE_PATH,
)
from test_hygiene import skip_or_fail_on_missing_binary  # noqa: E402

TEMPLATE_FILE = REPO_ROOT / TEMPLATE_PATH


# --------------------------------------------------------------------------- #
# Extract the ACTUAL shipped gate shell from the template
# --------------------------------------------------------------------------- #
def _gate_run_body() -> str:
    workflow = yaml.safe_load(TEMPLATE_FILE.read_text(encoding="utf-8"))
    for job in (workflow.get("jobs") or {}).values():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if isinstance(step, dict) and step.get("id") == CRITICAL_GATE_STEP_ID:
                run = step.get("run")
                assert run, f"gate step {CRITICAL_GATE_STEP_ID!r} has an empty run: body"
                return run
    pytest.fail(f"no step with id={CRITICAL_GATE_STEP_ID!r} in {TEMPLATE_FILE}")


# --------------------------------------------------------------------------- #
# Minimal SARIF fixtures — mirror the real scanner shapes verified empirically
# --------------------------------------------------------------------------- #
def _sarif(driver: str, rules: list[dict], results: list[dict]) -> str:
    return json.dumps(
        {
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {"driver": {"name": driver, "rules": rules}},
                    "results": results,
                }
            ],
        }
    )


def _result(rule_id: str, *, rule_index: int | None = None) -> dict:
    res = {
        "ruleId": rule_id,
        "message": {"text": "finding"},
        "locations": [
            {"physicalLocation": {"artifactLocation": {"uri": "src/x"}}}
        ],
    }
    if rule_index is not None:
        res["ruleIndex"] = rule_index
    return res


def _trivy_critical() -> str:
    # security-severity ONLY on the rule (the exact shape the old gate missed).
    return _sarif(
        "Trivy",
        [{"id": "CVE-2026-99999", "properties": {"security-severity": "9.8"}}],
        [_result("CVE-2026-99999", rule_index=0)],
    )


def _trivy_clean() -> str:
    return _sarif(
        "Trivy",
        [{"id": "CVE-2026-00001", "properties": {"security-severity": "5.5"}}],
        [_result("CVE-2026-00001", rule_index=0)],
    )


def _result_index_only(rule_index: int) -> dict:
    """A result that references its rule ONLY by ruleIndex (no ruleId) — the
    third resolution branch, most likely to silently regress on a future edit."""
    return {
        "message": {"text": "finding"},
        "ruleIndex": rule_index,
        "locations": [{"physicalLocation": {"artifactLocation": {"uri": "src/x"}}}],
    }


def _trivy_critical_index_only() -> str:
    # Result points (by index, no ruleId) at the critical rule -> must block.
    return _sarif(
        "Trivy",
        [
            {"id": "CVE-A", "properties": {"security-severity": "2.0"}},
            {"id": "CVE-B", "properties": {"security-severity": "9.5"}},
        ],
        [_result_index_only(1)],
    )


def _trivy_noncritical_index_only() -> str:
    # A 9.5 rule EXISTS, but the result points at the 4.0 rule. Proves the gate
    # resolves per-result (not "any rule >= 9.0 anywhere") -> must NOT block.
    return _sarif(
        "Trivy",
        [
            {"id": "CVE-A", "properties": {"security-severity": "9.5"}},
            {"id": "CVE-B", "properties": {"security-severity": "4.0"}},
        ],
        [_result_index_only(1)],
    )


def _trivy_nonnumeric_severity() -> str:
    # A future / 3rd-party scanner could emit a non-numeric security-severity
    # (e.g. "high"). It must degrade to not-critical, NOT wedge the gate with a
    # jq error under `set -e` (which would over-block every PR).
    return _sarif(
        "Trivy",
        [{"id": "CVE-NN", "properties": {"security-severity": "high"}}],
        [_result("CVE-NN", rule_index=0)],
    )


def _semgrep_no_severity() -> str:
    # Semgrep OSS emits no security-severity anywhere -> must NOT block.
    return _sarif(
        "Semgrep OSS",
        [{"id": "rule.x", "properties": {}}],
        [_result("rule.x"), _result("rule.x")],
    )


def _gitleaks_secret() -> str:
    return _sarif("gitleaks", [{"id": "generic-api-key"}], [_result("generic-api-key")])


def _gitleaks_empty() -> str:
    return _sarif("gitleaks", [], [])  # gitleaks ran, found no secret


# --------------------------------------------------------------------------- #
# Gate runner
# --------------------------------------------------------------------------- #
def _run_gate(tmp_path: Path, files: dict[str, str]) -> subprocess.CompletedProcess:
    sarif_dir = tmp_path / "sarif"
    sarif_dir.mkdir(exist_ok=True)
    for name, content in files.items():
        (sarif_dir / name).write_text(content, encoding="utf-8")
    script = tmp_path / "gate.sh"
    script.write_text(_gate_run_body(), encoding="utf-8")
    env = {**os.environ, "GITHUB_OUTPUT": str(tmp_path / "gh_output")}
    return subprocess.run(
        ["bash", str(script)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture(autouse=True)
def _need_tools() -> None:
    # ADR-044 CI-discipline: hard-fail in CI (ubuntu ships bash+jq), skip local.
    skip_or_fail_on_missing_binary("bash", "Git for Windows ships bash; CI ubuntu has it.")
    skip_or_fail_on_missing_binary("jq", "Install jq (winget install jqlang.jq); CI ubuntu ships it.")


# --------------------------------------------------------------------------- #
# Behavioural cases
# --------------------------------------------------------------------------- #
def test_rule_level_critical_blocks(tmp_path: Path) -> None:
    """The exact bug shape: security-severity only on the rule, >=9.0 -> block."""
    p = _run_gate(tmp_path, {"trivy.sarif": _trivy_critical()})
    assert p.returncode != 0, f"critical CVE must block.\nstdout={p.stdout}\nstderr={p.stderr}"


def test_rule_index_only_critical_blocks(tmp_path: Path) -> None:
    """Result references its critical rule only by ruleIndex (no ruleId) -> block."""
    p = _run_gate(tmp_path, {"trivy.sarif": _trivy_critical_index_only()})
    assert p.returncode != 0, (
        f"ruleIndex-resolved critical must block.\nstdout={p.stdout}\nstderr={p.stderr}"
    )


def test_rule_index_points_to_noncritical_passes(tmp_path: Path) -> None:
    """A 9.5 rule exists but the result points at a 4.0 rule -> per-result
    resolution must NOT block (guards against a naive any-rule>=9.0 impl)."""
    p = _run_gate(tmp_path, {"trivy.sarif": _trivy_noncritical_index_only()})
    assert p.returncode == 0, (
        f"per-result mapping must not over-block.\nstdout={p.stdout}\nstderr={p.stderr}"
    )


def test_secret_blocks(tmp_path: Path) -> None:
    p = _run_gate(tmp_path, {"gitleaks.sarif": _gitleaks_secret()})
    assert p.returncode != 0, f"a gitleaks secret must block.\nstdout={p.stdout}\nstderr={p.stderr}"


def test_clean_scan_passes(tmp_path: Path) -> None:
    p = _run_gate(
        tmp_path,
        {
            "trivy.sarif": _trivy_clean(),
            "semgrep.sarif": _semgrep_no_severity(),
            "gitleaks.sarif": _gitleaks_empty(),
        },
    )
    assert p.returncode == 0, f"clean scan must pass.\nstdout={p.stdout}\nstderr={p.stderr}"


def test_semgrep_without_severity_does_not_block(tmp_path: Path) -> None:
    p = _run_gate(tmp_path, {"semgrep.sarif": _semgrep_no_severity()})
    assert p.returncode == 0, (
        f"semgrep findings without CVSS must NOT block.\nstdout={p.stdout}\nstderr={p.stderr}"
    )


def test_nonnumeric_severity_degrades_not_wedge(tmp_path: Path) -> None:
    """A non-numeric security-severity must degrade to not-critical (try/catch),
    not abort the gate under set -e and over-block every PR."""
    p = _run_gate(tmp_path, {"trivy.sarif": _trivy_nonnumeric_severity()})
    assert p.returncode == 0, (
        f"non-numeric severity must not wedge the gate.\nstdout={p.stdout}\nstderr={p.stderr}"
    )


def test_empty_sarif_dir_fails_closed(tmp_path: Path) -> None:
    p = _run_gate(tmp_path, {})  # dir exists, zero SARIF files (all scanners crashed)
    assert p.returncode != 0, f"empty sarif/ must fail closed.\nstdout={p.stdout}\nstderr={p.stderr}"


def test_invalid_json_fails_closed(tmp_path: Path) -> None:
    p = _run_gate(tmp_path, {"semgrep.sarif": "{not valid json"})
    assert p.returncode != 0, f"invalid SARIF must fail closed.\nstdout={p.stdout}\nstderr={p.stderr}"
