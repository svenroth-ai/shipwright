"""Whose run does ``shipwright_test_results.json.iterate_latest`` belong to?

Every F11 check that reads that block used to answer "the run I am verifying",
and never asked. The file is a DERIVED_SNAPSHOT
(:data:`lib.derived_snapshots.DERIVED_SNAPSHOTS`), so at F11 ``ensure_current`` →
``integrate_main`` calls ``restore_derived_to_head`` and resets it to ``HEAD``.
An iterate no longer commits it, so ``HEAD``'s copy is ``main``'s — the previous
run's evidence, in this run's worktree, shaped exactly like this run's would be.

Observed: the ledger gate reported *"complete: 30 tested, 1 untestable"* for a
run that had six behaviours; the numbers belonged to
``iterate-2026-07-27-checks-that-gate-nothing``.

**Five states, not two.** "I read a block" and "I read *this run's* block" are
different answers, and so are the four ways the second can fail. Collapsing them
is what let a foreign block present as evidence, so :func:`read_iterate_latest`
names each one and hands the block back **only** in the ``current`` state — a
caller cannot accidentally use what it was not given.

The durable alternative is the per-run F5c entry
(``.shipwright/agent_docs/iterates/<run_id>.json``), which is deliberately NOT a
derived snapshot and therefore survives the restore. Callers prefer it and fall
back to this file; :func:`stale_detail` writes the repair for both.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "STATE_CURRENT",
    "STATE_FOREIGN",
    "STATE_MALFORMED",
    "STATE_MISSING",
    "STATE_UNATTRIBUTED",
    "IterateLatest",
    "read_iterate_latest",
    "stale_detail",
]

RESULTS_NAME = "shipwright_test_results.json"

#: The block names this run — the only state in which it is evidence.
STATE_CURRENT = "current"
#: It names a DIFFERENT run. The restore happened, or F5 never re-ran after it.
STATE_FOREIGN = "foreign"
#: It names no run at all, so it cannot be attributed to this one either.
STATE_UNATTRIBUTED = "unattributed"
#: The file is unreadable / not the shape it claims.
STATE_MALFORMED = "malformed"
#: No file, or no ``iterate_latest`` in it.
STATE_MISSING = "missing"


@dataclass(frozen=True)
class IterateLatest:
    """The answer, with the block attached only when it is this run's."""

    state: str
    block: dict | None = None
    owner: str = ""
    detail: str = ""

    @property
    def is_current(self) -> bool:
        return self.state == STATE_CURRENT


def read_iterate_latest(project_root: Path, run_id: str) -> IterateLatest:
    """Read ``iterate_latest`` and say whose run it is."""
    path = Path(project_root) / RESULTS_NAME
    if not path.exists():
        return IterateLatest(STATE_MISSING, detail=f"{RESULTS_NAME} does not exist")
    try:
        results = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        return IterateLatest(STATE_MALFORMED, detail=f"{RESULTS_NAME} is unreadable: {exc}")
    if not isinstance(results, dict):
        return IterateLatest(STATE_MALFORMED, detail=f"{RESULTS_NAME} is not a JSON object")

    block = results.get("iterate_latest")
    if block is None:
        return IterateLatest(STATE_MISSING, detail=f"{RESULTS_NAME} has no iterate_latest")
    if not isinstance(block, dict):
        return IterateLatest(STATE_MALFORMED, detail="iterate_latest is not an object")

    owner = block.get("run_id")
    owner = owner.strip() if isinstance(owner, str) else ""
    if not owner:
        return IterateLatest(
            STATE_UNATTRIBUTED,
            detail="iterate_latest carries no run_id, so nothing says which run "
                   "wrote it — an unattributed block is not evidence for any run",
        )
    if owner != run_id:
        return IterateLatest(
            STATE_FOREIGN, owner=owner,
            detail=f"iterate_latest belongs to {owner}, not {run_id}",
        )
    return IterateLatest(STATE_CURRENT, block=block, owner=owner)


def stale_detail(result: IterateLatest, run_id: str, field: str) -> str:
    """The failure message for a non-``current`` read, with both repairs.

    Both are one command, and the second is the durable one: the F5c entry is a
    per-run path, so unlike the shared results file it cannot be rewound by the
    integration this very gate performs.
    """
    return (
        f"{result.detail} — the F5c entry for {run_id} carries no {field} "
        f"either, so this gate has no evidence belonging to THIS run. "
        f"{RESULTS_NAME} is a derived snapshot that `restore_derived_to_head` "
        "resets to HEAD during the F11 integration, which is how another run's "
        f"block ends up here. Repair: re-run F5 to rewrite {RESULTS_NAME} for "
        f"this run, or (durable) include {field!r} in the F5c "
        "`--entry-json` so it lives on a per-run path the restore cannot reach."
    )
