"""INTEGRATION — two parallel iterates each add an ADR, and both rows survive.

`iterate-2026-07-31-adr-index-producer` (#505) gave `.shipwright/planning/adr/INDEX.md`
a producer at iterate F3, so the index row ships in the same commit as its ADR.
The cost of that correct decision is a conflict class that did not exist before:
the index used to change only on `main` at release time, and now two branches
each appending a row collide on it.

This proves the pieces COMPOSE on real git — the registry entry
(`churn_merge.CHURN_ALLOWLIST`), the conflict classification (`classify`), the
resolver's `--theirs` placeholder, and the re-derive from the MERGED tree
(`integrate_regenerate.regenerate_after_merge` → `lib.adr_index.refresh_best_effort`,
deliberately OUTSIDE the `only`-scoped `regenerate_tracked_snapshots`) — through
the REAL `integrate_main.integrate`, the engine behind the F11 `ensure_current`
guard. A unit test on any one piece would still pass while the cascade left the
merge blocked or the committed index carrying only one side's ADR.

Non-dodgeable: `cross_component` fires on this diff, so the F11 verifier
`check_integration_coverage` recomputes the flag and STOPs the run without a
`category:"integration"` behavior backed by a test like this one.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402

from lib import gitattributes_union as gu  # noqa: E402
from lib.adr_index import ADR_INDEX_FILENAME, ADR_SPEC_FOLDER, rebuild_adr_index  # noqa: E402
from lib.churn_merge import ADR_INDEX, CHURN_ALLOWLIST, classify  # noqa: E402
from tools import integrate_main  # noqa: E402

_INDEX = f"{ADR_SPEC_FOLDER}/{ADR_INDEX_FILENAME}"


def _add_adr(root: Path, num: str, slug: str, title: str) -> str:
    """Write an ADR spec file and refresh the index, exactly as iterate F3 does."""
    rel = f"{ADR_SPEC_FOLDER}/{num}-{slug}.md"
    _write(root, rel, f"# ADR-{num} — {title}\n")
    rebuild_adr_index(root)
    return rel


def _rows(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.startswith("- [")]


def _show_utf8(repo: Path, ref: str) -> str:
    """`git show <ref>` decoded as UTF-8.

    The shared `_git` helper uses `text=True`, which decodes with the locale
    codec — cp1252 on Windows — and every index row contains an em-dash, so a
    byte-comparison against the generator's output would fail on mojibake alone.
    """
    proc = subprocess.run(
        ["git", "show", ref], cwd=str(repo),
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_the_index_is_registered_as_resolvable_churn():
    """AC1 — without this, `classify` puts it in `blocking` and the gate aborts."""
    assert ADR_INDEX in CHURN_ALLOWLIST
    resolvable, blocking = classify([ADR_INDEX])
    assert resolvable == [ADR_INDEX] and blocking == []


def test_two_parallel_adr_iterates_both_keep_their_row(git_origin_repo, make_worktree, monkeypatch):
    """AC1+AC2+AC3+AC4 — the whole cascade, on real git.

    Branch A and branch B each add a DIFFERENT ADR and refresh the index, so both
    touch the same file at the same anchor. A merges to main first; B then
    integrates main. B's merge must not abort, and the index B commits must list
    BOTH ADRs — not A's copy, not B's pre-merge copy.
    """
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "adr-index-churn-integration")

    # main: one pre-existing ADR + its index, pushed.
    _add_adr(work, "100", "baseline", "Baseline decision")
    _write(work, ".gitattributes", gu.merge_into(None)[0])
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed: baseline ADR + index")
    _git(work, "push", "origin", "main")

    # Branch A adds ADR-101 and merges to main first.
    wt_a = make_worktree(work, "adr-a")
    _add_adr(wt_a, "101", "branch-a", "Branch A decision")
    _git(wt_a, "add", "-A")
    _git(wt_a, "commit", "-m", "feat: ADR-101")
    _git(wt_a, "push", "origin", "HEAD:main")

    # Branch B forked BEFORE A landed and adds ADR-102 — same anchor, real conflict.
    wt_b = make_worktree(work, "adr-b")
    _add_adr(wt_b, "102", "branch-b", "Branch B decision")
    _git(wt_b, "add", "-A")
    _git(wt_b, "commit", "-m", "feat: ADR-102")

    result = integrate_main.integrate(
        wt_b, run_id="iterate-2026-07-31-adr-b", reason="parallel ADR merge",
    )
    assert result.get("status") == "ok", result

    # POSITIVE: the two sides really did diverge AT THE INDEX, so the merge this
    # exercises is a genuine conflict rather than a clean 3-way. Without this the
    # test would still pass if a future renumbering let git merge the index
    # cleanly — the allowlist entry and the `--theirs` path would never run while
    # every assertion below stayed green.
    merge_sha = _git(wt_b, "rev-list", "--merges", "-1", "HEAD").stdout.strip()
    assert merge_sha, f"no merge commit was created: {result}"
    ours = _show_utf8(wt_b, f"{merge_sha}^1:{_INDEX}")   # branch B before the merge
    theirs = _show_utf8(wt_b, f"{merge_sha}^2:{_INDEX}")  # mainline, carrying A
    assert "101-branch-a.md" not in ours, "branch B already had A's row — no divergence"
    assert "102-branch-b.md" not in theirs, "mainline already had B's row — no divergence"
    # Divergence alone is not conflict: separate the two ADRs by enough rows and git
    # 3-way-merges cleanly, carrying both — the allowlist entry and the `--theirs`
    # path would then never run while every assertion here stayed green. The merge
    # commit's index equals the MAINLINE side iff `complete_merge` took `--theirs`.
    assert _show_utf8(wt_b, f"{merge_sha}:{_INDEX}") == theirs, (
        "the index did not actually conflict — `--theirs` was never taken, so the "
        "auto-resolution this test exists to prove was not exercised"
    )

    committed = _show_utf8(wt_b, f"HEAD:{_INDEX}")
    rows = _rows(committed)
    assert any("101-branch-a.md" in r for r in rows), f"branch A's ADR lost from the index: {rows}"
    assert any("102-branch-b.md" in r for r in rows), f"branch B's ADR lost from the index: {rows}"
    assert any("100-baseline.md" in r for r in rows), f"the baseline ADR was dropped: {rows}"
    # Re-derived from the MERGED folder, so it equals what the generator would emit now.
    assert committed == (wt_b / _INDEX).read_text(encoding="utf-8")
    assert "<<<<<<<" not in committed, "conflict markers reached the commit"


def test_a_failed_index_refresh_is_reported_not_swallowed(git_origin_repo, make_worktree, monkeypatch):
    """The failure path, which the success tests cannot reach.

    On a failed refresh the resolver's one-sided `--theirs` index survives the
    merge. That is the register's deliberate fail-soft behaviour (the merge commit
    has already landed; failing would strand it over a transient lock), but a
    stale index is precisely the quiet-drift class this change exists to close —
    so the failure MUST reach the caller's result, not only stderr. CI's drift
    guard is the second backstop.
    """
    from tools import integrate_regenerate

    work, _origin = git_origin_repo
    _set_repo_identity(work)
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "adr-index-churn-failpath")
    _add_adr(work, "100", "baseline", "Baseline decision")
    _write(work, ".gitattributes", gu.merge_into(None)[0])
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "adr-fail")
    _add_adr(wt, "104", "mine", "My decision")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "feat: ADR-104")
    _write(work, "unrelated.txt", "main moved on\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "chore: unrelated")
    _git(work, "push", "origin", "main")

    monkeypatch.setattr(
        integrate_regenerate, "refresh_best_effort", lambda _root: "index is unwritable",
    )
    result = integrate_main.integrate(
        wt, run_id="iterate-2026-07-31-adr-fail", reason="fail path",
    )
    steps = result.get("steps") or []
    assert "adr-index-refresh-failed" in steps, (
        f"a failed index refresh must reach the caller's result, not just stderr: {result}"
    )
    assert "adr-index-refreshed" not in steps


def test_a_failed_stage_leaves_no_dirty_index(git_origin_repo, make_worktree, monkeypatch):
    """A refresh that cannot be staged must not leave the tree dirty.

    The refresh rewrites `INDEX.md`; if the `git add` then fails (index.lock, an
    ignored path in a consumer repo), leaving the file modified-but-unstaged makes
    a later `git merge` refuse when it overlaps an incoming change and invites a
    stray `git add -A` to smuggle it into an unrelated commit — the same hazard
    `restore_derived_to_head` exists to prevent.
    """
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "adr-index-churn-stagefail")
    _add_adr(work, "100", "baseline", "Baseline decision")
    _write(work, ".gitattributes", gu.merge_into(None)[0])
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")

    wt_a = make_worktree(work, "stagefail-a")
    _add_adr(wt_a, "105", "branch-a", "A decision")
    _git(wt_a, "add", "-A")
    _git(wt_a, "commit", "-m", "feat: ADR-105")
    _git(wt_a, "push", "origin", "HEAD:main")

    wt_b = make_worktree(work, "stagefail-b")
    _add_adr(wt_b, "106", "branch-b", "B decision")
    _git(wt_b, "add", "-A")
    _git(wt_b, "commit", "-m", "feat: ADR-106")

    real_git = integrate_main._git

    def failing_git(root, *args, **kwargs):
        if args[:1] == ("add",) and ADR_INDEX in args:
            return subprocess.CompletedProcess(args, 1, "", "simulated index.lock")
        return real_git(root, *args, **kwargs)

    monkeypatch.setattr(integrate_main, "_git", failing_git)
    result = integrate_main.integrate(
        wt_b, run_id="iterate-2026-07-31-stagefail", reason="stage failure",
    )
    steps = result.get("steps") or []
    assert "adr-index-stage-failed" in steps, result
    # The branch must stay FAIL-SOFT. A mutation check cannot reach this class: turn
    # this branch terminal and the step token is still present and the tree still
    # clean, so every other assertion here would stay green.
    assert result.get("status") == "ok", result
    # The worktree is clean: the index was restored, not left dirty.
    dirty = real_git(wt_b, "status", "--porcelain", "--", ADR_INDEX).stdout.strip()
    assert dirty == "", f"the index was left dirty after a failed stage: {dirty!r}"
    # And it was rewound to the merge commit's `--theirs` copy — i.e. STALE, missing
    # this branch's own ADR. Asserting only cleanliness would stay green if a future
    # change "cleaned" the tree by reverting more than intended.
    committed = _show_utf8(wt_b, f"HEAD:{ADR_INDEX}")
    assert "105-branch-a.md" in committed, "mainline's row should still be there"
    assert "106-branch-b.md" not in committed, (
        "the fail-soft outcome is the stale --theirs copy; this branch's row is "
        "expected to be MISSING until the index is regenerated"
    )


def test_the_index_is_not_a_derived_snapshot():
    """AC4, the membership half — cheap, and the half that actually guards.

    `restore_derived_to_head` resets DERIVED_SNAPSHOTS to the merge commit right
    before the index is refreshed. Adding the index to that register would rewind
    the re-derive; keeping it out is what makes AC4 true by construction.
    """
    from lib.derived_snapshots import DERIVED_SNAPSHOTS

    assert _INDEX not in DERIVED_SNAPSHOTS
