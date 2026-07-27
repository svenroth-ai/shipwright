"""Two workflow-shape contracts for checks that must actually hold something up.

@FR-01.17

This repo's own workflows, not the adopt templates (those are pinned by
``test_ci_workflow_convention.py`` / ``test_security_workflow_convention.py``).

Both halves guard the same failure: **a check that runs, reports a result and
gates nothing reads as protection while providing none.**

- *Surface verifiers wired to nothing* — ``scripts/verify_contract_surface.py``
  and ``scripts/verify_sweep_delivery_surface.py`` existed, were correct, and
  were referenced by no workflow. They ran nowhere. The reverse-drift test here
  is the load-bearing one: it fails on the NEXT surface verifier born an orphan,
  which is the only way this does not recur.
- *A gate verdict that overstates itself* — ``security.yml`` printed a bare
  ``Critical findings: 0`` and exited 0 while high findings sat unmentioned. The
  gate is correct (blocking on critical is the deliberate posture); the
  *reporting* implied a clean bill of health. The tests pin the honest form AND
  that adding it did not move the gate.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"
_CI = _WORKFLOWS / "ci.yml"
_SECURITY = _WORKFLOWS / "security.yml"

# The required job. Wiring a gate into a job branch protection does not require
# would leave it exactly as decorative as running it nowhere.
_REQUIRED_JOB = "python-checks"

_SURFACE_GATES = {
    "Contract surface (gate)": "scripts/verify_contract_surface.py",
    "Sweep delivery surface (gate)": "scripts/verify_sweep_delivery_surface.py",
}


def _steps(workflow: Path, job: str) -> list[dict]:
    data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    return data["jobs"][job]["steps"]


def _executable_run_bodies() -> str:
    """Every workflow `run:` line that actually executes and can fail the job.

    Deliberately NOT a raw text search of the workflow files: a verifier named in
    a YAML comment, an `env:` value or a `continue-on-error` step would satisfy
    that while still running nowhere or gating nothing — which is the exact
    condition this module exists to detect.
    """
    lines: list[str] = []
    for path in sorted(_WORKFLOWS.glob("*.y*ml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job in (data.get("jobs") or {}).values():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                if not isinstance(step, dict) or step.get("continue-on-error") is True:
                    continue
                run = step.get("run")
                if not isinstance(run, str):
                    continue
                lines += [ln for ln in run.splitlines() if not ln.strip().startswith("#")]
    return "\n".join(lines)


def _step(workflow: Path, job: str, name: str) -> dict:
    for step in _steps(workflow, job):
        if step.get("name") == name:
            return step
    raise AssertionError(
        f"{workflow.name} job {job!r} has no step named {name!r} — "
        f"found: {[s.get('name') for s in _steps(workflow, job) if s.get('name')]}"
    )


# ---------------------------------------------------------------------------
# Item 5 + the third orphan — the surface verifiers block
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("step_name,script", sorted(_SURFACE_GATES.items()))
def test_surface_verifier_runs_in_the_required_job(step_name: str, script: str) -> None:
    step = _step(_CI, _REQUIRED_JOB, step_name)
    assert script in step.get("run", ""), (
        f"{step_name!r} no longer invokes {script} — the verifier is back to "
        f"running nowhere."
    )


@pytest.mark.parametrize("step_name", sorted(_SURFACE_GATES))
def test_surface_verifier_is_a_hard_gate(step_name: str) -> None:
    step = _step(_CI, _REQUIRED_JOB, step_name)
    assert step.get("continue-on-error") is not True, (
        f"{step_name!r} carries continue-on-error — it would run, report, and "
        f"hold nothing up, which is the whole defect this step was added to fix."
    )
    assert "|| true" not in step.get("run", ""), (
        f"{step_name!r} suppresses its own exit code."
    )


@pytest.mark.parametrize("script", sorted(_SURFACE_GATES.values()))
def test_gated_script_exists(script: str) -> None:
    """Forward drift: a step naming a script that is gone fails the whole job."""
    assert (_REPO_ROOT / script).is_file(), f"{script} is referenced by ci.yml but absent"


def test_every_surface_verifier_is_wired_to_some_workflow() -> None:
    """Reverse drift — the one that stops this recurring.

    Both current verifiers shipped correct and connected to nothing, because
    nothing ever asked. Pinning the two names by hand would pin only today's
    orphans; enumerating the namespace catches tomorrow's.
    """
    verifiers = sorted(p.name for p in (_REPO_ROOT / "scripts").glob("verify_*_surface.py"))
    assert verifiers, "no scripts/verify_*_surface.py found — did the naming change?"

    executed = _executable_run_bodies()
    orphans = [name for name in verifiers if name not in executed]
    assert not orphans, (
        f"surface verifier(s) referenced by no workflow: {orphans}. They run "
        f"nowhere and gate nothing. Wire them into ci.yml's {_REQUIRED_JOB!r} "
        f"job (verify they pass locally FIRST — wiring a red gate blocks every "
        f"PR), or delete them."
    )


def test_a_verifier_named_only_in_a_comment_is_still_an_orphan() -> None:
    """The wiring check must read what EXECUTES, not what is merely written down.

    A raw text search over the workflow files would accept a verifier mentioned in
    a YAML comment, an `env:` value, or a `continue-on-error` step — all of which
    run nowhere or gate nothing, which is the condition being detected. Guards the
    guard: `_executable_run_bodies` is what makes the orphan test mean something.
    """
    executed = _executable_run_bodies()
    raw = "\n".join(p.read_text(encoding="utf-8") for p in sorted(_WORKFLOWS.glob("*.y*ml")))

    # A phrase that appears ONLY inside a comment in ci.yml (see the wiring
    # rationale above the two gate steps) must be visible raw and absent from
    # the executable view.
    assert "It existed and was referenced by no workflow" in raw
    assert "It existed and was referenced by no workflow" not in executed, (
        "comment text is leaking into the executable view — the orphan check "
        "would accept a verifier that is only talked about"
    )
    # The real command, by contrast, must be present in both.
    assert "scripts/verify_contract_surface.py" in executed


def test_the_gate_guard_can_see_the_surface_gates() -> None:
    """The loose-gate guard must recognise these steps, or it cannot defend them.

    ``check_ci_gate_coverage.py`` only flags a *gate* step that goes loose. These
    two run a bespoke script, so they matched no gate command and no name
    keyword: the guard was blind to them and a later ``continue-on-error`` would
    have passed unnoticed. The ``(gate)`` name suffix is what enrols them.
    """
    import importlib.util
    import sys

    sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))
    tool = _REPO_ROOT / "shared" / "scripts" / "tools" / "check_ci_gate_coverage.py"
    spec = importlib.util.spec_from_file_location("_cgc_probe", tool)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_cgc_probe"] = module
    try:
        spec.loader.exec_module(module)
        from lib.ci_gate_scan import parse_workflows

        seen = {
            step.name: module.is_gate_step(step)
            for step in parse_workflows(_REPO_ROOT)
            if step.workflow == "ci.yml" and step.name in _SURFACE_GATES
        }
    finally:
        sys.modules.pop("_cgc_probe", None)

    assert set(seen) == set(_SURFACE_GATES), f"steps not parsed from ci.yml: {seen}"
    blind = [name for name, is_gate in seen.items() if not is_gate]
    assert not blind, (
        f"the CI-gate guard does not classify {blind} as gate steps, so it would "
        f"not notice them being loosened. Keep the `(gate)` name suffix, or "
        f"register the command in GATE_COMMANDS."
    )


# ---------------------------------------------------------------------------
# Item 4 — the security verdict says what it covers
# ---------------------------------------------------------------------------


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
