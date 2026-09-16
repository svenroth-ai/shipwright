#!/usr/bin/env python3
"""Durable audit trail for every ``rollback.py`` invocation.

FR-01.08 criterion 7: a return to the previous state announces itself
(``operator_message``, already true) *and is recorded* — this module is the
"is recorded" half, deterministic and unconditional. ``rollback.py``'s
``main()`` calls :func:`record` after every run, whatever the outcome
(refused / halted / completed), for both strategies.

FR-01.08 criterion 5's override half rides the same file: overriding a
data-drift refusal (``--ack-data-drift``) requires ``--override-reason``,
which is carried into the same record — the "why the stored-data warning was
overridden" lives next to the record of the rollback it enabled, one
append-only trail rather than two.

Format: one JSON object per line (JSONL) under
``.shipwright/deploy/rollback-history.jsonl``, append-only, created on first
write. Never rotated or pruned by this module.

``json.dumps`` encodes every value (an ``--override-reason`` with an embedded
newline or control character becomes an escaped in-string sequence, never a
literal line break), so one call to :func:`record` can never itself produce a
torn/partial line. The lock below guards the remaining risk: two *separate*
processes (an auto rollback racing an operator-requested one) appending at
the same instant, which ``open(..., "a")`` alone does not make atomic on
every platform (external review, round 1, e4-checks-deploy-changelog).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Same shared-tree resolution rollback.py uses (two levels above the plugin
# root) — done here too, independently, so this module's own import order
# never depends on having been imported *after* a caller already extended
# sys.path.
_SHARED_SCRIPTS = Path(__file__).resolve().parents[2].parent.parent / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.file_lock import file_lock  # noqa: E402

HISTORY_RELATIVE_PATH = Path(".shipwright") / "deploy" / "rollback-history.jsonl"


def history_path(project_root: Path | str | None) -> Path:
    """Resolve the history file under ``project_root``.

    ``project_root`` is typed to allow ``None`` defensively — external code
    review (rounds 1 and 2, e4-checks-deploy-changelog) both flagged this
    shape even though ``rollback.py``'s own ``--project-root`` was, at the
    time, an optional flag defaulting to ``"."`` (round 7 made it required
    instead, precisely because that silent default let a real rollback's
    audit record land somewhere no verifier could find it — but this
    module's own contract stays defensive regardless of what any ONE
    caller's CLI currently requires). Any OTHER caller of this module is
    not bound by ``rollback.py``'s own argument parsing, so falling back to
    ``Path.cwd()`` here — matching argparse's own default semantics —
    keeps the function correct on its own, not merely correct-by-accident
    via its one current caller.
    """
    return Path(project_root if project_root is not None else Path.cwd()) / HISTORY_RELATIVE_PATH


def record(
    project_root: Path | str | None,
    result: dict,
    *,
    invocation: str = "auto",
) -> dict:
    """Append one audit record for this rollback invocation. Returns it.

    ``result`` is exactly the dict ``rollback_git`` / ``rollback_clone`` (or
    a CLI-level argument refusal) returned — every field it carries is
    recorded verbatim, never summarised, so the record can answer the same
    questions ``operator_message`` does. ``invocation`` distinguishes an
    automatic (smoke-test-triggered) rollback from an operator-requested
    (``--rollback``) one; the caller passes it, since ``rollback.py`` itself
    has no way to know which it was.
    """
    path = history_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        # ``**result`` first: the audit fields below must always win a key
        # collision. ``result`` is rollback_report's growing "every field
        # always present" dict, and a future field literally named
        # ``invocation`` or ``recorded_at`` would otherwise silently clobber
        # the two keys check_manual_rollback_proves_alive filters and orders
        # on — matching smoke_test.py's own merge direction (external code
        # review, e4-checks-deploy-changelog).
        **result,
        # Microsecond precision, not truncated to whole seconds — external
        # code review round 2 (e4-checks-deploy-changelog): a rollback and
        # its post-check liveness probe can both land in the same wall-clock
        # second; truncating either timestamp makes same-second ordering
        # ambiguous (`check_manual_rollback_proves_alive` compares this
        # against `smoke_test.py`'s `checked_at`, which now matches).
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "invocation": invocation,
    }
    lock_path = path.with_suffix(path.suffix + ".lock")
    with file_lock(lock_path, timeout_seconds=5.0):
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def record_degraded(project_root: Path | str | None, *, invocation: str, reason: str) -> None:
    """Best-effort fallback for when :func:`record` itself could not write.

    Called ONLY from ``rollback.py``'s own except handler around
    :func:`record` — Tier-3 PR review round 4 (e4-checks-deploy-changelog):
    a lock timeout or unwritable audit dir used to be reduced to a stderr
    warning with no durable trace, letting a real (possibly host-mutating)
    manual rollback whose record was lost read, downstream, as "no
    rollback happened" — the append-only trail's own fail-open-on-absence
    design turned an audit failure into a false pass. This writes a
    separate, unlocked marker file so ``deploy_checks.py``'s reader can
    fail closed on ITS presence instead. Never raises: it runs from inside
    an already-failing path, and a SECOND storage failure here must never
    mask ``rollback.py``'s real exit code / ``operator_message`` for an
    outcome that already happened.
    """
    try:
        path = history_path(project_root).with_name("rollback-audit-degraded.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "at": datetime.now(timezone.utc).isoformat(),
            "invocation": invocation,
            "reason": reason,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError:
        pass


def last_entry(project_root: Path | str | None) -> dict | None:
    """Return the most recently recorded entry, or ``None`` when the file is
    absent, empty, or contains only unparseable lines.
    """
    path = history_path(project_root)
    if not path.exists():
        return None
    last: dict | None = None
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                last = json.loads(line)
            except json.JSONDecodeError:
                continue
    return last


__all__ = ["HISTORY_RELATIVE_PATH", "history_path", "last_entry", "record", "record_degraded"]
