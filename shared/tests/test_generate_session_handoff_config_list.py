"""The handoff's config list reads the resolver's path table (campaign root-files-into-config R1a, AC7)."""

from pathlib import Path

import pytest

from lib import shipwright_paths as sp
from lib.config import CONFIG_FILES
from tools.generate_session_handoff import generate_handoff


@pytest.mark.covers("FR-01.11")
def test_config_list_names_each_file_by_its_repo_relative_path(tmp_project):
    """R1a (BRIEF 12.7c): the list is read from the resolver's table, so it follows a moved file. The
    expected lines are the literal pre-move names: today's output must not change by one byte."""
    (tmp_project / "shipwright_run_config.json").write_text('{"status": "complete"}', encoding="utf-8")
    content = generate_handoff(tmp_project, session_id="s")
    section = content.split("## Config Files to Read\n\n", 1)[1].split("\n\n", 1)[0].splitlines()
    names = ["run", "project", "plan", "build", "security", "compliance"]
    assert section == [f"- `shipwright_{n}_config.json` — {'exists' if n == 'run' else 'missing'}" for n in names]


@pytest.mark.covers("FR-01.11")
def test_config_list_equals_the_pre_r1a_expression_for_every_skill():
    """Oracle for AC7's byte-identity: the expression the handoff used before R1a."""
    for skill in (s for s in CONFIG_FILES if s != "events"):
        old = (sp.json_path_or_none(skill + "_config", "") or Path(skill)).name
        assert CONFIG_FILES[skill] == old, skill
