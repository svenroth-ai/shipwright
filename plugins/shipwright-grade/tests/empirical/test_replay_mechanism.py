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

_MANIFEST = Path(__file__).resolve().parent / "repos.yaml"
_VALID_BANDS = {"A", "B", "C", "D", "F"}


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
        assert 2 <= len(repos) <= 5
        for entry in repos:
            for field in ("name", "url", "pinned_sha", "expected_band", "rationale", "tags"):
                assert field in entry, f"{entry.get('name')} missing {field}"
            assert entry["expected_band"] in _VALID_BANDS

    def test_expected_bands_encode_descending_ordering(self):
        data = yaml.safe_load(_MANIFEST.read_text(encoding="utf-8"))
        order = {b: i for i, b in enumerate(["A", "B", "C", "D", "F"])}
        bands = [order[e["expected_band"]] for e in data["repos"]]
        assert bands == sorted(bands), "manifest should list exemplary → poor"

    def test_fixtures_dir_exists(self):
        assert (Path(__file__).resolve().parent / "fixtures").is_dir()
