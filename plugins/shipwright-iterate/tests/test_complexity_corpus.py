"""Golden corpus test for the broadened scope vocabulary (AC-3/AC-4).

The fixture rows are REAL classify_complexity --message args harvested from
session transcripts (2026-05-10..2026-06-10), hand-joined to the runs' final
complexity. Two passes:

1. vocabulary-only — classify(message) without history must return
   expected_vocab_estimate exactly (golden).
2. with a small-median history — fall-through rows lift to small; the
   under-classification count vs final_complexity must beat the recorded
   old estimates with hard numbers.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _complexity_test_helpers import seeded_root  # noqa: E402
from classify_complexity import COMPLEXITY_ORDER, classify  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "complexity_corpus.json"
LEVELS = set(COMPLEXITY_ORDER)

# Hard ceilings measured at fixture-creation time. old: 18 under / 1 over of
# 26 verified rows. A vocabulary or prior change that worsens these numbers
# must fail here, not be discovered in the field.
OLD_UNDER = 18
OLD_OVER = 1
MAX_NEW_UNDER = 11
MAX_NEW_OVER = 0


def load_rows():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data["rows"]


def idx(level: str) -> int:
    return COMPLEXITY_ORDER.index(level)


@pytest.fixture(scope="module")
def rows():
    return load_rows()


@pytest.fixture()
def small_history_root(tmp_path):
    """Synthetic history whose median mirrors this repo's reality (small)."""
    return seeded_root(tmp_path, ["small"] * 5)


class TestFixtureSchema:
    def test_rows_present_and_typed(self, rows):
        assert len(rows) >= 25
        for row in rows:
            assert row["message"].strip()
            assert row["old_estimate"] in LEVELS
            assert row["expected_vocab_estimate"] in LEVELS
            assert row["final_complexity"] is None or (
                row["final_complexity"] in LEVELS
            )
            assert row["note"].strip(), "every row carries join provenance"

    def test_enough_verified_rows_for_the_metric(self, rows):
        verified = [r for r in rows if r["final_complexity"]]
        assert len(verified) >= 20

    def test_old_baseline_matches_recorded_constants(self, rows):
        # The OLD_UNDER/OLD_OVER constants document the harvested baseline;
        # keep them honest against the fixture content.
        verified = [r for r in rows if r["final_complexity"]]
        under = sum(1 for r in verified
                    if idx(r["old_estimate"]) < idx(r["final_complexity"]))
        over = sum(1 for r in verified
                   if idx(r["old_estimate"]) > idx(r["final_complexity"]))
        assert under == OLD_UNDER
        assert over == OLD_OVER


class TestVocabularyGolden:
    def test_each_row_vocab_only(self, rows):
        failures = []
        for row in rows:
            got = classify(row["message"])["estimate"]
            if got != row["expected_vocab_estimate"]:
                failures.append(
                    f"{row['date']} expected {row['expected_vocab_estimate']}"
                    f" got {got}: {row['message'][:80]}…"
                )
        assert not failures, "\n".join(failures)


class TestUnderClassificationMetric:
    def test_with_history_prior_beats_old(self, rows, small_history_root):
        verified = [r for r in rows if r["final_complexity"]]
        new_under = new_over = 0
        for row in verified:
            got = classify(row["message"],
                           project_root=small_history_root)["estimate"]
            if idx(got) < idx(row["final_complexity"]):
                new_under += 1
            elif idx(got) > idx(row["final_complexity"]):
                new_over += 1
        assert new_under < OLD_UNDER, (
            f"prior+vocabulary must under-classify less than the old "
            f"classifier: {new_under} vs {OLD_UNDER}"
        )
        assert new_under <= MAX_NEW_UNDER
        assert new_over <= MAX_NEW_OVER


class TestFalsePositiveGuards:
    """Anchored matching must not over-fire on generic engineering prose."""

    def test_renew_commander_is_not_new_command(self):
        # substring 'new command' hides inside 'renew commander' — the
        # alnum-boundary matcher must reject it.
        assert classify("renew commander license handling")["estimate"] == (
            "trivial"
        )

    def test_typo_in_parser_docs_stays_small(self):
        # bare 'parser' is deliberately NOT a keyword (review finding);
        # 'typo' fires small.
        assert classify("fix typo in the parser docs")["estimate"] == "small"

    def test_dump_utility_stays_trivial(self):
        assert classify("improve dump utility for stack traces")[
            "estimate"] == "trivial"

    def test_comment_update_is_small(self):
        assert classify("update the stale comment in the size checker")[
            "estimate"] == "small"

    def test_consolidated_past_tense_does_not_fire(self):
        # 'consolidate' must not fire inside 'consolidated' (suffix rule
        # allows only plural-ish s/es, not arbitrary inflection).
        assert classify("show consolidated error output")["estimate"] == (
            "trivial"
        )

    def test_research_does_not_fire_search(self):
        # old substring matching fired 'search' inside 'research(ing)'.
        assert classify("researching the flaky behavior")["estimate"] == (
            "trivial"
        )

    def test_filename_with_underscores_still_matches(self):
        # update_build_dashboard.py — '_' must count as a separator, not a
        # word character, or real filename-embedded keywords stop firing.
        assert classify("fix update_build_dashboard.py output")[
            "estimate"] == "medium"

    def test_plural_keyword_still_fires(self):
        assert classify("adjust the CI workflows for adopt")["estimate"] == (
            "medium"
        )


class TestIntendedNewKeywords:
    def test_new_command_fires_medium(self):
        assert classify("new command for listing runs in the CLI")[
            "estimate"] == "medium"

    def test_add_support_for_fires_medium(self):
        assert classify("add support for csv export")["estimate"] == "medium"

    def test_systemic_fires_medium(self):
        assert classify("systemic fix for the propagation gap")[
            "estimate"] == "medium"

    def test_producer_consumer_fires_medium(self):
        assert classify("align the producer-consumer pair for events")[
            "estimate"] == "medium"

    def test_breaking_change_fires_large(self):
        assert classify("this is a breaking change to the entry format")[
            "estimate"] == "large"

    def test_new_module_is_medium_not_large(self):
        # moved large → medium: the corpus shows 'new module' prompts
        # finalize medium (over-classification fixed).
        assert classify("split helpers into a new module")["estimate"] == (
            "medium"
        )

    def test_typo_fires_small(self):
        assert classify("fix typo in banner")["estimate"] == "small"

    def test_es_plural_suffix_fires(self):
        # pins the `es` branch of the (?:e?s)? plural matcher
        assert classify("speed up repeated searches in the list view")[
            "estimate"] == "medium"

    def test_bump_fires_small(self):
        assert classify("bump the ruff version in ci")["estimate"] == "small"
