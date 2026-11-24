"""``changelog_checks.check_release_tag``: the public entry the changelog plugin's ``verify_release_tag.py`` calls (unit P5).

The plugin script used to import two ``_`` helpers of this module; the boundary is now one public function, proven here on a
real repository (the plugin side proves the script and the source scan in ``tests/test_release_p5.py``).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.verifiers import changelog_checks
from tools.verifiers.changelog_checks import check_release_tag

pytestmark = pytest.mark.covers("FR-01.09/AC01")


def _repo(tmp_path: Path, heading: str, tag: str | None) -> Path:
    (tmp_path / "CHANGELOG.md").write_text(f"# Changelog\n\n## [{heading}] - 2026-01-01\n\n- x\n", encoding="utf-8")
    for cmd in (["init", "-b", "main"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "--allow-empty", "-m", "x"],
                *([["tag", tag]] if tag else [])):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def test_a_tag_that_exists_and_a_changelog_that_names_the_release_pass(tmp_path):
    out = check_release_tag(_repo(tmp_path, "v1.2.3", "v1.2.3"), "1.2.3")
    assert out["ok"] is True and set(out["checks"]) == {"tag_exists", "changelog_names_release"}
    assert out["advisory"]["changelog_matches_latest_tag"]["ok"] is True


def test_a_missing_tag_or_a_changelog_naming_another_version_fails_by_name(tmp_path):
    out = check_release_tag(_repo(tmp_path, "v1.2.3", None), "1.2.3")
    assert out["ok"] is False and out["checks"]["tag_exists"]["ok"] is False and out["checks"]["changelog_names_release"]["ok"] is True
    out = check_release_tag(tmp_path, "9.9.9")
    assert out["ok"] is False and out["checks"]["changelog_names_release"]["ok"] is False


def test_the_entry_is_public():
    assert "check_release_tag" in changelog_checks.__all__
