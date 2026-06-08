"""`self_heal_gitattributes` — the guarded git commit-path (AC-3) that backfills
the union `.gitattributes` into an already-adopted repo on its next iterate, plus
the `setup_iterate_worktree` wiring that makes it fire automatically.

Modeled on the `reconcile_main_triage` guard suite. A managed repo is one that
tracks at least one append-log artifact; the self-heal acts only there, only when
the union lines are missing, and only when git state is safe to commit into.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # shared/tests (helper)
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))  # shared/scripts — wins

import _reconcile_helpers as h  # noqa: E402  (git() + set_identity)
from lib import gitattributes_union as gu  # noqa: E402
from lib.churn_merge import EVENTS_LOG  # noqa: E402

_SETUP_SCRIPT = REPO_ROOT / "shared" / "scripts" / "tools" / "setup_iterate_worktree.py"
_CHORE_SUBJECT = "chore: scaffold append-log union merge driver into .gitattributes"


def _seed_managed_repo(work: Path, *, gitattributes: str | None = None) -> None:
    """Track an events.jsonl (the managed-repo marker) + set commit identity."""
    h.set_identity(work)
    (work / EVENTS_LOG).write_text('{"type":"adopted"}\n', encoding="utf-8")
    if gitattributes is not None:
        (work / ".gitattributes").write_text(gitattributes, encoding="utf-8")
    h.git(work, "add", "-A")
    h.git(work, "commit", "-m", "seed managed repo")


# --------------------------------------------------------------------------- #
# AC-3 — commit, idempotent, never-clobber
# --------------------------------------------------------------------------- #


def test_self_heal_commits_when_union_missing(git_origin_repo):
    work, _ = git_origin_repo
    _seed_managed_repo(work)
    before = h.head_count(work)

    res = gu.self_heal_gitattributes(work, allow_ci=True)

    assert res.status == "committed", res
    assert set(res.added) == set(gu.UNION_PATHS)
    assert h.head_count(work) == before + 1
    assert h.git(work, "log", "-1", "--format=%s").stdout.strip() == _CHORE_SUBJECT
    ga = (work / ".gitattributes").read_text(encoding="utf-8")
    assert gu.missing_union_paths(ga) == []
    # the file was committed, not left dirty/staged
    assert h.git(work, "status", "--porcelain").stdout.strip() == ""


def test_self_heal_is_idempotent(git_origin_repo):
    work, _ = git_origin_repo
    _seed_managed_repo(work)
    gu.self_heal_gitattributes(work, allow_ci=True)
    before = h.head_count(work)

    res = gu.self_heal_gitattributes(work, allow_ci=True)

    assert res.status == "no_change", res
    assert h.head_count(work) == before


def test_self_heal_preserves_existing_user_gitattributes(git_origin_repo):
    work, _ = git_origin_repo
    _seed_managed_repo(work, gitattributes="*.png binary\n")

    res = gu.self_heal_gitattributes(work, allow_ci=True)

    assert res.status == "committed", res
    ga = (work / ".gitattributes").read_text(encoding="utf-8")
    assert "*.png binary" in ga
    assert gu.missing_union_paths(ga) == []


# --------------------------------------------------------------------------- #
# AC-3 — safety guards (never corrupt git state)
# --------------------------------------------------------------------------- #


def test_skip_repo_without_tracked_append_log(git_origin_repo):
    work, _ = git_origin_repo  # tracks only README + .shipwright/.gitkeep
    h.set_identity(work)
    res = gu.self_heal_gitattributes(work, allow_ci=True)
    assert (res.status, res.reason) == ("skipped", "no_tracked_append_log")


def test_skip_in_ci_without_optin(git_origin_repo, monkeypatch):
    work, _ = git_origin_repo
    _seed_managed_repo(work)
    monkeypatch.setenv("CI", "true")
    res = gu.self_heal_gitattributes(work)  # allow_ci defaults False
    assert (res.status, res.reason) == ("skipped", "ci_without_optin")


def test_skip_on_detached_head(git_origin_repo):
    work, _ = git_origin_repo
    _seed_managed_repo(work)
    h.git(work, "checkout", h.git(work, "rev-parse", "HEAD").stdout.strip())
    res = gu.self_heal_gitattributes(work, allow_ci=True)
    assert (res.status, res.reason) == ("skipped", "detached_head")


def test_skip_on_staged_changes(git_origin_repo):
    work, _ = git_origin_repo
    _seed_managed_repo(work)
    (work / "README.md").write_text("changed\n", encoding="utf-8")
    h.git(work, "add", "README.md")  # unrelated staged WIP
    res = gu.self_heal_gitattributes(work, allow_ci=True)
    assert (res.status, res.reason) == ("skipped", "staged_changes")


def test_skip_on_merge_in_progress(git_origin_repo):
    work, _ = git_origin_repo
    _seed_managed_repo(work)
    head = h.git(work, "rev-parse", "HEAD").stdout.strip()
    (work / ".git" / "MERGE_HEAD").write_text(head + "\n", encoding="utf-8")  # merge underway
    res = gu.self_heal_gitattributes(work, allow_ci=True)
    assert (res.status, res.reason) == ("skipped", "op_in_progress")


def test_skip_when_not_a_git_repo(tmp_path):
    res = gu.self_heal_gitattributes(tmp_path, allow_ci=True)
    assert (res.status, res.reason) == ("skipped", "not_a_git_repo")


def test_rolls_back_on_commit_rejection(git_origin_repo, tmp_path):
    # A rejecting pre-commit hook (the bloat-gate failure mode) must leave git
    # state untouched: no leftover written/staged .gitattributes.
    work, _ = git_origin_repo
    _seed_managed_repo(work)  # no .gitattributes before the call
    hookdir = tmp_path / "failhooks"
    hookdir.mkdir()
    hook = hookdir / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    # Linux git only runs an EXECUTABLE hook (Windows git runs it regardless) —
    # without the +x bit this test silently passes the commit on CI and the
    # rollback path is never exercised.
    os.chmod(hook, 0o755)
    h.git(work, "config", "core.hooksPath", str(hookdir))

    res = gu.self_heal_gitattributes(work, allow_ci=True)

    assert res.status == "error" and res.reason.startswith("commit_failed"), res
    assert not (work / ".gitattributes").exists()  # rolled back (didn't exist before)
    assert h.git(work, "status", "--porcelain").stdout.strip() == ""  # nothing staged/dirty


# --------------------------------------------------------------------------- #
# Wiring — setup_iterate_worktree self-heals the new worktree automatically
# --------------------------------------------------------------------------- #


def test_setup_iterate_worktree_self_heals_new_worktree(git_origin_repo):
    work, _ = git_origin_repo
    # Managed repo on origin/main WITHOUT a union .gitattributes (the
    # already-adopted-before-the-scaffolder state). Push so the worktree, cut
    # from origin/main, inherits the events.jsonl but no union driver.
    _seed_managed_repo(work)
    h.git(work, "push", "origin", "main")

    env = os.environ.copy()
    env["CI"] = ""  # simulate the developer's interactive session, not CI
    env.setdefault("SHIPWRIGHT_SESSION_ID", "sess-test")
    proc = subprocess.run(
        [sys.executable, str(_SETUP_SCRIPT), "--project-root", str(work),
         "--slug", "heal-me", "--run-id", "iterate-20260607-heal-me"],
        env=env, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    wt = Path(json.loads(proc.stdout)["project_root"])

    # The iterate branch carries the gitattributes chore commit + the union
    # lines. The gitignore self-heal (setup step 4.6, campaign 2026-06-08) lands
    # a SECOND chore on top in the SAME setup, so the documented order is:
    #   HEAD     = gitignore self-heal (step 4.6)
    #   HEAD~1   = gitattributes self-heal (step 4.5)
    # Assert the gitattributes chore is the SECOND-newest commit (recency-precise,
    # not merely "somewhere in history" — a regression that skips step 4.5 fails).
    _GI_SUBJECT = (
        "chore: scaffold canonical .shipwright/ artifact-ignore block into .gitignore"
    )
    assert h.git(wt, "log", "-1", "--format=%s").stdout.strip() == _GI_SUBJECT
    assert h.git(wt, "log", "-1", "--skip=1", "--format=%s").stdout.strip() == _CHORE_SUBJECT
    assert gu.missing_union_paths((wt / ".gitattributes").read_text(encoding="utf-8")) == []
