"""phase_boundary_baseline.path_unchanged: a manifest edited in the phase cannot authorise its own install."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from lib import phase_boundary_baseline as pbb

pytestmark = pytest.mark.covers("FR-01.05/AC05")

REL = pbb.BUILD_BASELINE_REL


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@example.com", "-c", "user.name=t",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "run-a")
    _git(tmp_path, "init", "-q")
    (tmp_path / "package.json").write_text('{"devDependencies": {"vitest": "1"}}\n', encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_no_usable_baseline_cannot_tell(repo, monkeypatch):
    assert pbb.path_unchanged(repo, REL, "01-a", "package.json") is None
    assert pbb.record(repo, REL, "01-a") == "written"
    assert pbb.path_unchanged(repo, REL, "02-b", "package.json") is None  # another section
    assert pbb.path_unchanged(repo, REL, "01-a", "src/app.ts") is None  # not a watched file
    sub = repo / "sub"
    (sub / ".shipwright").mkdir(parents=True)
    (sub / pbb.baseline_path(REL, "01-a")).write_bytes((repo / pbb.baseline_path(REL, "01-a")).read_bytes())
    assert pbb.path_unchanged(sub, REL, "01-a", "package.json") is None  # not the repo root
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "run-b")
    assert pbb.path_unchanged(repo, REL, "01-a", "package.json") is None  # another run, setup not re-run


def test_a_baseline_without_manifest_fingerprints_cannot_tell(repo):
    assert pbb.record(repo, REL, "01-a") == "written"
    path = repo / pbb.baseline_path(REL, "01-a")
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["manifests"]  # written before manifest fingerprints existed
    path.write_text(json.dumps(data), encoding="utf-8")
    assert pbb.path_unchanged(repo, REL, "01-a", "package.json") is None


def test_a_clean_manifest_counts_until_edited_or_committed(repo):
    assert pbb.record(repo, REL, "01-a") == "written"
    assert pbb.path_unchanged(repo, REL, "01-a", "package.json") is True
    (repo / "package.json").write_text('{"devDependencies": {"left-pad": "1"}}\n', encoding="utf-8")
    assert pbb.path_unchanged(repo, REL, "01-a", "package.json") is False
    _git(repo, "commit", "-q", "-am", "add left-pad")  # committing the edit does not launder it
    assert pbb.record(repo, REL, "01-a") == "written"  # HEAD moved: fingerprints carried forward
    assert pbb.path_unchanged(repo, REL, "01-a", "package.json") is False
    assert pbb.path_unchanged(repo, REL, "01-a", "pyproject.toml") is True


def test_a_resume_in_a_new_session_cannot_rebaseline_an_edited_manifest(repo, monkeypatch):
    assert pbb.record(repo, REL, "01-a") == "written"
    (repo / ".npmrc").write_text("registry=https://evil.example/\n", encoding="utf-8")
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "run-b")  # context pressure: the section resumes fresh
    assert pbb.record(repo, REL, "01-a") == "written"
    assert pbb.path_unchanged(repo, REL, "01-a", ".npmrc") is False
    assert pbb.path_unchanged(repo, REL, "01-a", "package.json") is True


def test_a_manifest_dirty_at_the_start_compares_its_content(repo):
    (repo / "package.json").write_text('{"devDependencies": {"vitest": "2"}}\n', encoding="utf-8")
    assert pbb.record(repo, REL, "01-a") == "written"
    assert pbb.path_unchanged(repo, REL, "01-a", "package.json") is True
    (repo / "package.json").write_text('{"devDependencies": {"evil": "1"}}\n', encoding="utf-8")
    assert pbb.path_unchanged(repo, REL, "01-a", "package.json") is False


def test_crlf_bytes_compare_as_bytes_under_autocrlf(repo):
    _git(repo, "config", "core.autocrlf", "true")
    (repo / "package.json").write_bytes(b'{"devDependencies": {"vitest": "1"}}\r\n')  # a CRLF checkout of the LF blob
    assert pbb.record(repo, REL, "01-a") == "written"
    assert pbb.path_unchanged(repo, REL, "01-a", "package.json") is True  # no git filter, no false change


def test_the_boundary_gate_sees_only_this_sessions_changes(repo, monkeypatch):
    (repo / "earlier.md").write_text("left by an earlier phase\n", encoding="utf-8")
    assert pbb.record(repo, REL, "01-a") == "written"
    assert pbb.record(repo, REL, "01-a") == "kept"  # same run, same commit: never re-snapshotted
    (repo / "mine.ts").write_text("x\n", encoding="utf-8")
    changed = pbb.session_changes(repo, REL, "01-a")
    assert "mine.ts" in changed and "earlier.md" not in changed
    (repo / "earlier.md").write_text("edited by this session\n", encoding="utf-8")
    assert "earlier.md" in pbb.session_changes(repo, REL, "01-a")
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "run-b")  # another run's baseline is never trusted
    assert {"mine.ts", "earlier.md"} <= set(pbb.session_changes(repo, REL, "01-a"))


def test_absent_then_and_now_is_unchanged_and_a_new_manifest_is_not(repo):
    assert pbb.record(repo, REL, "01-a") == "written"
    assert pbb.path_unchanged(repo, REL, "01-a", "uv.lock") is True
    (repo / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    assert pbb.path_unchanged(repo, REL, "01-a", "uv.lock") is False
    (repo / "package.json").unlink()
    assert pbb.path_unchanged(repo, REL, "01-a", "package.json") is False
