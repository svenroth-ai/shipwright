"""Pins ``lib.backfill_ac_provenance`` — the footnote-to-AC join logic for the
P3.4 tagging-backfill mechanical leg (campaign req3-04c-ac-identity-wave2).

Pure logic only (no git, no filesystem) — the git correlation half lives in
``tools/backfill_ac_provenance.py`` and is exercised by
``tools/tests/test_backfill_ac_provenance_cli.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.backfill_ac_provenance import footnote_slugs, unique_provenance_acs  # noqa: E402


def test_no_footnote_yields_no_slugs():
    assert footnote_slugs("Given a thing, when it happens, then it is recorded.") == []


def test_a_single_footnote_slug_is_extracted():
    text = "Given a thing, when it happens, then it is recorded. (iterate-2026-07-21-review-record)"
    assert footnote_slugs(text) == ["iterate-2026-07-21-review-record"]


def test_multiple_comma_separated_slugs_are_extracted_in_order():
    text = (
        "Given a thing, when it happens, then it is recorded. "
        "(iterate-2026-07-27-no-silent-revert, iterate-2026-07-28-silent-revert-false-positives)"
    )
    assert footnote_slugs(text) == [
        "iterate-2026-07-27-no-silent-revert",
        "iterate-2026-07-28-silent-revert-false-positives",
    ]


def test_an_adr_footnote_is_also_recognised():
    assert footnote_slugs("Given ..., then ... (adr-099-something)") == ["adr-099-something"]


def test_a_footnote_that_is_not_at_the_very_end_is_not_matched():
    # A parenthetical mid-sentence is not a provenance footnote — only a
    # TRAILING one is (the shipped shape always puts it last).
    text = "Given a thing (iterate-2026-07-21-review-record) that happens, then it is recorded."
    assert footnote_slugs(text) == []


def test_unique_provenance_acs_keeps_a_slug_naming_exactly_one_ac():
    read_all = {
        "FR-01.11": [
            ("AC11", "... (iterate-2026-07-21-review-record)"),
            ("AC12", "... (iterate-2026-08-08-plan-reviewer-configurable)"),
        ],
    }
    assert unique_provenance_acs(read_all) == {
        "FR-01.11": {
            "iterate-2026-07-21-review-record": "AC11",
            "iterate-2026-08-08-plan-reviewer-configurable": "AC12",
        },
    }


def test_unique_provenance_acs_drops_a_slug_shared_by_two_criteria_in_the_same_fr():
    # The real shape: one iterate landed two criteria at once. Real provenance,
    # but not resolvable to a SINGLE ac_id without reading test content — never
    # guessed.
    read_all = {
        "FR-01.11": [
            ("AC11", "... (iterate-2026-07-21-review-record)"),
            ("AC13", "... (iterate-2026-07-21-review-record)"),
        ],
    }
    assert unique_provenance_acs(read_all) == {}


def test_unique_provenance_acs_drops_a_slug_unique_per_fr_but_reused_across_frs():
    # P3.4 post-hoc fix: the SAME slug footnotes exactly one AC in EACH of two
    # different FRs is NOT two independent unique facts — it is one commit
    # that delivered (at least) two distinct criteria, and neither occurrence
    # is safe to trust without reading which test covers which. Measured on
    # this repo's own spec.md: a real slug was unique within one FR (1
    # bullet) while repeating 3x within another FR (correctly dropped there)
    # — the "unique" FR's occurrence was still wrong, because the underlying
    # commit's scope spans both FRs, not just the one that happened to see it
    # once. Document-wide uniqueness is the only scope a git commit actually
    # respects.
    read_all = {
        "FR-01.01": [("AC01", "... (iterate-2026-01-01-shared-slug)")],
        "FR-01.02": [("AC03", "... (iterate-2026-01-01-shared-slug)")],
    }
    assert unique_provenance_acs(read_all) == {}


def test_unique_provenance_acs_keeps_a_slug_unique_within_a_single_fr_and_absent_elsewhere():
    # The document-wide check does not collapse to "always drop cross-FR
    # slugs" — a slug that names exactly one (fr_id, ac_id) pair IN THE WHOLE
    # DOCUMENT is still kept, whether or not other FRs exist alongside it.
    read_all = {
        "FR-01.01": [("AC01", "... (iterate-2026-01-01-only-here)")],
        "FR-01.02": [("AC03", "... (iterate-2026-02-02-unrelated-slug)")],
    }
    assert unique_provenance_acs(read_all) == {
        "FR-01.01": {"iterate-2026-01-01-only-here": "AC01"},
        "FR-01.02": {"iterate-2026-02-02-unrelated-slug": "AC03"},
    }


def test_unique_provenance_acs_ignores_a_bullet_with_no_minted_ac_id():
    # ac_id is None for a not-yet-minted criterion (ac_identity.read's own
    # contract) — never a source of a false signal here.
    read_all = {"FR-01.01": [(None, "... (iterate-2026-01-01-some-slug)")]}
    assert unique_provenance_acs(read_all) == {}


def test_unique_provenance_acs_skips_a_fr_with_no_footnotes_at_all():
    read_all = {"FR-01.01": [("AC01", "Given ..., then it is recorded.")]}
    assert unique_provenance_acs(read_all) == {}
