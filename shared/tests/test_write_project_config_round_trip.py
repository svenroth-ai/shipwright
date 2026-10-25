"""Round trip of the project plugin's config writer against its real readers.

``write-project-config.py`` is called by the project skill with only
``--planning-dir <project>/.shipwright/planning``. The file it writes must land where
the readers look (``<project>/shipwright_project_config.json``), or the phase-complete
verifier reports the config missing although the phase finished. Tagged to FR-01.06
(see test_profile_resolver.py for the FR note).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tools.verifiers.project_checks import check_project_config_status_complete

pytestmark = pytest.mark.covers("FR-01.06")

REPO = Path(__file__).resolve().parents[2]
WRITER = REPO / "plugins" / "shipwright-project" / "scripts" / "checks" / "write-project-config.py"


def test_skill_call_writes_where_the_phase_verifier_and_config_reader_look(tmp_path):
    from lib.config import read_config

    planning = tmp_path / ".shipwright" / "planning"
    planning.mkdir(parents=True)
    done = subprocess.run(
        [sys.executable, str(WRITER), "--planning-dir", str(planning), "--profile-root", str(tmp_path),
         "--profile", "vite-hono", "--scope", "full_app"],
        capture_output=True, text=True, check=False,
    )
    assert done.returncode == 0, done.stderr
    assert check_project_config_status_complete(tmp_path).ok is True
    config = read_config("project", tmp_path)
    assert config["status"] == "complete" and config["planning_dir"] == ".shipwright/planning"
    assert not (tmp_path / ".shipwright" / "shipwright_project_config.json").exists()
