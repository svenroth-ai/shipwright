#!/usr/bin/env python3
"""What the compliance refresh is allowed to UNDO in the producer's own inputs.

Fifth module of the compliance-evidence refresh
(iterate-2026-07-31-derived-docs-at-release), and its own subject: the fixpoint
needs pass N and pass N+1 to see identical inputs, but the producer's inputs are
files other writers own. Deciding what may be rewound — and refusing to guess — is
a different question from how to regenerate, where the result goes, or what it
claims.

The rule is asymmetric on purpose, and both halves were learned the hard way:

* **Append-only logs are never rewound once they changed.** There is no way to
  tell this run's appends from a concurrent writer's, and guessing costs somebody
  evidence nothing can recompute. A first attempt guarded on "restore only while
  the snapshot is still a PREFIX", which has the test exactly backwards: a
  concurrent append leaves the snapshot as a prefix, so the guard passed and
  destroyed it, and fired only on a rewrite — never the reported case (Stage-3
  doubt D1).
* **Rewritten inputs always are.** ``shipwright_compliance_config.json`` is
  reserialised whole by the producer, so a prefix test could never pass for it and
  the same guard left it permanently dirty after every run, including every
  refusal — which then blocked the next ``--pr`` on a change the operator never
  made (Stage-3 doubt D6). Hence per-PATH handling, not per-call.
"""

from __future__ import annotations

import sys
from pathlib import Path

# UNCONDITIONAL — see the note in `tools/compliance_refresh_produce.py` (ADR-045).
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # shared/scripts
sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.churn_merge import EVENTS_LOG, TRIAGE_LOG  # noqa: E402

__all__ = ["APPEND_ONLY_INPUTS", "PRODUCER_STATE", "rewind", "snapshot"]


#: Tracked paths the producers WRITE that are not part of the derivation's
#: output. Rewound before every pass so pass N and pass N+1 see identical inputs:
#: the sbom and test-evidence legs append to the backlog, ``update_compliance``
#: appends one ``grade_snapshot`` event per run by documented contract, and it
#: rewrites the compliance config unconditionally. Hashing the derived paths while
#: letting these drift proves a fixpoint of a projection, not of the producer.
PRODUCER_STATE: tuple[str, ...] = (
    EVENTS_LOG, TRIAGE_LOG, "shipwright_compliance_config.json",
)

#: The subset of :data:`PRODUCER_STATE` that is an APPEND-ONLY log, handled
#: per-path rather than per-call (Stage-3 doubt D1/D6).
#:
#: These are never rewound once anything has been appended, because **there is no
#: way to tell this run's appends from a concurrent writer's**. The first attempt
#: guarded on "the snapshot is still a prefix" and had the test exactly backwards:
#: a concurrent append LEAVES the snapshot as a prefix, so the guard passed and the
#: append was destroyed — while the guard only fired on a rewrite or compaction,
#: which is not the reported defect. Data loss on the event log is the one outcome
#: this whole change exists to prevent, so the rule is now the safe direction:
#: **never destroy an appended line.**
#:
#: The fixpoint survives that, and the reason is specific rather than hopeful.
#: ``update_compliance`` appends one ``grade_snapshot`` event per run, and
#: ``change_history.collect_events`` filters that type out — so it moves no derived
#: document. Its sbom / test-evidence triage appends carry a ``dedupKey`` and are
#: idempotent, so they land once on pass 1 and are absorbed from pass 2 on. Two
#: consecutive passes therefore still agree, which is all :func:`converge` asks.
APPEND_ONLY_INPUTS: frozenset[str] = frozenset({EVENTS_LOG, TRIAGE_LOG})


def snapshot(root: Path, rels) -> dict[str, bytes | None]:
    """``{relpath: bytes}`` as they are RIGHT NOW; ``None`` for an absent path."""
    return {rel: (root / rel).read_bytes() if (root / rel).is_file() else None
            for rel in sorted(rels)}


def rewind(
    root: Path, snapshot: dict[str, bytes | None], *, append_only: bool = False,
) -> list[str]:
    """Put the snapshotted paths back. Used between passes and on every refusal.

    Rewinds to the SNAPSHOT, never to ``HEAD``. ``git checkout HEAD --`` cannot
    tell this run's writes from work that was already in the tree, so on the
    ``--stage`` path — which has no clean-tree preflight, and where a dirty
    ``shipwright_events.jsonl`` is the normal mid-session state — it would discard
    the operator's uncommitted work. That is trg-ad29a709's defect wearing a
    different hat: resetting a run-written path destroys evidence nothing can
    recompute (Stage-1 spec review MEDIUM-4; external code review openai/medium for
    the same defect one level up, on the documents themselves).

    ``append_only`` is decided **per path**, from :data:`APPEND_ONLY_INPUTS`, not
    per call — the compliance config is rewritten rather than appended to, and
    lumping it in with the logs left it permanently dirty after every run,
    including every refusal, which then blocked the next ``--pr`` on a change the
    operator never made (Stage-3 doubt D6). An append-only path that GREW is left
    exactly as it is and returned in ``unrewound``; see
    :data:`APPEND_ONLY_INPUTS` for why never destroying an appended line is the
    right trade, and why the fixpoint survives it.

    Everything else is rewound wholesale, which is the job: the producer REWRITES
    those, so undoing its rewrite is exactly what is wanted.
    """
    unrewound: list[str] = []
    for rel, blob in snapshot.items():
        path = root / rel
        if blob is None:
            path.unlink(missing_ok=True)
            continue
        current = path.read_bytes() if path.is_file() else None
        if current == blob:
            continue
        if append_only and rel in APPEND_ONLY_INPUTS:
            # Grew, shrank or was rewritten — either way this run cannot prove the
            # difference is its own, and guessing costs somebody's evidence.
            unrewound.append(rel)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    return unrewound
