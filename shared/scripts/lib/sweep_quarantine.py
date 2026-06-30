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
    """

    action: str
    deduped_text: str = ""
    trimmed_outbox: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _is_status_with_id(line: str, ids: frozenset[str]) -> bool:
    """True iff ``line`` is a ``status`` event whose id is in ``ids``."""
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return False
    return isinstance(obj, dict) and obj.get("event") == "status" and obj.get("id") in ids


def _materialize(worktree_lines: list[str], outbox_lines: list[str], eol: str) -> str:
    deduped, _ = dedup_triage_lines(worktree_lines + outbox_lines)
    return (eol.join(deduped) + eol) if deduped else ""


def decide(worktree_lines: list[str], outbox_lines: list[str], eol: str) -> QuarantineDecision:
    """Classify the materialized log and decide clean / quarantine / block.

    Only OUTBOX-originating orphan-status lines are quarantine candidates (the sweep
    cannot rewrite the worktree-tracked/origin log). Quarantine is adopted ONLY when
    trimming the candidates leaves a fully-clean remainder; any residual error → block.
    """
    text = _materialize(worktree_lines, outbox_lines, eol)
    verdict = classify_triage_text(text)
    if not verdict.errors:
        return QuarantineDecision("clean", deduped_text=text, trimmed_outbox=list(outbox_lines))
    if verdict.has_non_orphan_error or not verdict.orphan_status_ids:
        return QuarantineDecision("block", errors=list(verdict.errors))

    candidates = [ln for ln in outbox_lines if _is_status_with_id(ln, verdict.orphan_status_ids)]
    if not candidates:
        # Every orphan lives in the worktree-tracked log; the sweep cannot fix it.
        return QuarantineDecision("block", errors=list(verdict.errors))

    candidate_set = set(candidates)
    trimmed = [ln for ln in outbox_lines if ln not in candidate_set]
    trimmed_text = _materialize(worktree_lines, trimmed, eol)
    if validate_triage_text(trimmed_text):
        # A residual error after trimming (e.g. an origin-side orphan) → fail closed.
        return QuarantineDecision("block", errors=list(verdict.errors))
    return QuarantineDecision(
        "quarantine", deduped_text=trimmed_text, trimmed_outbox=trimmed, candidates=candidates,
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
    existing = path.read_text(encoding="utf-8", newline="") if path.exists() else ""
    records = [
        json.dumps({"quarantined_at": ts, "reason": reason, "original": ln}, ensure_ascii=False)
        for ln in lines
    ]
    out = existing
    if out and not out.endswith("\n"):
        out += "\n"
    out += "\n".join(records) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    durable_atomic_write(path, out)
