"""Layer 4: drift detector tests.

Covers ``shared/scripts/lib/stale_artifact_detector.py``: the streaming
scan, the warn-vs-block severity split, the report write/clear self-heal,
and the SessionStart hook entry behavior. SessionStart cannot block, so
both severities are warn-only — block (``migrated``) findings reach the
model via a schema-valid ``additionalContext`` payload on stdout (exit 0),
warn (``in_progress``) findings via a stderr notice (exit 0).
"""
from __future__ import annotations

import json

import pytest

from lib import stale_artifact_detector as sad


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _migration_in_progress() -> dict:
    return {
        "name": "planning",
        "canonical": ".shipwright/planning",
        "legacy_dirname": "planning",
        "old_path_patterns": [],
        "ast_check_string": "planning",
        "status": "in_progress",
    }


def _migration_migrated() -> dict:
    m = _migration_in_progress()
    m["status"] = "migrated"
    return m


@pytest.fixture
def with_in_progress(monkeypatch):
    monkeypatch.setattr(sad, "active_migrations", lambda: [_migration_in_progress()])


@pytest.fixture
def with_migrated(monkeypatch):
    monkeypatch.setattr(sad, "active_migrations", lambda: [_migration_migrated()])


# ---------------------------------------------------------------------------
# scan_for_stale_legacy_dirs
# ---------------------------------------------------------------------------


def test_scan_returns_empty_when_only_canonical_exists(tmp_path, with_in_progress):
    canonical = tmp_path / ".shipwright" / "planning"
    canonical.mkdir(parents=True)
    (canonical / "spec.md").write_text("hello", encoding="utf-8")
    assert sad.scan_for_stale_legacy_dirs(tmp_path) == []


def test_scan_returns_empty_when_neither_exists(tmp_path, with_in_progress):
    assert sad.scan_for_stale_legacy_dirs(tmp_path) == []


def test_scan_returns_finding_when_only_legacy_exists(tmp_path, with_in_progress):
    legacy = tmp_path / "planning"
    legacy.mkdir()
    (legacy / "spec.md").write_text("legacy content", encoding="utf-8")

    findings = sad.scan_for_stale_legacy_dirs(tmp_path)
    assert len(findings) == 1
    f = findings[0]
    assert f["name"] == "planning"
    assert f["status"] == "in_progress"
    assert f["severity"] == "warn"
    assert f["canonical_exists"] is False
    assert f["sample_count"] == 1
    assert "planning" in f["legacy_path"]


def test_scan_returns_finding_when_both_exist(tmp_path, with_in_progress):
    """Most important case: user manually migrated but didn't delete legacy."""
    legacy = tmp_path / "planning"
    legacy.mkdir()
    (legacy / "spec.md").write_text("stale", encoding="utf-8")
    canonical = tmp_path / ".shipwright" / "planning"
    canonical.mkdir(parents=True)
    (canonical / "spec.md").write_text("fresh", encoding="utf-8")

    findings = sad.scan_for_stale_legacy_dirs(tmp_path)
    assert len(findings) == 1
    assert findings[0]["canonical_exists"] is True
    assert findings[0]["sample_count"] == 1


def test_scan_severity_block_when_migrated(tmp_path, with_migrated):
    legacy = tmp_path / "planning"
    legacy.mkdir()
    (legacy / "spec.md").write_text("x", encoding="utf-8")
    findings = sad.scan_for_stale_legacy_dirs(tmp_path)
    assert findings[0]["severity"] == "block"


def test_scan_skips_empty_legacy_dir(tmp_path, with_in_progress):
    """Empty top-level dir at legacy path is NOT a drift signal."""
    (tmp_path / "planning").mkdir()
    assert sad.scan_for_stale_legacy_dirs(tmp_path) == []


def test_scan_streaming_caps_at_sample_cap(tmp_path, with_in_progress, monkeypatch):
    monkeypatch.setattr(sad, "SAMPLE_CAP", 5)
    legacy = tmp_path / "planning"
    legacy.mkdir()
    for i in range(20):
        (legacy / f"file_{i}.md").write_text("x", encoding="utf-8")
    findings = sad.scan_for_stale_legacy_dirs(tmp_path)
    assert findings[0]["sample_count"] == 5  # cap reached


def test_scan_skips_pending_status(tmp_path, monkeypatch):
    pending = _migration_in_progress()
    pending["status"] = "pending"
    monkeypatch.setattr(sad, "active_migrations", lambda: [])  # active filter excludes
    legacy = tmp_path / "planning"
    legacy.mkdir()
    (legacy / "spec.md").write_text("x", encoding="utf-8")
    assert sad.scan_for_stale_legacy_dirs(tmp_path) == []


# ---------------------------------------------------------------------------
# write_drift_report_or_clear
# ---------------------------------------------------------------------------


def test_write_drift_report_writes_when_findings(tmp_path):
    findings = [{
        "name": "planning",
        "status": "in_progress",
        "legacy_path": str(tmp_path / "planning"),
        "canonical_path": str(tmp_path / ".shipwright" / "planning"),
        "canonical_exists": False,
        "sample_count": 3,
        "severity": "warn",
    }]
    out = sad.write_drift_report_or_clear(tmp_path, findings)
    assert out is not None
    assert out == tmp_path / sad.REPORT_FILENAME
    text = out.read_text(encoding="utf-8")
    assert "planning" in text
    assert "warn" in text
    assert "git mv" in text  # remediation present


