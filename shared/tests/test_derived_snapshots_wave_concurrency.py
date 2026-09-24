"""``restore_derived_to_head`` under concurrency (campaign-dag-scheduler R5a).

Real-git composition test (category: integration) — actual concurrent git
worktrees, not a mocked stand-in. The wave model's whole safety argument for
running `restore_derived_to_head` inside N per-unit worktrees at once is
"each worktree has its own copy of the twelve derived paths, so file-level
collisions cannot occur" — this proves it directly, rather than assuming it
follows from git worktrees being a thing.

Split from `test_derived_snapshots.py`/`test_derived_snapshots_integrate.py`
(both already scoped to the single-worktree case) — this file never existed
before, no baseline implication.

Covers `RESTORABLE_SNAPSHOTS` (ten of the twelve `DERIVED_SNAPSHOTS`), not all
twelve — a decision, not an oversight (external review, LOW): `TEST_RESULTS`
and `SESSION_HANDOFF` are excluded from `RESTORABLE_SNAPSHOTS` by
`lib.derived_snapshots`'s own definition, since a mid-run restore must never
reset either of them to HEAD (see that module's comment on the set). Nothing
in this file's own subject exercises a reset that could touch them, so a
concurrency test over the other two would test code this mechanism never
calls.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.derived_snapshots import RESTORABLE_SNAPSHOTS, restore_derived_to_head  # noqa: E402

_DASH = ".shipwright/compliance/dashboard.md"
_THROUGHPUT = ".shipwright/compliance/performance/iterate-throughput.md"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(cwd), *args],
                           capture_output=True, text=True, check=True)


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_restore_in_one_unit_worktree_never_touches_a_sibling_units_dirty_copy(
    git_origin_repo, make_worktree,
):
    work, _origin = git_origin_repo
    # Commit both derived paths to HEAD on `main` before either unit worktree
    # is created, so both start from the SAME committed content.
    _write(work, _DASH, "HEAD dashboard\n")
    _write(work, _THROUGHPUT, "HEAD throughput\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed derived snapshots")
    _git(work, "push", "origin", "main")

    unit_a = make_worktree(work, "unit-a")
    unit_b = make_worktree(work, "unit-b")

    # Each unit's own F5a/F5b regeneration dirties its OWN copy, with
    # DIFFERENT content — simulating two units mid-build in the same wave.
    _write(unit_a, _DASH, "unit A's own regenerated dashboard\n")
    _write(unit_a, _THROUGHPUT, "unit A's own regenerated throughput\n")
    _write(unit_b, _DASH, "unit B's own regenerated dashboard\n")
    _write(unit_b, _THROUGHPUT, "unit B's own regenerated throughput\n")

    restored_a = restore_derived_to_head(unit_a)

    assert sorted(restored_a) == sorted([_DASH, _THROUGHPUT])
    # Unit A's own copy is back to HEAD content.
    assert (unit_a / _DASH).read_text(encoding="utf-8") == "HEAD dashboard\n"
    assert (unit_a / _THROUGHPUT).read_text(encoding="utf-8") == "HEAD throughput\n"
    # Unit B's still-dirty copy in its OWN worktree is completely untouched —
    # the file-level collision the wave model's safety argument depends on.
    assert (unit_b / _DASH).read_text(encoding="utf-8") == "unit B's own regenerated dashboard\n"
    assert (unit_b / _THROUGHPUT).read_text(encoding="utf-8") == "unit B's own regenerated throughput\n"
    status_b = _git(unit_b, "status", "--porcelain", "--", _DASH, _THROUGHPUT).stdout
    assert status_b.strip(), "unit B's derived paths must still show dirty after A's own restore"

    # Restoring unit B afterwards is independent and does not re-touch A.
    _write(unit_a, _DASH, "unit A regenerated again, after its own restore\n")
    restored_b = restore_derived_to_head(unit_b)
    assert sorted(restored_b) == sorted([_DASH, _THROUGHPUT])
    assert (unit_b / _DASH).read_text(encoding="utf-8") == "HEAD dashboard\n"
    assert (unit_a / _DASH).read_text(encoding="utf-8") == "unit A regenerated again, after its own restore\n"


def test_a_deleted_derived_path_in_one_worktree_does_not_resurrect_in_a_sibling(
    git_origin_repo, make_worktree,
):
    """A deletion is dirty precisely because it is gone from disk (the
    function's own documented behavior) — proven per-worktree too: deleting
    in A and restoring A must never write the path back into B's worktree,
    which never touched it at all."""
    work, _origin = git_origin_repo
    _write(work, _DASH, "HEAD dashboard\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed dashboard")
    _git(work, "push", "origin", "main")

    unit_a = make_worktree(work, "unit-a")
    unit_b = make_worktree(work, "unit-b")

    (unit_a / _DASH).unlink()

    restored = restore_derived_to_head(unit_a)
    assert restored == [_DASH]
    assert (unit_a / _DASH).read_text(encoding="utf-8") == "HEAD dashboard\n"
    # Unrelated to A's deletion+restore cycle: B's own on-disk copy is
    # whatever it always was, from the shared HEAD it cloned/checked out.
    assert (unit_b / _DASH).read_text(encoding="utf-8") == "HEAD dashboard\n"
    status_b = _git(unit_b, "status", "--porcelain", "--", _DASH).stdout
    assert status_b.strip() == "", "unit B's untouched copy must not read as dirty"


def test_truly_concurrent_restores_across_all_ten_restorable_paths_never_cross_contaminate(
    git_origin_repo, make_worktree,
):
    """External code review (openai, medium): the two tests above call
    `restore_derived_to_head` SEQUENTIALLY in one process and cover only 2 of
    the 10 restorable paths. This test runs two REAL overlapping calls (a
    `threading.Barrier` forces both threads' `git` subprocesses to start
    inside the same window, not one after the other) against every path in
    `RESTORABLE_SNAPSHOTS`, in two separate per-unit worktrees."""
    work, _origin = git_origin_repo
    paths = sorted(RESTORABLE_SNAPSHOTS)
    for rel in paths:
        _write(work, rel, f"HEAD content for {rel}\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed all restorable snapshots")
    _git(work, "push", "origin", "main")

    unit_a = make_worktree(work, "unit-a")
    unit_b = make_worktree(work, "unit-b")
    for rel in paths:
        _write(unit_a, rel, f"unit A dirty {rel}\n")
        _write(unit_b, rel, f"unit B dirty {rel}\n")

    barrier = threading.Barrier(2)
    results: dict[str, list[str]] = {}
    errors: dict[str, BaseException] = {}

    def _run(name: str, root: Path) -> None:
        try:
            barrier.wait(timeout=10)  # both threads' git subprocesses overlap
            results[name] = restore_derived_to_head(root)
        except BaseException as exc:  # noqa: BLE001 — re-raised in the main thread below
            errors[name] = exc

    t_a = threading.Thread(target=_run, args=("a", unit_a))
    t_b = threading.Thread(target=_run, args=("b", unit_b))
    t_a.start()
    t_b.start()
    t_a.join(timeout=30)
    t_b.join(timeout=30)
    assert not t_a.is_alive() and not t_b.is_alive(), "concurrent restore hung"
    if errors:
        # A thread's own exception would otherwise vanish silently (a bare
        # KeyError on `results[name]` below, with no trace of the real
        # cause) — code review round 3, LOW.
        raise next(iter(errors.values()))

    assert sorted(results["a"]) == paths
    assert sorted(results["b"]) == paths
    for rel in paths:
        assert (unit_a / rel).read_text(encoding="utf-8") == f"HEAD content for {rel}\n"
        assert (unit_b / rel).read_text(encoding="utf-8") == f"HEAD content for {rel}\n"
