"""Behavioural test: the monorepo security workflow's critical-gate fails closed on
``prompt_risks.json``.

The gate step (``id: shipwright-critical-gate``) in ``.github/workflows/security.yml``
used to read an absent ``prompt_risks.json`` as "0 prompt-critical" with a warning,
and an empty file as a silent green. ``findings.json`` was already held to a
fail-closed standard; this pins the same for the prompt-injection report.

Policy: with the scan step meant to run (outcome ``success``, or unset when the gate
body is executed outside Actions), a missing / empty / non-report ``prompt_risks.json``
blocks; a scan step that ended ``failure`` / ``cancelled`` blocks; a step that was
``skipped`` on purpose only warns. A real critical prompt finding always blocks.

Executes the real ``bash`` + ``jq`` the workflow uses (ADR-044: the missing-binary
guard hard-fails in CI, skips locally).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.security_workflow import CRITICAL_GATE_STEP_ID  # noqa: E402
from test_hygiene import skip_or_fail_on_missing_binary  # noqa: E402

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "security.yml"

pytestmark = pytest.mark.covers("FR-01.07/AC20")

CLEAN = json.dumps({"findings": []})


def _gate_body() -> str:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in (workflow.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            if isinstance(step, dict) and step.get("id") == CRITICAL_GATE_STEP_ID:
                return step["run"]
    raise AssertionError(f"no step id={CRITICAL_GATE_STEP_ID!r} in {WORKFLOW}")


def _run(tmp_path: Path, prompt_risks: str | None, outcome: str | None = None):
    (tmp_path / "findings.json").write_text(CLEAN, encoding="utf-8")
    if prompt_risks is not None:
        (tmp_path / "prompt_risks.json").write_text(prompt_risks, encoding="utf-8")
    script = tmp_path / "gate.sh"
    # LF only: a checkout with autocrlf hands YAML a CRLF body that bash rejects.
    script.write_bytes(_gate_body().replace("\r\n", "\n").encode("utf-8"))
    # Never inherit the runner's step-summary / output files: the gate appends a verdict table
    # to GITHUB_STEP_SUMMARY, which would land in the pytest job's own summary.
    drop = {"PROMPT_SCAN_OUTCOME", "GITHUB_STEP_SUMMARY", "GITHUB_OUTPUT"}
    env = {k: v for k, v in os.environ.items() if k not in drop}
    if outcome is not None:
        env["PROMPT_SCAN_OUTCOME"] = outcome
    return subprocess.run(
        ["bash", script.name], cwd=str(tmp_path), env=env, capture_output=True, text=True,
    )


@pytest.fixture(autouse=True)
def _need_tools() -> None:
    skip_or_fail_on_missing_binary("bash", "Git for Windows ships bash; CI ubuntu has it.")
    skip_or_fail_on_missing_binary("jq", "Install jq (winget install jqlang.jq); CI ubuntu ships it.")


def _detail(p: subprocess.CompletedProcess) -> str:
    return f"stdout={p.stdout}\nstderr={p.stderr}"


def _assert_blocked(p: subprocess.CompletedProcess) -> None:
    """The gate said no BECAUSE of the prompt-injection report, not for another reason.

    Exit 1 plus an ``::error::`` line that names the prompt-injection scan - so a launch
    error (127) or a failure on ``findings.json`` cannot satisfy it by accident.
    """
    assert p.returncode == 1, _detail(p)
    errors = [ln for ln in p.stdout.splitlines() if ln.startswith("::error::")]
    assert any("prompt" in ln.lower() for ln in errors), _detail(p)


class TestWiring:
    """The behaviour tests inject the outcome by hand; this pins the workflow side of it."""

    def _steps(self) -> list[dict]:
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        return [s for job in workflow["jobs"].values() for s in job.get("steps") or []]

    def test_gate_reads_the_outcome_of_the_prompt_scan_step(self):
        steps = self._steps()
        scan = next(s for s in steps if s.get("name") == "Run Prompt Injection scan")
        gate = next(s for s in steps if s.get("id") == CRITICAL_GATE_STEP_ID)
        assert scan.get("id"), "the prompt-injection scan step needs an id for the gate to read"
        assert gate["env"]["PROMPT_SCAN_OUTCOME"] == f"${{{{ steps.{scan['id']}.outcome }}}}"

    def test_gate_keeps_the_implicit_success_condition(self):
        # `skipped` is read as a deliberate opt-out only while an upstream failure stops the job
        # before the gate runs; `if: always()` on the gate would break that.
        gate = next(s for s in self._steps() if s.get("id") == CRITICAL_GATE_STEP_ID)
        assert "if" not in gate

    def test_scan_step_passes_no_fail_on(self):
        # A non-zero scanner exit is read by the gate as "the scan crashed".
        scan = next(s for s in self._steps() if s.get("name") == "Run Prompt Injection scan")
        assert "--fail-on" not in scan["run"]


class TestFailsClosed:

    def test_absent_report_blocks(self, tmp_path):
        p = _run(tmp_path, None)
        _assert_blocked(p)

    def test_empty_report_blocks(self, tmp_path):
        p = _run(tmp_path, "")
        _assert_blocked(p)

    @pytest.mark.parametrize("body", ["{not json", "[]", '{"findings": null}', '{"findings": {}}', "{}"])
    def test_unusable_report_blocks(self, tmp_path, body):
        p = _run(tmp_path, body)
        _assert_blocked(p)

    @pytest.mark.parametrize("outcome", ["failure", "cancelled", "bogus"])
    def test_scan_step_that_did_not_complete_blocks_even_with_a_clean_file(self, tmp_path, outcome):
        p = _run(tmp_path, CLEAN, outcome=outcome)
        _assert_blocked(p)

    def test_critical_prompt_finding_blocks(self, tmp_path):
        report = json.dumps({"findings": [{"severity": "critical", "rule": "X"}]})
        p = _run(tmp_path, report, outcome="success")
        assert p.returncode == 1, _detail(p)
        assert "Found 1 critical" in p.stdout, _detail(p)


class TestStaysOpenWhereItShould:

    def test_clean_report_passes(self, tmp_path):
        p = _run(tmp_path, CLEAN, outcome="success")
        assert p.returncode == 0, _detail(p)

    def test_unset_outcome_is_the_strict_path_and_passes_with_a_clean_report(self, tmp_path):
        p = _run(tmp_path, CLEAN)
        assert p.returncode == 0, _detail(p)

    def test_high_and_medium_findings_do_not_block(self, tmp_path):
        report = json.dumps({"findings": [{"severity": "high"}, {"severity": "medium"}]})
        p = _run(tmp_path, report, outcome="success")
        assert p.returncode == 0, _detail(p)

    def test_deliberately_skipped_scan_only_warns(self, tmp_path):
        p = _run(tmp_path, None, outcome="skipped")
        assert p.returncode == 0, _detail(p)
        assert "skipped" in p.stdout.lower()

    def test_skipped_scan_ignores_a_stale_report(self, tmp_path):
        stale = json.dumps({"findings": [{"severity": "critical"}]})
        p = _run(tmp_path, stale, outcome="skipped")
        assert p.returncode == 0, _detail(p)
