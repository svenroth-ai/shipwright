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

# @covers FR-01.17/AC06 — "when [the configured must-pass set] no longer
# matches the checks the project actually has, then that difference is
# raised as a tracked follow-up." The comparison below is the derivation
# half of that guarantee; test_check_required_checks_cli.py's
# test_one_divergence_files_one_card_across_repeated_invocations proves the
# other half (the difference is actually FILED, once, not merely computed).

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.required_checks_drift import (  # noqa: E402
    all_workflow_check_names,
    compare_required_checks,
    dedup_key,
    load_advisory_checks,
    render_drift,
    workflow_check_sets,
)

_ROOT = Path(__file__).resolve().parents[2]


def test_identical_sets_are_in_sync() -> None:
    r = compare_required_checks(["a", "b"], ["b", "a"])
    assert r["in_sync"] and not r["unenforced"] and not r["phantom"]


@pytest.mark.covers("FR-01.17/AC06")
def test_a_check_nobody_requires_is_unenforced() -> None:
    r = compare_required_checks(["gate", "ungated"], ["gate"])
    assert r["unenforced"] == ["ungated"]
    assert r["phantom"] == []
    assert not r["in_sync"]
    assert "gates nothing" in render_drift(r, "o/r")


@pytest.mark.covers("FR-01.17/AC06")
def test_a_required_check_nothing_produces_is_phantom() -> None:
    r = compare_required_checks(["gate"], ["gate", "renamed-away"])
    assert r["phantom"] == ["renamed-away"]
    assert "never reported" in render_drift(r, "o/r")


@pytest.mark.covers("FR-01.17/AC06")
def test_both_directions_are_reported_together() -> None:
    r = compare_required_checks(["a", "only-derived"], ["a", "only-configured"])
    assert r["unenforced"] == ["only-derived"]
    assert r["phantom"] == ["only-configured"]


def test_advisory_contexts_are_not_drift() -> None:
    """An operator's deliberate 'this one is informational' must not nag."""
    r = compare_required_checks(["a", "informational"], ["a"], advisory=["informational"])
    assert r["in_sync"]


def test_a_declared_advisory_check_is_not_unenforced_but_never_hides_a_phantom() -> None:
    """Advisory = "runs, reports, deliberately not required"."""
    r = compare_required_checks(["gate", "helper"], ["gate"], advisory=["helper"])
    assert r["in_sync"] and r["unenforced"] == []
    other = compare_required_checks(["gate", "x"], ["gate"], advisory=["helper"])
    assert other["unenforced"] == ["x"]
    # Required yet no longer produced is merge-blocking; a stale in-repo
    # declaration must not silence it.
    stale = compare_required_checks(["gate"], ["gate", "helper"], advisory=["helper"])
    assert stale["phantom"] == ["helper"]


def _write_cfg(root: Path, text: str) -> None:
    (root / "shipwright_run_config.json").write_text(text, encoding="utf-8")


def test_advisory_list_is_read_from_the_run_config(tmp_path: Path) -> None:
    _write_cfg(tmp_path, '{"status": "complete", "required_checks_advisory": '
                         '[" Prepare review request ", "", 7]}')
    assert load_advisory_checks(tmp_path) == ["Prepare review request"]


def test_advisory_list_survives_a_utf8_bom(tmp_path: Path) -> None:
    (tmp_path / "shipwright_run_config.json").write_text(
        '{"required_checks_advisory": ["helper"]}', encoding="utf-8-sig")
    assert load_advisory_checks(tmp_path) == ["helper"]


@pytest.mark.parametrize("text", [
    None, "not json", "[]", '{"status": "complete"}',
    '{"required_checks_advisory": "Prepare review request"}',
])
def test_missing_or_malformed_advisory_declaration_declares_nothing(
    tmp_path: Path, text: str | None
) -> None:
    """An unreadable declaration must never suppress a finding."""
    if text is not None:
        _write_cfg(tmp_path, text)
    assert load_advisory_checks(tmp_path) == []


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
    # Posted statuses stay every-PR candidates, unanalysed (documented limit).
    assert "PR Review" in workflow_check_sets(_ROOT, branch="main")[1]


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


def _write_ci(tmp_path: Path, on: str, jobs: str) -> None:
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text(
        f"name: CI\non:\n{on}\njobs:\n{jobs}", encoding="utf-8"
    )


