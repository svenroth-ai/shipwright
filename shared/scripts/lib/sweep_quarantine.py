"""Orphan-status quarantine for the triage outbox sweep.

iterate-2026-06-30-sweep-outbox-quarantine-orphans. When the sweep's materialized
log (``worktree-tracked ∪ outbox``) fails validation ONLY because of orphan-status
lines (a ``status`` whose id has no ``append`` anywhere) that originate in the
OUTBOX, those lines are moved to ``.shipwright/triage.outbox.quarantine.jsonl``
instead of hard-blocking the entire sweep — which previously stranded every
legitimate pending append in the buffer. Genuine corruption (bad/missing header,
duplicate append, invalid JSON, empty log) still hard-blocks, untouched.

Split from :mod:`lib.sweep_outbox` so both modules stay under the 300-LOC guideline.
The quarantine write reuses the same ``durable_atomic_write`` the sweep uses, and the
caller invokes :func:`decide` + :func:`append_quarantine` under the canonical triage
``_FileLock`` (same critical section as the rest of the sweep).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from lib.atomic_write import durable_atomic_write
from lib.churn_merge import classify_triage_text, dedup_triage_lines, validate_triage_text

#: Operator-review buffer for quarantined orphan-status lines (gitignored, main-tree).
QUARANTINE_LOG = ".shipwright/triage.outbox.quarantine.jsonl"


def quarantine_path(main_root: Path | str) -> Path:
    return Path(main_root) / QUARANTINE_LOG


@dataclass
class QuarantineDecision:
    """Outcome of :func:`decide`.

    ``action`` ∈ {``clean``, ``quarantine``, ``block``}:
      * ``clean``      — the materialized log validates as-is; deliver normally.
      * ``quarantine`` — only orphan-status lines failed, all originate in the outbox,
        and the remainder validates after trimming them; ``candidates`` are the outbox
        lines to quarantine and ``trimmed_outbox`` is the outbox without them.
      * ``block``      — genuine corruption (or a residual orphan the sweep cannot
        rewrite, e.g. an origin-side one) remains; ``errors`` carries the validator output.
    ``deduped_text`` is the post-(trim)-dedup materialized log to write to the branch.

    ``warnings`` carries whatever :func:`lib.triage_dedup.dedup_triage_lines` reported
    while materializing — a same-id ``append`` collapse, or a probable 32-bit id
    collision it refused to collapse. They are **informational and never blocking**:
    a benign keep-last collapse leaves ``action == "clean"``. What blocks a collision
    is the retained duplicate reaching ``validate_triage_text``, not this list. Before
    audit 2026-07-28 finding 25 the dedup could not warn at all and this caller
    discarded the value it returned.
    """

    action: str
    deduped_text: str = ""
    trimmed_outbox: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _is_status_with_id(line: str, ids: frozenset[str]) -> bool:
    """True iff ``line`` is a ``status`` event whose id is in ``ids``."""
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return False
    return isinstance(obj, dict) and obj.get("event") == "status" and obj.get("id") in ids


def _materialize(
    worktree_lines: list[str], outbox_lines: list[str], eol: str
) -> tuple[str, list[str]]:
    """The merged log plus whatever the dedup had to say about it. The warnings are
    returned rather than dropped: this is the sweep, i.e. the delivery channel, and
    a record the dedup declined to collapse (or collapsed) is exactly the thing an
    operator needs told."""
    deduped, warnings = dedup_triage_lines(worktree_lines + outbox_lines)
    return ((eol.join(deduped) + eol) if deduped else ""), warnings


def decide(
    worktree_lines: list[str],
    outbox_lines: list[str],
    eol: str,
    known_append_ids: frozenset[str] = frozenset(),
) -> QuarantineDecision:
    """Classify the materialized log and decide clean / quarantine / block.

    Only OUTBOX-originating orphan-status lines are quarantine candidates (the sweep
    cannot rewrite the worktree-tracked/origin log). Quarantine is adopted ONLY when
    trimming the candidates leaves a fully-clean remainder; any residual error → block.

    ``known_append_ids`` widens the orphan UNIVERSE beyond ``worktree-tracked ∪ outbox``
    (iterate-2026-07-14-sweep-drift-dismiss-loss). The caller passes the append ids it
    knows from MAIN's tracked log; a ``status`` for one of those has a real append — it
    is NOT an orphan and must never be quarantined, because quarantining it DELETES the
    operator's only dismiss and the item resurrects on the board forever. If such a
    status still cannot be validated (its append exists but the repair could not place
    it in the materialized log), every remaining error is a protected one → ``block``:
    a loud hard stop is the correct failure, silent data loss is not.
    """
    text, warnings = _materialize(worktree_lines, outbox_lines, eol)
    verdict = classify_triage_text(text)
    if not verdict.errors:
        # A dedup warning does NOT make the log undeliverable — a keep-last collapse
        # is expected and benign. It rides along on a `clean` decision so the sweep
        # can report it without quarantining anything.
        return QuarantineDecision("clean", deduped_text=text,
                                  trimmed_outbox=list(outbox_lines), warnings=warnings)
    protected = verdict.orphan_status_ids & frozenset(known_append_ids)
    orphan_ids = verdict.orphan_status_ids - frozenset(known_append_ids)
    if verdict.has_non_orphan_error or not orphan_ids:
        # A protected status is NOT "an append the merge dropped" — we blocked precisely
        # BECAUSE we know its append exists, in main's tracked log, unreachable from this
        # branch. Saying "no append anywhere" would send the operator hunting for corruption
        # that isn't there and offer no remedy (code review). Name the real state and the fix.
        errors = list(verdict.errors) + [
            f"protected_status_unplaceable: id {iid!r} has an append in main's tracked log that is "
            f"not reachable from this branch — deliver main (push / merge origin), then re-run"
            for iid in sorted(protected)
        ]
        return QuarantineDecision("block", errors=errors, warnings=warnings)

    candidates = [ln for ln in outbox_lines if _is_status_with_id(ln, orphan_ids)]
    if not candidates:
        # Every orphan lives in the worktree-tracked log; the sweep cannot fix it.
        return QuarantineDecision("block", errors=list(verdict.errors), warnings=warnings)

    candidate_set = set(candidates)
    trimmed = [ln for ln in outbox_lines if ln not in candidate_set]
    trimmed_text, _ = _materialize(worktree_lines, trimmed, eol)
    if validate_triage_text(trimmed_text):
        # A residual error after trimming (e.g. an origin-side orphan) → fail closed.
        return QuarantineDecision("block", errors=list(verdict.errors), warnings=warnings)
    return QuarantineDecision(
        "quarantine", deduped_text=trimmed_text, trimmed_outbox=trimmed,
        candidates=candidates, warnings=warnings,
    )


def append_quarantine(
    path: Path,
    lines: list[str],
    *,
    reason: str,
    now: str | None = None,
) -> None:
    """Durably append ``lines`` (each wrapped with ``quarantined_at`` / ``reason`` /
    ``original``) to the quarantine log. ``now`` overridable for deterministic tests."""
    ts = now or datetime.now(timezone.utc).isoformat()
    # Read BYTES. The previous text read needed an explicit ``newline=""`` open (the
    # log's existing EOLs must survive the round-trip, and ``Path.read_text(newline=)``
    # is 3.13+ only, which once took setup_iterate_worktree.py down AFTER the worktree
    # was already created). Bytes answer that and one more: this runs on the same
    # interrupted-write path as the rest of the sweep, and a strict decode of a store
    # truncated mid multi-byte sequence would raise straight out of step 5. Nothing is
    # decoded here, so nothing can fail to decode or be re-encoded differently.
    existing = path.read_bytes() if path.exists() else b""
    records = [
        json.dumps({"quarantined_at": ts, "reason": reason, "original": ln}, ensure_ascii=False)
        for ln in lines
    ]
    out = existing
    if out and not out.endswith(b"\n"):
        out += b"\n"
    # ``surrogateescape`` on the way out too: a quarantined line reached us through a
    # surrogate-escaped read, so a strict encode here would crash on exactly the
    # corrupt line the quarantine exists to preserve. This restores its original bytes.
    out += ("\n".join(records) + "\n").encode("utf-8", errors="surrogateescape")
    path.parent.mkdir(parents=True, exist_ok=True)
    durable_atomic_write(path, out)
