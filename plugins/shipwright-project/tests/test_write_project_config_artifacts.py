"""Pin `write-project-config.py`'s `artifacts` dict against doc/code drift.

Code-review cascade (R4, iterate-2026-09-23-m5-agents-md-generation-drift)
found a fresh drift this same diff introduced: `project-scaffolding.md`'s
illustrative Config Output example gained `"agents_md": true`, but the real
script that writes `shipwright_project_config.json` did not — the doc example
an agent reads no longer matched what actually lands on disk. This pins the
real output so a future doc-only edit can't reopen that gap unnoticed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "checks" / "write-project-config.py"
)


def test_artifacts_dict_reports_agents_md(tmp_path: Path) -> None:
    project_root = tmp_path
    planning_dir = project_root / ".shipwright" / "planning"
    planning_dir.mkdir(parents=True)
    (project_root / "CLAUDE.md").write_text("# Demo\n", encoding="utf-8")
    (project_root / "AGENTS.md").write_text("# Demo\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--planning-dir", str(planning_dir),
            "--profile", "vite-hono",
            "--scope", "full_app",
            "--project-root", str(project_root),
        ],
        capture_output=True, text=True, check=True,
    )
    config = json.loads(result.stdout)
    assert config["artifacts"]["claude_md"] is True
    assert config["artifacts"]["agents_md"] is True

    on_disk = json.loads(
        (project_root / "shipwright_project_config.json").read_text(encoding="utf-8"),
    )
    assert on_disk["artifacts"]["agents_md"] is True


def test_artifacts_dict_reports_agents_md_absent(tmp_path: Path) -> None:
    project_root = tmp_path
    planning_dir = project_root / ".shipwright" / "planning"
    planning_dir.mkdir(parents=True)

    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--planning-dir", str(planning_dir),
            "--profile", "vite-hono",
            "--scope", "full_app",
            "--project-root", str(project_root),
        ],
        capture_output=True, text=True, check=True,
    )
    config = json.loads(result.stdout)
    assert config["artifacts"]["claude_md"] is False
    assert config["artifacts"]["agents_md"] is False
