"""Tests for shared/scripts/lib/iterate_entry.py — schema + merge semantics."""

from __future__ import annotations

import json
from pathlib import Path


from lib.iterate_entry import (
    MAX_ENTRY_FILE_BYTES,
    RUN_CONFIG_NAME,
    entry_file_for,
    find_entry_by_run_id,
    iterates_dir,
    last_iterate_entry,
    normalize_legacy_entry,
    now_utc_iso,
    read_iterate_entries,
    sanitize_run_id_for_filename,
    sort_key,
    validate_iterate_entry,
)


def _valid_entry(**overrides) -> dict:
    base = {
        "run_id": "iterate-2026-04-23-parallel-worktree",
        "date": "2026-04-23T10:00:00Z",
        "type": "feature",
        "complexity": "medium",
        "branch": "iterate/parallel-worktree",
        "spec": ".shipwright/planning/iterate/foo.md",
        "tests_passed": True,
        "adr": "ADR-055",
    }
    base.update(overrides)
    return base


def _write_entry_file(project: Path, entry: dict) -> Path:
    d = iterates_dir(project)
    d.mkdir(parents=True, exist_ok=True)
    path = entry_file_for(project, entry["run_id"])
    path.write_text(json.dumps(entry), encoding="utf-8")
    return path


def _write_legacy_array(project: Path, entries: list[dict]) -> None:
    config = {"scope": "full_app", "iterate_history": entries}
    (project / RUN_CONFIG_NAME).write_text(json.dumps(config), encoding="utf-8")


# ---------------------------------------------------------------------------
# validate_iterate_entry
# ---------------------------------------------------------------------------


class TestValidate:
    def test_happy_path_strict_accepts_canonical_entry(self):
        ok, err = validate_iterate_entry(_valid_entry())
        assert ok is True
        assert err is None

    def test_rejects_non_dict(self):
        ok, err = validate_iterate_entry(["not", "a", "dict"])
        assert ok is False
        assert "JSON object" in err

    def test_rejects_missing_required_field(self):
        entry = _valid_entry()
        del entry["branch"]
        ok, err = validate_iterate_entry(entry)
        assert ok is False
        assert "missing required field: branch" in err

    def test_rejects_wrong_type_on_tests_passed(self):
        ok, err = validate_iterate_entry(_valid_entry(tests_passed="yes"))
        assert ok is False
        assert "tests_passed" in err

    def test_strict_rejects_uppercase_run_id(self):
        ok, err = validate_iterate_entry(
            _valid_entry(run_id="Iterate-2026-04-23-X"), strict=True
        )
        assert ok is False
        assert "run_id" in err

    def test_legacy_accepts_uppercase_run_id(self):
        ok, err = validate_iterate_entry(
            _valid_entry(run_id="iterate_2026_04_23_foo"), strict=False
        )
        assert ok is True

    def test_legacy_still_rejects_shell_metachars_in_run_id(self):
        ok, _ = validate_iterate_entry(
            _valid_entry(run_id="iterate-$(rm rf)"), strict=False
        )
        assert ok is False

    def test_rejects_unparseable_date(self):
        ok, err = validate_iterate_entry(_valid_entry(date="yesterday"))
        assert ok is False
        assert "ISO-8601" in err

    def test_accepts_both_Z_and_offset_date_forms(self):
        ok1, _ = validate_iterate_entry(
            _valid_entry(date="2026-04-23T10:00:00Z")
        )
        ok2, _ = validate_iterate_entry(
            _valid_entry(date="2026-04-23T12:00:00+02:00")
        )
        assert ok1 and ok2

    def test_rejects_unknown_type(self):
        ok, err = validate_iterate_entry(_valid_entry(type="hotfix"))
        assert ok is False
        assert "type" in err

    def test_rejects_unknown_complexity(self):
        ok, err = validate_iterate_entry(_valid_entry(complexity="epic"))
        assert ok is False
        assert "complexity" in err

    def test_accepts_null_spec_and_null_adr(self):
        ok, _ = validate_iterate_entry(_valid_entry(spec=None, adr=None))
        assert ok is True

    def test_rejects_non_string_spec(self):
        ok, err = validate_iterate_entry(_valid_entry(spec=42))
        assert ok is False
        assert "spec" in err


# ---------------------------------------------------------------------------
# normalize_legacy_entry
# ---------------------------------------------------------------------------


