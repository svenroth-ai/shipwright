"""Unit tests for event_seeder."""

import json
from pathlib import Path

from lib.event_seeder import seed_adopted_event, seed_backfill_events


def test_seed_adopted_event(tmp_path: Path) -> None:
    events = tmp_path / "shipwright_events.jsonl"
    seed_adopted_event(
        events,
        profile="supabase-nextjs", scope="full_app",
        features_inferred=7, nested_excluded=["webui"],
        plugin_version="0.1.0", commit_sha="abc123",
    )
    lines = events.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    ev = json.loads(lines[0])
    assert ev["type"] == "adopted"
    assert ev["profile"] == "supabase-nextjs"
    assert ev["features_inferred"] == 7
    assert ev["commit_at_adoption"] == "abc123"


def test_seed_backfill_events(tmp_path: Path) -> None:
    events = tmp_path / "shipwright_events.jsonl"
    commits = [
        {"sha": "1111", "subject": "refactor(auth)", "date": "2026-01-01T00:00:00Z", "author": "A", "files_changed": 8},
        {"sha": "2222", "subject": "refactor(db)", "date": "2026-02-01T00:00:00Z", "author": "B", "files_changed": 12},
    ]
    n = seed_backfill_events(events, commits)
    assert n == 2
    lines = events.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["type"] == "work_completed"
    assert first["source"] == "adopted-backfill"
    assert first["confidence"] == "low"


def test_seed_backfill_respects_max(tmp_path: Path) -> None:
    events = tmp_path / "shipwright_events.jsonl"
    commits = [{"sha": str(i), "subject": "refactor", "files_changed": 7} for i in range(20)]
    n = seed_backfill_events(events, commits, max_count=3)
    assert n == 3
