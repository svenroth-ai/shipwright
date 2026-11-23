"""Real git for what the fix round of unit P4 changed: the F7 check on release tags, and ``release.main`` end to end for ``record-event``."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import release

from .test_release_event_real_git import Tools, git

pytestmark = pytest.mark.covers("FR-01.09/AC01")
SCRIPT = Path(release.__file__).resolve().parent / "checks" / "verify_release_tag.py"
SHARED = Path(__file__).resolve().parents[3] / "shared"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    config = tmp_path / "gitconfig"
    config.write_text("[user]\n\tname = t\n\temail = t@example.com\n[commit]\n\tgpgsign = false\n[init]\n\tdefaultBranch = main\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(remote), str(work)], check=True, capture_output=True)
    (work / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    git(work, "add", "CHANGELOG.md")
    git(work, "commit", "-m", "init")
    git(work, "push", "origin", "main")
    return work, remote


def _release(work: Path, version: str, *, tag: bool = True) -> dict:
    """A CHANGELOG whose top section is ``version``, committed, and (by default) tagged: the state ``commit-and-tag`` checks."""
    (work / "CHANGELOG.md").write_text(f"# Changelog\n\n## [{version}] - 2026-11-23\n\n### Added\n- x\n", encoding="utf-8")
    git(work, "add", "CHANGELOG.md")
    git(work, "commit", "-m", f"chore(release): v{version}")
    if tag:
        git(work, "tag", "-a", f"v{version}", "-m", f"Release v{version}")
    done = subprocess.run([sys.executable, str(SCRIPT), "--shared-root", str(SHARED), "--project-root", str(work), "--version", version],
                          capture_output=True, text=True, encoding="utf-8")
    return {"exit": done.returncode, **json.loads(done.stdout)}


def test_a_final_cut_over_its_own_prerelease_tag_passes_the_tag_check(repo):
    work, _ = repo
    _release(work, "1.4.0-rc.1")
    out = _release(work, "1.4.0")
    assert out["exit"] == 0 and out["ok"] is True and set(out["checks"]) == {"tag_exists", "changelog_names_release"}


def test_a_backport_while_a_newer_tag_exists_passes_the_tag_check(repo):
    work, _ = repo
    _release(work, "1.3.0")
    assert _release(work, "1.2.5")["ok"] is True


def test_an_untagged_release_and_a_changelog_naming_another_release_still_fail(repo):
    work, _ = repo
    assert _release(work, "1.5.0", tag=False)["checks"]["tag_exists"]["ok"] is False
    git(work, "tag", "-a", "v1.6.0", "-m", "x")
    assert _release(work, "1.5.1", tag=False)["ok"] is False  # no v1.5.1 tag
    out = subprocess.run([sys.executable, str(SCRIPT), "--shared-root", str(SHARED), "--project-root", str(work), "--version", "1.6.0"],
                         capture_output=True, text=True, encoding="utf-8")
    assert json.loads(out.stdout)["checks"]["changelog_names_release"]["ok"] is False  # the top section is 1.5.1


def test_record_event_through_release_main_commits_and_pushes_on_real_git(repo, capsys):
    work, remote = repo
    git(work, "checkout", "-b", "release/v1.2.3")
    stub = Tools()

    def runner(key, argv, cwd):  # the two event tools are stubs, everything else (git, argv building, state) is the real thing
        return stub(key, argv, cwd)

    code = release.main(["record-event", "--project-root", str(work), "--version", "1.2.3", "--pr-url", "https://example.test/pr/1"], runner=runner)
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["status"] == "ok" and out["pushed"] is True and out["committed"] == ["shipwright_events.jsonl"]
    assert git(remote, "rev-parse", "release/v1.2.3") == git(work, "rev-parse", "HEAD")
    code = release.main(["record-event", "--project-root", str(work), "--version", "1.2.4"], runner=runner)  # a feature branch needs the PR url
    assert code == 1 and json.loads(capsys.readouterr().out)["reason"] == "pr_url_missing"
