"""Tests for shared/scripts/lib/decision_drop_legacy.py.

doubt-reviewer HIGH #3 (iterate-2026-08-08-track-decision-drops): a project's
decision-drops directory going from gitignored to tracked exposes whatever
pre-tracking drops already sit on disk — never gitleaks/prompt-scanned. These
pure functions decide which drops are "legacy" and move them out of
``git add -A``'s reach; see the module docstring for the full rationale on why
freshness is read from filesystem mtime, not the JSON ``date`` field.
"""

from __future__ import annotations

import os
import time
from datetime import datetime

from lib.decision_drop_legacy import (
    LEGACY_CUTOFF_DATE,
    LEGACY_QUARANTINE_DIRNAME,
    format_quarantine_warning,
    is_legacy_drop,
    legacy_dir,
    partition_by_freshness,
    quarantine_legacy_drops,
)

_OLD_TS = datetime.fromisoformat("2026-01-01").timestamp()
_NEW_TS = time.time()


def _write(path, *, mtime):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


# ─── is_legacy_drop ─────────────────────────────────────────────────────────


def test_is_legacy_drop_true_for_mtime_before_cutoff(tmp_path):
    old = _write(tmp_path / "old_001.json", mtime=_OLD_TS)
    assert is_legacy_drop(old) is True


def test_is_legacy_drop_false_for_mtime_today(tmp_path):
    fresh = _write(tmp_path / "fresh_001.json", mtime=_NEW_TS)
    assert is_legacy_drop(fresh) is False


def test_is_legacy_drop_ignores_narrative_date_field(tmp_path):
    """A drop written TODAY (fresh mtime) but carrying a backdated narrative
    `date` field (write_decision_drop --date, test_authoring_date_preserved's
    use case) must NOT be treated as legacy — only the file's own mtime, not
    its JSON content, decides provenance."""
    path = tmp_path / "backdated_001.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"date": "2020-01-01"}', encoding="utf-8")  # fresh mtime
    assert is_legacy_drop(path) is False


def test_is_legacy_drop_fails_closed_on_missing_file(tmp_path):
    assert is_legacy_drop(tmp_path / "does_not_exist_001.json") is True


# ─── partition_by_freshness ─────────────────────────────────────────────────


def test_partition_splits_fresh_and_legacy(tmp_path):
    fresh = _write(tmp_path / "fresh_001.json", mtime=_NEW_TS)
    legacy = _write(tmp_path / "legacy_001.json", mtime=_OLD_TS)
    fresh_out, legacy_out = partition_by_freshness([fresh, legacy])
    assert fresh_out == [fresh]
    assert legacy_out == [legacy]


def test_partition_empty_input(tmp_path):
    assert partition_by_freshness([]) == ([], [])


# ─── quarantine_legacy_drops ────────────────────────────────────────────────


def test_quarantine_moves_files_into_legacy_dir(tmp_path):
    src = _write(tmp_path / ".shipwright" / "agent_docs" / "decision-drops"
                 / "old_001.json", mtime=_OLD_TS)
    moved, errors = quarantine_legacy_drops(tmp_path, [src])
    assert moved == ["old_001.json"]
    assert errors == []
    assert not src.exists()
    assert (legacy_dir(tmp_path) / "old_001.json").exists()


def test_quarantine_empty_input_is_noop(tmp_path):
    moved, errors = quarantine_legacy_drops(tmp_path, [])
    assert moved == [] and errors == []
    assert not legacy_dir(tmp_path).exists()


def test_legacy_dir_is_named_and_placed_as_documented(tmp_path):
    assert legacy_dir(tmp_path) == (
        tmp_path / ".shipwright" / "agent_docs" / LEGACY_QUARANTINE_DIRNAME
    )


# ─── format_quarantine_warning ──────────────────────────────────────────────


def test_format_quarantine_warning_names_files_and_cutoff():
    msg = format_quarantine_warning(["a_001.json", "b_001.json"], dry_run=False)
    assert "quarantined 2" in msg
    assert LEGACY_CUTOFF_DATE in msg
    assert "a_001.json" in msg and "b_001.json" in msg


def test_format_quarantine_warning_dry_run_uses_would():
    msg = format_quarantine_warning(["a_001.json"], dry_run=True)
    assert "would quarantine" in msg
