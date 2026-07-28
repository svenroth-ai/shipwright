"""AC-1 / AC-1b — an ``iterate_latest`` block that names another run is not evidence.

``shipwright_test_results.json`` is a DERIVED_SNAPSHOT. At F11 ``ensure_current``
→ ``integrate_main`` calls ``restore_derived_to_head``, which resets it to
``HEAD`` — and since an iterate no longer commits it, ``HEAD``'s copy is
``main``'s, i.e. the PREVIOUS run's evidence. Three F11 readers used to accept
that silently.

The fixtures below are deliberately *valid* for the foreign run: a gate that
merely re-validated the shape would pass them, which is exactly how the observed
"complete: 30 tested, 1 untestable" was reported for a run that had six.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from tools.verifiers._iterate_latest import (  # noqa: E402
    STATE_CURRENT,
    STATE_FOREIGN,
    STATE_MALFORMED,
    STATE_MISSING,
    STATE_UNATTRIBUTED,
    read_iterate_latest,
)
from tools.verifiers.iterate_checks import (  # noqa: E402
    check_surface_verification,
    check_test_completeness_ledger,
)

RUN = "iterate-2026-07-28-this-run"
OTHER = "iterate-2026-07-27-some-other-run"

_GOOD_LEDGER = {
    "status": "complete",
    "behaviors": [{"behavior": "b", "disposition": "tested", "evidence": "test_x"}],
    "counts": {"untested_testable": 0},
}
_GOOD_SURFACE = {"surface": "cli", "tests_run": 22, "exit_code": 0}


def _entry(root: Path, run_id: str, complexity: str = "medium", **extra) -> None:
    d = root / ".shipwright" / "agent_docs" / "iterates"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{run_id}.json").write_text(json.dumps({
        "run_id": run_id, "type": "bug", "complexity": complexity,
        "branch": "iterate/x", "tests_passed": True,
        "date": "2026-07-28T00:00:00+00:00", **extra,
    }), encoding="utf-8")


def _results(root: Path, owner: str | None, **blocks) -> None:
    latest: dict = dict(blocks)
    if owner is not None:
        latest["run_id"] = owner
    (root / "shipwright_test_results.json").write_text(
        json.dumps({"iterate_latest": latest}), encoding="utf-8",
    )


# --- the reader's typed contract (openai #5) --------------------------------

def test_states_are_distinguished(tmp_path):
    assert read_iterate_latest(tmp_path, RUN).state == STATE_MISSING

    _results(tmp_path, RUN, test_completeness=_GOOD_LEDGER)
    assert read_iterate_latest(tmp_path, RUN).state == STATE_CURRENT

    _results(tmp_path, OTHER, test_completeness=_GOOD_LEDGER)
    foreign = read_iterate_latest(tmp_path, RUN)
    assert foreign.state == STATE_FOREIGN
    assert foreign.owner == OTHER
    assert foreign.block is None, "a foreign block must not be handed to a caller"

    _results(tmp_path, None, test_completeness=_GOOD_LEDGER)
    assert read_iterate_latest(tmp_path, RUN).state == STATE_UNATTRIBUTED

    (tmp_path / "shipwright_test_results.json").write_text("{not json", encoding="utf-8")
    assert read_iterate_latest(tmp_path, RUN).state == STATE_MALFORMED


def test_a_blank_run_id_is_unattributed_not_current(tmp_path):
    """`""` must not compare equal to a caller that also passes `""`."""
    _results(tmp_path, "   ", test_completeness=_GOOD_LEDGER)
    assert read_iterate_latest(tmp_path, RUN).state == STATE_UNATTRIBUTED


# --- AC-1: the three callers fail closed ------------------------------------

def test_ledger_rejects_another_runs_ledger(tmp_path):
    _entry(tmp_path, RUN)
    _results(tmp_path, OTHER, test_completeness=_GOOD_LEDGER)

    result = check_test_completeness_ledger(tmp_path, RUN)

    assert result.is_failure, "a valid ledger belonging to another run passed the gate"
    assert OTHER in result.detail and RUN in result.detail


def test_surface_verification_rejects_another_runs_block(tmp_path):
    _entry(tmp_path, RUN)
    _results(tmp_path, OTHER, surface_verification=_GOOD_SURFACE)

    result = check_surface_verification(tmp_path, RUN)

    assert result.is_failure
    assert OTHER in result.detail


def test_declared_removals_do_not_cross_runs(tmp_path):
    """The worst direction: another run's declaration EXCUSING this run's removal."""
    from tools.verifiers.silent_revert import attributed_declared_removals

    _results(tmp_path, OTHER, declared_removals=[{"path": "a.md", "reason": "on purpose"}])
    entries, problem = attributed_declared_removals(tmp_path, RUN)

    assert entries == []
    assert problem and OTHER in problem


def test_declared_removals_are_honoured_for_their_own_run(tmp_path):
    from tools.verifiers.silent_revert import attributed_declared_removals

    _results(tmp_path, RUN, declared_removals=[{"path": "a.md", "reason": "on purpose"}])
    entries, problem = attributed_declared_removals(tmp_path, RUN)

    assert entries == [{"path": "a.md", "reason": "on purpose"}]
    assert problem is None


# --- AC-1b: the per-run entry is a home the restore cannot reach -------------

def test_the_f5c_entry_carries_the_run_past_a_rewound_snapshot(tmp_path):
    """Both blocks in the per-run entry ⇒ green even when the shared file was
    rewound to another run. Without this, AC-1 turns a false green into a
    permanent red (external review, gemini/high)."""
    _entry(tmp_path, RUN,
           test_completeness=_GOOD_LEDGER, surface_verification=_GOOD_SURFACE)
    _results(tmp_path, OTHER,
             test_completeness={"status": "complete", "behaviors": [], "counts": {}},
             surface_verification={"surface": "web", "tests_run": 0, "exit_code": 9})

    assert check_test_completeness_ledger(tmp_path, RUN).ok is True
    assert check_surface_verification(tmp_path, RUN).ok is True


def test_the_shared_file_still_works_when_it_names_this_run(tmp_path):
    _entry(tmp_path, RUN)
    _results(tmp_path, RUN,
             test_completeness=_GOOD_LEDGER, surface_verification=_GOOD_SURFACE)

    assert check_test_completeness_ledger(tmp_path, RUN).ok is True
    assert check_surface_verification(tmp_path, RUN).ok is True


# --- AC-3: a missing F5c entry fails, it does not skip -----------------------

def test_missing_iterate_entry_fails_the_ledger_check(tmp_path):
    _results(tmp_path, RUN, test_completeness=_GOOD_LEDGER)

    result = check_test_completeness_ledger(tmp_path, RUN)

    assert result.is_failure, "no F5c entry must not read as 'not applicable'"
    assert "F5c" in result.detail


def test_missing_iterate_entry_fails_surface_verification(tmp_path):
    _results(tmp_path, RUN, surface_verification=_GOOD_SURFACE)

    result = check_surface_verification(tmp_path, RUN)

    assert result.is_failure
    assert "F5c" in result.detail


def test_trivial_complexity_still_skips(tmp_path):
    """AC-3 must not swallow the deliberate trivial exemption."""
    _entry(tmp_path, RUN, complexity="trivial")
    _results(tmp_path, OTHER, test_completeness=_GOOD_LEDGER)

    assert check_test_completeness_ledger(tmp_path, RUN).is_skipped


# --- the WIRING, not just the function (external code review, openai #1) ----

def test_run_all_checks_hands_the_run_id_to_the_silent_revert_check(tmp_path, monkeypatch):
    """The regression this file did not catch on its own.

    `check_silent_revert_for_run` gained a `run_id` parameter and the F11
    orchestrator kept calling it without one. Every test above exercised the
    FUNCTION and passed, while the wired path would have resolved every
    declaration as foreign and reported legitimate declared removals as silent
    reverts. Testing the decision and not the call site is exactly how that got
    through, so the call site is asserted here directly.
    """
    from tools.verifiers import iterate_checks

    seen = {}

    def _spy(project_root, default_branch="main", run_id=""):
        seen["run_id"] = run_id
        from tools.verifiers.common import CheckResult
        return CheckResult("no silent revert of merged work", True, "stub")

    # By MODULE OBJECT, never the "tools.verifiers.X" string (ADR-045): the
    # orchestrator resolved its own reference at import time.
    monkeypatch.setattr(iterate_checks, "check_silent_revert_for_run", _spy)
    iterate_checks.run_all_checks(tmp_path, RUN, "")

    assert seen.get("run_id") == RUN, (
        "run_all_checks must pass the run id, or the declarations of the run "
        "being verified are read as another run's and silently dropped"
    )


def test_a_declaration_survives_the_wired_path(tmp_path):
    """End-to-end complement to the spy: a declaration attributed to THIS run
    is honoured by `check_silent_revert_for_run` as F11 actually calls it."""
    from tools.verifiers.silent_revert import check_silent_revert_for_run

    _results(tmp_path, RUN, declared_removals=[{"path": "a.md", "reason": "on purpose"}])
    result = check_silent_revert_for_run(tmp_path, run_id=RUN)

    # Not a git work tree → SKIPPED, but the point is that it did not blow up
    # and did not report the declaration as ignored.
    assert "ignored" not in result.detail


def test_a_disregarded_declaration_is_disclosed_even_on_a_clean_run(tmp_path):
    """openai #2 — silence about disregarded evidence is the one thing this
    check may not do.

    Nothing was dropped, so nothing was wrongly excused and a hard failure
    would be a false red. But declarations the gate did not use must still be
    reported: only the operator can tell stale leftovers from "my evidence was
    rewound and the run I meant to describe is unprotected".
    """
    import subprocess

    from tools.verifiers.common import Severity
    from tools.verifiers.silent_revert import check_silent_revert_for_run

    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)],
                   capture_output=True, check=False)
    _results(tmp_path, OTHER,
             declared_removals=[{"path": "a.md", "reason": "another run's reason"}])

    result = check_silent_revert_for_run(tmp_path, run_id=RUN)

    assert result.severity == Severity.WARNING.value
    assert OTHER in result.detail and "F5c" in result.detail


def test_no_declarations_anywhere_stays_silent(tmp_path):
    """The deliberate limit of "fail closed on every non-current state".

    Nothing was declared anywhere, so nothing is disregarded and nothing is
    excused — the caller still gets `[]`, so every dropped line still blocks.
    Reporting here would mean every iterate that removed nothing had to write
    `declared_removals: []` to prove a negative: ceremony on 100% of runs,
    defending against nothing. Declarations are an EXCEPTION mechanism, not
    evidence, which is why absence blocks the ledger and F0.5 gates but not
    this one. Asserted rather than left implicit, because a later reading of
    AC-1 will otherwise "fix" it (external code review, openai).
    """
    import subprocess

    from tools.verifiers.silent_revert import check_silent_revert_for_run

    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)],
                   capture_output=True, check=False)
    _results(tmp_path, OTHER, test_completeness=_GOOD_LEDGER)

    result = check_silent_revert_for_run(tmp_path, run_id=RUN)

    assert not result.is_failure
    assert "ignored" not in result.detail


def test_a_declaration_in_the_f5c_entry_survives_a_rewound_snapshot(tmp_path):
    """The durable producer path for declarations, end to end.

    `declared_removals` is the one block whose loss BLOCKS rather than merely
    failing to catch: a removal declared at F5 and then rewound by the F11
    integration is reported as undeclared, with the operator's reason sitting in
    a file that now describes another run. Carried in the per-run entry it
    survives, exactly as the ledger and F0.5 blocks do (external code review,
    openai #1).
    """
    from tools.verifiers.silent_revert import attributed_declared_removals

    _entry(tmp_path, RUN, declared_removals=[{"path": "a.md", "reason": "on purpose"}])
    _results(tmp_path, OTHER,
             declared_removals=[{"path": "z.md", "reason": "another run's reason"}])

    entries, problem = attributed_declared_removals(tmp_path, RUN)

    assert entries == [{"path": "a.md", "reason": "on purpose"}]
    assert problem is None, "the entry answered, so nothing was disregarded"


def test_a_truthy_non_object_iterate_latest_does_not_crash_the_gate(tmp_path):
    """`{"iterate_latest": ["stale"]}` is valid JSON and reaches the reader.

    `(x or {}).get(...)` guards None but not a truthy list, so counting the
    declarations about to be disregarded raised AttributeError and took the gate
    down instead of reporting it (external code review, openai #1).
    """
    import subprocess

    from tools.verifiers.silent_revert import (
        attributed_declared_removals,
        check_silent_revert_for_run,
    )

    (tmp_path / "shipwright_test_results.json").write_text(
        json.dumps({"iterate_latest": ["stale"]}), encoding="utf-8")

    assert read_iterate_latest(tmp_path, RUN).state == STATE_MALFORMED
    entries, problem = attributed_declared_removals(tmp_path, RUN)
    assert entries == []
    # Malformed is the one non-current state that reports unconditionally:
    # "no declarations" cannot be told from "declarations we could not read".
    assert problem and "could not be read" in problem

    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)],
                   capture_output=True, check=False)
    check_silent_revert_for_run(tmp_path, run_id=RUN)   # must not raise


def test_the_run_id_is_required_not_defaulted(tmp_path):
    """An unconverted two-argument caller must fail loudly, not silently treat
    every attributed block as foreign (external code review, openai #2)."""
    import pytest

    from tools.verifiers.silent_revert import check_silent_revert_for_run

    with pytest.raises(TypeError):
        check_silent_revert_for_run(tmp_path, "main")
