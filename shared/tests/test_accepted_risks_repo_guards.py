"""Live guards — the accepted-risk gate running against THIS repo.

These are what actually fails the build. The register and the drift reconciler
are libraries; what makes them binding is that this file runs on the path CI
already requires (``shared/tests``). The first draft of the register shipped the
reconciler with nothing invoking it — which the external review correctly called
out as rebuilding the very defect the register exists to fix: an expiry nobody
enforces is a comment, not a control.

Split out of ``test_accepted_risks_register.py`` when that file crossed the
300-line cap. The seam is the one its docstring already drew: live guards here,
synthetic negative controls (proving each guard fires) there.

Every assertion here reads real repo state, so a failure means this repo has
drifted — not that a fixture is stale.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import accepted_risk_scan as scan  # noqa: E402
import accepted_risks as ar  # noqa: E402
from tools import accepted_risks_cli as cli  # noqa: E402


def test_register_and_suppressions_agree():
    """Every suppression is recorded, and every record is a real suppression."""
    result = cli.reconcile(REPO_ROOT)
    problems = cli._format_check(result)
    assert result["ok"], (
        "Accepted-risk register drift in this repo:\n\n"
        + "\n".join(problems)
        + "\n\nReconcile with: uv run shared/scripts/tools/"
        "accepted_risks_cli.py check --project-root ."
    )


def test_no_acceptance_is_past_its_review_date():
    entries = ar.load_register(REPO_ROOT)
    overdue = ar.expired(entries, ar.today_utc())
    assert not overdue, (
        "Accepted risks are past their re-review date — fix the finding or renew "
        "`expires` with a fresh rationale:\n  - "
        + "\n  - ".join(
            f"{e.id} (due {e.expires}, ref {e.rationale_ref})" for e in overdue)
    )


def test_repo_register_is_loadable_and_non_empty():
    # If the register ever silently became empty, both guards above would pass
    # vacuously while every suppression went unrecorded.
    entries = ar.load_register(REPO_ROOT)
    assert entries, "this repo has accepted risks; the register must record them"
    assert all(e.rationale_ref for e in entries)


def test_every_seeded_rationale_ref_is_a_recorded_decision():
    for entry in ar.load_register(REPO_ROOT):
        assert ar.DECISION_REF_RE.search(entry.rationale_ref), entry.id


def test_ignore_entries_outlive_their_register_entry():
    """A paired ignore entry must not lapse before its acceptance falls due.

    The two fields lapse on different days by their owners' definitions — a
    register entry is active ON its ``expires``, a Trivy entry is already
    inactive ON its ``expired_at``. Setting both to the same day leaves exactly
    one day on which the scanner has stopped suppressing while the acceptance is
    still current: ``check`` reports STALE and CI goes red with nothing due.

    This repo shipped that misalignment (both dates 2026-12-22, both 2027-01-28)
    and would have gone red on exactly those two days. Pinned rather than merely
    fixed, because the failure is invisible until the date arrives — which is
    also why it survived a full green suite and two review stages.
    """
    # `date.min` predates every date a repo would write, so nothing is filtered:
    # this is every id in the ignore file, lapsed or not.
    all_ids = scan.read_trivyignore_ids(REPO_ROOT, now=date.min)
    entries = [
        e for e in ar.load_register(REPO_ROOT)
        if e.target == ar.TARGET_TRIVY_IGNORE and e.rule in all_ids
    ]
    assert entries, "expected this repo to pair register entries with ignore ids"

    for entry in entries:
        # The ignore entry must still be in effect on the acceptance's own last
        # active day, i.e. expired_at > expires.
        still_live = scan.read_trivyignore_ids(REPO_ROOT, now=entry.expires)
        assert entry.rule in still_live, (
            f"{entry.id}: the ignore entry for {entry.rule} lapses on or before "
            f"the register's own due date ({entry.expires}), so the gate would "
            "report STALE while the acceptance is still current. Set the ignore "
            "file's expired_at to at least one day AFTER expires."
        )
