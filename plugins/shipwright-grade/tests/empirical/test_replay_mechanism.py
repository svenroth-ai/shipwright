"""Hermetic tests for the empirical harness: the record/replay cache mechanism
and manifest well-formedness. These run in the DEFAULT suite (no network) — they
prove the anti-rot mechanism (Gemini #1) without touching GitHub. The real-repo
grading assertions live in ``test_empirical.py`` (``-m empirical``, G5 gate).
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

import replay  # noqa: E402
from calibration import BAND_ORDER, parse_band_set  # noqa: E402

_MANIFEST = Path(__file__).resolve().parent / "repos.yaml"
_VALID_BANDS = set(BAND_ORDER)


class TestReplayCache:
    def test_record_then_replay_round_trips(self, tmp_path: Path):
        key = "pallets/flask@abc123"
        payload = {"grade": "A", "score": 92.0}
        replay.record(key, payload, cache_dir=tmp_path)
        assert replay.replay(key, cache_dir=tmp_path) == payload

    def test_load_or_record_replays_without_refetching(self, tmp_path: Path):
        key = "x@y"
        replay.record(key, {"cached": True}, cache_dir=tmp_path)
        calls = []

        def _fetch():
            calls.append(1)
            return {"cached": False}

        got = replay.load_or_record(key, _fetch, allow_network=True, cache_dir=tmp_path)
        assert got == {"cached": True}
        assert calls == []  # replayed from cache, never fetched

    def test_load_or_record_offline_miss_returns_none(self, tmp_path: Path):
        got = replay.load_or_record(
            "missing", lambda: {}, allow_network=False, cache_dir=tmp_path)
        assert got is None

    def test_is_pinned_sha(self):
        assert replay.is_pinned_sha("a" * 40) is True
        assert replay.is_pinned_sha("PENDING-G5") is False
        assert replay.is_pinned_sha("abc") is False


class TestManifest:
    def test_manifest_parses_with_required_fields(self):
        data = yaml.safe_load(_MANIFEST.read_text(encoding="utf-8"))
        repos = data["repos"]
        assert 4 <= len(repos) <= 20  # calibration spread + edge cases
        for entry in repos:
            for field in ("name", "url", "pinned_sha", "expected_band", "rationale", "tags"):
                assert field in entry, f"{entry.get('name')} missing {field}"
            # A calibration entry names a band (or range like "A/B"); an edge
            # entry carries `expected_band: null` (robustness only, no band).
            bands = parse_band_set(entry["expected_band"])
            if entry["expected_band"]:
                assert bands and bands <= _VALID_BANDS, entry["name"]
            else:
                assert bands == frozenset()

    def test_calibration_entries_span_the_range(self):
        # G6 calibration: cold-repo signals order WELL-RUN > DEPRECATED, so the
        # required spread is exemplary (well-run) + poor (deprecated); the middle
        # `average` tier stays in the vocabulary but is optional (the fixes make the
        # A-vs-B/C split a per-repo band, not a separate tier). The ordering gate
        # (assert_ordering) still needs both ends present to bite.
        data = yaml.safe_load(_MANIFEST.read_text(encoding="utf-8"))
        tiers = {t for e in data["repos"] for t in (e.get("tags") or [])
                 if t in ("exemplary", "average", "poor")}
        assert {"exemplary", "poor"} <= tiers, "need both ends of the calibration spread"

    def test_calibration_bands_listed_best_to_worst(self):
        """Calibration entries are ordered exemplary → poor by their best band."""
        data = yaml.safe_load(_MANIFEST.read_text(encoding="utf-8"))
        ranks = [min(BAND_ORDER[b] for b in parse_band_set(e["expected_band"]))
                 for e in data["repos"] if e.get("expected_band")]
        assert ranks == sorted(ranks), "list calibration repos exemplary → poor"

    def test_pinned_shas_are_real(self):
        """Every entry pins a real 40-hex SHA (no leftover G5 placeholder)."""
        data = yaml.safe_load(_MANIFEST.read_text(encoding="utf-8"))
        for entry in data["repos"]:
            assert replay.is_pinned_sha(str(entry["pinned_sha"])), entry["name"]

    def test_fixtures_dir_exists(self):
        assert (Path(__file__).resolve().parent / "fixtures").is_dir()
