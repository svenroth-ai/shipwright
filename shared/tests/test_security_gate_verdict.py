"""The security gate's verdict says what it covers — and still gates the same.

@FR-01.17

This repo's own ``security.yml``, not the adopt template (whose gate is a
different, SARIF-based body pinned by ``test_security_workflow_convention.py``).

The step printed a bare ``Critical findings: 0`` and exited 0 while high findings
sat unmentioned — a clean bill of health for a gate that only ever looked at one
severity. The gate itself is correct: blocking on ``critical`` alone is the
deliberate posture. So these tests pin the honest report AND that adding it did
not move the gate — turning highs into merge blockers is a posture change and
belongs in an ADR, not in a reporting fix.

The sibling half — checks wired to nothing at all — is
``test_checks_that_gate.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_SECURITY = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "security.yml"



@pytest.fixture(scope="module")
def critical_gate_run() -> str:
    data = yaml.safe_load(_SECURITY.read_text(encoding="utf-8"))
    for job in data["jobs"].values():
        for step in job.get("steps") or []:
            if step.get("id") == "shipwright-critical-gate":
                return step.get("run", "")
    raise AssertionError(
        "security.yml has no step with id 'shipwright-critical-gate' — the "
        "compliance A5 audit locates the gate by that id (lib/security_workflow.py)"
    )


def test_verdict_is_labelled_not_a_bare_count(critical_gate_run: str) -> None:
    """`Critical findings: 0` reads as 'secure'. Name the gate and its verdict."""
    assert "critical-gate" in critical_gate_run
    assert "PASS" in critical_gate_run and "FAIL" in critical_gate_run, (
        "the gate prints no verdict word — a reader has to infer pass/fail from "
        "a number whose scope they cannot see"
    )


def test_every_severity_is_counted_across_both_scan_outputs(critical_gate_run: str) -> None:
    """A prompt-injection high is still a high.

    The blocking total already spans `findings.json` + `prompt_risks.json`.
    Counting the breakdown from `findings.json` alone printed `0 high` while an
    open prompt-injection high sat unmentioned — the exact understatement this
    block exists to remove, reintroduced one line below the fix.
    """
    run = critical_gate_run
    helper = re.search(r"count_sev\(\)\s*\{(.*?)\n\s*\}", run, re.DOTALL)
    assert helper, "no count_sev helper — severities are counted ad hoc"
    body = helper.group(1)
    assert "findings.json" in body and "prompt_risks.json" in body, (
        "the severity count consults only one scan output"
    )
    for severity in ("high", "medium", "low"):
        assert f"{severity}=$(count_sev {severity})" in run, (
            f"{severity} is not counted through the both-sources helper"
        )


def test_breakdown_reaches_the_job_summary(critical_gate_run: str) -> None:
    """Step logs are one click deep; the summary is the page people read."""
    assert "GITHUB_STEP_SUMMARY" in critical_gate_run
    assert "| severity |" in critical_gate_run, "no severity table in the summary"


def test_the_console_verdict_line_spends_the_counts_it_computed(
    critical_gate_run: str,
) -> None:
    """The counts must reach the ONE line the step log leads with.

    The two tests above pin that every severity is *counted* and that the table
    reaches the job summary. Neither pins the console line, and a verdict that
    computes `$high` and then prints only the blocking total is the original
    understatement restated one sink over — visible precisely where a reader
    looks first.

    Scoped to the text BEFORE the job-summary guard, which is what makes it a
    test about the step log rather than about the phrase. Matching the whole
    body would accept the line being MOVED inside the `>> $GITHUB_STEP_SUMMARY`
    group: the console would fall silent, the summary would still be complete,
    and both this test and `test_breakdown_reaches_the_job_summary` would stay
    green. Selection is by prefix, not position, so the summary's own
    `**critical-gate ...` line cannot stand in for the console one either.
    """
    head, guard, _ = critical_gate_run.partition('if [ -n "${GITHUB_STEP_SUMMARY:-}"')
    assert guard, (
        "the job-summary guard is gone — without it this test cannot tell the "
        "step log from the summary sink, and would pass on a silent console"
    )
    console = [
        ln.strip() for ln in head.splitlines()
        if ln.strip().startswith('echo "critical-gate')
    ]
    assert len(console) == 1, (
        f'expected exactly one `echo "critical-gate ..."` line, found '
        f"{len(console)}: {console}. The guarantee is that ONE line carries the "
        f"whole breakdown; spread over several, each is incomplete where it is "
        f"read and only their union is honest."
    )
    missing = [
        var for var in ("$total", "$high", "$medium", "$low")
        if var not in console[0]
    ]
    assert not missing, (
        f"the console verdict omits {missing} — it reports only the severity it "
        f"blocks on, which is what this module exists to remove: {console[0]}"
    )


def test_reporting_cannot_fail_the_gate(critical_gate_run: str) -> None:
    """The breakdown is a log line; it must never be able to block a merge.

    The step runs under `set -e`, so appending to an unset `GITHUB_STEP_SUMMARY`
    redirects to an empty filename and exits 1 — a security gate failing over a
    cosmetic sink. The A5.8 behavioral probe executes this body outside Actions
    and caught exactly that.
    """
    assert 'if [ -n "${GITHUB_STEP_SUMMARY:-}" ]' in critical_gate_run, (
        "the job-summary write is unguarded — outside GitHub Actions the gate "
        "dies on a clean scan"
    )


def test_passing_with_open_high_findings_is_said_out_loud(critical_gate_run: str) -> None:
    assert "::warning::" in critical_gate_run, (
        "a PASS with open high findings emits no warning annotation — the "
        "run reads as clean in the checks list"
    )


def test_the_gate_itself_still_blocks_on_critical_only(critical_gate_run: str) -> None:
    """The change was reporting-only. Pin that it did not move the gate.

    Blocking on critical alone is the deliberate posture; making the report
    honest must not quietly turn highs into merge blockers (nor stop criticals
    from blocking).
    """
    assert re.search(r'total=\$\(\(critical \+ prompt_critical\)\)', critical_gate_run), (
        "the blocking total is no longer critical + prompt-critical"
    )
    # `\n\s*fi` — a bare `fi` also occurs inside the word "findings" one line in.
    blocking = re.search(
        r'if \[ "\$total" -gt 0 \]; then(.*?)\n\s*fi\b', critical_gate_run, re.DOTALL
    )
    assert blocking and "exit 1" in blocking.group(1), (
        "criticals no longer fail the step — the gate stopped gating"
    )
    for severity in ("high", "medium", "low"):
        assert not re.search(rf'\[ "\${severity}" -gt 0 \][^\n]*\n[^\n]*exit 1', critical_gate_run), (
            f"{severity} findings now block the merge. That may be right, but it "
            f"is a posture change and belongs in an ADR, not in a reporting fix."
        )
