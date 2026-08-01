"""F0 diff-coverage gate — argv construction and the fail-closed verdict.

Every behaviour here is reachable IN-PROCESS. That is deliberate, not stylistic:
the gate this change adds measures the percentage of CHANGED lines that tests
execute, and a test that only shells out to the gate would score its own subject
at 0% (the code runs in another interpreter, where `coverage` cannot see it). So
the decision function is pure, and the one function that does spawn processes
takes its `runner` as a parameter — no monkeypatching of a dotted string, which
under ADR-045 may not even name the module under test.

This half covers the PURE decisions: the two argv builders and the verdict/exit-code
functions. The side-effecting halves (compare-branch resolution, the reset, the
missing-data check, the orchestrator) are in `test_suite_coverage_gate.py`; the
end-to-end proof that the gate BITES against the real pinned diff-cover is in
`test_f0_diff_coverage_e2e.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.tools.suite_coverage import (
    COVERAGE_XML,
    DATA_DIR,
    DIFF_COVER_VERSION,
    DIFF_COVER_BELOW_THRESHOLD,
    FAIL_UNDER,
    GATE_FAILED,
    GATE_PASSED,
    GateResult,
    combine_argv,
    final_exit_code,
    gate_argv,
    verdict,
)
from scripts.tools.suite_units import PYTHON_VERSION


# --------------------------------------------------------------------------- #
# argv builders (pure)
# --------------------------------------------------------------------------- #
def test_gate_argv_mirrors_the_ci_composite_action():
    """AC-3 shape. The version/threshold are pinned against action.yml itself by
    test_f0_ci_parity; here we pin the COMMAND, so a local run and CI cannot
    diverge on flags."""
    argv = gate_argv("origin/main")
    assert argv[:2] == ["uvx", f"diff-cover@{DIFF_COVER_VERSION}"]
    assert argv[2] == COVERAGE_XML
    assert "--compare-branch=origin/main" in argv
    assert f"--fail-under={FAIL_UNDER:g}" in argv


def test_gate_argv_measures_files_the_iterate_has_not_committed_yet():
    """The one deliberate divergence from the CI action, and the reason for it.

    F0 runs BEFORE F6 (the commit), so every file the iterate ADDS is untracked —
    and diff-cover reads git, which by default cannot see them. Without this flag a
    diff of mostly-new modules is scored over the few tracked lines it happens to
    touch, and a diff of ONLY new files measures nothing and reports a confident
    100%: the under-covered case the gate exists for, passing locally and reddening
    CI. The action needs no such flag because it runs on a committed PR head.
    """
    assert "--include-untracked" in gate_argv("origin/main")


def test_gate_argv_carries_the_resolved_branch_not_a_hardcoded_one():
    argv = gate_argv("origin/trunk")
    assert "--compare-branch=origin/trunk" in argv
    assert "--compare-branch=origin/main" not in argv


def test_combine_argv_delegates_to_the_one_combiner():
    """There must be exactly ONE combine implementation. This builds the same
    invocation ci.yml's Combine step makes, so `combine_coverage.py` stays it."""
    argv = combine_argv()
    assert argv[:4] == ["uv", "run", "--python", PYTHON_VERSION]
    joined = " ".join(argv)
    assert "combine_coverage.py" in joined
    assert f"--data-dir {DATA_DIR}" in joined.replace("  ", " ")
    assert f"--output {COVERAGE_XML}" in joined.replace("  ", " ")


def test_both_argvs_are_lists_never_shell_strings():
    for argv in (gate_argv("origin/main"), combine_argv()):
        assert isinstance(argv, list)
        assert all(isinstance(tok, str) for tok in argv)
        assert not any(tok in ("&&", "||", ";", "|") for tok in argv)


# --------------------------------------------------------------------------- #
# verdict (pure) — the fail-closed decision
# --------------------------------------------------------------------------- #
def test_nothing_eligible_is_n_a_and_passes():
    """AC-4b, first half: a repo with no measurable unit has nothing to gate."""
    res = verdict(eligible=0, branch="origin/main")
    assert res.exit_code == GATE_PASSED
    assert any("n/a" in line for line in res.lines)


def test_eligible_units_but_no_xml_fails_closed():
    """AC-4b, second half — and the one place this is deliberately STRICTER than
    ci.yml, whose `if: hashFiles('coverage.xml') != ''` guard cannot tell a
    legitimately empty measurement from a broken one."""
    res = verdict(eligible=3, branch="origin/main", combine_rc=0, xml_exists=False)
    assert res.exit_code == GATE_FAILED
    assert any("no combined coverage.xml" in line for line in res.lines)


def test_a_failed_combine_fails_closed():
    res = verdict(eligible=3, branch="origin/main", combine_rc=1, xml_exists=False)
    assert res.exit_code == GATE_FAILED
    assert any("combine" in line for line in res.lines)


def test_below_threshold_fails_and_says_what_to_do():
    res = verdict(eligible=3, branch="origin/main", combine_rc=0, xml_exists=True,
                  gate_rc=DIFF_COVER_BELOW_THRESHOLD)
    assert res.exit_code == GATE_FAILED
    joined = " ".join(res.lines)
    assert "Add tests" in joined
    # This gate can be STRICTER than CI, because a test that skips locally still
    # runs there. Saying so is the difference between a fixable message and one that
    # tells the operator to write a test that already exists.
    assert "SKIP on this machine" in joined


def test_a_broken_diff_cover_is_not_reported_as_a_threshold_verdict():
    """diff-cover exits 1 for EXACTLY below-threshold. Any other non-zero is its own
    failure — an unresolvable ref, a package it could not fetch — where the coverage
    number is unknown and "add tests" is the wrong instruction."""
    res = verdict(eligible=3, branch="origin/main", combine_rc=0, xml_exists=True,
                  gate_rc=2, detail="No such file")
    assert res.exit_code == GATE_FAILED
    joined = " ".join(res.lines)
    assert "not a threshold verdict" in joined
    assert "Add tests" not in joined
    assert "Pre-fetch" in joined


def test_at_or_above_threshold_passes():
    res = verdict(eligible=3, branch="origin/main", combine_rc=0, xml_exists=True, gate_rc=0)
    assert res.exit_code == GATE_PASSED


def test_an_unresolvable_compare_branch_fails_closed_with_a_fix():
    """AC-4d. A base that cannot be found must never silently green a gate whose
    entire job is to compare against it."""
    res = verdict(eligible=3, branch=None)
    assert res.exit_code == GATE_FAILED
    joined = " ".join(res.lines)
    assert "compare branch" in joined
    assert "git fetch" in joined, "the refusal must name the command that fixes it"


# --------------------------------------------------------------------------- #
# final_exit_code — how the three verdicts compose
# --------------------------------------------------------------------------- #
_PASS = GateResult(GATE_PASSED, [])
_FAIL = GateResult(GATE_FAILED, [])


@pytest.mark.parametrize("suite_rc,race_failed,gate,expected", [
    (0, False, _PASS, 0),
    (0, False, _FAIL, GATE_FAILED),
    # A red suite keeps its own rc: it STOPs either way, and reporting the
    # coverage code would misdescribe why.
    (1, False, _FAIL, 1),
    (2, False, _FAIL, 2),
    # An unrecorded race outranks the coverage gate for the same reason.
    (0, True, _FAIL, 3),
    (0, True, _PASS, 3),
])
def test_exit_code_precedence(suite_rc, race_failed, gate, expected):
    assert final_exit_code(suite_rc, race_failed, gate) == expected