class TestNormalize:
    def test_lowercases_type_and_complexity(self):
        raw = _valid_entry(type="Feature", complexity="Medium")
        out = normalize_legacy_entry(raw)
        assert out["type"] == "feature"
        assert out["complexity"] == "medium"

    def test_maps_conventional_commit_shorthand(self):
        assert normalize_legacy_entry(_valid_entry(type="feat"))["type"] == "feature"
        assert normalize_legacy_entry(_valid_entry(type="fix"))["type"] == "bug"
        assert normalize_legacy_entry(_valid_entry(type="bugfix"))["type"] == "bug"
        assert normalize_legacy_entry(_valid_entry(type="refactor"))["type"] == "change"
        assert normalize_legacy_entry(_valid_entry(type="chore"))["type"] == "change"

    def test_trims_whitespace(self):
        out = normalize_legacy_entry(_valid_entry(type="  feature  ", complexity=" SMALL "))
        assert out["type"] == "feature"
        assert out["complexity"] == "small"

    def test_leaves_unknown_variants_lowercased_but_unchanged(self):
        out = normalize_legacy_entry(_valid_entry(type="hotpatch"))
        assert out["type"] == "hotpatch"  # caller's validate() will reject

    def test_does_not_mutate_input(self):
        raw = _valid_entry(type="Feature")
        normalize_legacy_entry(raw)
        assert raw["type"] == "Feature"

    def test_tolerates_non_string_type(self):
        raw = _valid_entry()
        raw["type"] = None  # corrupt legacy data
        out = normalize_legacy_entry(raw)
        # Normalize leaves non-str untouched, validator will fail-soft.
        assert out["type"] is None


# ---------------------------------------------------------------------------
# sanitize_run_id_for_filename  (path-traversal defense)
# ---------------------------------------------------------------------------


class TestSanitize:
    def test_passes_canonical_run_id_through(self):
        out = sanitize_run_id_for_filename("iterate-2026-04-23-feat-x")
        assert out == "iterate-2026-04-23-feat-x"

    def test_replaces_forward_slash(self):
        out = sanitize_run_id_for_filename("iterate/../etc/passwd")
        assert "/" not in out
        assert ".." not in out

    def test_replaces_backslash(self):
        out = sanitize_run_id_for_filename("iterate\\..\\windows")
        assert "\\" not in out

    def test_replaces_null_byte_and_control_chars(self):
        out = sanitize_run_id_for_filename("iterate-\x00-foo\x07bar")
        assert "\x00" not in out
        assert "\x07" not in out

    def test_never_returns_empty(self):
        out = sanitize_run_id_for_filename("/////")
        assert out == "iterate-unknown"

    def test_strips_trailing_separator_chars(self):
        out = sanitize_run_id_for_filename("iterate-x---")
        assert not out.endswith("-")


# ---------------------------------------------------------------------------
# sort_key  (mixed-timezone correctness)
# ---------------------------------------------------------------------------


class TestSortKey:
    def test_sorts_same_utc_instant_regardless_of_offset(self):
        """Same moment expressed as `Z` and `+02:00` must sort equal on date."""
        a = {"run_id": "a", "date": "2026-04-23T10:00:00Z"}
        b = {"run_id": "b", "date": "2026-04-23T12:00:00+02:00"}
        assert sort_key(a)[0] == sort_key(b)[0]
        # Tie-breaker pushes by run_id alphabetically.
        assert sort_key(a) < sort_key(b)

    def test_orders_chronologically_not_lexically(self):
        """Lexical order would put +02:00 before Z for the same day.
        sort_key corrects to true chronological order."""
        utc_later = {"run_id": "later", "date": "2026-04-23T12:00:00Z"}
        offset_earlier = {"run_id": "earlier", "date": "2026-04-23T12:00:00+02:00"}
        assert sort_key(offset_earlier) < sort_key(utc_later)

    def test_treats_naive_dates_as_utc(self):
        """A date without timezone info must not crash and must sort stably."""
        naive = {"run_id": "naive", "date": "2026-04-23"}
        aware = {"run_id": "aware", "date": "2026-04-23T00:00:00Z"}
        # Both normalize to 00:00 UTC on the same day.
        assert sort_key(naive)[0] == sort_key(aware)[0]

    def test_malformed_date_sinks_to_bottom(self):
        """Corrupt entries shouldn't crash the sort; they get a minimal key."""
        bad = {"run_id": "bad", "date": "garbage"}
        good = {"run_id": "good", "date": "2026-04-23T10:00:00Z"}
        assert sort_key(bad) < sort_key(good)


