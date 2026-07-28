"""Unit tests for the ``check_security_scan`` PreToolUse deploy gate.

Split out of ``test_enforcement_hooks.py`` when this coverage pushed that file
past the 300-line cap (iterate-2026-07-28-hygiene-sweep).

The gate reads the SECURITY scan summary
(``.shipwright/compliance/ci-security.json``). Until this run it read the RTM row
``| Unresolved findings | N |`` instead — ``sum(review.findings - review.fixed)``
over ``work_completed`` events, i.e. code-review findings, which have nothing to
do with a scan (trg-17f53a39). Measured on the monorepo 2026-07-28: RTM said 24
unresolved while the scan said ``critical_gate=pass`` / ``by_severity.critical=0``,
so every deploy was soft-blocked with a message naming security.

Each branch of the gate is pinned here; the composition on a real project tree
is pinned by ``integration-tests/test_security_gate_subject.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).parent.parent / "scripts" / "hooks"
HOOK = "check_security_scan.py"
DEPLOY = {"tool_input": {"command": "deploy to jelastic"}}


def _run_hook(payload: dict, cwd: str | Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(HOOKS_DIR / HOOK)],
        input=json.dumps(payload), capture_output=True, text=True, cwd=str(cwd),
    )
    return result.returncode, result.stdout.strip()


def write_ci_security(
    project_root: Path,
    *,
    critical: int = 0,
    high: int = 0,
    degraded: bool = False,
    raw: str | None = None,
    omit_by_severity: bool = False,
    critical_gate: str | None = None,
) -> None:
    """Write ci-security.json in the producer's shape
    (``ci_security.summarize_ci_security``). ``raw`` writes arbitrary bytes so a
    malformed artifact can be exercised."""
    compliance_dir = project_root / ".shipwright" / "compliance"
    compliance_dir.mkdir(parents=True, exist_ok=True)
    target = compliance_dir / "ci-security.json"
    if raw is not None:
        target.write_text(raw, encoding="utf-8")
        return
    summary: dict = {
        "schema": 1,
        "scan_date": "2026-07-28T07:51:37Z",
        "source": "security.yml#30340025168",
        "total": critical + high,
        "open_high_critical": critical + high,
        "critical_gate": (critical_gate if critical_gate is not None
                          else ("fail" if critical > 0 else "pass")),
        "prompt_injection": 0,
        "degraded": degraded,
    }
    if not omit_by_severity:
        summary["by_severity"] = {
            "critical": critical, "high": high, "medium": 0, "low": 0}
    target.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def _write_rtm_unresolved(project_root: Path, unresolved: int) -> None:
    compliance_dir = project_root / ".shipwright" / "compliance"
    compliance_dir.mkdir(parents=True, exist_ok=True)
    (compliance_dir / "traceability-matrix.md").write_text(
        "# Requirements Traceability Matrix\n\n## Summary\n\n"
        "| Metric | Value |\n|--------|-------|\n"
        f"| Total review findings | 66 |\n| Unresolved findings | {unresolved} |\n",
        encoding="utf-8")


class TestCommandScope:
    def test_allows_non_deploy_command(self, tmp_path: Path):
        write_ci_security(tmp_path, critical=5)
        assert _run_hook({"tool_input": {"command": "npm test"}}, tmp_path)[0] == 0

    def test_deploy_word_in_quoted_arg_not_blocked(self, tmp_path: Path):
        """Regression: findings present, but the deploy word lives ONLY inside a
        quoted argument value (an iterate-finalization justification)."""
        write_ci_security(tmp_path, critical=5)
        rc, _ = _run_hook({"tool_input": {"command":
            'uv run surface_verification.py --justification '
            '"no status.json in any deployed flow"'}}, tmp_path)
        assert rc == 0


class TestScanVerdict:
    def test_allows_when_scan_is_clean(self, tmp_path: Path):
        write_ci_security(tmp_path, critical=0)
        assert _run_hook(DEPLOY, tmp_path)[0] == 0

    def test_blocks_deploy_on_open_criticals(self, tmp_path: Path):
        write_ci_security(tmp_path, critical=3)
        rc, output = _run_hook(DEPLOY, tmp_path)
        assert rc == 2
        data = json.loads(output)
        assert data["hookSpecificOutput"]["blocked"] is True
        assert "3 open critical" in data["hookSpecificOutput"]["reason"]

    def test_falls_back_to_critical_gate_when_counts_absent(self, tmp_path: Path):
        """An older/partial summary without by_severity still gates on the
        producer's own verdict rather than failing open."""
        write_ci_security(tmp_path, omit_by_severity=True, critical_gate="fail")
        assert _run_hook(DEPLOY, tmp_path)[0] == 2
        write_ci_security(tmp_path, omit_by_severity=True, critical_gate="pass")
        assert _run_hook(DEPLOY, tmp_path)[0] == 0

    def test_an_unsizeable_fail_blocks_at_every_threshold(self, tmp_path: Path):
        """Self-review catch. ``critical_gate`` is a boolean verdict; reading a
        'fail' as "1 critical" would let a threshold of 1+ ALLOW a deploy the
        producer just refused, on a count nobody measured. Unsizeable ⇒ block.
        """
        (tmp_path / "shipwright_compliance_config.json").write_text(
            json.dumps({"enforcement": {"allowed_critical_findings": 5}}),
            encoding="utf-8")
        write_ci_security(tmp_path, omit_by_severity=True, critical_gate="fail")
        rc, output = _run_hook(DEPLOY, tmp_path)
        assert rc == 2
        assert "cannot be sized" in json.loads(output)["hookSpecificOutput"]["reason"]

    def test_an_exact_count_is_still_sized_against_the_threshold(self, tmp_path: Path):
        """The counterpart: with a real count, tolerance applies normally."""
        (tmp_path / "shipwright_compliance_config.json").write_text(
            json.dumps({"enforcement": {"allowed_critical_findings": 5}}),
            encoding="utf-8")
        write_ci_security(tmp_path, critical=4)
        assert _run_hook(DEPLOY, tmp_path)[0] == 0

    def test_high_findings_alone_do_not_gate(self, tmp_path: Path):
        """External review (OpenAI #7): the config key is named
        allowed_critical_findings. Gating it on critical+high would silently
        broaden an operator's existing setting."""
        write_ci_security(tmp_path, critical=0, high=7)
        assert _run_hook(DEPLOY, tmp_path)[0] == 0

    def test_review_findings_counter_no_longer_gates(self, tmp_path: Path):
        """The monorepo's exact state on 2026-07-28."""
        _write_rtm_unresolved(tmp_path, 24)
        write_ci_security(tmp_path, critical=0)
        assert _run_hook(DEPLOY, tmp_path)[0] == 0

    def test_an_old_but_valid_clean_scan_still_allows(self, tmp_path: Path):
        """Pins a DELIBERATE limitation rather than leaving it implicit.

        External plan review (OpenAI #2) asked for a freshness rule. The summary
        has no commit binding, and the producer is a weekly cron plus a PR gate,
        so gating on age would block every deploy between scans. This asserts
        the decision so a future reader sees intent, not an oversight: freshness
        belongs to the producer, and this gate reads what the producer wrote.
        """
        write_ci_security(tmp_path, critical=0)
        path = tmp_path / ".shipwright" / "compliance" / "ci-security.json"
        summary = json.loads(path.read_text(encoding="utf-8"))
        summary["scan_date"] = "2019-01-01T00:00:00Z"
        path.write_text(json.dumps(summary), encoding="utf-8")
        assert _run_hook(DEPLOY, tmp_path)[0] == 0


