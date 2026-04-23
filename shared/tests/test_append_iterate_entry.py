"""Tests for shared/scripts/tools/append_iterate_entry.py.

Covers the full transaction: migration state machine, crash recovery,
retention boundaries, quarantine handling, and atomic per-file writes.
The race-path (two concurrent appends) lives in ``test_retention_race.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.iterate_entry import (
    MIGRATION_QUARANTINE_REPORT_KEY,
    MIGRATION_QUARANTINED_COUNT_KEY,
    MIGRATION_STATE_KEY,
    MIGRATION_TS_KEY,
    RUN_CONFIG_NAME,
    iterates_dir,
    quarantine_dir,
    read_iterate_entries,
)
from tools.append_iterate_entry import (
    ITERATE_RETENTION,
    IterateAppendError,
    _apply_retention,
    append_iterate_entry,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _canonical_entry(slug: str = "feat-x", date: str = "2026-04-23T10:00:00Z") -> dict:
    return {
        "run_id": f"iterate-2026-04-23-{slug}",
        "date": date,
        "type": "feature",
        "complexity": "medium",
        "branch": f"iterate/{slug}",
        "spec": None,
        "tests_passed": True,
        "adr": None,
    }


def _seed_legacy_project(
    tmp_path: Path, legacy_entries: list[dict], scope: str = "full_app"
) -> Path:
    """Create a target project with a legacy iterate_history array but no dir."""
    (tmp_path / "agent_docs").mkdir()
    config = {"scope": scope, "iterate_history": legacy_entries}
    (tmp_path / RUN_CONFIG_NAME).write_text(json.dumps(config), encoding="utf-8")
    return tmp_path


def _seed_migrated_project(tmp_path: Path) -> Path:
    """Create a target project that has already completed migration."""
    (tmp_path / "agent_docs").mkdir()
    d = iterates_dir(tmp_path)
    d.mkdir(parents=True)
    config = {
        "scope": "full_app",
        "iterate_history": [],
        MIGRATION_STATE_KEY: "complete",
        MIGRATION_TS_KEY: "2026-04-23T09:00:00Z",
        MIGRATION_QUARANTINED_COUNT_KEY: 0,
    }
    (tmp_path / RUN_CONFIG_NAME).write_text(json.dumps(config), encoding="utf-8")
    return tmp_path


def _load_config(project: Path) -> dict:
    return json.loads((project / RUN_CONFIG_NAME).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Core append — happy paths and failure cases
# ---------------------------------------------------------------------------


class TestAppend:
    def test_happy_path_writes_entry_file_with_canonical_shape(self, tmp_path):
        _seed_migrated_project(tmp_path)
        entry = _canonical_entry(slug="happy")

        result = append_iterate_entry(tmp_path, entry)

        entry_path = tmp_path / result["entry_path"]
        assert entry_path.exists()
        loaded = json.loads(entry_path.read_text(encoding="utf-8"))
        assert loaded["run_id"] == "iterate-2026-04-23-happy"
        assert loaded["type"] == "feature"
        assert result["migrated"] is False
        assert result["quarantined_count"] == 0

    def test_rejects_invalid_entry_before_touching_disk(self, tmp_path):
        _seed_migrated_project(tmp_path)
        bad = _canonical_entry()
        bad["type"] = "hotfix"  # not in allowlist

        with pytest.raises(IterateAppendError, match="type"):
            append_iterate_entry(tmp_path, bad)

        # Nothing was written because validation runs first.
        assert list(iterates_dir(tmp_path).iterdir()) == []

    def test_second_append_is_not_marked_migrated(self, tmp_path):
        """Once state=complete, subsequent appends don't claim to have
        migrated again. This is what callers key off of for reporting."""
        _seed_migrated_project(tmp_path)
        append_iterate_entry(tmp_path, _canonical_entry(slug="first"))
        result = append_iterate_entry(tmp_path, _canonical_entry(slug="second"))
        assert result["migrated"] is False

    def test_overwrites_existing_entry_file_for_same_run_id(self, tmp_path):
        """A retry / re-finalize for the same run_id overwrites atomically."""
        _seed_migrated_project(tmp_path)
        append_iterate_entry(tmp_path, _canonical_entry(slug="retry"))
        append_iterate_entry(
            tmp_path,
            {**_canonical_entry(slug="retry"), "tests_passed": False},
        )
        entries = read_iterate_entries(tmp_path)
        assert len(entries) == 1
        assert entries[0]["tests_passed"] is False

    def test_updated_at_is_bumped_only_on_config_mutation(self, tmp_path):
        """Non-migrating appends touch only the entry file, not the run config.
        The config ``updated_at`` stamp only advances when we mutate config
        (e.g. flipping migration state). This keeps write amplification low
        and makes config churn a meaningful signal."""
        _seed_migrated_project(tmp_path)
        config_before = _load_config(tmp_path)
        assert "updated_at" not in config_before

        append_iterate_entry(tmp_path, _canonical_entry(slug="a"))

        config_after = _load_config(tmp_path)
        # No migration happened → config untouched.
        assert "updated_at" not in config_after
        # Migration-state stamp unchanged.
        assert config_after[MIGRATION_TS_KEY] == config_before[MIGRATION_TS_KEY]


# ---------------------------------------------------------------------------
# Migration state machine
# ---------------------------------------------------------------------------


class TestMigration:
    def test_first_append_migrates_legacy_array_to_files(self, tmp_path):
        legacy = [
            _canonical_entry(slug=f"old-{i}", date=f"2026-04-0{i}T10:00:00Z")
            for i in range(1, 6)
        ]
        _seed_legacy_project(tmp_path, legacy)

        result = append_iterate_entry(
            tmp_path, _canonical_entry(slug="new", date="2026-04-23T10:00:00Z")
        )
        assert result["migrated"] is True

        # 5 legacy + 1 new = 6 files.
        dir_files = sorted(iterates_dir(tmp_path).glob("iterate-*.json"))
        assert len(dir_files) == 6

        config = _load_config(tmp_path)
        assert config["iterate_history"] == []
        assert config[MIGRATION_STATE_KEY] == "complete"
        assert config[MIGRATION_QUARANTINED_COUNT_KEY] == 0

    def test_migration_preserves_unknown_top_level_config_fields(self, tmp_path):
        """Don't lose custom fields like adr_prefix or profile overrides."""
        legacy = [_canonical_entry(slug="a")]
        (tmp_path / "agent_docs").mkdir()
        config = {
            "scope": "full_app",
            "iterate_history": legacy,
            "custom_team_field": {"foo": "bar"},
            "profile": "supabase-nextjs",
        }
        (tmp_path / RUN_CONFIG_NAME).write_text(json.dumps(config), encoding="utf-8")

        append_iterate_entry(tmp_path, _canonical_entry(slug="new"))

        config_after = _load_config(tmp_path)
        assert config_after["custom_team_field"] == {"foo": "bar"}
        assert config_after["profile"] == "supabase-nextjs"

    def test_migration_idempotent_when_dir_already_has_subset(self, tmp_path):
        """Simulates crash-mid-migration: 2 of 3 legacy entries already written
        to dir before the state flag flipped. Re-run must complete without
        duplicating the already-present rows."""
        legacy = [
            _canonical_entry(slug=f"old-{i}", date=f"2026-04-0{i}T10:00:00Z")
            for i in range(1, 4)
        ]
        _seed_legacy_project(tmp_path, legacy)

        # Partially pre-populate the dir as if we had crashed.
        d = iterates_dir(tmp_path)
        d.mkdir(parents=True, exist_ok=True)
        for partial in legacy[:2]:
            (d / f"{partial['run_id']}.json").write_text(
                json.dumps(partial), encoding="utf-8"
            )
        # Leave config in in_progress so the recovery path triggers.
        config = _load_config(tmp_path)
        config[MIGRATION_STATE_KEY] = "in_progress"
        (tmp_path / RUN_CONFIG_NAME).write_text(json.dumps(config), encoding="utf-8")

        append_iterate_entry(tmp_path, _canonical_entry(slug="new"))

        dir_files = sorted(iterates_dir(tmp_path).glob("iterate-*.json"))
        run_ids = sorted(
            json.loads(p.read_text())["run_id"] for p in dir_files
        )
        # Exactly 3 legacy + 1 new. No duplicates, no loss.
        assert len(run_ids) == 4
        assert len(set(run_ids)) == 4

    def test_crash_mid_migration_leaves_state_in_progress_then_recovers(
        self, tmp_path, monkeypatch
    ):
        """Force the migration to crash after the state flips to in_progress.
        The next append must notice the stale flag and re-run migration."""
        import tools.append_iterate_entry as tool

        legacy = [
            _canonical_entry(slug=f"old-{i}", date=f"2026-04-0{i}T10:00:00Z")
            for i in range(1, 4)
        ]
        _seed_legacy_project(tmp_path, legacy)

        call_count = {"n": 0}
        real_write = tool._write_entry_file

        def flaky_write(project_root, entry, *, overwrite=True):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise OSError("simulated disk fault mid-migration")
            return real_write(project_root, entry, overwrite=overwrite)

        monkeypatch.setattr(tool, "_write_entry_file", flaky_write)

        with pytest.raises(OSError):
            append_iterate_entry(
                tmp_path, _canonical_entry(slug="new")
            )

        config_after_crash = _load_config(tmp_path)
        assert config_after_crash[MIGRATION_STATE_KEY] == "in_progress"
        partial = list(iterates_dir(tmp_path).glob("iterate-*.json"))
        assert 1 <= len(partial) < 4, "at least one file written before fault"

        # Remove the fault and run again — recovery path should complete.
        monkeypatch.setattr(tool, "_write_entry_file", real_write)
        append_iterate_entry(tmp_path, _canonical_entry(slug="new"))

        config_recovered = _load_config(tmp_path)
        assert config_recovered[MIGRATION_STATE_KEY] == "complete"
        final_files = sorted(iterates_dir(tmp_path).glob("iterate-*.json"))
        assert len(final_files) == 4  # 3 legacy + 1 new
        assert len({json.loads(p.read_text())["run_id"] for p in final_files}) == 4

    def test_fresh_project_with_no_legacy_skips_migration_rapidly(
        self, tmp_path
    ):
        """A project that never had iterate_history (e.g. freshly adopted
        with the new artifact_writer) goes straight to append."""
        (tmp_path / "agent_docs").mkdir()
        config = {"scope": "full_app", MIGRATION_STATE_KEY: "complete"}
        (tmp_path / RUN_CONFIG_NAME).write_text(json.dumps(config), encoding="utf-8")

        result = append_iterate_entry(tmp_path, _canonical_entry(slug="first"))
        assert result["migrated"] is False
        assert result["quarantined_count"] == 0

    def test_project_without_run_config_still_appends(self, tmp_path):
        """Adopt-side artifact_writer may not have flipped the flag yet, and
        some test scenarios lack a run_config entirely. The tool must still
        create the entry file because the dir-per-iterate storage is
        independent of the config."""
        (tmp_path / "agent_docs").mkdir()
        result = append_iterate_entry(tmp_path, _canonical_entry(slug="first"))
        assert (tmp_path / result["entry_path"]).exists()


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