def test_now_utc_iso_emits_Z_suffix_not_offset():
    out = now_utc_iso()
    assert out.endswith("Z")
    assert "+00:00" not in out


# ---------------------------------------------------------------------------
# read_iterate_entries  (merge, precedence, defensive)
# ---------------------------------------------------------------------------


class TestReadEntries:
    def test_empty_project_returns_empty_list(self, tmp_path):
        assert read_iterate_entries(tmp_path) == []

    def test_reads_only_legacy_when_no_dir(self, tmp_path):
        _write_legacy_array(
            tmp_path,
            [
                _valid_entry(run_id="iterate-2026-04-01-old"),
                _valid_entry(run_id="iterate-2026-04-10-mid"),
            ],
        )
        entries = read_iterate_entries(tmp_path)
        run_ids = [e["run_id"] for e in entries]
        assert run_ids == ["iterate-2026-04-01-old", "iterate-2026-04-10-mid"]

    def test_reads_only_dir_when_no_legacy(self, tmp_path):
        _write_entry_file(tmp_path, _valid_entry(run_id="iterate-2026-04-15-a"))
        _write_entry_file(tmp_path, _valid_entry(run_id="iterate-2026-04-20-b"))
        entries = read_iterate_entries(tmp_path)
        run_ids = [e["run_id"] for e in entries]
        assert run_ids == ["iterate-2026-04-15-a", "iterate-2026-04-20-b"]

    def test_merges_legacy_and_dir_sorted_by_date(self, tmp_path):
        _write_legacy_array(
            tmp_path,
            [_valid_entry(run_id="iterate-2026-04-10-old", date="2026-04-10T10:00:00Z")],
        )
        _write_entry_file(
            tmp_path,
            _valid_entry(run_id="iterate-2026-04-20-new", date="2026-04-20T10:00:00Z"),
        )
        _write_entry_file(
            tmp_path,
            _valid_entry(run_id="iterate-2026-04-15-middle", date="2026-04-15T10:00:00Z"),
        )
        entries = read_iterate_entries(tmp_path)
        assert [e["run_id"] for e in entries] == [
            "iterate-2026-04-10-old",
            "iterate-2026-04-15-middle",
            "iterate-2026-04-20-new",
        ]

    def test_dir_wins_on_duplicate_run_id(self, tmp_path):
        """Partial migration: same run_id in both sources. Dir version wins."""
        _write_legacy_array(
            tmp_path,
            [_valid_entry(run_id="iterate-2026-04-23-foo", tests_passed=False)],
        )
        _write_entry_file(
            tmp_path,
            _valid_entry(run_id="iterate-2026-04-23-foo", tests_passed=True),
        )
        entries = read_iterate_entries(tmp_path)
        assert len(entries) == 1
        assert entries[0]["tests_passed"] is True

    def test_partial_migration_does_not_hide_legacy_entries(self, tmp_path):
        """Crash mid-migration: 3 of 5 legacy entries copied to dir. Reader must
        still surface all 5 run_ids so verifier output stays correct."""
        legacy = [
            _valid_entry(run_id=f"iterate-2026-04-0{i}-x", date=f"2026-04-0{i}T10:00:00Z")
            for i in range(1, 6)
        ]
        _write_legacy_array(tmp_path, legacy)
        # Only first 3 migrated (simulates crash mid-run).
        for entry in legacy[:3]:
            _write_entry_file(tmp_path, entry)

        entries = read_iterate_entries(tmp_path)
        assert len(entries) == 5  # NOT 3 — merge exposes everything
        run_ids = [e["run_id"] for e in entries]
        assert all(
            f"iterate-2026-04-0{i}-x" in run_ids for i in range(1, 6)
        )

    def test_skips_non_canonical_filenames(self, tmp_path):
        d = iterates_dir(tmp_path)
        d.mkdir(parents=True)
        # These should be ignored by the reader.
        (d / "_index.json").write_text(json.dumps({"junk": True}), encoding="utf-8")
        (d / "notes.md").write_text("# notes", encoding="utf-8")
        (d / "iterate-2026-04-23-backup.json.bak").write_text("{}", encoding="utf-8")
        # Canonical entry that SHOULD load.
        _write_entry_file(tmp_path, _valid_entry(run_id="iterate-2026-04-23-valid"))

        entries = read_iterate_entries(tmp_path)
        assert len(entries) == 1
        assert entries[0]["run_id"] == "iterate-2026-04-23-valid"

    def test_skips_oversized_file(self, tmp_path, capsys):
        d = iterates_dir(tmp_path)
        d.mkdir(parents=True)
        # Oversized file: 64 KB + some padding.
        oversized = d / "iterate-2026-04-23-huge.json"
        oversized.write_bytes(b'{"run_id": "x"}' + b" " * (MAX_ENTRY_FILE_BYTES + 10))
        # Valid sibling.
        _write_entry_file(tmp_path, _valid_entry(run_id="iterate-2026-04-23-valid"))

        entries = read_iterate_entries(tmp_path)
        run_ids = [e["run_id"] for e in entries]
        assert "iterate-2026-04-23-valid" in run_ids
        assert "x" not in run_ids  # oversized entry was skipped

    def test_skips_corrupt_json_and_warns_via_logger(self, tmp_path, caplog):
        import logging

        d = iterates_dir(tmp_path)
        d.mkdir(parents=True)
        (d / "iterate-2026-04-23-broken.json").write_text(
            "{ not valid json", encoding="utf-8"
        )
        _write_entry_file(tmp_path, _valid_entry(run_id="iterate-2026-04-23-ok"))

        with caplog.at_level(logging.WARNING, logger="shipwright.iterate_entry"):
            entries = read_iterate_entries(tmp_path)

        assert [e["run_id"] for e in entries] == ["iterate-2026-04-23-ok"]
        # Warning was raised (routed through the stdlib logger, not stderr)
        # so callers like generate_session_handoff can control verbosity.
        messages = [rec.getMessage() for rec in caplog.records]
        assert any("broken" in m and "corrupt" in m.lower() for m in messages), (
            f"expected corrupt-file warning, got: {messages}"
        )

    def test_malformed_run_config_returns_empty_legacy(self, tmp_path):
        (tmp_path / RUN_CONFIG_NAME).write_text("{ not valid json", encoding="utf-8")
        # No dir either — reader must still return [] without crashing.
        assert read_iterate_entries(tmp_path) == []

    def test_ignores_quarantine_subdir(self, tmp_path):
        d = iterates_dir(tmp_path)
        q = d / "_quarantine"
        q.mkdir(parents=True)
        # Place what LOOKS like an entry inside the quarantine subdir.
        (q / "iterate-2026-04-23-quarantined.json").write_text(
            json.dumps(_valid_entry(run_id="iterate-2026-04-23-quarantined")),
            encoding="utf-8",
        )
        _write_entry_file(tmp_path, _valid_entry(run_id="iterate-2026-04-23-valid"))

        entries = read_iterate_entries(tmp_path)
        assert len(entries) == 1
        assert entries[0]["run_id"] == "iterate-2026-04-23-valid"