class TestBrokenOrAbsentArtifact:
    def test_allows_when_never_scanned(self, tmp_path: Path):
        """No summary at all = never scanned (fresh adopt), not scanned-clean.
        The one state that legitimately fails open."""
        assert _run_hook(DEPLOY, tmp_path)[0] == 0

    def test_blocks_on_malformed_summary(self, tmp_path: Path):
        """External review (OpenAI #1, Gemini #1): a truncated write or a format
        regression must not read as clean. Present-but-unusable fails CLOSED."""
        write_ci_security(tmp_path, raw='{"schema": 1, "by_sever')
        rc, output = _run_hook(DEPLOY, tmp_path)
        assert rc == 2
        assert "unreadable or malformed" in json.loads(output)[
            "hookSpecificOutput"]["reason"]

    def test_blocks_when_summary_is_not_an_object(self, tmp_path: Path):
        write_ci_security(tmp_path, raw="[]")
        assert _run_hook(DEPLOY, tmp_path)[0] == 2

    def test_blocks_when_the_path_is_a_directory(self, tmp_path: Path):
        """External code review (OpenAI): ``is_file()`` alone reads a directory
        (or any non-regular artifact) at that path as 'never scanned' and fails
        OPEN — precisely the corrupted state the gate exists to catch."""
        (tmp_path / ".shipwright" / "compliance" / "ci-security.json").mkdir(
            parents=True)
        rc, output = _run_hook(DEPLOY, tmp_path)
        assert rc == 2
        assert "unreadable or malformed" in json.loads(output)[
            "hookSpecificOutput"]["reason"]

    def test_blocks_on_degraded_scan(self, tmp_path: Path):
        """A leg that fataled returned [] — green by absence, not by evidence."""
        write_ci_security(tmp_path, critical=0, degraded=True)
        rc, output = _run_hook(DEPLOY, tmp_path)
        assert rc == 2
        assert "degraded" in json.loads(output)["hookSpecificOutput"]["reason"]

    def test_blocks_when_summary_carries_no_verdict(self, tmp_path: Path):
        write_ci_security(tmp_path, omit_by_severity=True, critical_gate="unknown")
        assert _run_hook(DEPLOY, tmp_path)[0] == 2


