"""Tests for run_scan_and_report.py — local-interactive OSS wrapper.

Covers the unit-level contract:
  - Aikido backend short-circuits cleanly
  - Reports land at securityreports/latest.{md,json}
  - History gets archived as scan-{ts}-{uuid}.{md,json}
  - Pairs (md+json) are pruned together; strict filename pattern; manual
    files in history/ are left alone
  - .gitignore best-effort: appended only when missing; never overwritten
  - scan_id is consistent between md (HTML comment) and json (field)
  - --full-evidence retains raw secret values; default-on redaction strips them
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))

import run_scan_and_report  # noqa: E402

SCAN_FILENAME_RE = re.compile(r"^scan-\d{8}-\d{6}-[0-9a-f]{6}\.(md|json)$")


def _stub_findings() -> list[dict[str, Any]]:
    return [
        {
            "id": "f-01",
            "source": "semgrep",
            "type": "sast",
            "rule": "subprocess-shell-true",
            "severity": "high",
            "affected_file": "scripts/run.py",
            "affected_line": 42,
            "description": "Found shell=True.",
            "_remediation_class": "agent-fixable",
        },
        {
            "id": "f-02",
            "source": "gitleaks",
            "type": "secret_detection",
            "rule": "generic-api-key",
            "severity": "high",
            "affected_file": "tests/fixtures/sample.json",
            "affected_line": 8,
            "description": "Detected sk-live-1234567890abcdef in source.",
            # Raw secret evidence the redactor must strip:
            "match": "sk-live-1234567890abcdef",
            "secret": "sk-live-1234567890abcdef",
            "_remediation_class": "agent-fixable",
        },
    ]


@pytest.fixture
def stub_oss_backend(monkeypatch):
    """Patch get_backend to return an OSS-named mock that returns _stub_findings."""
    backend = MagicMock()
    backend.name = "oss"
    backend.scan.return_value = _stub_findings()
    monkeypatch.setattr(run_scan_and_report, "get_backend", lambda: backend)
    return backend


# ---------------------------------------------------------------------------
# Backend short-circuit
# ---------------------------------------------------------------------------


class TestBackendShortCircuit:

    def test_aikido_backend_short_circuits_with_message(self, monkeypatch, tmp_path: Path, capsys):
        backend = MagicMock()
        backend.name = "aikido"
        monkeypatch.setattr(run_scan_and_report, "get_backend", lambda: backend)

        rc = run_scan_and_report.run(project_root=tmp_path, repo="x/y", full_evidence=False)
        assert rc == 0
        backend.scan.assert_not_called()
        # No reports written
        assert not (tmp_path / "securityreports").exists()


# ---------------------------------------------------------------------------
# Happy path — outputs land in the right places
# ---------------------------------------------------------------------------


class TestHappyPath:

    def test_writes_latest_md_and_latest_json(self, stub_oss_backend, tmp_path: Path):
        rc = run_scan_and_report.run(project_root=tmp_path, repo="test/repo", full_evidence=False)
        assert rc == 0

        latest_md = tmp_path / "securityreports" / "latest.md"
        latest_json = tmp_path / "securityreports" / "latest.json"
        assert latest_md.exists()
        assert latest_json.exists()

    def test_archives_to_history_with_strict_pattern(self, stub_oss_backend, tmp_path: Path):
        rc = run_scan_and_report.run(project_root=tmp_path, repo="test/repo", full_evidence=False)
        assert rc == 0

        history = tmp_path / "securityreports" / "history"
        archived = sorted(p.name for p in history.iterdir())
        assert len(archived) == 2  # one md + one json

        for name in archived:
            assert SCAN_FILENAME_RE.match(name), f"unexpected archived file: {name}"

    def test_scan_id_matches_between_md_and_json(self, stub_oss_backend, tmp_path: Path):
        run_scan_and_report.run(project_root=tmp_path, repo="test/repo", full_evidence=False)

        latest_json_text = (tmp_path / "securityreports" / "latest.json").read_text(encoding="utf-8")
        latest_md_text = (tmp_path / "securityreports" / "latest.md").read_text(encoding="utf-8")

        json_payload = json.loads(latest_json_text)
        scan_id = json_payload["scan_id"]
        assert scan_id, "json must include scan_id"

        # MD carries the same scan_id in an HTML comment so readers can correlate
        # files after a partial-write crash (different scan_ids → mismatch detected).
        assert f"scan_id: {scan_id}" in latest_md_text

    def test_redaction_default_strips_raw_secret_fields(self, stub_oss_backend, tmp_path: Path):
        run_scan_and_report.run(project_root=tmp_path, repo="test/repo", full_evidence=False)

        payload = json.loads((tmp_path / "securityreports" / "latest.json").read_text(encoding="utf-8"))
        for finding in payload["findings"]:
            assert "match" not in finding
            assert "secret" not in finding
            # description prose stripped of the secret value
            if finding.get("description"):
                assert "sk-live-1234567890abcdef" not in finding["description"]

    def test_full_evidence_retains_raw_secret_fields(self, stub_oss_backend, tmp_path: Path):
        run_scan_and_report.run(project_root=tmp_path, repo="test/repo", full_evidence=True)

        payload = json.loads((tmp_path / "securityreports" / "latest.json").read_text(encoding="utf-8"))
        gitleaks_finding = next(f for f in payload["findings"] if f["source"] == "gitleaks")
        assert gitleaks_finding["match"] == "sk-live-1234567890abcdef"

    def test_full_evidence_refused_in_ci(self, stub_oss_backend, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.setenv("CI", "true")
        rc = run_scan_and_report.run(project_root=tmp_path, repo="test/repo", full_evidence=True)
        # Refuses with non-zero exit OR forces redaction; either way the
        # raw secret must NOT appear in the output.
        assert rc != 0 or not (tmp_path / "securityreports" / "latest.json").exists() or (
            "sk-live-1234567890abcdef"
            not in (tmp_path / "securityreports" / "latest.json").read_text(encoding="utf-8")
        )

    def test_atomic_write_no_tmp_files_left_behind(self, stub_oss_backend, tmp_path: Path):
        run_scan_and_report.run(project_root=tmp_path, repo="test/repo", full_evidence=False)
        # tmp/staging files must be cleaned up
        leftovers = list((tmp_path / "securityreports").glob("*.tmp"))
        leftovers += list((tmp_path / "securityreports").glob("*.partial"))
        assert leftovers == []


# ---------------------------------------------------------------------------
# History retention + paired prune
# ---------------------------------------------------------------------------


class TestRetention:

    def test_keeps_at_most_20_pairs_after_many_runs(self, stub_oss_backend, tmp_path: Path):
        # Pre-populate 25 pairs in history/
        history = tmp_path / "securityreports" / "history"
        history.mkdir(parents=True)
        from datetime import datetime, timedelta
        base = datetime(2026, 1, 1, 12, 0, 0)
        for i in range(25):
            ts = (base + timedelta(seconds=i)).strftime("%Y%m%d-%H%M%S")
            stem = f"scan-{ts}-{i:06x}"
            (history / f"{stem}.md").write_text("md", encoding="utf-8")
            (history / f"{stem}.json").write_text("{}", encoding="utf-8")

        # Run once more; retention should prune to 20 pairs
        run_scan_and_report.run(project_root=tmp_path, repo="x", full_evidence=False)

        archived = list(history.iterdir())
        # 20 newest pairs = 40 files (plus the new run we just added)
        # The new run ADDS one pair, prune is to 20 most recent total.
        # So expected: exactly 40 files (20 pairs).
        assert len(archived) == 40

    def test_prune_deletes_pairs_atomically_md_and_json_together(
        self, stub_oss_backend, tmp_path: Path,
    ):
        history = tmp_path / "securityreports" / "history"
        history.mkdir(parents=True)
        # Populate 22 pairs, prune to 20 → 2 pairs deleted
        from datetime import datetime, timedelta
        base = datetime(2026, 1, 1, 12, 0, 0)
        for i in range(22):
            ts = (base + timedelta(seconds=i)).strftime("%Y%m%d-%H%M%S")
            stem = f"scan-{ts}-{i:06x}"
            (history / f"{stem}.md").write_text("md", encoding="utf-8")
            (history / f"{stem}.json").write_text("{}", encoding="utf-8")

        run_scan_and_report.run(project_root=tmp_path, repo="x", full_evidence=False)

        # Every remaining stem must have BOTH .md and .json (no orphaned siblings)
        stems_md = {p.stem for p in history.glob("*.md")}
        stems_json = {p.stem for p in history.glob("*.json")}
        assert stems_md == stems_json

    def test_prune_ignores_files_that_dont_match_strict_pattern(
        self, stub_oss_backend, tmp_path: Path,
    ):
        history = tmp_path / "securityreports" / "history"
        history.mkdir(parents=True)
        # User-added or out-of-pattern files: must not be deleted
        (history / "user-notes.md").write_text("notes", encoding="utf-8")
        (history / "manual-export.json").write_text("{}", encoding="utf-8")
        (history / "scan-2026-04-23.md").write_text("legacy without seconds", encoding="utf-8")

        run_scan_and_report.run(project_root=tmp_path, repo="x", full_evidence=False)

        assert (history / "user-notes.md").exists()
        assert (history / "manual-export.json").exists()
        assert (history / "scan-2026-04-23.md").exists()


# ---------------------------------------------------------------------------
# .gitignore best-effort
# ---------------------------------------------------------------------------


class TestGitignoreBestEffort:

    def test_appends_entry_when_gitignore_exists_without_it(
        self, stub_oss_backend, tmp_path: Path,
    ):
        gi = tmp_path / ".gitignore"
        gi.write_text("node_modules/\n.venv/\n", encoding="utf-8")

        run_scan_and_report.run(project_root=tmp_path, repo="x", full_evidence=False)
        content = gi.read_text(encoding="utf-8")
        assert "/securityreports/" in content
        # Existing entries preserved
        assert "node_modules/" in content
        assert ".venv/" in content

    def test_does_not_duplicate_when_entry_already_present(
        self, stub_oss_backend, tmp_path: Path,
    ):
        gi = tmp_path / ".gitignore"
        gi.write_text("node_modules/\n/securityreports/\n", encoding="utf-8")

        run_scan_and_report.run(project_root=tmp_path, repo="x", full_evidence=False)
        content = gi.read_text(encoding="utf-8")
        assert content.count("/securityreports/") == 1

    def test_does_not_create_gitignore_when_absent(
        self, stub_oss_backend, tmp_path: Path,
    ):
        # No .gitignore exists in tmp_path
        assert not (tmp_path / ".gitignore").exists()

        run_scan_and_report.run(project_root=tmp_path, repo="x", full_evidence=False)
        # We don't materialize a .gitignore in projects that didn't have one
        assert not (tmp_path / ".gitignore").exists()

    def test_handles_gitignore_without_trailing_newline(
        self, stub_oss_backend, tmp_path: Path,
    ):
        gi = tmp_path / ".gitignore"
        gi.write_text("node_modules/", encoding="utf-8")  # no trailing \n

        run_scan_and_report.run(project_root=tmp_path, repo="x", full_evidence=False)
        content = gi.read_text(encoding="utf-8")
        # Entry on its own line — no merge with the previous line
        assert "node_modules//securityreports/" not in content
        assert "/securityreports/" in content
