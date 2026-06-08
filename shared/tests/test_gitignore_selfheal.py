"""`self_heal_gitignore` — the guarded git commit-path (campaign 2026-06-08 / D3)
that backfills the canonical `.shipwright/` artifact-ignore block into an
already-adopted repo on its next iterate, plus the `setup_iterate_worktree`
wiring (step 4.6) that makes it fire automatically.

Modeled on `test_gitattributes_union_selfheal.py`. A managed repo is one that
tracks at least one append-log artifact; the self-heal acts only there, only when
canonical rules are missing, and only when git state is safe to commit into. The
backfilled block keeps the gitignored `triage.outbox.jsonl` buffer ignored — the
empirical check-ignore round-trip pins that.
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

import _reconcile_helpers as h  # noqa: E402  (git() + set_identity + head_count)
from lib import gitignore_selfheal as gs  # noqa: E402
from lib.churn_merge import EVENTS_LOG  # noqa: E402
from lib.gitignore_canon import read_canonical_rules  # noqa: E402

_SETUP_SCRIPT = REPO_ROOT / "shared" / "scripts" / "tools" / "setup_iterate_worktree.py"
_CHORE_SUBJECT = (
    "chore: scaffold canonical .shipwright/ artifact-ignore block into .gitignore"
)
_OUTBOX_REL = ".shipwright/triage.outbox.jsonl"


def _seed_managed_repo(work: Path, *, gitignore: str | None = None) -> None:
    """Track an events.jsonl (the managed-repo marker) + set commit identity."""
    h.set_identity(work)
    (work / EVENTS_LOG).write_text('{"type":"adopted"}\n', encoding="utf-8")
    if gitignore is not None:
        (work / ".gitignore").write_text(gitignore, encoding="utf-8")
    h.git(work, "add", "-A")
    h.git(work, "commit", "-m", "seed managed repo")


def _check_ignored(repo: Path, rel: str) -> bool:
    proc = h.git(repo, "check-ignore", rel, check=False)
    assert proc.returncode in (0, 1), f"check-ignore rc={proc.returncode} {proc.stderr!r}"
    return proc.returncode == 0


# --------------------------------------------------------------------------- #
# Commit, idempotent, never-clobber
# --------------------------------------------------------------------------- #


def test_self_heal_commits_when_block_missing(git_origin_repo):
    work, _ = git_origin_repo
    _seed_managed_repo(work)  # no .gitignore at all
    before = h.head_count(work)

    res = gs.self_heal_gitignore(work, allow_ci=True)

    assert res.status == "committed", res
    assert set(res.added) == set(read_canonical_rules()), res
    assert h.head_count(work) == before + 1
    assert h.git(work, "log", "-1", "--format=%s").stdout.strip() == _CHORE_SUBJECT
    assert h.git(work, "status", "--porcelain").stdout.strip() == ""

    # Empirical: the healed block ignores the outbox buffer.
    (work / ".shipwright").mkdir(exist_ok=True)
    (work / _OUTBOX_REL).write_text("{}\n", encoding="utf-8")
    assert _check_ignored(work, _OUTBOX_REL)
    assert not _check_ignored(work, ".shipwright/triage.jsonl")


def test_self_heal_is_idempotent(git_origin_repo):
    work, _ = git_origin_repo
    _seed_managed_repo(work)
    gs.self_heal_gitignore(work, allow_ci=True)
    before = h.head_count(work)

    res = gs.self_heal_gitignore(work, allow_ci=True)

    assert res.status == "no_change", res
    assert h.head_count(work) == before


def test_self_heal_preserves_existing_user_gitignore(git_origin_repo):
    work, _ = git_origin_repo
    _seed_managed_repo(work, gitignore="node_modules/\n.env.local\n")

    res = gs.self_heal_gitignore(work, allow_ci=True)

    assert res.status == "committed", res
    gi = (work / ".gitignore").read_text(encoding="utf-8")
    assert "node_modules/" in gi and ".env.local" in gi
    assert "/.shipwright/triage.outbox.jsonl" in gi


def test_self_heal_backfills_only_missing_outbox_rule(git_origin_repo):
    """Already-adopted-before-D3 repo: full canon block EXCEPT the new outbox line."""
    work, _ = git_origin_repo
    canonical = read_canonical_rules()
    outbox_rule = "/.shipwright/triage.outbox.jsonl"
    pre_existing = [r for r in canonical if r != outbox_rule]
    _seed_managed_repo(work, gitignore="\n".join(pre_existing) + "\n")

    res = gs.self_heal_gitignore(work, allow_ci=True)

    assert res.status == "committed", res
    assert res.added == [outbox_rule], res


# --------------------------------------------------------------------------- #
# Safety guards (never corrupt git state)
# --------------------------------------------------------------------------- #


def test_skip_repo_without_tracked_append_log(git_origin_repo):
    work, _ = git_origin_repo  # tracks only README + .shipwright/.gitkeep
    h.set_identity(work)
    res = gs.self_heal_gitignore(work, allow_ci=True)
    assert (res.status, res.reason) == ("skipped", "no_tracked_append_log")


def test_skip_in_ci_without_optin(git_origin_repo, monkeypatch):
    work, _ = git_origin_repo
    _seed_managed_repo(work)
    monkeypatch.setenv("CI", "true")
    res = gs.self_heal_gitignore(work)  # allow_ci defaults False
    assert (res.status, res.reason) == ("skipped", "ci_without_optin")


def test_skip_on_detached_head(git_origin_repo):
    work, _ = git_origin_repo
    _seed_managed_repo(work)
    h.git(work, "checkout", h.git(work, "rev-parse", "HEAD").stdout.strip())
    res = gs.self_heal_gitignore(work, allow_ci=True)
    assert (res.status, res.reason) == ("skipped", "detached_head")


def test_skip_on_staged_changes(git_origin_repo):
    work, _ = git_origin_repo
    _seed_managed_repo(work)
    (work / "README.md").write_text("changed\n", encoding="utf-8")
    h.git(work, "add", "README.md")  # unrelated staged WIP
    res = gs.self_heal_gitignore(work, allow_ci=True)
    assert (res.status, res.reason) == ("skipped", "staged_changes")


def test_skip_on_merge_in_progress(git_origin_repo):
    work, _ = git_origin_repo
    _seed_managed_repo(work)
    head = h.git(work, "rev-parse", "HEAD").stdout.strip()
    (work / ".git" / "MERGE_HEAD").write_text(head + "\n", encoding="utf-8")
    res = gs.self_heal_gitignore(work, allow_ci=True)
    assert (res.status, res.reason) == ("skipped", "op_in_progress")


def test_skip_when_not_a_git_repo(tmp_path):
    res = gs.self_heal_gitignore(tmp_path, allow_ci=True)
    assert (res.status, res.reason) == ("skipped", "not_a_git_repo")


def test_non_utf8_gitignore_does_not_raise(git_origin_repo):
    """LOW-3 (D3 review cascade): a non-UTF-8 ``.gitignore`` must NOT raise a
    UnicodeDecodeError (a ValueError uncaught by setup.main's (GitError, OSError)
    handler → would crash setup). ``errors="replace"`` keeps it fail-soft: the read
    survives, the missing canon rules are still merged, a structured result returns."""
    work, _ = git_origin_repo
    # A user .gitignore WITHOUT the canon block + a raw non-UTF-8 byte (0xFF, an
    # invalid UTF-8 start byte). Write bytes directly so it is genuinely undecodable.
    (work / ".gitignore").write_bytes(b"node_modules/\n\xff\xfe bad bytes\n")
    _seed_managed_repo(work)  # commits the .gitignore + the managed marker

    res = gs.self_heal_gitignore(work, allow_ci=True)  # must not raise

    assert res.status == "committed", res
    assert "/.shipwright/triage.outbox.jsonl" in (
        work / ".gitignore"
    ).read_text(encoding="utf-8", errors="replace")
    assert h.git(work, "status", "--porcelain").stdout.strip() == ""


def test_rolls_back_on_commit_rejection(git_origin_repo, tmp_path):
    # A rejecting pre-commit hook must leave git state untouched: no leftover
    # written/staged .gitignore.
    work, _ = git_origin_repo
    _seed_managed_repo(work)  # no .gitignore before the call
    hookdir = tmp_path / "failhooks"
    hookdir.mkdir()
    hook = hookdir / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    os.chmod(hook, 0o755)
    h.git(work, "config", "core.hooksPath", str(hookdir))

    res = gs.self_heal_gitignore(work, allow_ci=True)

    assert res.status == "error" and res.reason.startswith("commit_failed"), res
    assert not (work / ".gitignore").exists()  # rolled back (didn't exist before)
    assert h.git(work, "status", "--porcelain").stdout.strip() == ""


# --------------------------------------------------------------------------- #
# Wiring — setup_iterate_worktree self-heals the new worktree automatically
# --------------------------------------------------------------------------- #


def test_setup_iterate_worktree_self_heals_gitignore(git_origin_repo):
    work, _ = git_origin_repo
    # Managed repo on origin/main WITHOUT the canon .gitignore block (the
    # already-adopted-before-D3 state). Push so the worktree inherits the
    # events.jsonl but no canon block.
    _seed_managed_repo(work)
    # PRECONDITION (external code review): prove the block is genuinely ABSENT
    # before setup, so a no-op implementation that never calls step 4.6 fails.
    assert not (work / ".gitignore").exists()
    h.git(work, "push", "origin", "main")
    origin_tip = h.git(work, "rev-parse", "origin/main").stdout.strip()

    env = os.environ.copy()
    env["CI"] = ""  # interactive session, not CI
    env.setdefault("SHIPWRIGHT_SESSION_ID", "sess-test")
    proc = subprocess.run(
        [sys.executable, str(_SETUP_SCRIPT), "--project-root", str(work),
         "--slug", "heal-gi", "--run-id", "iterate-20260608-heal-gi"],
        env=env, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    wt = Path(json.loads(proc.stdout)["project_root"])

    # The gitignore self-heal (step 4.6) runs LAST of the committing steps here
    # (step 4.5 gitattributes precedes it; no outbox → no step-5 sweep commit), so
    # it must be the worktree HEAD commit.
    assert h.git(wt, "log", "-1", "--format=%s").stdout.strip() == _CHORE_SUBJECT, (
        "the gitignore self-heal (step 4.6) must be the worktree HEAD commit"
    )
    # The new commit was NOT in the origin base — it was created by THIS setup.
    new_commits = h.git(wt, "rev-list", f"{origin_tip}..HEAD", "--format=%s").stdout
    assert _CHORE_SUBJECT in new_commits, "self-heal commit must be new to this branch"

    # The iterate branch carries the canon .gitignore block + ignores the outbox.
    gi = (wt / ".gitignore").read_text(encoding="utf-8")
    assert "/.shipwright/triage.outbox.jsonl" in gi
    (wt / ".shipwright").mkdir(exist_ok=True)
    (wt / _OUTBOX_REL).write_text("{}\n", encoding="utf-8")
    assert _check_ignored(wt, _OUTBOX_REL)
