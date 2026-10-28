"""FR-01.09 AC04 wiring: the version the skill proposes comes from
`suggest_version_bump` via the setup script, not from the model's own reading
of the commit types (a break before 1.0 raises the second number)."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_PLUGIN = Path(__file__).resolve().parent.parent
_SETUP = _PLUGIN / "scripts" / "checks" / "setup-changelog.py"
_SKILL = _PLUGIN / "skills" / "changelog" / "SKILL.md"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t",
         "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
        cwd=repo, check=True, capture_output=True,
    )


def _repo(tmp_path: Path, tag: str, message: str) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "commit", "--allow-empty", "-q", "-m", "chore: base")
    _git(tmp_path, "tag", tag)
    _git(tmp_path, "commit", "--allow-empty", "-q", "-m", message)


def _setup_output(tmp_path: Path, tag: str, message: str) -> dict:
    _repo(tmp_path, tag, message)
    result = subprocess.run(
        [sys.executable, str(_SETUP), "--plugin-root", str(_PLUGIN)],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.covers("FR-01.09/AC04")
def test_setup_breaking_change_before_1_0_raises_second_number(tmp_path: Path):
    out = _setup_output(tmp_path, "v0.2.0", "feat!: drop the old flag")
    assert out["suggested_version"] == "0.3.0"


@pytest.mark.covers("FR-01.09/AC04")
def test_setup_breaking_change_from_1_0_raises_first_number(tmp_path: Path):
    out = _setup_output(tmp_path, "v1.4.2", "feat!: drop the old flag")
    assert out["suggested_version"] == "2.0.0"


@pytest.mark.covers("FR-01.09/AC04")
def test_setup_main_in_process_reports_suggestion(tmp_path: Path, monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("setup_changelog_ac04", _SETUP)
    module = importlib.util.module_from_spec(spec)
    sys.modules["setup_changelog_ac04"] = module
    spec.loader.exec_module(module)
    _repo(tmp_path, "v0.2.0", "feat!: drop the old flag")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["setup-changelog.py", "--plugin-root", str(_PLUGIN)])
    assert module.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["suggested_version"], out["version_reason"]) == ("0.3.0", "breaking change (pre-1.0)")


@pytest.mark.covers("FR-01.09/AC04")
def test_skill_step_3_uses_the_suggestion_not_its_own_rule():
    text = _SKILL.read_text(encoding="utf-8")
    step3 = text[text.index("## Step 3: Determine Version Bump"):text.index("## Step 4:")]
    assert "suggested_version" in step3
    assert "verbatim" in step3
    assert not re.search(r"breaking.{0,40}major", step3, re.IGNORECASE)
