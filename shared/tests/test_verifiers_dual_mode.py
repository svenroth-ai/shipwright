"""Dual-mode smoke tests for verifiers after the iterate_history refactor.

The existing verifier test files (test_verify_iterate_finalization.py,
test_spec_checks.py, test_generate_session_handoff.py) keep passing
unchanged because they use legacy-array fixtures. These tests exercise
the other half of the matrix: entries that live ONLY in the new
per-file directory (``agent_docs/iterates/``) with no legacy
``iterate_history`` array in the run config.

A freshly adopted project initialized by the updated
``shipwright-adopt`` artifact writer reaches this path on every
subsequent iterate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.iterate_entry import (
    MIGRATION_STATE_KEY,
    MIGRATION_TS_KEY,
    RUN_CONFIG_NAME,
    entry_file_for,
    iterates_dir,
)
from tools.generate_session_handoff import generate_handoff
from tools.verifiers.iterate_checks import (
    check_adr_in_iterate_history,
    check_architecture_reviewed,
    check_compliance_reflects_run_id,
    check_conventions_reviewed,
    check_iterate_history_has_run_id,
    check_migration_quarantine_empty,
)
from tools.verifiers.spec_checks import _iterate_complexity, _read_iterate_entry


def _canonical_entry(slug: str = "feat-x", complexity: str = "medium") -> dict:
    return {
        "run_id": f"iterate-2026-04-23-{slug}",
        "date": "2026-04-23T10:00:00Z",
        "type": "feature",
        "complexity": complexity,
        "branch": f"iterate/{slug}",
        "spec": "planning/iterate/foo.md",
        "tests_passed": True,
        "adr": "ADR-055",
    }


def _seed_dir_only_project(tmp_path: Path, entries: list[dict]) -> Path:
    """Fresh-adopted project: entries live in the dir, run config has no
    legacy array."""
    (tmp_path / "agent_docs").mkdir()
    d = iterates_dir(tmp_path)
    d.mkdir(parents=True)
    for entry in entries:
        entry_file_for(tmp_path, entry["run_id"]).write_text(
            json.dumps(entry), encoding="utf-8"
        )
    config = {
        "scope": "full_app",
        MIGRATION_STATE_KEY: "complete",
        MIGRATION_TS_KEY: "2026-04-23T09:00:00Z",
    }
    (tmp_path / RUN_CONFIG_NAME).write_text(json.dumps(config), encoding="utf-8")
    return tmp_path


def _seed_decision_log(project_root: Path, adr_id: str = "ADR-055") -> None:
    log = project_root / "agent_docs" / "decision_log.md"
    log.parent.mkdir(exist_ok=True)
    log.write_text(
        f"# Decision log\n\n### {adr_id}: File-per-iterate refactor\n\n"
        "Some decision text.\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# iterate_checks
# ---------------------------------------------------------------------------


class TestIterateChecksDirOnly:
    def test_iterate_history_has_run_id_passes_with_dir_only_entry(self, tmp_path):
        entry = _canonical_entry(slug="dir-only-a")
        _seed_dir_only_project(tmp_path, [entry])
        result = check_iterate_history_has_run_id(tmp_path, entry["run_id"])
        assert result.ok is True
        assert entry["run_id"] in result.detail

    def test_iterate_history_has_run_id_fails_when_entry_missing(self, tmp_path):
        _seed_dir_only_project(tmp_path, [_canonical_entry(slug="other")])
        result = check_iterate_history_has_run_id(
            tmp_path, "iterate-2026-04-23-not-there"
        )
        assert result.ok is False
        assert "not in iterate history" in result.detail

    def test_adr_check_passes_with_dir_only_entry(self, tmp_path):
        entry = _canonical_entry(slug="adr-a")
        _seed_dir_only_project(tmp_path, [entry])
        _seed_decision_log(tmp_path, adr_id="ADR-055")
        result = check_adr_in_iterate_history(tmp_path, entry["run_id"])
        assert result.ok is True
        assert "ADR-055" in result.detail

    def test_adr_check_fails_when_adr_not_in_decision_log(self, tmp_path):
        entry = _canonical_entry(slug="adr-b")
        entry["adr"] = "ADR-999"  # not present in log
        _seed_dir_only_project(tmp_path, [entry])
        _seed_decision_log(tmp_path, adr_id="ADR-055")
        result = check_adr_in_iterate_history(tmp_path, entry["run_id"])
        assert result.ok is False
        assert "ADR-999" in result.detail

    def test_architecture_reviewed_for_bugfix_entry_passes_trivially(
        self, tmp_path
    ):
        entry = _canonical_entry(slug="bugfix-a")
        entry["type"] = "bug"
        entry["intent"] = "bug"  # legacy field name also present
        _seed_dir_only_project(tmp_path, [entry])
        result = check_architecture_reviewed(tmp_path, entry["run_id"])
        assert result.ok is True

    def test_compliance_reflects_entry_count_with_dir_only(self, tmp_path):
        entries = [_canonical_entry(slug=f"c{i}") for i in range(3)]
        # Make them unique
        for i, e in enumerate(entries):
            e["run_id"] = f"iterate-2026-04-2{i}-count-{i}"
            e["date"] = f"2026-04-2{i}T10:00:00Z"
        _seed_dir_only_project(tmp_path, entries)

        compliance_dir = tmp_path / "compliance"
        compliance_dir.mkdir()
        (compliance_dir / "dashboard.md").write_text(
            "# Compliance dashboard\n\nTotal iterates: 3\n",
            encoding="utf-8",
        )

        result = check_compliance_reflects_run_id(
            tmp_path, "iterate-2026-04-20-count-0"
        )
        assert result.ok is True

    def test_migration_quarantine_check_passes_when_zero(self, tmp_path):
        _seed_dir_only_project(tmp_path, [_canonical_entry()])
        result = check_migration_quarantine_empty(tmp_path)
        assert result.ok is True

    def test_migration_quarantine_check_warns_when_nonzero(self, tmp_path):
        """When migration left quarantined entries behind, the verifier
        surfaces a loud WARN so the operator notices data was diverted."""
        _seed_dir_only_project(tmp_path, [_canonical_entry()])
        config = json.loads((tmp_path / RUN_CONFIG_NAME).read_text())
        config["_iterate_migration_quarantined_count"] = 2
        config["_iterate_migration_quarantine_report"] = (
            "agent_docs/iterates/_quarantine/invalid-legacy-20260423.json"
        )
        (tmp_path / RUN_CONFIG_NAME).write_text(json.dumps(config), encoding="utf-8")

        result = check_migration_quarantine_empty(tmp_path)
        assert result.ok is False
        assert "2" in result.detail
        assert "quarantine" in result.detail.lower()


# ---------------------------------------------------------------------------
# spec_checks
# ---------------------------------------------------------------------------


class TestSpecChecksDirOnly:
    def test_read_iterate_entry_resolves_from_dir(self, tmp_path):
        entry = _canonical_entry(slug="dir-resolver")
        _seed_dir_only_project(tmp_path, [entry])
        resolved = _read_iterate_entry(tmp_path, entry["run_id"])
        assert resolved is not None
        assert resolved["run_id"] == entry["run_id"]

    def test_read_iterate_entry_falls_back_to_tail_on_unknown_run_id(
        self, tmp_path
    ):
        """Mid-flow finalize: run_id hasn't been written yet, but there IS
        a tail entry. The resolver returns it so S2/S3 still get a
        complexity signal."""
        entries = [
            _canonical_entry(slug="old", complexity="small"),
            _canonical_entry(slug="new", complexity="large"),
        ]
        entries[0]["run_id"] = "iterate-2026-04-10-old"
        entries[0]["date"] = "2026-04-10T10:00:00Z"
        entries[1]["run_id"] = "iterate-2026-04-20-new"
        entries[1]["date"] = "2026-04-20T10:00:00Z"
        _seed_dir_only_project(tmp_path, entries)

        # run_id below does NOT exist. Resolver must return the tail.
        resolved = _read_iterate_entry(tmp_path, "iterate-2026-04-23-mid-flow")
        assert resolved is not None
        assert resolved["run_id"] == "iterate-2026-04-20-new"

    def test_iterate_complexity_returns_none_for_empty_project(self, tmp_path):
        (tmp_path / "agent_docs").mkdir()
        assert _iterate_complexity(tmp_path, "iterate-2026-04-23-x") is None

    def test_iterate_complexity_lowercase_normalization_via_reader(
        self, tmp_path
    ):
        """The lib reader serves back data untouched; legacy mixed-case values
        are only normalized during migration, not on read. Verify the
        resolver handles lower-case values directly (the happy path post-
        migration)."""
        entry = _canonical_entry(slug="comp", complexity="medium")
        _seed_dir_only_project(tmp_path, [entry])
        assert _iterate_complexity(tmp_path, entry["run_id"]) == "medium"


# ---------------------------------------------------------------------------
# generate_session_handoff
# ---------------------------------------------------------------------------


class TestHandoffDirOnly:
    def test_last_iterate_block_renders_from_dir(self, tmp_path):
        entry = _canonical_entry(slug="handoff-a")
        _seed_dir_only_project(tmp_path, [entry])
        out = generate_handoff(
            tmp_path,
            session_id="sess-123",
            reason="finalize",
        )
        assert "## Last Iterate" in out
        assert entry["run_id"] in out
        assert "ADR-055" in out

    def test_last_iterate_block_omitted_on_empty_project(self, tmp_path):
        """Fresh adopted project with no iterate runs yet must render a
        handoff without the Last Iterate section — no placeholder noise."""
        (tmp_path / "agent_docs").mkdir()
        (tmp_path / RUN_CONFIG_NAME).write_text(
            json.dumps({"scope": "full_app", MIGRATION_STATE_KEY: "complete"}),
            encoding="utf-8",
        )
        out = generate_handoff(tmp_path, session_id="sess-empty", reason="smoke")
        assert "## Last Iterate" not in out

    def test_quarantine_warning_rendered_when_count_nonzero(self, tmp_path):
        entry = _canonical_entry(slug="with-quarantine")
        _seed_dir_only_project(tmp_path, [entry])
        config = json.loads((tmp_path / RUN_CONFIG_NAME).read_text())
        config["_iterate_migration_quarantined_count"] = 3
        config["_iterate_migration_quarantine_report"] = (
            "agent_docs/iterates/_quarantine/invalid-legacy-20260423.json"
        )
        (tmp_path / RUN_CONFIG_NAME).write_text(json.dumps(config), encoding="utf-8")

        out = generate_handoff(tmp_path, session_id="sess-q", reason="smoke")
        assert "Migration Quarantine" in out
        assert "3 legacy iterate entries" in out

    def test_quarantine_warning_absent_when_count_zero(self, tmp_path):
        entry = _canonical_entry(slug="clean")
        _seed_dir_only_project(tmp_path, [entry])
        out = generate_handoff(tmp_path, session_id="sess-clean", reason="smoke")
        assert "Migration Quarantine" not in out
