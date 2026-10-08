"""Reading the traceability manifest being committed: index, then HEAD, then working tree (U9)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "lib"))
import rtm_gate_support  # noqa: E402
import rtm_manifest_read as rmr  # noqa: E402

if str(Path(__file__).parent) not in sys.path:  # sibling support module; tests/ is no package root
    sys.path.insert(0, str(Path(__file__).parent))
from rtm_hook_test_support import git, init_repo  # noqa: E402
from rtm_hook_test_support import scrub_git_env  # noqa: E402,F401 - autouse

pytestmark = pytest.mark.covers("FR-01.10")

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def test_read_manifest_distinguishes_absent_corrupt_and_ok(tmp_path):
    assert rmr.read_manifest(tmp_path) == (None, None)
    path = tmp_path / rmr.MANIFEST_RELPATH
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    data, problem = rmr.read_manifest(tmp_path)
    assert data is None and "cannot read" in problem
    path.write_text("[]", encoding="utf-8")
    assert rmr.read_manifest(tmp_path)[0] is None
    path.write_text(json.dumps({"requirements": {}}), encoding="utf-8")
    assert rmr.read_manifest(tmp_path) == ({"requirements": {}}, None)


def test_read_manifest_tolerates_utf8_bom_and_crlf(tmp_path):
    """Boundary probe: an editor-saved manifest (BOM / CRLF) must not read as corrupt."""
    path = tmp_path / rmr.MANIFEST_RELPATH
    path.parent.mkdir(parents=True)
    body = json.dumps({"requirements": {}}, indent=1).replace("\n", "\r\n")
    path.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    assert rmr.read_manifest(tmp_path) == ({"requirements": {}}, None)


def test_read_manifest_non_object_and_undecodable(tmp_path):
    path = tmp_path / rmr.MANIFEST_RELPATH
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe{")
    assert "cannot read" in rmr.read_manifest(tmp_path)[1]
    path.write_text("[]", encoding="utf-8")
    assert "not a JSON object" in rmr.read_manifest(tmp_path)[1]


def _working_tree_manifest(tmp_path):
    path = tmp_path / rmr.MANIFEST_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"requirements": {}}), encoding="utf-8")


@pytest.mark.parametrize("error, reason", [
    (FileNotFoundError("git"), "git is not runnable (FileNotFoundError)"),
    (PermissionError("git"), "git is not runnable (PermissionError)"),
    (subprocess.TimeoutExpired("git", 5), "reading the index timed out after 5 s"),
])
def test_a_failed_head_read_says_why_and_warns_on_the_working_tree_read(
        tmp_path, monkeypatch, error, reason):
    def broken(*_a, **_k):
        raise error

    monkeypatch.setattr(rmr.subprocess, "run", broken)
    assert rmr._committed_bytes(tmp_path) == (None, reason)
    # nothing to fall back to, but the unreadable git copy is still announced
    assert rmr.read_manifest_noted(tmp_path) == (
        None, None, [f"committed manifest unreadable: {reason}"])
    # ... and the gate never falls to the legacy RTM section line: WARN + NOT evaluating
    rtm = tmp_path / ".shipwright" / "compliance" / "traceability-matrix.md"
    rtm.parent.mkdir(parents=True)
    rtm.write_text("| Traceability coverage | 5% |\n", encoding="utf-8")
    measurement, warnings = rtm_gate_support.measure(str(tmp_path))
    assert measurement is None and warnings[0] == f"committed manifest unreadable: {reason}"
    assert warnings[-1] == "the 80% commit gate is NOT evaluating"
    _working_tree_manifest(tmp_path)
    data, problem, notes = rmr.read_manifest_noted(tmp_path)
    assert data == {"requirements": {}} and problem is None
    assert notes == [f"reading working-tree manifest: {reason}"]


@pytest.mark.parametrize("stderr, reason, warns", [
    (b"fatal: not a git repository (or any of the parent directories): .git",
     "not a git repo", False),
    (b"fatal: path 'x' does not exist in 'HEAD'", "HEAD has no such file", False),
    (b"fatal: path 'x' exists on disk, but not in 'HEAD'", "HEAD has no such file", False),
    (b"fatal: invalid object name 'HEAD'.", "HEAD has no commit yet", True),
    (b"fatal: something odd", "reading the index failed (fatal: something odd)", True),
    (b"", "reading the index failed (exit 128)", True),
])
def test_git_failure_reasons_are_classified(tmp_path, monkeypatch, stderr, reason, warns):
    monkeypatch.setattr(rmr.subprocess, "run", lambda *_a, **_k: subprocess.CompletedProcess(
        [], 128, stdout=b"", stderr=stderr))
    assert rmr._committed_bytes(tmp_path) == (None, reason)
    _working_tree_manifest(tmp_path)
    assert bool(rmr.read_manifest_noted(tmp_path)[2]) is warns


def _git_by_spec(monkeypatch, index_stderr: bytes, head_stderr: bytes):
    """Fake ``git cat-file``: the index read fails with *index_stderr*, HEAD with *head_stderr*."""
    calls = []

    def fake(args, **_k):
        calls.append(args[-1])
        err = index_stderr if args[-1].startswith(":") else head_stderr
        return subprocess.CompletedProcess(args, 128, stdout=b"", stderr=err)

    monkeypatch.setattr(rmr.subprocess, "run", fake)
    return calls


def test_an_index_miss_reads_head_and_reports_one_reason(tmp_path, monkeypatch):
    calls = _git_by_spec(monkeypatch, b"fatal: path 'x' exists on disk, but not in the index",
                         b"fatal: something odd")
    assert rmr._committed_bytes(tmp_path) == (None, "reading HEAD failed (fatal: something odd)")
    assert [c.split(":")[0] for c in calls] == ["", "HEAD"]
    _working_tree_manifest(tmp_path)
    assert rmr.read_manifest_noted(tmp_path)[2] == [
        "reading working-tree manifest: reading HEAD failed (fatal: something odd)"]


def test_an_index_failure_other_than_a_miss_never_tries_head(tmp_path, monkeypatch):
    calls = _git_by_spec(monkeypatch, b"fatal: index file corrupt", b"unused")
    assert rmr._committed_bytes(tmp_path) == (
        None, "reading the index failed (fatal: index file corrupt)")
    assert len(calls) == 1


def test_an_unborn_head_with_nothing_anywhere_is_simply_no_manifest(tmp_path, monkeypatch):
    _git_by_spec(monkeypatch, b"fatal: path 'x' does not exist (neither on disk nor in the index)",
                 b"fatal: invalid object name 'HEAD'.")
    assert rmr.read_manifest_noted(tmp_path) == (None, None, [])


@needs_git
def test_staged_manifest_wins_over_head_and_the_working_tree(tmp_path):
    init_repo(tmp_path)
    path = tmp_path / rmr.MANIFEST_RELPATH
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"requirements": {}, "v": "head"}), encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "c")
    path.write_text(json.dumps({"requirements": {}, "v": "dirty"}), encoding="utf-8")
    assert rmr.read_manifest_noted(tmp_path)[0]["v"] == "head"  # index == HEAD
    path.write_text(json.dumps({"requirements": {}, "v": "staged"}), encoding="utf-8")
    git(tmp_path, "add", "-A")
    path.write_text(json.dumps({"requirements": {}, "v": "dirty"}), encoding="utf-8")
    assert rmr.read_manifest_noted(tmp_path) == ({"requirements": {}, "v": "staged"}, None, [])
