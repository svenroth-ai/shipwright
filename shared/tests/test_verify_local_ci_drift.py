"""`scripts/verify_local.py`'s registry must keep describing ci.yml's real merge gates.

@FR-01.17

Split from `test_verify_local.py` (which holds the wrapper's own behaviour) to keep both
under the 300-line budget. This half is the workflow-shape contract, and it guards two
failure modes that pull in opposite directions:

1. **Silent under-coverage.** A fourth guard is added to `ci.yml`, nobody adds it here,
   and `verify_local.py` keeps reporting "all gates passed" while covering three of
   four. A pre-flight that quietly stops being complete is worse than none, because it
   is trusted. The reverse-drift test is the load-bearing one.
2. **Over-claiming.** FR-01.17 requires an independent re-check on the code host and
   says a local pass is never accepted in place of it. This tool is a pre-flight, not a
   substitute, and the two gates that structurally cannot run locally must be recorded
   as such WITH a reason rather than quietly dropped.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"
_VERIFY_LOCAL = _REPO_ROOT / "scripts" / "verify_local.py"


def _load_subject():
    """Load the subject by path, never via `sys.path` (ADR-045).

    Duplicated from `test_verify_local.py` rather than imported: a test module importing
    a sibling test module depends on pytest's import mode and on `shared/tests` being an
    importable package, neither of which holds here. Six lines is the cheaper coupling.
    """
    spec = importlib.util.spec_from_file_location("_verify_local_drift_probe", _VERIFY_LOCAL)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_verify_local_drift_probe"] = module  # register BEFORE exec — ADR-045
    spec.loader.exec_module(module)
    return module


verify_local = _load_subject()

# A bespoke merge guard, as opposed to a test tier, lint, or provisioning: the step is
# named `(gate)`, or it runs one of this repo's own check_*/verify_* scripts. Test tiers
# are F0's job and lint is already in CLAUDE.md; the guards were nobody's job locally,
# which is the gap this tool fills.
#
# Both `check_` and `verify_` under EITHER script root, so a guard that lands without the
# `(gate)` suffix is still caught. The suffix is a separately-enforced convention
# (docs/hooks-and-pipeline.md), and leaning on it alone would make this test's coverage
# contingent on a rule living somewhere else.
_GUARD_SCRIPT = re.compile(r"(?:shared/)?scripts/(?:tools/)?(?:check|verify)_\w+\.py")


#: A shell comment, whether it owns the line or trails a command. Stripping only
#: full-line comments would pin half the property: a trailing
#: `pytest "$dir"   # kept in sync with .../check_ci_gate_coverage.py` enrols a TEST step
#: as a guard, and since such a step is neither mirrorable nor legitimately CI-only,
#: every PR in the repo goes red with no honest fix. A false red on a repo-wide gate is
#: worse than the gap it would be reporting.
_SHELL_COMMENT = re.compile(r"(^|\s)#.*$")


def _run_body(step: dict) -> str:
    """A step's `run:` with shell comments removed.

    Matching the raw body would let a script named in a COMMENT enrol an unrelated step —
    `ci.yml`'s "Run shared tests" carries 34 comment lines.
    `test_checks_that_gate.py:_executable_run_bodies` strips comments for the same reason.
    """
    return "\n".join(
        _SHELL_COMMENT.sub("", line) for line in (step.get("run") or "").splitlines()
    )


def _guard_steps() -> dict[str, str]:
    """Every bespoke guard across ALL workflows and ALL jobs.

    Not just `ci.yml`, and not just its required job. `.github/workflows/` holds seven
    workflows and `bloat-check.yml` / `pr-review.yml` are Required Checks too, so a
    guard landing in one of those would otherwise be invisible here forever while
    `verify_local.py` kept printing a count the operator reads as *the* list of
    unmirrored CI gates. Scanning everything costs nothing — it finds the same five
    today — and removes the blind spot rather than documenting it.
    """
    found: dict[str, str] = {}
    for path in sorted(_WORKFLOWS.glob("*.y*ml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job_name, job in (data.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            steps = job.get("steps") or []
            # A job with no steps is a workflow CALL (`uses:`). Its steps live in the
            # called file and are enumerated when the glob reaches it. A job that is
            # neither is malformed and must fail loudly, not yield silently.
            assert steps or job.get("uses"), (
                f"{path.name}:{job_name} has no steps and is not a workflow call — a "
                f"guard inside it would be invisible to this test"
            )
            for step in steps:
                body = _run_body(step)
                # An unnamed step is still gating. Key it by what it runs, so it cannot
                # slip through for lacking a label.
                name = step.get("name") or f"{path.name}:{step.get('uses') or body[:60]}"
                if name.endswith("(gate)") or _GUARD_SCRIPT.search(body):
                    assert name not in found, (
                        f"two guard steps named {name!r} — the registry is keyed by "
                        f"name, so one would silently shadow the other"
                    )
                    found[name] = body
    return found


def test_every_ci_guard_step_is_registered_exactly_once() -> None:
    """Reverse drift — the test that stops this going stale.

    Pinning today's five names by hand would pin only today's gates. Enumerating the
    guard steps out of `ci.yml` catches the next one: it lands unregistered and fails
    here, forcing a decision (mirror it locally, or record why it cannot be).
    """
    local = {gate.step for gate in verify_local.LOCAL_GATES}
    ci_only = set(verify_local.CI_ONLY_GATES)
    assert not (local & ci_only), f"registered as both: {sorted(local & ci_only)}"

    registered = local | ci_only
    found = set(_guard_steps())
    assert found, "no guard steps parsed from ci.yml — did the workflow shape change?"

    unregistered = found - registered
    assert not unregistered, (
        f"ci.yml guard step(s) missing from scripts/verify_local.py: "
        f"{sorted(unregistered)}. Add each to LOCAL_GATES (so it runs before a push) "
        f"or to CI_ONLY_GATES with the reason it cannot run locally. A pre-flight that "
        f"silently covers less than it claims is worse than none."
    )

    phantom = registered - found
    assert not phantom, (
        f"registered gate(s) that no longer exist in ci.yml: {sorted(phantom)}. Forward "
        f"drift — the local mirror would run a gate the merge no longer depends on, or "
        f"claim coverage of one that is gone."
    )


def test_a_checker_named_only_in_a_comment_does_not_enrol_a_step() -> None:
    """Guards the guard: `_run_body` is what makes the reverse-drift test survivable.

    Without comment-stripping, one sentence added to a test step's `run:` block that
    happens to mention a checker turns that step into an unregisterable "guard" and
    reddens every PR in the repo.
    """
    own_line = {"run": "set -e\n  # see shared/scripts/tools/check_ci_gate_coverage.py\n  pytest"}
    assert not _GUARD_SCRIPT.search(_run_body(own_line)), (
        "a checker named in a full-line comment still enrols the step"
    )
    # The half a full-line-only strip would miss. Trailing shell comments are ordinary.
    trailing = {"run": 'pytest "$dir"   # kept in sync with scripts/verify_contract_surface.py'}
    assert not _GUARD_SCRIPT.search(_run_body(trailing)), (
        "a checker named in a TRAILING comment still enrols the step — the "
        "reverse-drift test will false-red on an unrelated PR"
    )
    real = {"run": "uv run shared/scripts/tools/check_ci_gate_coverage.py --project-root ."}
    assert _GUARD_SCRIPT.search(_run_body(real)), "a real guard command must still match"


def test_the_wrapper_never_registers_itself() -> None:
    """`_GUARD_SCRIPT` matches `scripts/verify_local.py` too — that is a live trap.

    The natural next step for this tool is wiring it into a workflow. The moment that
    happens the reverse-drift test demands it be registered, and registering it in
    LOCAL_GATES makes `verify()` shell out to `uv run scripts/verify_local.py`, which
    shells out to itself: unbounded recursion, each level carrying its own timeout.
    CI_ONLY_GATES is the correct home for it. Nothing else says so.
    """
    assert not any(gate.script.endswith("verify_local.py")
                   for gate in verify_local.LOCAL_GATES), (
        "verify_local.py registered itself in LOCAL_GATES — running it would spawn "
        "itself recursively. If it is now wired into a workflow, record it in "
        "CI_ONLY_GATES instead: the wrapper cannot be one of its own gates."
    )


@pytest.mark.parametrize("gate", verify_local.LOCAL_GATES, ids=lambda g: g.step)
def test_each_local_gate_runs_what_ci_runs(gate) -> None:
    """Forward drift, per gate: the local command must be CI's command, as a WHOLE line.

    Substring containment would let `ci.yml` grow a flag — `... --strict` — while this
    stayed green and ran the weaker command, reporting PASS on a push CI rejects. That
    is the subtlest way for this tool to lie.
    """
    lines = [line.strip() for line in _guard_steps()[gate.step].splitlines()]
    assert " ".join(gate.command) in lines, (
        f"{gate.step!r} runs {[ln for ln in lines if ln]!r} in ci.yml but "
        f"{' '.join(gate.command)!r} here — the local mirror is checking a different "
        f"thing than the merge gate does."
    )


def test_every_ci_only_gate_says_why_it_cannot_run_locally() -> None:
    """An empty reason turns a deliberate exclusion into an unexplained gap."""
    for step, reason in verify_local.CI_ONLY_GATES.items():
        assert reason and len(reason.strip()) > 30, (
            f"CI_ONLY_GATES[{step!r}] carries no usable reason. Record WHY it cannot "
            f"run locally, so the next reader can tell a structural limit from a "
            f"to-do nobody got to."
        )


@pytest.mark.parametrize("gate", verify_local.LOCAL_GATES, ids=lambda g: g.step)
def test_the_registered_script_exists(gate) -> None:
    assert (_REPO_ROOT / gate.script).is_file(), (
        f"{gate.step!r} names {gate.script}, which is absent — the gate would fail for "
        f"a reason that is not a defect."
    )
