"""The detective audit records its own run — end to end, through the CLI.

Nothing schedules this audit, so it is the only thing that can say it ran.
These tests drive the real ``run_audit.py`` process (not the helper) so the
wiring itself is covered: if the recording call is dropped from the CLI, the
evidence documents silently go back to saying "never run" forever.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.lib.audit_disclosure import CONFIG_FILE, LAST_AUDIT_KEY

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
RUN_AUDIT = PLUGIN_ROOT / "scripts" / "audit" / "run_audit.py"


@pytest.fixture
def audited_project(tmp_path: Path) -> Path:
    (tmp_path / "shipwright_run_config.json").write_text(
        '{"status": "in_progress"}\n', encoding="utf-8",
    )
    return tmp_path


def _run(project_root: Path, *extra: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(RUN_AUDIT), "--project-root", str(project_root),
         *extra],
        capture_output=True, text=True, encoding="utf-8",
    )
    # 0 on all-pass, 1 on any-fail — both mean the audit ran.
    assert result.returncode in (0, 1), result.stderr
    return json.loads(result.stdout)


def _recorded(project_root: Path) -> dict:
    doc = json.loads((project_root / CONFIG_FILE).read_text(encoding="utf-8"))
    return doc[LAST_AUDIT_KEY]


def test_a_full_run_is_recorded_in_tracked_state(audited_project: Path):
    payload = _run(audited_project)
    assert payload["last_audit_recorded"]["recorded"] is True

    block = _recorded(audited_project)
    assert block["scope"] == "full"
    assert block["ran_at"]
    assert block["verdict"] == ("fail" if payload["any_fail"] else "pass")
    assert block["checks"]["total"] == len(payload["findings"])


def test_a_partial_run_is_recorded_as_partial(audited_project: Path):
    """``--only`` must never be readable as a full cross-check."""
    _run(audited_project, "--only", "A")
    assert _recorded(audited_project)["scope"] == "A"


def test_recording_does_not_disturb_an_existing_config(audited_project: Path):
    (audited_project / CONFIG_FILE).write_text(
        json.dumps({"enforcement": {"rtm_coverage_min": 0.7}}, indent=2) + "\n",
        encoding="utf-8",
    )
    _run(audited_project)

    doc = json.loads((audited_project / CONFIG_FILE).read_text(encoding="utf-8"))
    assert doc["enforcement"] == {"rtm_coverage_min": 0.7}
    assert doc[LAST_AUDIT_KEY]["ran_at"]
