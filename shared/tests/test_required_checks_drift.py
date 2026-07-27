"""The must-pass set is compared against the checks that actually exist.

@FR-01.17

Which checks block a merge is configured outside the repository, so the two
drift in both directions and neither is visible from inside:

- **unenforced** — a check runs on every PR, reports a result, and holds nothing
  up. Worse than no check, because it reads as protection.
- **phantom** — the configured set names a check nothing produces, so every PR
  waits forever on a result that cannot arrive.

The enumeration test is the load-bearing one. The first draft of the producer
derived names from ``automerge_readiness.KNOWN_WORKFLOWS`` — deliberately the
five workflows ``/shipwright-adopt`` scaffolds — and reported this repo's own
``bloat-check.yml`` and ``pr-review-run.yml`` contexts as phantoms. A drift
producer that cries wolf gets muted, so under-derivation is the failure mode to
pin, not a detail.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.required_checks_drift import (  # noqa: E402
    all_workflow_check_names,
    compare_required_checks,
    dedup_key,
    render_drift,
)

_ROOT = Path(__file__).resolve().parents[2]


def test_identical_sets_are_in_sync() -> None:
    r = compare_required_checks(["a", "b"], ["b", "a"])
    assert r["in_sync"] and not r["unenforced"] and not r["phantom"]


def test_a_check_nobody_requires_is_unenforced() -> None:
    r = compare_required_checks(["gate", "ungated"], ["gate"])
    assert r["unenforced"] == ["ungated"]
    assert r["phantom"] == []
    assert not r["in_sync"]
    assert "gates nothing" in render_drift(r, "o/r")


def test_a_required_check_nothing_produces_is_phantom() -> None:
    r = compare_required_checks(["gate"], ["gate", "renamed-away"])
    assert r["phantom"] == ["renamed-away"]
    assert "never reported" in render_drift(r, "o/r")


def test_both_directions_are_reported_together() -> None:
    r = compare_required_checks(["a", "only-derived"], ["a", "only-configured"])
    assert r["unenforced"] == ["only-derived"]
    assert r["phantom"] == ["only-configured"]


def test_advisory_contexts_are_not_drift() -> None:
    """An operator's deliberate 'this one is informational' must not nag."""
    r = compare_required_checks(["a", "informational"], ["a"], advisory=["informational"])
    assert r["in_sync"]


def test_whitespace_and_blanks_do_not_create_phantom_drift() -> None:
    r = compare_required_checks([" a ", "", "b"], ["a", "b", "   "])
    assert r["in_sync"], r


def test_dedup_key_is_stable_and_divergence_specific() -> None:
    """The same drift must not re-file every run; a NEW one must."""
    a = compare_required_checks(["x", "y"], ["x"])
    b = compare_required_checks(["y", "x"], ["x"])
    assert dedup_key(a, "o/r") == dedup_key(b, "o/r")
    c = compare_required_checks(["x", "z"], ["x"])
    assert dedup_key(c, "o/r") != dedup_key(a, "o/r")


# ---------------------------------------------------------------------------
# Enumeration — the under-derivation failure mode
# ---------------------------------------------------------------------------


def test_enumeration_covers_every_workflow_not_just_adopts_five() -> None:
    """Regression: KNOWN_WORKFLOWS is adopt's scope, not this repo's."""
    names = all_workflow_check_names(_ROOT)
    assert "Anti-ratchet + allowlist diff" in names, (
        "bloat-check.yml is not one of adopt's scaffolded workflows, so deriving "
        "from KNOWN_WORKFLOWS misses it and reports the configured context as a "
        "phantom — the producer would cry wolf on a correctly-configured repo"
    )
    assert "PR Review" in names, (
        "pr-review-run.yml posts the `PR Review` status; it must be derived, or "
        "this repo's own required check reads as configured-but-nonexistent"
    )


def test_a_workflow_that_cannot_run_on_a_pr_is_not_derived(tmp_path: Path) -> None:
    """Over-derivation mutes the producer as surely as under-derivation.

    A `workflow_dispatch`-only workflow never reports on a pull request, so it
    cannot be "runs but gates nothing" — and requiring it would block every PR
    forever on a result that never arrives. The first draft counted it and
    reported this repo's manual-only `grade-empirical.yml` as drift.
    """
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "manual.yml").write_text(
        "name: M\non:\n  workflow_dispatch:\njobs:\n  j:\n    name: Manual only\n"
        "    runs-on: ubuntu-latest\n    steps:\n      - run: true\n",
        encoding="utf-8",
    )
    (wf / "pr.yml").write_text(
        "name: P\non:\n  pull_request:\njobs:\n  j:\n    name: On every PR\n"
        "    runs-on: ubuntu-latest\n    steps:\n      - run: true\n",
        encoding="utf-8",
    )
    assert all_workflow_check_names(tmp_path) == ["On every PR"]


def test_the_monorepos_manual_launch_gate_is_not_reported_as_drift() -> None:
    """The false positive, pinned against the real file."""
    assert "Empirical calibration (real OSS repos)" not in all_workflow_check_names(_ROOT)


def test_enumeration_survives_a_repo_with_no_workflows(tmp_path: Path) -> None:
    assert all_workflow_check_names(tmp_path) == []


def test_enumeration_skips_an_unparseable_workflow(tmp_path: Path) -> None:
    """One broken file must not take the whole comparison down."""
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "broken.yml").write_text("{{ not: [valid", encoding="utf-8")
    (wf / "ok.yml").write_text(
        "name: X\non:\n  pull_request:\njobs:\n  build:\n    name: Build\n"
        "    runs-on: ubuntu-latest\n    steps:\n      - run: true\n",
        encoding="utf-8",
    )
    assert all_workflow_check_names(tmp_path) == ["Build"]


@pytest.mark.parametrize("payload", [[], ["only-configured"]])
def test_empty_derived_never_reads_as_in_sync(payload: list[str]) -> None:
    """No derived names is 'we could not see the workflows', not 'all good'."""
    r = compare_required_checks([], payload)
    assert r["in_sync"] == (not payload)
