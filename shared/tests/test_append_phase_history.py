"""Tests for shared/scripts/tools/append_phase_history.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.append_phase_history import (
    RETENTION_PER_PHASE,
    RUN_CONFIG_NAME,
    append_history,
)


def write_run_config(root: Path, data: dict) -> Path:
    path = root / RUN_CONFIG_NAME
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def read_run_config(root: Path) -> dict:
    return json.loads((root / RUN_CONFIG_NAME).read_text(encoding="utf-8"))


def test_append_history_creates_bucket_when_missing(tmp_path):
    write_run_config(tmp_path, {"scope": "full_app"})
    append_history(tmp_path, "project", {"run_id": "r1", "date": "2026-04-14", "splits": 3})
    data = read_run_config(tmp_path)
    assert "phase_history" in data
    assert len(data["phase_history"]["project"]) == 1
    assert data["phase_history"]["project"][0]["splits"] == 3


def test_append_history_appends_to_existing_bucket(tmp_path):
    write_run_config(tmp_path, {
        "phase_history": {"build": [{"run_id": "old", "date": "2026-04-10"}]}
    })
    append_history(tmp_path, "build", {"run_id": "new", "date": "2026-04-14", "split": "02"})
    data = read_run_config(tmp_path)
    bucket = data["phase_history"]["build"]
    assert len(bucket) == 2
    assert bucket[0]["run_id"] == "old"
    assert bucket[1]["run_id"] == "new"


def test_append_history_preserves_unknown_top_level_fields(tmp_path):
    write_run_config(tmp_path, {
        "scope": "full_app",
        "profile": "supabase-nextjs",
        "iterate_history": [{"run_id": "it-1"}],
        "some_future_field": {"foo": "bar"},
    })
    append_history(tmp_path, "project", {"run_id": "p1", "date": "2026-04-14"})
    data = read_run_config(tmp_path)
    # Pre-existing fields must survive verbatim
    assert data["scope"] == "full_app"
    assert data["profile"] == "supabase-nextjs"
    assert data["iterate_history"] == [{"run_id": "it-1"}]
    assert data["some_future_field"] == {"foo": "bar"}
    # New field added
    assert data["phase_history"]["project"][0]["run_id"] == "p1"


def test_append_history_retention_drops_oldest(tmp_path):
    existing_bucket = [
        {"run_id": f"r{i}", "date": "2026-04-14"}
        for i in range(RETENTION_PER_PHASE)
    ]
    write_run_config(tmp_path, {"phase_history": {"design": existing_bucket}})
    result = append_history(
        tmp_path, "design",
        {"run_id": "newest", "date": "2026-04-14"},
    )
    data = read_run_config(tmp_path)
    bucket = data["phase_history"]["design"]
    assert len(bucket) == RETENTION_PER_PHASE
    # Oldest dropped, newest at tail
    assert bucket[0]["run_id"] == "r1"
    assert bucket[-1]["run_id"] == "newest"
    assert result["dropped"] == 1


def test_append_history_retention_zero_keeps_all(tmp_path):
    write_run_config(tmp_path, {})
    for i in range(10):
        append_history(
            tmp_path, "build",
            {"run_id": f"r{i}", "date": "2026-04-14"},
            retention=0,
        )
    data = read_run_config(tmp_path)
    assert len(data["phase_history"]["build"]) == 10


def test_append_history_raises_when_run_config_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        append_history(tmp_path, "build", {"run_id": "r1", "date": "2026-04-14"})


def test_append_history_parallel_callers_dont_collide(tmp_path):
    """Two sequential append calls — simulates lock-serialised parallel runs.

    This test doesn't spawn real threads (tmp_path is per-test, and
    fcntl+msvcrt are both blocking anyway), but it does exercise the
    read-modify-write invariant: each call must see the other's writes
    if they run under the same lock.
    """
    write_run_config(tmp_path, {})
    append_history(tmp_path, "test", {"run_id": "a", "date": "2026-04-14"})
    append_history(tmp_path, "test", {"run_id": "b", "date": "2026-04-14"})
    bucket = read_run_config(tmp_path)["phase_history"]["test"]
    assert [e["run_id"] for e in bucket] == ["a", "b"]


def test_append_history_malformed_run_config_raises(tmp_path):
    (tmp_path / RUN_CONFIG_NAME).write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError):
        append_history(tmp_path, "build", {"run_id": "r1", "date": "2026-04-14"})