class TestSubdirectoryProjectLayout:
    """F5 (WP5): the gate resolves the project root via resolve_project_root(),
    NOT os.getcwd(), so a workspace whose managed project lives one level down
    does not fail open."""

    def test_blocks_from_workspace_root(self, tmp_path: Path):
        project = tmp_path / "webui"
        project.mkdir(parents=True, exist_ok=True)
        (project / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
        write_ci_security(project, critical=3)
        rc, output = _run_hook(DEPLOY, tmp_path)  # cwd ABOVE the managed project
        assert rc == 2
        data = json.loads(output)
        assert data["hookSpecificOutput"]["blocked"] is True
        assert "3 open critical" in data["hookSpecificOutput"]["reason"]


class TestThreshold:
    def _config(self, tmp_path: Path, allowed: int) -> None:
        (tmp_path / "shipwright_compliance_config.json").write_text(
            json.dumps({"enforcement": {"allowed_critical_findings": allowed}}),
            encoding="utf-8")

    def test_respects_custom_threshold(self, tmp_path: Path):
        write_ci_security(tmp_path, critical=2)
        self._config(tmp_path, 3)
        assert _run_hook(DEPLOY, tmp_path)[0] == 0

    def test_threshold_boundary_is_inclusive(self, tmp_path: Path):
        self._config(tmp_path, 2)
        write_ci_security(tmp_path, critical=2)
        assert _run_hook(DEPLOY, tmp_path)[0] == 0, "exactly at threshold allows"
        write_ci_security(tmp_path, critical=3)
        assert _run_hook(DEPLOY, tmp_path)[0] == 2, "one above threshold blocks"

    def test_a_malformed_threshold_falls_back_to_zero_tolerance(self, tmp_path: Path):
        """A hand-edited config must not be able to widen the gate (or crash
        the comparison into the fail-open wrapper)."""
        write_ci_security(tmp_path, critical=1)
        for bad in ("lots", -3, True, None):
            (tmp_path / "shipwright_compliance_config.json").write_text(
                json.dumps({"enforcement": {"allowed_critical_findings": bad}}),
                encoding="utf-8")
            assert _run_hook(DEPLOY, tmp_path)[0] == 2, f"threshold={bad!r}"
