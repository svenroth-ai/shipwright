"""``record_review_pass.py show`` survives a console that is not UTF-8.

``show`` prints with ``ensure_ascii=False``; on Windows the default cp1252 stdout
raised ``UnicodeEncodeError`` on the first ``→`` in a stored disposition.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _review_cli_harness import RUN_ID, TOOL, make_project, run_tool  # noqa: E402


@pytest.mark.covers("FR-01.11")
def test_show_prints_non_ascii_on_a_cp1252_console(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    rc, out = run_tool(
        project, "record", "--review-type", "doubt", "--status", "not_applicable",
        "--reason-code", "diff-below-threshold",
        "--disposition", "Stage 3 skipped → diff below the threshold — see the rule",
    )
    assert rc == 0, out
    result = subprocess.run(
        [sys.executable, TOOL, "show", "--project-root", str(project), "--run-id", RUN_ID],
        capture_output=True, env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    shown = json.loads(result.stdout.decode("utf-8"))
    assert "→" in shown["reviews"]["doubt"]["disposition"]