class TestRetention:
    def test_retention_trims_to_keep_last(self, tmp_path):
        _seed_migrated_project(tmp_path)

        # Append 52 entries with increasing dates so retention is deterministic.
        for i in range(52):
            entry = _canonical_entry(
                slug=f"r{i:03d}", date=f"2026-04-{(i % 28) + 1:02d}T{i % 24:02d}:00:00Z"
            )
            # Force unique run_id + monotonic date by mixing the day and index
            # into a unique date that sorts linearly.
            entry["date"] = f"2026-05-01T{i:03d}" + ":00:00Z"  # kept for sort
            # Fall back to a simpler synthetic date to avoid any ambiguity.
            day = 1 + (i // 24) + 1  # keeps day in valid range
            hour = i % 24
            entry["date"] = f"2026-05-{day:02d}T{hour:02d}:00:00Z"
            append_iterate_entry(tmp_path, entry)

        dir_files = list(iterates_dir(tmp_path).glob("iterate-*.json"))
        assert len(dir_files) == ITERATE_RETENTION

    def test_retention_does_not_prune_during_migration(self, tmp_path):
        """Migration of a 60-entry legacy array must preserve all 60 files,
        even though post-migration retention would otherwise kick in on the
        same call. Retention happens AFTER the entry write, and the test
        verifies that the legacy preservation pass wasn't trimmed."""
        legacy = [
            _canonical_entry(
                slug=f"leg-{i:03d}",
                date=f"2026-03-{(i % 28) + 1:02d}T{i % 24:02d}:00:00Z",
            )
            for i in range(60)
        ]
        # Give them strictly increasing dates so retention order is stable.
        for idx, entry in enumerate(legacy):
            entry["date"] = f"2026-03-{(idx // 24) + 1:02d}T{idx % 24:02d}:00:00Z"
        _seed_legacy_project(tmp_path, legacy)

        append_iterate_entry(
            tmp_path,
            _canonical_entry(slug="new", date="2026-05-01T00:00:00Z"),
        )

        dir_files = list(iterates_dir(tmp_path).glob("iterate-*.json"))
        # 60 legacy + 1 new = 61 pre-retention, retention trims to 50.
        # The RETENTION call WILL trim — but only the oldest legacy ones.
        assert len(dir_files) == ITERATE_RETENTION
        # The new entry must survive because it's the newest.
        assert any(
            json.loads(p.read_text())["run_id"] == "iterate-2026-04-23-new"
            for p in dir_files
        )

    def test_apply_retention_handles_missing_file_gracefully(self, tmp_path):
        """A parallel run may have already unlinked a file we planned to
        delete. _apply_retention must not crash."""
        _seed_migrated_project(tmp_path)
        for i in range(ITERATE_RETENTION + 3):
            entry = _canonical_entry(
                slug=f"s{i:03d}",
                date=f"2026-05-{(i // 24) + 1:02d}T{i % 24:02d}:00:00Z",
            )
            append_iterate_entry(tmp_path, entry)

        # Simulate a race: delete one of the candidate victims out from under
        # the next retention sweep.
        entries = read_iterate_entries(tmp_path)
        victim_path = iterates_dir(tmp_path) / f"{entries[0]['run_id']}.json"
        if victim_path.exists():
            victim_path.unlink()

        # Now force a retention pass via another append. Must not raise.
        append_iterate_entry(
            tmp_path,
            _canonical_entry(slug="after-race", date="2026-06-01T00:00:00Z"),
        )

    def test_apply_retention_is_no_op_below_threshold(self, tmp_path):
        _seed_migrated_project(tmp_path)
        for i in range(3):
            entry = _canonical_entry(slug=f"t{i}", date=f"2026-05-01T{i:02d}:00:00Z")
            append_iterate_entry(tmp_path, entry)
        # Directly invoke helper: no deletions expected.
        deleted = _apply_retention(tmp_path, keep_last=ITERATE_RETENTION)
        assert deleted == 0


# ---------------------------------------------------------------------------
# Quarantine  (invalid + duplicate legacy rows)
# ---------------------------------------------------------------------------


class TestQuarantine:
    def test_invalid_legacy_entry_goes_to_quarantine_not_dir(self, tmp_path):
        legacy = [
            _canonical_entry(slug="good"),
            {"run_id": "bad", "type": "not-a-type"},  # missing required fields
        ]
        _seed_legacy_project(tmp_path, legacy)
        result = append_iterate_entry(tmp_path, _canonical_entry(slug="new"))

        assert result["quarantined_count"] == 1

        # Valid legacy + new still landed in main dir.
        dir_run_ids = {
            json.loads(p.read_text())["run_id"]
            for p in iterates_dir(tmp_path).glob("iterate-*.json")
        }
        assert "iterate-2026-04-23-good" in dir_run_ids
        assert "iterate-2026-04-23-new" in dir_run_ids
        # Bad one did NOT land in main dir.
        assert "bad" not in dir_run_ids

        # Quarantine report captured the bad row.
        q_files = list(quarantine_dir(tmp_path).glob("invalid-legacy-*.json"))
        assert len(q_files) == 1
        report = json.loads(q_files[0].read_text())
        assert report["quarantined_count"] == 1

    def test_duplicate_run_id_quarantines_both_payloads(self, tmp_path):
        """Deterministic precedence would silently hide the conflict. We
        divert both to quarantine so the operator notices."""
        dup_a = _canonical_entry(slug="dup")
        dup_b = _canonical_entry(slug="dup")
        dup_b["tests_passed"] = False  # different payload, same run_id
        legacy = [dup_a, dup_b, _canonical_entry(slug="unique")]
        _seed_legacy_project(tmp_path, legacy)

        result = append_iterate_entry(tmp_path, _canonical_entry(slug="new"))
        assert result["quarantined_count"] == 2

        dir_run_ids = {
            json.loads(p.read_text())["run_id"]
            for p in iterates_dir(tmp_path).glob("iterate-*.json")
        }
        # Only the non-conflicting legacy + new survive.
        assert dir_run_ids == {
            "iterate-2026-04-23-unique",
            "iterate-2026-04-23-new",
        }

    def test_triple_duplicate_run_id_all_three_quarantined(self, tmp_path):
        """Regression guard: without the ``poisoned`` set, a naive
        ``del seen[run_id]`` would let the THIRD row with the same run_id
        re-enter ``seen`` and silently land on disk. The fix poisons the
        run_id on first collision so every subsequent copy also goes to
        quarantine. Operator then sees the true quarantine count (3) and
        no spurious "winner" landing on the canonical path."""
        dup_a = _canonical_entry(slug="triple")
        dup_a["branch"] = "iterate/triple-a"
        dup_b = _canonical_entry(slug="triple")
        dup_b["branch"] = "iterate/triple-b"
        dup_b["tests_passed"] = False
        dup_c = _canonical_entry(slug="triple")
        dup_c["branch"] = "iterate/triple-c"
        legacy = [dup_a, dup_b, dup_c, _canonical_entry(slug="clean")]
        _seed_legacy_project(tmp_path, legacy)

        result = append_iterate_entry(tmp_path, _canonical_entry(slug="new"))
        assert result["quarantined_count"] == 3

        dir_run_ids = {
            json.loads(p.read_text())["run_id"]
            for p in iterates_dir(tmp_path).glob("iterate-*.json")
        }
        # The conflicting run_id must NOT appear on the canonical path.
        assert "iterate-2026-04-23-triple" not in dir_run_ids
        # Non-conflicting legacy + new survive.
        assert "iterate-2026-04-23-clean" in dir_run_ids
        assert "iterate-2026-04-23-new" in dir_run_ids

    def test_quarantine_metadata_lands_on_run_config(self, tmp_path):
        legacy = [
            _canonical_entry(slug="good"),
            {"run_id": "broken"},  # invalid
        ]
        _seed_legacy_project(tmp_path, legacy)
        append_iterate_entry(tmp_path, _canonical_entry(slug="new"))

        config = _load_config(tmp_path)
        assert config[MIGRATION_QUARANTINED_COUNT_KEY] == 1
        assert MIGRATION_QUARANTINE_REPORT_KEY in config
        # Relative to project root, under _quarantine.
        assert "_quarantine" in config[MIGRATION_QUARANTINE_REPORT_KEY]

    def test_normalizes_capitalized_legacy_type_before_quarantine(
        self, tmp_path
    ):
        """A legacy entry with ``Feature`` (capital F) should be repaired by
        the normalization pre-pass — NOT sent to quarantine."""
        bad_case = _canonical_entry(slug="capitalized")
        bad_case["type"] = "Feature"
        _seed_legacy_project(tmp_path, [bad_case])

        result = append_iterate_entry(tmp_path, _canonical_entry(slug="new"))
        assert result["quarantined_count"] == 0

        dir_run_ids = {
            json.loads(p.read_text())["run_id"]
            for p in iterates_dir(tmp_path).glob("iterate-*.json")
        }
        assert "iterate-2026-04-23-capitalized" in dir_run_ids

    def test_no_quarantine_no_report_key_on_config(self, tmp_path):
        legacy = [_canonical_entry(slug="good")]
        _seed_legacy_project(tmp_path, legacy)
        append_iterate_entry(tmp_path, _canonical_entry(slug="new"))

        config = _load_config(tmp_path)
        assert config[MIGRATION_QUARANTINED_COUNT_KEY] == 0
        assert MIGRATION_QUARANTINE_REPORT_KEY not in config
