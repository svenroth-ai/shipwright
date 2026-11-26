"""P8b fix round 1, on real git: Q8 compares with the last release tag on THIS branch (D100), a re-run of a finished
section takes no newer hand-written entry, and the PR body is ``## Changelog``, a blank line, then the section."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import release
from lib import release_aggregate
from lib.release_runner import CmdResult, Recorder, subprocess_runner

from .test_release_cli import SETUP, ok_runner, run_prepare
from .test_release_event_real_git import git

pytestmark = pytest.mark.covers("FR-01.09/AC01", "FR-01.09/AC04")
PLUGIN = Path(__file__).resolve().parents[1]
SECTION = "## [1.3.0] - 2026-11-25\n\n### Added\n\n- A new capability"
DONE = f"# Changelog\n\n## [Unreleased]\n\n{SECTION}\n\n## [1.2.0] - 2026-01-15\n\n- Old\n"


@pytest.fixture
def work(tmp_path, monkeypatch):
    config = tmp_path / "gitconfig"
    config.write_text("[user]\n\tname = t\n\temail = t@example.com\n[commit]\n\tgpgsign = false\n[init]\n\tdefaultBranch = main\n"
                      "[tag]\n\tgpgsign = false\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    root = tmp_path / "work"
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    git(root, "add", "CHANGELOG.md")
    git(root, "commit", "-q", "-m", "init")
    return root


def _commit(root: Path, tag: str) -> None:
    git(root, "commit", "-q", "--allow-empty", "-m", tag)
    git(root, "tag", "-a", tag, "-m", tag)


def _prepare_on(root: Path, plugin_root: Path, version: str):
    """``prepare`` with the real git tag lookups and a setup script that reports the repo-wide highest tag (v2.0.0)."""
    fake = ok_runner(setup={"stdout": json.dumps({**SETUP, "last_tag": "v2.0.0", "branch": "1.x"})})

    def runner(key, argv, cwd, **opts):
        return subprocess_runner(key, argv, cwd, **opts) if key in ("tags-merged", "tag-check") else fake(key, argv, cwd, **opts)
    return run_prepare(root, plugin_root, runner, version=version)


def test_a_backport_on_a_maintenance_branch_passes_while_a_newer_tag_lives_on_another_branch(work, plugin_root):
    _commit(work, "v1.4.0")
    git(work, "branch", "1.x")
    _commit(work, "v2.0.0")  # main moves on to 2.0.0
    git(work, "checkout", "-q", "1.x")
    code, out = _prepare_on(work, plugin_root, "1.4.1")
    assert (code, out["status"], out["version"]) == (0, "ok", "1.4.1")
    for low in ("1.4.0", "1.3.9"):
        code, out = _prepare_on(work, plugin_root, low)
        assert (code, out["reason"], out["release_tag"]) == (2, "version_not_above_last_tag", "v1.4.0")
        assert "last release tag on this branch, v1.4.0" in out["message"]


def test_a_pre_release_tag_on_the_branch_is_not_compared(work, plugin_root):
    _commit(work, "v1.4.0")
    _commit(work, "v1.5.0-rc.1")
    code, out = _prepare_on(work, plugin_root, "1.4.1")
    assert (code, out["version"]) == (0, "1.4.1")


def test_a_rerun_of_a_finished_section_takes_no_newer_hand_written_entry_and_converges(work, plugin_root):
    text = DONE.replace("## [Unreleased]\n", "## [Unreleased]\n\n### Fixed\n\n- Written by hand after the release\n")
    (work / "CHANGELOG.md").write_text(text, encoding="utf-8")
    calls: list[list[str]] = []

    def runner(key, argv, cwd, **opts):
        calls.append(list(argv))
        if key == "tag-check":
            return CmdResult(key, tuple(argv), 0, "", "")
        return subprocess_runner(key, argv, cwd, **opts)
    code, out = release_aggregate.aggregate(Recorder(runner, work), plugin_root, version="1.3.0", release_date="2026-11-25")
    assert "--move-unreleased" not in next(a for a in calls if any(x.endswith("aggregate_changelog.py") for x in a))
    assert (work / "CHANGELOG.md").read_text(encoding="utf-8") == text  # the new entry stays in [Unreleased]
    assert out.get("hand_written", []) == []


def test_the_pr_body_through_the_cli_is_the_header_a_blank_line_and_the_section(work, capsys):
    (work / "CHANGELOG.md").write_text(DONE, encoding="utf-8")
    assert release.main(["pr-body", "--project-root", str(work), "--version", "1.3.0"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert Path(out["body_file"]).read_text(encoding="utf-8") == "## Changelog\n\n" + SECTION + "\n"
