"""Project profiles must be committable (D10, S1 items 15-16).

Tagged to FR-01.06; see test_profile_resolver.py for the FR note.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from lib.gitignore_canon import extract_marked_rules, read_canonical_rules

pytestmark = pytest.mark.covers("FR-01.06")
_REPO = Path(__file__).resolve().parents[2]
_TEMPLATE = _REPO / "shared" / "templates" / "shipwright-gitignore.template"
_NEGATION = "!/.shipwright/profiles/"


def test_template_and_repo_block_both_carry_the_negation_after_the_wildcard():
    tpl = read_canonical_rules(_TEMPLATE)
    repo = extract_marked_rules((_REPO / ".gitignore").read_text(encoding="utf-8"))
    for rules in (tpl, repo):
        assert _NEGATION in rules
        assert rules.index("/.shipwright/*") < rules.index(_NEGATION)
    assert tpl == repo


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_rendered_template_in_scratch_repo_shows_profile_without_force(tmp_path):
    def git(*args):
        return subprocess.run(["git", "-C", str(tmp_path), *args], capture_output=True,
                              text=True, check=False)
    assert git("init", "-q").returncode == 0
    # The RENDERED template, not the monorepo's own .gitignore.
    (tmp_path / ".gitignore").write_text(_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    profile = tmp_path / ".shipwright" / "profiles" / "x.json"
    profile.parent.mkdir(parents=True)
    profile.write_text('{"name": "x"}', encoding="utf-8")
    (tmp_path / ".shipwright" / "scratch.txt").write_text("transient", encoding="utf-8")
    status = git("status", "--porcelain", "-uall").stdout
    assert ".shipwright/profiles/x.json" in status
    assert "scratch.txt" not in status  # the wildcard still hides everything else
    assert git("add", ".shipwright/profiles/x.json").returncode == 0  # no -f needed
    assert git("check-ignore", "-q", ".shipwright/profiles/x.json").returncode == 1


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_profile_temp_files_stay_ignored(tmp_path):
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    (tmp_path / ".gitignore").write_text(_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    d = tmp_path / ".shipwright" / "profiles"
    d.mkdir(parents=True)
    (d / "x.json").write_text("{}", encoding="utf-8")
    (d / "x.json.tmp").write_text("{", encoding="utf-8")
    status = subprocess.run(["git", "-C", str(tmp_path), "status", "--porcelain", "-uall"],
                            capture_output=True, text=True, check=False).stdout
    assert "profiles/x.json" in status and "x.json.tmp" not in status