def test_last_iterate_entry_returns_none_on_empty(tmp_path):
    assert last_iterate_entry(tmp_path) is None


def test_last_iterate_entry_returns_latest_by_date(tmp_path):
    _write_entry_file(
        tmp_path, _valid_entry(run_id="iterate-2026-04-10-old", date="2026-04-10T10:00:00Z")
    )
    _write_entry_file(
        tmp_path, _valid_entry(run_id="iterate-2026-04-20-new", date="2026-04-20T10:00:00Z")
    )
    last = last_iterate_entry(tmp_path)
    assert last is not None
    assert last["run_id"] == "iterate-2026-04-20-new"


def test_find_entry_by_run_id_resolves_from_either_source(tmp_path):
    _write_legacy_array(
        tmp_path,
        [_valid_entry(run_id="iterate-2026-04-10-legacy-only")],
    )
    _write_entry_file(
        tmp_path, _valid_entry(run_id="iterate-2026-04-20-dir-only")
    )
    assert (
        find_entry_by_run_id(tmp_path, "iterate-2026-04-10-legacy-only") is not None
    )
    assert (
        find_entry_by_run_id(tmp_path, "iterate-2026-04-20-dir-only") is not None
    )
    assert find_entry_by_run_id(tmp_path, "iterate-nonexistent") is None


def test_entry_file_for_stays_under_iterates_dir(tmp_path):
    """Even for pathologically crafted run_ids, the derived path must stay
    within .shipwright/agent_docs/iterates/."""
    malicious = "iterate-../../../etc/passwd"
    path = entry_file_for(tmp_path, malicious)
    # Resolved path must still be inside the iterates directory.
    assert iterates_dir(tmp_path).resolve() in path.resolve().parents
