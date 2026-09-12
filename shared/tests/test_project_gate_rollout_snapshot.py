"""Real-git tests for :mod:`_project_gate_rollout_snapshot` — the FR-01.02
#5/#10 rollout-transition grace's "what did that historical commit actually
say" half (`trg-9583d3a8`). Companion to ``test_project_gate_rollout.py``,
which covers "which commit" instead.

The nested-``project_root`` tests pin the git path-resolution fix this
iterate's internal plan review caught: ``git show <sha>:<path>`` resolves
``<path>`` relative to the REPO TOPLEVEL, never to ``-C <dir>``'s own
directory — the opposite of ``git archive``. A regression here would silently
make every nested-project rollout lookup a false negative (no grace ever
granted), not a loud failure — exactly the shape that "was empirically
discovered rather than caught by an existing test" describes, so this file
exists to make sure it stays caught.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools.verifiers._project_gate_rollout_snapshot import (  # noqa: E402
    build_rollout_snapshot,
    clear_snapshot_cache,
)


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


pytestmark = pytest.mark.skipif(not _git_available(), reason="git not available")


def _init(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.dev")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")


def _write(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _commit_at(root: Path, msg: str, iso_date: str) -> str:
    _git(root, "add", "-A")
    proc = subprocess.run(
        ["git", "-C", str(root), "commit", "-q", "-m", msg],
        capture_output=True, text=True,
        env={**os.environ, "GIT_AUTHOR_DATE": iso_date, "GIT_COMMITTER_DATE": iso_date},
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git commit failed: {proc.stderr}")
    return _git(root, "rev-parse", "HEAD")


_BEFORE_ROLLOUT = "2026-09-06T00:00:00+00:00"
_AFTER_ROLLOUT = "2026-09-13T00:00:00+00:00"

_SPLITS_MANIFEST_PRE = json.dumps({"splits": [{"name": "01-a", "status": "not_started"}]})


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_snapshot_cache()
    yield
    clear_snapshot_cache()


def test_build_rollout_snapshot_reads_pre_rollout_spec_text_at_repo_root(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/01-a/spec.md", "pre-rollout content")
    _write(root, "shipwright_project_config.json", _SPLITS_MANIFEST_PRE)
    _commit_at(root, "pre-rollout", _BEFORE_ROLLOUT)
    _write(root, ".shipwright/planning/01-a/spec.md", "post-rollout content")
    head_sha = _commit_at(root, "post-rollout", _AFTER_ROLLOUT)

    snapshot = build_rollout_snapshot(root, head_sha)
    assert snapshot.resolved is True
    assert snapshot.spec_text(".shipwright/planning/01-a/spec.md") == "pre-rollout content"


def test_build_rollout_snapshot_unresolved_when_repo_born_after_rollout(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/01-a/spec.md", "content")
    head_sha = _commit_at(root, "born after rollout", _AFTER_ROLLOUT)

    snapshot = build_rollout_snapshot(root, head_sha)
    assert snapshot.resolved is False
    assert snapshot.spec_text(".shipwright/planning/01-a/spec.md") is None
    assert snapshot.declared_split_names() == frozenset()


def test_build_rollout_snapshot_spec_text_none_for_a_path_absent_at_rollout(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/01-a/spec.md", "pre")
    _commit_at(root, "pre-rollout", _BEFORE_ROLLOUT)
    _write(root, ".shipwright/planning/02-b/spec.md", "new split, post-rollout only")
    head_sha = _commit_at(root, "post-rollout", _AFTER_ROLLOUT)

    snapshot = build_rollout_snapshot(root, head_sha)
    assert snapshot.spec_text(".shipwright/planning/02-b/spec.md") is None


def test_build_rollout_snapshot_declared_split_names_reads_project_config_at_rollout(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, "shipwright_project_config.json", _SPLITS_MANIFEST_PRE)
    _commit_at(root, "pre-rollout", _BEFORE_ROLLOUT)
    _write(root, "shipwright_project_config.json", json.dumps({
        "splits": [{"name": "01-a"}, {"name": "02-b"}],
    }))
    head_sha = _commit_at(root, "post-rollout", _AFTER_ROLLOUT)

    snapshot = build_rollout_snapshot(root, head_sha)
    assert snapshot.declared_split_names() == frozenset({"01-a"})  # PRE-rollout state, not head's


def test_build_rollout_snapshot_declared_split_names_falls_back_to_run_config(tmp_path):
    """No project config at rollout — falls back to run_config's splits list,
    same manifest priority order the live-manifest reader uses."""
    root = tmp_path / "repo"
    _init(root)
    _write(root, "shipwright_run_config.json", json.dumps({
        "splits": [{"name": "legacy-split"}],
    }))
    _commit_at(root, "pre-rollout", _BEFORE_ROLLOUT)
    _write(root, "README.md", "unrelated post-rollout touch")
    head_sha = _commit_at(root, "post-rollout, unrelated", _AFTER_ROLLOUT)

    snapshot = build_rollout_snapshot(root, head_sha)
    assert snapshot.declared_split_names() == frozenset({"legacy-split"})


def test_build_rollout_snapshot_declared_split_names_empty_when_manifest_malformed_at_rollout(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, "shipwright_project_config.json", "{not valid json")
    _commit_at(root, "pre-rollout", _BEFORE_ROLLOUT)
    _write(root, "README.md", "unrelated post-rollout touch")
    head_sha = _commit_at(root, "post-rollout, unrelated", _AFTER_ROLLOUT)

    snapshot = build_rollout_snapshot(root, head_sha)
    assert snapshot.declared_split_names() == frozenset()


def test_build_rollout_snapshot_declared_split_names_does_not_fall_back_when_project_config_exists_but_is_splitless(tmp_path):
    """project_config.json existing at rollout is authoritative even when its
    own ``splits`` key is absent/invalid — it must NOT fall through to
    run_config.json's splits, exactly like the live-manifest reader
    (code review, medium): an earlier draft fell through on ANY parse
    failure, indistinguishable from the file being absent, which would have
    let this stale run_config split inherit grace the authoritative
    manifest at this same historical commit never declared."""
    root = tmp_path / "repo"
    _init(root)
    _write(root, "shipwright_project_config.json", json.dumps({"scope": "extension"}))
    _write(root, "shipwright_run_config.json", json.dumps({
        "splits": [{"name": "legacy-split"}],
    }))
    _commit_at(root, "pre-rollout", _BEFORE_ROLLOUT)
    _write(root, "README.md", "unrelated post-rollout touch")
    head_sha = _commit_at(root, "post-rollout, unrelated", _AFTER_ROLLOUT)

    snapshot = build_rollout_snapshot(root, head_sha)
    assert snapshot.declared_split_names() == frozenset()


def test_build_rollout_snapshot_declared_split_names_empty_when_no_manifest_ever_existed(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, "README.md", "hello")
    _commit_at(root, "pre-rollout", _BEFORE_ROLLOUT)
    _write(root, "README.md", "hello, updated post-rollout")
    head_sha = _commit_at(root, "post-rollout, unrelated", _AFTER_ROLLOUT)

    snapshot = build_rollout_snapshot(root, head_sha)
    assert snapshot.declared_split_names() == frozenset()


# --------------------------------------------------------------------------- #
# Nested project_root — the git show/-C path-resolution fix
# --------------------------------------------------------------------------- #


def test_build_rollout_snapshot_resolves_spec_text_when_project_root_is_nested_below_toplevel(tmp_path):
    """The git repo's toplevel is ``tmp_path``; the SHIPWRIGHT project root is
    a subdirectory of it (``tmp_path/sub-project``) — the exact shape where
    ``git show <sha>:<path>`` (repo-toplevel-relative) and ``git -C <dir>``
    (directory-relative) diverge. Without the repo-relative-prefix fix, this
    would silently return None (no grace) for every path, even though the
    content genuinely predates the rollout."""
    repo_root = tmp_path
    _init(repo_root)
    _write(repo_root, "sub-project/.shipwright/planning/01-a/spec.md", "pre-rollout, nested")
    _commit_at(repo_root, "pre-rollout", _BEFORE_ROLLOUT)
    _write(repo_root, "sub-project/.shipwright/planning/01-a/spec.md", "post-rollout, nested")
    head_sha = _commit_at(repo_root, "post-rollout", _AFTER_ROLLOUT)

    project_root = repo_root / "sub-project"
    snapshot = build_rollout_snapshot(project_root, head_sha)
    assert snapshot.resolved is True
    assert snapshot.spec_text(".shipwright/planning/01-a/spec.md") == "pre-rollout, nested"


def test_build_rollout_snapshot_declared_split_names_when_project_root_is_nested(tmp_path):
    repo_root = tmp_path
    _init(repo_root)
    _write(repo_root, "sub-project/shipwright_project_config.json", _SPLITS_MANIFEST_PRE)
    _commit_at(repo_root, "pre-rollout", _BEFORE_ROLLOUT)
    _write(repo_root, "README.md", "unrelated post-rollout touch")
    head_sha = _commit_at(repo_root, "post-rollout, unrelated", _AFTER_ROLLOUT)

    project_root = repo_root / "sub-project"
    snapshot = build_rollout_snapshot(project_root, head_sha)
    assert snapshot.declared_split_names() == frozenset({"01-a"})


def test_two_sibling_nested_projects_at_the_same_sha_do_not_share_text_cache_entries(tmp_path):
    """External code review (both reviewers, high/medium): `_TEXT_CACHE` used
    to be keyed by `(sha, posix_path)` alone, omitting `project_root` — unlike
    the sibling `_MANIFEST_CACHE`, which already includes it. Two nested
    projects in one repo (`repo/a/`, `repo/b/`), both resolving the SAME
    rollout SHA and reading the SAME relative path
    (`.shipwright/planning/01-a/spec.md`), would collide on one cache entry
    and one project would silently read the other's historical text."""
    repo_root = tmp_path
    _init(repo_root)
    _write(repo_root, "a/.shipwright/planning/01-a/spec.md", "project A, pre-rollout")
    _write(repo_root, "b/.shipwright/planning/01-a/spec.md", "project B, pre-rollout")
    head_sha = _commit_at(repo_root, "pre-rollout", _BEFORE_ROLLOUT)

    snapshot_a = build_rollout_snapshot(repo_root / "a", head_sha)
    snapshot_b = build_rollout_snapshot(repo_root / "b", head_sha)

    assert snapshot_a.spec_text(".shipwright/planning/01-a/spec.md") == "project A, pre-rollout"
    assert snapshot_b.spec_text(".shipwright/planning/01-a/spec.md") == "project B, pre-rollout"
    # Order reversed too — a collision would show up in whichever read second.
    assert snapshot_b.spec_text(".shipwright/planning/01-a/spec.md") == "project B, pre-rollout"
    assert snapshot_a.spec_text(".shipwright/planning/01-a/spec.md") == "project A, pre-rollout"


# --------------------------------------------------------------------------- #
# Caching
# --------------------------------------------------------------------------- #


def test_spec_text_is_cached_by_sha_and_path(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/01-a/spec.md", "pre")
    _commit_at(root, "pre-rollout", _BEFORE_ROLLOUT)
    _write(root, ".shipwright/planning/01-a/spec.md", "post")
    head_sha = _commit_at(root, "post-rollout", _AFTER_ROLLOUT)

    snapshot = build_rollout_snapshot(root, head_sha)
    first = snapshot.spec_text(".shipwright/planning/01-a/spec.md")
    assert first == "pre"

    # Break the underlying git call `_read_at_commit` would make on a MISS —
    # a cache hit must never reach it, only a fresh (sha, path) pair would.
    import tools.verifiers._project_gate_rollout_snapshot as snap_mod
    def _boom(*_a, **_kw):
        raise AssertionError("_run_git should not be invoked again on a cache hit")
    monkeypatch.setattr(snap_mod, "_run_git", _boom)

    # Same snapshot object, same path — must not re-invoke git.
    second = snapshot.spec_text(".shipwright/planning/01-a/spec.md")
    assert second == first