@pytest.mark.covers("FR-01.17/AC06")
def test_configured_pr_conditional_job_is_not_a_phantom(tmp_path: Path) -> None:
    _write_ci(
        tmp_path, "  pull_request:",
        "  client:\n    name: Client (type + lint + test)\n"
        "    if: github.event_name != 'schedule'\n    runs-on: ubuntu-latest\n",
    )
    configured = ["Client (type + lint + test)"]
    possible, candidates = workflow_check_sets(tmp_path)
    assert possible == configured and candidates == configured
    result = compare_required_checks(possible, configured, unenforced_candidates=candidates)
    assert result["in_sync"]
    # Provably true on every PR, so a missing requirement is still unenforced.
    missing = compare_required_checks(possible, [], unenforced_candidates=candidates)
    assert missing["unenforced"] == configured


@pytest.mark.parametrize("condition, candidate", [
    ("${{ github.event_name == 'pull_request' }}", True),
    ("github.event_name != 'schedule'", True),
    ("true", True),
    ("github.event_name == 'push'", False),
    ("github.event_name != 'pull_request'", False),
    ("github.event_name != 'Pull_Request'", False),  # GitHub compares case-insensitively
    ("false", False),
    ("github.ref == 'refs/heads/main'", False),  # unknown: possible-only
    ("github.event_name == 'pull_request' && github.base_ref == 'main'", False),
])
def test_job_condition_is_possible_but_candidate_only_when_proved(
    tmp_path: Path, condition: str, candidate: bool
) -> None:
    _write_ci(
        tmp_path, "  pull_request:",
        f"  gate:\n    name: Gate\n    if: {condition}\n    runs-on: ubuntu-latest\n",
    )
    possible, candidates = workflow_check_sets(tmp_path)
    assert possible == ["Gate"]  # a skipped job still reports Success
    assert (candidates == ["Gate"]) is candidate


def test_yaml_boolean_false_if_is_conditional_not_unconditional(tmp_path: Path) -> None:
    _write_ci(
        tmp_path, "  pull_request:",
        "  disabled:\n    name: Disabled\n    if: false\n    runs-on: ubuntu-latest\n",
    )
    assert workflow_check_sets(tmp_path) == (["Disabled"], [])


@pytest.mark.parametrize("on, expected", [
    ("  [push, pull_request]", (["A"], ["A"])),
    ("  pull_request", (["A"], ["A"])),
    ("  push", ([], [])),
])
def test_list_and_string_pull_request_triggers_are_not_dormant(
    tmp_path: Path, on: str, expected: tuple
) -> None:
    _write_ci(tmp_path, on, "  a:\n    name: A\n    runs-on: x\n")
    assert workflow_check_sets(tmp_path) == expected


@pytest.mark.covers("FR-01.17/AC06")
@pytest.mark.parametrize("filters, branch, candidate", [
    ("branches: [main]", "main", True),
    ("branches: [main]", "develop", False),
    ("branches-ignore: [release]", "main", True),
    ("branches-ignore: [main]", "main", False),
    ("branches: ['release/**']", "release/v1", False),  # glob: not proved
    ("branches: [main]", None, False),
    ("paths: ['src/**']", "main", False),
    ("types: [opened]", "main", False),
    ("types: [opened, synchronize, reopened, labeled]", "main", True),
])
def test_pr_filters_make_a_check_possible_only_unless_proved(
    tmp_path: Path, filters: str, branch: str | None, candidate: bool
) -> None:
    _write_ci(
        tmp_path, "  pull_request:\n    " + filters,
        "  gate:\n    name: Gate\n    runs-on: ubuntu-latest\n",
    )
    possible, candidates = workflow_check_sets(tmp_path, branch=branch)
    assert possible == ["Gate"]  # never a phantom because of a filter we cannot prove
    assert (candidates == ["Gate"]) is candidate


def test_jobs_with_needs_remain_unenforced_candidates(tmp_path: Path) -> None:
    _write_ci(
        tmp_path, "  pull_request:",
        "  a:\n    name: A\n    runs-on: x\n  b:\n    name: B\n    needs: a\n    runs-on: x\n",
    )
    assert workflow_check_sets(tmp_path)[1] == ["A", "B"]


@pytest.mark.parametrize("payload", [[], ["only-configured"]])
def test_empty_derived_never_reads_as_in_sync(payload: list[str]) -> None:
    """No derived names is 'we could not see the workflows', not 'all good'."""
    r = compare_required_checks([], payload)
    assert r["in_sync"] == (not payload)
