"""`.gitignore` handling of run_scan_and_report.py.

The scan ignores ONLY its own output folder (`/.shipwright/securityreports/`),
never the whole `.shipwright/` directory: that holds tracked ADRs, specs and
triage, and ignoring it made `git add -A` silently skip every NEW file there
(GitHub issue #985). Split out of test_run_scan_and_report.py, which is over
the file-size limit and may not grow.

Contract:
  - appended only when missing; never overwritten; no .gitignore => none created
  - legacy `/securityreports/` and the canonical `/.shipwright/*` whitelist
    count as already-present (no double-write)
  - a pre-existing broad `/.shipwright/` is left in place and warned about
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))

import run_scan_and_report  # noqa: E402
import scan_gitignore  # noqa: E402

REPORTS_ENTRY = "/.shipwright/securityreports/"


@pytest.fixture
def stub_oss_backend(monkeypatch):
    """Patch get_backend to an OSS-named mock; findings are irrelevant here."""
    backend = MagicMock()
    backend.name = "oss"
    backend.scan.return_value = []
    monkeypatch.setattr(run_scan_and_report, "get_backend", lambda: backend)
    return backend


def _scan(tmp_path: Path) -> None:
    run_scan_and_report.run(project_root=tmp_path, repo="x", full_evidence=False)


@pytest.mark.covers("FR-01.07/AC12")
class TestGitignoreBestEffort:

    def test_appends_reports_entry_when_gitignore_exists_without_it(
        self, stub_oss_backend, tmp_path: Path,
    ):
        # AC12's actual claim is that the findings "stay in a place that does
        # not travel with the code" — a string appended to .gitignore proves
        # nothing about Git's own behavior. Prove it with Git itself: init a
        # real repo, run the scan, then ask `git check-ignore` whether the
        # exact report path the scan just wrote is actually excluded.
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        gi = tmp_path / ".gitignore"
        gi.write_text("node_modules/\n.venv/\n", encoding="utf-8")

        _scan(tmp_path)
        content = gi.read_text(encoding="utf-8")
        # Only the reports folder is ignored, never the whole `.shipwright/`
        assert REPORTS_ENTRY in content
        assert "/.shipwright/\n" not in content
        # Existing entries preserved
        assert "node_modules/" in content
        assert ".venv/" in content

        report_path = tmp_path / run_scan_and_report.REPORTS_DIR / run_scan_and_report.LATEST_JSON
        assert report_path.exists(), "the scan must have actually written a report to prove against"
        check = subprocess.run(["git", "check-ignore", "-q", str(report_path)], cwd=tmp_path)
        assert check.returncode == 0, (
            "git must actually ignore the written report path, not merely have "
            "an appended .gitignore line that happens to look right"
        )

    def test_new_tracked_files_under_shipwright_are_not_ignored(
        self, stub_oss_backend, tmp_path: Path,
    ):
        # #985: prove with Git itself that a new ADR stays stageable.
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        (tmp_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        adr = tmp_path / ".shipwright" / "planning" / "adr" / "two.md"
        adr.parent.mkdir(parents=True)
        adr.write_text("# ADR\n", encoding="utf-8")

        _scan(tmp_path)

        check = subprocess.run(["git", "check-ignore", "-q", str(adr)], cwd=tmp_path)
        assert check.returncode == 1, "a new ADR under .shipwright/ must stay stageable"

    def test_broad_entry_is_kept_and_warned_about(
        self, stub_oss_backend, tmp_path: Path, capsys,
    ):
        gi = tmp_path / ".gitignore"
        gi.write_text("node_modules/\n/.shipwright/\n", encoding="utf-8")

        _scan(tmp_path)

        # Never deleted or rewritten (the operator may rely on it) ...
        assert gi.read_text(encoding="utf-8") == "node_modules/\n/.shipwright/\n"
        # ... but the operator is told what it costs.
        assert "NOT staged" in capsys.readouterr().err

    def test_broad_entry_next_to_canonical_block_is_still_warned_about(
        self, stub_oss_backend, tmp_path: Path, capsys,
    ):
        # Older versions appended the broad line AFTER the canonical block, so
        # real projects hold both. The wildcard must not mask the warning.
        gi = tmp_path / ".gitignore"
        original = "/.shipwright/*\n!/.shipwright/planning/\n/.shipwright/\n"
        gi.write_text(original, encoding="utf-8")

        _scan(tmp_path)

        assert gi.read_text(encoding="utf-8") == original
        assert "NOT staged" in capsys.readouterr().err

    def test_status_values(self, tmp_path: Path):
        def ensure(root: Path) -> str:
            return scan_gitignore.ensure_gitignore_entry(root, run_scan_and_report.REPORTS_DIR)

        assert ensure(tmp_path) == "skipped"
        gi = tmp_path / ".gitignore"
        gi.write_text("a/\n", encoding="utf-8")
        assert ensure(tmp_path) == "added"
        assert ensure(tmp_path) == "present"
        gi.write_text("/.shipwright/\n", encoding="utf-8")
        assert ensure(tmp_path) == "present_broad"

    def test_canonical_whitelist_wildcard_counts_as_present(
        self, stub_oss_backend, tmp_path: Path,
    ):
        gi = tmp_path / ".gitignore"
        original = "/.shipwright/*\n!/.shipwright/planning/\n"
        gi.write_text(original, encoding="utf-8")

        _scan(tmp_path)
        assert gi.read_text(encoding="utf-8") == original

    def test_does_not_duplicate_when_reports_entry_already_present(
        self, stub_oss_backend, tmp_path: Path,
    ):
        gi = tmp_path / ".gitignore"
        gi.write_text(f"node_modules/\n{REPORTS_ENTRY}\n", encoding="utf-8")

        _scan(tmp_path)
        assert gi.read_text(encoding="utf-8").count(REPORTS_ENTRY) == 1

    def test_does_not_double_write_when_legacy_entry_present(
        self, stub_oss_backend, tmp_path: Path,
    ):
        # Migration-friendly: a project still on the legacy /securityreports/
        # entry counts as "present"; the user cleans it up on their own schedule.
        gi = tmp_path / ".gitignore"
        gi.write_text("node_modules/\n/securityreports/\n", encoding="utf-8")

        _scan(tmp_path)
        content = gi.read_text(encoding="utf-8")
        assert content.count("/securityreports/") == 1
        assert REPORTS_ENTRY not in content

    def test_does_not_create_gitignore_when_absent(
        self, stub_oss_backend, tmp_path: Path,
    ):
        assert not (tmp_path / ".gitignore").exists()

        _scan(tmp_path)
        # We don't materialize a .gitignore in projects that didn't have one
        assert not (tmp_path / ".gitignore").exists()

    def test_handles_gitignore_without_trailing_newline(
        self, stub_oss_backend, tmp_path: Path,
    ):
        gi = tmp_path / ".gitignore"
        gi.write_text("node_modules/", encoding="utf-8")  # no trailing \n

        _scan(tmp_path)
        content = gi.read_text(encoding="utf-8")
        # Entry on its own line — no merge with the previous line
        assert "node_modules/" + REPORTS_ENTRY not in content
        assert "\n" + REPORTS_ENTRY in content