def test_write_drift_report_returns_none_on_empty(tmp_path):
    assert sad.write_drift_report_or_clear(tmp_path, []) is None
    assert not (tmp_path / sad.REPORT_FILENAME).exists()


def test_write_drift_report_self_heals_by_deleting(tmp_path):
    """When findings disappear, the report file is removed (not overwritten)."""
    out = tmp_path / sad.REPORT_FILENAME
    out.parent.mkdir(parents=True)
    out.write_text("stale report", encoding="utf-8")
    assert out.exists()

    sad.write_drift_report_or_clear(tmp_path, [])
    assert not out.exists()


def test_write_drift_report_escapes_markdown_chars(tmp_path):
    """GPT-15: filenames with markdown-special chars must not break rendering."""
    findings = [{
        "name": "planning",
        "status": "in_progress",
        "legacy_path": str(tmp_path / "weird[name](path)"),
        "canonical_path": str(tmp_path / ".shipwright" / "planning"),
        "canonical_exists": False,
        "sample_count": 1,
        "severity": "warn",
    }]
    out = sad.write_drift_report_or_clear(tmp_path, findings)
    text = out.read_text(encoding="utf-8")
    # Escaped: backslash before [ and ( and ] and )
    assert r"\[name\]" in text
    assert r"\(path\)" in text


# ---------------------------------------------------------------------------
# hook_main: warn vs block exit codes + JSON output
# ---------------------------------------------------------------------------


def test_hook_main_returns_zero_when_no_findings(tmp_path, with_in_progress, capsys):
    rc = sad.hook_main(tmp_path)
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out == ""  # no JSON on stdout for the no-finding path


def test_hook_main_returns_zero_with_warn_only(tmp_path, with_in_progress, capsys):
    legacy = tmp_path / "planning"
    legacy.mkdir()
    (legacy / "spec.md").write_text("x", encoding="utf-8")

    rc = sad.hook_main(tmp_path)
    assert rc == 0  # warn-only, do not block
    captured = capsys.readouterr()
    assert "drift warning" in captured.err
    assert (tmp_path / sad.REPORT_FILENAME).exists()


def test_hook_main_warns_on_block_severity_via_sessionstart_channel(
    tmp_path, with_migrated, capsys
):
    """SessionStart cannot block a session, so a `migrated` (block) finding is
    delivered honestly as warn-only: a schema-valid SessionStart
    `additionalContext` JSON on stdout (the channel the model reads) + a stderr
    notice + the report, and exit 0 — NOT a fake `exit 1` hard-gate the model
    never sees (WP4 / iterate-2026-06-13-hook-block-channel)."""
    legacy = tmp_path / "planning"
    legacy.mkdir()
    (legacy / "spec.md").write_text("x", encoding="utf-8")

    rc = sad.hook_main(tmp_path)
    assert rc == 0  # warn-only — SessionStart cannot block

    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    # Schema-valid SessionStart envelope so the model actually receives it.
    hso = payload["hookSpecificOutput"]
    assert hso["hookEventName"] == "SessionStart"
    ctx = hso["additionalContext"]
    assert "git mv" in ctx
    # `success`/`error`/`findings` top-level keys are gone (they were never read).
    assert "success" not in payload
    # Human-facing notice still on stderr; report still written.
    assert "drift" in captured.err.lower()
    assert (tmp_path / sad.REPORT_FILENAME).exists()


def test_hook_main_fails_open_on_scan_exception(tmp_path, monkeypatch, capsys):
    """If the scan itself raises, hook still exits 0 (never bricks session)."""
    def _broken_scan(_root):
        raise RuntimeError("simulated filesystem failure")

    monkeypatch.setattr(sad, "scan_for_stale_legacy_dirs", _broken_scan)
    rc = sad.hook_main(tmp_path)
    assert rc == 0
    captured = capsys.readouterr()
    assert "drift detector skipped" in captured.err
    assert "simulated filesystem failure" in captured.err


def test_hook_main_warn_survives_report_write_failure(
    tmp_path, with_migrated, monkeypatch, capsys
):
    """A report-write OSError must NOT suppress the warning: the model still
    receives the additionalContext payload and the hook still exits 0
    (fail-open, WP4)."""
    legacy = tmp_path / "planning"
    legacy.mkdir()
    (legacy / "spec.md").write_text("x", encoding="utf-8")

    def _broken_write(_root, _findings):
        raise OSError("simulated unwritable .shipwright/")

    monkeypatch.setattr(sad, "write_drift_report_or_clear", _broken_write)
    rc = sad.hook_main(tmp_path)
    assert rc == 0  # fail-open

    captured = capsys.readouterr()
    # The write failure is noted on stderr, but the drift warning survives.
    assert "report write failed" in captured.err
    payload = json.loads(captured.out.strip())
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "git mv" in payload["hookSpecificOutput"]["additionalContext"]
