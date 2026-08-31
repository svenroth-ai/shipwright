"""``update_compliance.py``'s generator-error diagnostic must reach the caller's log.

On a generator-error exit, ``update_compliance.py`` writes
``{"success": false, "generator_errors": [...]}`` to STDOUT and leaves stderr
EMPTY — the failure is a caught exception turned into structured JSON, never a
traceback. ``_update_compliance`` used to look only at ``result.stderr`` on a
non-zero exit, so this diagnostic was silently discarded: the operator saw an
empty ``[finalize_iterate] compliance failed: `` line with no clue what broke
(surfaced during doubt-review of iterate-2026-08-29-compliance-interpreter-fix).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from tools import finalize_iterate  # noqa: E402


def test_generator_error_detail_from_stdout_reaches_stderr_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
):
    payload = {
        "success": False,
        "phase": "iterate",
        "updated_reports": ["change-history.md"],
        "generator_errors": [
            {"report": "test_links", "error": "DuplicateRequirementId",
             "detail": "FR-03.01 declared in two ACTIVE specs"},
        ],
    }

    class _Result:
        returncode = 1
        stdout = json.dumps(payload)
        stderr = ""  # the real bug: update_compliance.py writes nothing here

    monkeypatch.setattr(finalize_iterate.subprocess, "run", lambda *a, **k: _Result())

    result = finalize_iterate._update_compliance(tmp_path, "some-run-id")

    assert result == []
    captured = capsys.readouterr()
    assert "DuplicateRequirementId" in captured.err
    assert "FR-03.01" in captured.err


def test_non_json_stderr_failure_still_surfaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
):
    """A failure that never produces JSON on stdout (missing script, uv error,
    a bare traceback) must keep falling back to stderr — the fix must not
    swallow this other failure class."""

    class _Result:
        returncode = 1
        stdout = ""
        stderr = "uv: command not found"

    monkeypatch.setattr(finalize_iterate.subprocess, "run", lambda *a, **k: _Result())

    result = finalize_iterate._update_compliance(tmp_path, "some-run-id")

    assert result == []
    captured = capsys.readouterr()
    assert "uv: command not found" in captured.err


@pytest.mark.parametrize("malformed_generator_errors", ["failure", [None], [42]])
def test_malformed_generator_errors_falls_back_to_stderr_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
    malformed_generator_errors,
):
    """A malformed-but-JSON-valid `generator_errors` (not a list of dicts) must
    not raise `AttributeError` from `e.get(...)` — it must fall back to the
    real stderr, same as any other unsupported failure shape (external
    code-review finding, openai/medium)."""
    payload = {"success": False, "generator_errors": malformed_generator_errors}

    class _Result:
        returncode = 1
        stdout = json.dumps(payload)
        stderr = "real stderr text"

    monkeypatch.setattr(finalize_iterate.subprocess, "run", lambda *a, **k: _Result())

    result = finalize_iterate._update_compliance(tmp_path, "some-run-id")

    assert result == []
    captured = capsys.readouterr()
    assert "real stderr text" in captured.err
