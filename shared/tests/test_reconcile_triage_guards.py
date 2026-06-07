"""Safety-guard no-ops (AC-3), worktree resolution, and the AC-4 pull-unblock
integration test for ``lib/reconcile_triage.reconcile_main_triage``.

The guards make reconcile a structured no-op rather than ever mutating a user's
git state; AC-4 reproduces the 2026-06-07 block (uncommitted main-tree drift +
origin/main ahead on the same file) and proves a normal pull-merge then works.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# shared/scripts must precede shared/tests so ``from lib import ...`` resolves to
# shared/scripts/lib (shared/tests stays on path only for the _reconcile helper).
sys.path.insert(0, str(Path(__file__).resolve().parent))  # shared/tests (helper)
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))  # shared/scripts — wins

import _reconcile_helpers as h  # noqa: E402
from lib import reconcile_triage  # noqa: E402

TRIAGE = h.TRIAGE


# --------------------------------------------------------------------------- #
# AC-3 — safety-guard no-ops
# --------------------------------------------------------------------------- #


def test_skip_on_unrelated_staged_changes(git_origin_repo) -> None:
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))
    before = h.head_count(work)
    h.append(work, h.item("trg-bbbb"))
    (work / "other.txt").write_text("wip\n", encoding="utf-8")
    h.git(work, "add", "other.txt")

    res = reconcile_triage.reconcile_main_triage(work, allow_ci=True)

    assert res.status == "skipped" and res.reason == "staged_changes", res
    assert h.head_count(work) == before
    assert "trg-bbbb" in (work / TRIAGE).read_text(encoding="utf-8")


def test_skip_on_detached_head(git_origin_repo) -> None:
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))
    h.append(work, h.item("trg-bbbb"))
    h.git(work, "checkout", "--detach")

    res = reconcile_triage.reconcile_main_triage(work, allow_ci=True)

    assert res.status == "skipped" and res.reason == "detached_head", res


def test_skip_on_merge_in_progress(git_origin_repo) -> None:
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"), push=False)
    # Build a conflicting divergence so `git merge` leaves MERGE_HEAD.
    h.git(work, "checkout", "-b", "side")
    (work / "c.txt").write_text("side\n", encoding="utf-8")
    h.git(work, "add", "c.txt")
    h.git(work, "commit", "-m", "side")
    h.git(work, "checkout", "main")
    (work / "c.txt").write_text("main\n", encoding="utf-8")
    h.git(work, "add", "c.txt")
    h.git(work, "commit", "-m", "main")
    h.git(work, "merge", "side", check=False)  # conflict → MERGE_HEAD persists
    h.append(work, h.item("trg-bbbb"))

    res = reconcile_triage.reconcile_main_triage(work, allow_ci=True)

    assert res.status == "skipped" and res.reason == "op_in_progress", res


def test_skip_on_rebase_in_progress(git_origin_repo) -> None:
    """Covers the git-dir FILE branch of _op_in_progress (rebase-merge dir),
    distinct from the MERGE_HEAD pseudo-ref branch."""
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"), push=False)
    h.git(work, "checkout", "-b", "feature")
    (work / "f.txt").write_text("feature\n", encoding="utf-8")
    h.git(work, "add", "f.txt")
    h.git(work, "commit", "-m", "feature")
    h.git(work, "checkout", "main")
    (work / "f.txt").write_text("main\n", encoding="utf-8")
    h.git(work, "add", "f.txt")
    h.git(work, "commit", "-m", "main")
    h.git(work, "checkout", "feature")
    h.git(work, "rebase", "main", check=False)  # conflict → rebase-merge dir persists
    h.append(work, h.item("trg-bbbb"))

    res = reconcile_triage.reconcile_main_triage(work, allow_ci=True)

    assert res.status == "skipped" and res.reason == "op_in_progress", res


def test_skip_in_ci_without_optin(git_origin_repo, monkeypatch) -> None:
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))
    h.append(work, h.item("trg-bbbb"))
    monkeypatch.setenv("CI", "true")

    res = reconcile_triage.reconcile_main_triage(work)  # allow_ci defaults False

    assert res.status == "skipped" and res.reason == "ci_without_optin", res


def test_skip_when_triage_itself_is_staged(git_origin_repo) -> None:
    """Conservative: staging triage.jsonl ITSELF also blocks reconcile, so we
    never commit a hand-staged index state we did not validate/dedup."""
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))
    h.append(work, h.item("trg-bbbb"))
    h.git(work, "add", "--", TRIAGE)

    res = reconcile_triage.reconcile_main_triage(work, allow_ci=True)

    assert res.status == "skipped" and res.reason == "staged_changes", res


def test_skip_when_triage_log_deleted(git_origin_repo) -> None:
    """A deleted tracked log is drift, but reconcile must not auto-commit the
    deletion — it skips for the operator to restore."""
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))
    (work / TRIAGE).unlink()

    res = reconcile_triage.reconcile_main_triage(work, allow_ci=True)

    assert res.status == "skipped" and res.reason == "triage_missing", res


def test_not_a_git_repo_is_skip(tmp_path) -> None:
    res = reconcile_triage.reconcile_main_triage(tmp_path, allow_ci=True)
    assert res.status == "skipped" and res.reason == "not_a_git_repo", res


# --------------------------------------------------------------------------- #
# Worktree resolution — reconcile(worktree) acts on the MAIN tree
# --------------------------------------------------------------------------- #


def test_reconcile_from_worktree_commits_on_main(git_origin_repo, make_worktree) -> None:
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))
    wt = make_worktree(work, "recon-wt")
    before_main = h.head_count(work)
    # Background producer appends to the MAIN tree triage log (not the worktree).
    h.append(work, h.item("trg-bbbb"))

    res = reconcile_triage.reconcile_main_triage(wt, allow_ci=True)

    assert res.status == "committed", res
    assert h.head_count(work) == before_main + 1  # landed on main, not the wt branch
    assert "trg-bbbb" in h.git(work, "show", f"HEAD:{TRIAGE}").stdout


# --------------------------------------------------------------------------- #
# AC-4 — unblocks the 2026-06-07 pull/FF block
# --------------------------------------------------------------------------- #


def test_ac4_reconcile_unblocks_pull(git_origin_repo) -> None:
    work, origin = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-base"))

    # A second clone advances origin/main, touching the SAME file.
    other = work.parent / "other"
    h.git(work.parent, "clone", str(origin), str(other))
    h.set_identity(other)
    h.append(other, h.item("trg-origin"))
    h.git(other, "commit", "-am", "origin advances triage")
    h.git(other, "push", "origin", "main")

    # Back in the main work tree: uncommitted background drift + origin ahead.
    h.append(work, h.item("trg-local"))
    h.git(work, "fetch", "origin")

    # Reproduce the block: --ff-only refuses against the dirty + diverged tree.
    blocked = h.git(work, "merge", "--ff-only", "origin/main", check=False)
    assert blocked.returncode != 0

    res = reconcile_triage.reconcile_main_triage(work, allow_ci=True)
    assert res.status == "committed", res

    # The `git pull` mechanism (fetch already done) — a union merge — now works.
    merged = h.git(work, "merge", "origin/main", check=False)
    assert merged.returncode == 0, merged.stderr
    assert h.git(work, "status", "--porcelain", "--", TRIAGE).stdout.strip() == ""
    final = (work / TRIAGE).read_text(encoding="utf-8")
    assert "trg-local" in final and "trg-origin" in final  # no silent loss
