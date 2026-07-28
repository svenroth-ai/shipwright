"""The workflow-shape contract for checks that must actually hold something up.

@FR-01.17

This repo's own workflows, not the adopt templates (those are pinned by
``test_ci_workflow_convention.py`` / ``test_security_workflow_convention.py``).

The failure guarded here: **a check that runs, reports a result and gates
nothing reads as protection while providing none.**

*Surface verifiers wired to nothing* — ``scripts/verify_contract_surface.py``
and ``scripts/verify_sweep_delivery_surface.py`` existed, were correct, and were
referenced by no workflow. They ran nowhere. The reverse-drift test here is the
load-bearing one: it fails on the NEXT surface verifier born an orphan, which is
the only way this does not recur.

The sibling half — a gate verdict that overstates what it covers — is
``test_security_gate_verdict.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"
_CI = _WORKFLOWS / "ci.yml"

# The required job. Wiring a gate into a job that branch protection does not
# require would leave it exactly as decorative as running it nowhere.
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


def test_the_sweep_verifier_does_not_hand_its_own_ci_flag_to_its_subject() -> None:
    """A gate must not be reddened by the environment it is a gate in.

    `sweep_outbox_to_branch` refuses to auto-commit when `$CI` is set
    (`ci_without_optin`) — a real guard, and correct: a CI job must never commit
    to a branch on its own. But this verifier's fixture models an OPERATOR'S
    machine, so a child that inherits `$CI` makes the subject skip itself and the
    checks read the guard as six delivery failures. Caught the first time the
    step ran in Actions: 8/8 locally, 2/8 in CI, on the same commit.
    """
    path = _REPO_ROOT / "scripts" / "verify_sweep_delivery_surface.py"
    src = path.read_text(encoding="utf-8")
    assert 'k != "CI"' in src, (
        "the verifier no longer scrubs $CI from the child environment — it will "
        "pass locally and fail in CI for a reason that is not a defect"
    )
    # Read the call, not the text: a regex over source stops at the first ')'
    # and would pass on a call that builds the scrubbed env and never uses it.
    setup_calls = [
        node for node in ast.walk(ast.parse(src))
        if isinstance(node, ast.Call)
        and "_SETUP" in {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    ]
    assert setup_calls, "no subprocess call driving _SETUP found"
    assert any(kw.arg == "env" for call in setup_calls for kw in call.keywords), (
        "the scrubbed environment is built but never passed to the setup "
        "subprocess, so the child still inherits $CI"
    )


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
