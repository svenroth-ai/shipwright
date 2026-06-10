"""Tests for the history-calibrated complexity prior (complexity_history.py).

The prior replaces the bare "trivial" fall-through in classify_complexity
with the median final complexity of the last finalized iterate runs (F5c
entries). Round-trip against the REAL shared writer + CLI smoke live in
test_complexity_history_roundtrip.py.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _complexity_test_helpers import (  # noqa: E402
    FALLTHROUGH_MSG,
    KEYWORD_MSG,
    seeded_root,
    write_entry,
)
from classify_complexity import classify  # noqa: E402
from complexity_history import (  # noqa: E402
    HISTORY_MIN_ENTRIES,
    HISTORY_WINDOW,
    load_history_prior,
)


class TestLoadHistoryPrior:
    def test_none_when_project_root_is_none(self):
        assert load_history_prior(None) is None

    def test_none_when_dir_missing(self, tmp_path):
        assert load_history_prior(tmp_path) is None

    def test_none_below_min_entries(self, tmp_path):
        seeded_root(tmp_path, ["medium"] * (HISTORY_MIN_ENTRIES - 1))
        assert load_history_prior(tmp_path) is None

    def test_median_odd(self, tmp_path):
        seeded_root(tmp_path, ["small", "small", "medium"])
        assert load_history_prior(tmp_path)["prior"] == "small"

    def test_median_odd_upper(self, tmp_path):
        seeded_root(tmp_path, ["small", "medium", "medium"])
        assert load_history_prior(tmp_path)["prior"] == "medium"

    def test_median_even_takes_lower_middle(self, tmp_path):
        # Conservative choice, documented in the module: on even counts the
        # lower of the two middle values wins.
        seeded_root(tmp_path, ["small", "small", "medium", "medium"])
        assert load_history_prior(tmp_path)["prior"] == "small"

    def test_clamped_to_medium(self, tmp_path):
        # The prior alone must never route into the large escape hatch.
        seeded_root(tmp_path, ["large"] * 5)
        assert load_history_prior(tmp_path)["prior"] == "medium"

    def test_trivial_median_not_lifted(self, tmp_path):
        # No lower clamp: a genuinely trivial-heavy history stays trivial.
        seeded_root(tmp_path, ["trivial"] * 5)
        assert load_history_prior(tmp_path)["prior"] == "trivial"

    def test_window_takes_most_recent(self, tmp_path):
        # 5 oldest are trivial, HISTORY_WINDOW newest are medium → medium.
        seeded_root(tmp_path, ["trivial"] * 5 + ["medium"] * HISTORY_WINDOW)
        result = load_history_prior(tmp_path)
        assert result["prior"] == "medium"
        assert result["n"] == HISTORY_WINDOW

    def test_filter_valid_first_then_window(self, tmp_path):
        # Invalid entries interleaved at the cutoff must not displace valid
        # ones: sort all, filter to valid, THEN take the last WINDOW valid.
        root = seeded_root(tmp_path, ["small"] * HISTORY_WINDOW)
        # Newest-dated entries are invalid → must be skipped, not counted.
        write_entry(root, "iterate-2026-02-01-bad-cx",
                    "2026-02-01T00:00:00Z", "gigantic")
        d = root / ".shipwright" / "agent_docs" / "iterates"
        (d / "broken.json").write_text("{not json", encoding="utf-8")
        (d / "not-dict.json").write_text('["a list"]', encoding="utf-8")
        result = load_history_prior(root)
        assert result["prior"] == "small"
        assert result["n"] == HISTORY_WINDOW

    def test_entry_missing_date_is_skipped(self, tmp_path):
        seeded_root(tmp_path, ["medium"] * 3)
        d = tmp_path / ".shipwright" / "agent_docs" / "iterates"
        bad = {"run_id": "iterate-2026-03-01-no-date", "complexity": "large"}
        (d / "iterate-2026-03-01-no-date.json").write_text(
            json.dumps(bad), encoding="utf-8")
        result = load_history_prior(tmp_path)
        assert result["prior"] == "medium"
        assert result["n"] == 3

    def test_unparseable_date_is_skipped(self, tmp_path):
        seeded_root(tmp_path, ["medium"] * 3)
        write_entry(tmp_path, "iterate-2026-03-02-bad-date",
                    "not-a-date", "large")
        result = load_history_prior(tmp_path)
        assert result["prior"] == "medium"
        assert result["n"] == 3

    def test_naive_date_assumed_utc(self, tmp_path):
        # Mirrors shared iterate_entry sort semantics: naive → UTC.
        seeded_root(tmp_path, ["small"] * 2)
        write_entry(tmp_path, "iterate-2026-01-30-naive",
                    "2026-01-30T12:00:00", "small")
        result = load_history_prior(tmp_path)
        assert result["prior"] == "small"
        assert result["n"] == 3

    def test_quarantine_subdir_ignored(self, tmp_path):
        # _quarantine = shared iterate_entry.QUARANTINE_SUBDIR
        seeded_root(tmp_path, ["small"] * 3)
        q = tmp_path / ".shipwright" / "agent_docs" / "iterates" / "_quarantine"
        q.mkdir(parents=True)
        (q / "iterate-2026-04-01-poison.json").write_text(
            json.dumps({"run_id": "iterate-2026-04-01-poison",
                        "date": "2026-04-01T00:00:00Z",
                        "complexity": "large"}),
            encoding="utf-8",
        )
        result = load_history_prior(tmp_path)
        assert result["prior"] == "small"
        assert result["n"] == 3

    def test_non_string_date_is_skipped_not_crash(self, tmp_path):
        # Review HIGH: "date": null in valid JSON must be skipped, never
        # raise AttributeError out of classify().
        seeded_root(tmp_path, ["medium"] * 3)
        d = tmp_path / ".shipwright" / "agent_docs" / "iterates"
        for name, date_val in (("null-date", None), ("num-date", 12345),
                               ("list-date", ["2026"])):
            (d / f"iterate-2026-03-03-{name}.json").write_text(
                json.dumps({"run_id": f"iterate-2026-03-03-{name}",
                            "date": date_val, "complexity": "large"}),
                encoding="utf-8",
            )
        result = load_history_prior(tmp_path)
        assert result["prior"] == "medium"
        assert result["n"] == 3

    def test_run_id_tiebreak_decides_window_cutoff(self, tmp_path):
        # Review MEDIUM: 21 entries share one timestamp; the window drops
        # exactly the lexically smallest run_id. Its file is named zzz.json
        # so a reader relying on glob order instead of the run_id tiebreak
        # would drop a different entry and flip the median.
        d = tmp_path / ".shipwright" / "agent_docs" / "iterates"
        d.mkdir(parents=True)
        same_date = "2026-07-01T12:00:00Z"

        def entry(run_id, cx):
            return json.dumps({"run_id": run_id, "date": same_date,
                               "complexity": cx, "type": "change",
                               "branch": "b", "tests_passed": True})

        # run-a00 (medium) must be the one dropped → 10 small + 10 medium
        # remain → lower-middle median = small.
        (d / "zzz.json").write_text(
            entry("iterate-2026-07-01-a00", "medium"), encoding="utf-8")
        for i in range(1, 21):
            cx = "small" if i <= 10 else "medium"
            (d / f"a{i:02d}.json").write_text(
                entry(f"iterate-2026-07-01-b{i:02d}", cx), encoding="utf-8")
        result = load_history_prior(tmp_path)
        assert result["n"] == HISTORY_WINDOW
        assert result["prior"] == "small"

    def test_oversized_file_skipped(self, tmp_path):
        seeded_root(tmp_path, ["small"] * 3)
        d = tmp_path / ".shipwright" / "agent_docs" / "iterates"
        blob = json.dumps({
            "run_id": "iterate-2026-04-02-huge",
            "date": "2026-04-02T00:00:00Z",
            "complexity": "large",
            "padding": "x" * 400_000,
        })
        (d / "iterate-2026-04-02-huge.json").write_text(blob, encoding="utf-8")
        result = load_history_prior(tmp_path)
        assert result["prior"] == "small"
        assert result["n"] == 3


class TestClassifyPrecedence:
    def test_fallthrough_uses_history(self, tmp_path):
        seeded_root(tmp_path, ["medium"] * 5)
        result = classify(FALLTHROUGH_MSG, project_root=tmp_path)
        assert result["estimate"] == "medium"
        assert result["signals"]["prior_source"] == "history"
        assert result["signals"]["history_prior"] == "medium"
        assert result["signals"]["history_n"] == 5

    def test_keyword_beats_history(self, tmp_path):
        seeded_root(tmp_path, ["large"] * 5)  # clamps to medium anyway
        result = classify(KEYWORD_MSG, project_root=tmp_path)
        assert result["estimate"] == "medium"
        assert result["signals"]["prior_source"] == "keyword"
        assert result["signals"]["history_prior"] is None

    def test_fallthrough_without_history_is_default(self, tmp_path):
        result = classify(FALLTHROUGH_MSG, project_root=tmp_path)
        assert result["estimate"] == "trivial"
        assert result["signals"]["prior_source"] == "default"

    def test_no_project_root_preserves_old_behaviour(self):
        result = classify(FALLTHROUGH_MSG)
        assert result["estimate"] == "trivial"
        assert result["signals"]["prior_source"] == "default"
        # Old signal keys must survive for existing consumers.
        for key in ("scope_keyword_estimate", "risk_floor",
                    "cross_split", "has_sync_config"):
            assert key in result["signals"]

    def test_risk_floor_does_not_cap_history_prior(self, tmp_path):
        seeded_root(tmp_path, ["medium"] * 5)
        # 'login' fires touches_auth (floor small); prior medium must win.
        result = classify("fix the broken login redirect handling",
                          project_root=tmp_path)
        assert result["estimate"] == "medium"
        assert "touches_auth" in result["risk_flags"]

    def test_history_prior_lifts_to_risk_floor_at_least(self, tmp_path):
        seeded_root(tmp_path, ["trivial"] * 5)
        result = classify("fix the broken login redirect handling",
                          project_root=tmp_path)
        # prior trivial, floor small → small (floors still enforce minima).
        assert result["estimate"] == "small"
