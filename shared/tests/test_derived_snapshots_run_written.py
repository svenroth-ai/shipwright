"""``restore_derived_to_head`` must not reset a file nothing can re-derive.

trg-ad29a709 (A). ``ensure_current`` integrates ``main`` and then calls
``restore_derived_to_head`` to leave the worktree clean. That reset the whole
``DERIVED_SNAPSHOTS`` set — including ``shipwright_test_results.json``, which F5 had
just written the run's ledger into. The ledger was silently discarded: the file went
back to whatever HEAD held, which is some earlier run's block or none at all.

Two sessions reported this independently and one had its F5 block overwritten twice
in a single run. A landmine note in the operator's memory ("re-write F5, READ THE
NUMBERS") had already failed to prevent a third occurrence, which is the argument
for fixing the defect rather than documenting it again: a workaround that must be
remembered every time is not a control.

Restoring a DERIVED path is free — the next regeneration recreates it byte for byte.
Restoring a RUN-WRITTEN path is data loss, because there is no producer to put it
back. That distinction is what :data:`RESTORABLE_SNAPSHOTS` encodes.

iterate-2026-07-28-derived-snapshots-refresh.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.churn_merge import TEST_RESULTS  # noqa: E402
from lib.derived_snapshots import (  # noqa: E402
    DERIVED_SNAPSHOTS,
    RESTORABLE_SNAPSHOTS,
    restore_derived_to_head,
)

_DASH = ".shipwright/agent_docs/build_dashboard.md"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    for rel in (_DASH, TEST_RESULTS):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"from": "an earlier run"}\n', encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "base")
    return root


def test_restorable_excludes_exactly_the_run_written_path() -> None:
    """The exclusion is ONE path, and it is the one a run writes.

    Pinned as an exact set difference rather than "TEST_RESULTS is absent", so that
    widening the carve-out later is a deliberate edit to this assertion. Every other
    derived path is re-derivable, and restoring a re-derivable path costs nothing.
    """
    assert DERIVED_SNAPSHOTS - RESTORABLE_SNAPSHOTS == {TEST_RESULTS}
    assert RESTORABLE_SNAPSHOTS < DERIVED_SNAPSHOTS, "the exclusion must be a real subset"


def test_the_f5_ledger_survives_a_restore(repo: Path) -> None:
    """The exact reported failure. F5 writes the run's block; ``ensure_current``
    integrates and restores; the block must still be there afterwards."""
    ledger = {"iterate_latest": {"run_id": "iterate-2026-07-29-x", "tests": {"passed": 95}}}
    (repo / TEST_RESULTS).write_text(json.dumps(ledger), encoding="utf-8")

    restore_derived_to_head(repo)

    after = json.loads((repo / TEST_RESULTS).read_text(encoding="utf-8"))
    assert after == ledger, (
        "the F5 ledger was reset to HEAD — this is trg-ad29a709, and it costs a "
        "session every time because the loss is silent"
    )


def test_a_staged_f5_ledger_also_survives(repo: Path) -> None:
    """F5 may already have staged it. ``git checkout HEAD --`` resets index AND
    worktree, so a staged run-written file was reverted just as thoroughly."""
    (repo / TEST_RESULTS).write_text('{"iterate_latest": {"run_id": "r"}}', encoding="utf-8")
    _git(repo, "add", "--", TEST_RESULTS)

    restore_derived_to_head(repo)

    assert json.loads((repo / TEST_RESULTS).read_text(encoding="utf-8")) == {
        "iterate_latest": {"run_id": "r"}
    }


def test_a_derived_snapshot_is_still_restored(repo: Path) -> None:
    """The exclusion must be surgical. Everything re-derivable still gets reset —
    that is what keeps the worktree clean so a later merge does not refuse and a
    stray ``git add -A`` cannot smuggle a snapshot into the PR."""
    (repo / _DASH).write_text("a producer regenerated me\n", encoding="utf-8")

    assert restore_derived_to_head(repo) == [_DASH]
    assert (repo / _DASH).read_text(encoding="utf-8") == '{"from": "an earlier run"}\n'


def test_a_DELETED_run_written_path_is_still_restored(repo: Path) -> None:
    """The exclusion is about CONTENT, not about the path.

    A deletion has no ledger to lose, and letting it ride into the iterate commit
    would drop a tracked file — the very thing this function exists to prevent. So
    ``shipwright_test_results.json`` is skipped when it is modified and restored when
    it is gone.
    """
    (repo / TEST_RESULTS).unlink()

    assert TEST_RESULTS in restore_derived_to_head(repo)
    assert (repo / TEST_RESULTS).is_file()


def test_the_return_value_never_claims_the_run_written_path(repo: Path) -> None:
    """It reports what it restored, and it must not report a file it deliberately
    left alone — a caller logging that list would otherwise state the opposite of
    what happened."""
    (repo / _DASH).write_text("regenerated\n", encoding="utf-8")
    (repo / TEST_RESULTS).write_text('{"iterate_latest": {}}', encoding="utf-8")

    restored = restore_derived_to_head(repo)

    assert TEST_RESULTS not in restored
    assert restored == [_DASH]


def test_a_STAGED_ledger_whose_worktree_copy_is_gone_is_not_restored(repo: Path) -> None:
    """Porcelain `MD`: modified in the INDEX, deleted from the worktree.

    The first cut tested `"D" not in line[:2]` — a substring over both status columns
    — so `MD` (and `RD`) read as "deleted" and the path was restored. For the one path
    this exclusion exists to protect that is precisely wrong: an `MD` means the F5
    ledger IS present, in the index, and restoring blows it away. trg-ad29a709 again,
    inside the function added to prevent it.
    """
    ledger = '{"iterate_latest": {"run_id": "iterate-2026-07-29-x"}}'
    (repo / TEST_RESULTS).write_text(ledger, encoding="utf-8")
    _git(repo, "add", "--", TEST_RESULTS)
    (repo / TEST_RESULTS).unlink()

    status = _git(repo, "status", "--porcelain", "--", TEST_RESULTS).stdout
    assert status.startswith("MD"), f"fixture did not produce an MD state: {status!r}"

    assert TEST_RESULTS not in restore_derived_to_head(repo)
    staged = _git(repo, "show", f":{TEST_RESULTS}").stdout
    assert json.loads(staged) == json.loads(ledger), (
        "the staged F5 ledger was reset to HEAD — an MD is not a plain deletion"
    )


def test_a_ledger_unstaged_with_rm_cached_is_not_restored(repo: Path) -> None:
    """`git rm --cached` emits a `D ` line while the file is still ON DISK.

    The status pair alone reads that as a clean deletion, and restoring it would
    overwrite the run's ledger — trg-ad29a709 through the very function added to
    prevent it, reached by the natural operator move for "get this out of my commit".
    So the pair is necessary but not sufficient: the content must also be gone.
    """
    ledger = '{"iterate_latest": {"run_id": "iterate-2026-07-30-x"}}'
    (repo / TEST_RESULTS).write_text(ledger, encoding="utf-8")
    _git(repo, "add", "--", TEST_RESULTS)
    _git(repo, "commit", "-m", "seed the ledger")
    _git(repo, "rm", "--cached", "-q", "--", TEST_RESULTS)

    status = _git(repo, "status", "--porcelain", "--", TEST_RESULTS).stdout
    assert status.startswith("D "), f"fixture did not produce a `D ` state: {status!r}"
    assert (repo / TEST_RESULTS).is_file(), "the file must still be on disk"

    assert TEST_RESULTS not in restore_derived_to_head(repo)
    assert json.loads((repo / TEST_RESULTS).read_text(encoding="utf-8")) == json.loads(ledger)


def test_a_derived_path_unstaged_with_rm_cached_is_still_restored(repo: Path) -> None:
    """The extra condition applies ONLY to the run-written carve-out. A derived path
    is re-derivable, so restoring it costs nothing and the worktree must end clean."""
    _git(repo, "rm", "--cached", "-q", "--", _DASH)

    assert _DASH in restore_derived_to_head(repo)
