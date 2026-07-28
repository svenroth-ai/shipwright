"""The ``grade_snapshot`` wire shape — one owner, two producers
(iterate-2026-07-28-grade-snapshot-lineage).

``grade_snapshot`` lands on the DURABLE, tracked ``shipwright_events.jsonl`` and
is read cross-repo by the WebUI Ship's-Log. Two producers write it: the
compliance emitter (``_grade_snapshot.emit_grade_snapshot``, once per
Control-Grade regen) and the manual/replay CLI (``record_event.py --type
grade_snapshot``). They previously built the event independently, so the CLI
enforced a score range the emitter did not, and a field added to one would
silently not exist on the other.

This module decides the shape once. Its most important property is that
**attribution is not optional and cannot be asserted**: every event that leaves
here carries a ``lineage`` resolved from the tree on disk. There is deliberately
no parameter by which a caller could supply one — a caller able to pass
``lineage="main"`` from a branch worktree could manufacture a false main-lineage
point in the very log the grade trend is read from, and validating the
vocabulary would not help, because ``"main"`` is a valid value. The lie is the
assertion itself (external plan review, approach/medium).

Placed top-level under ``shared/scripts/`` (not under ``lib/``) for the same
ADR-045 reason as ``tree_lineage`` and ``tests_block``: the compliance emitter
lives in the plugin's own ``scripts.lib`` namespace and a shared ``lib.X`` import
would shadow it.

The validation messages name the CLI flags (``--grade`` / ``--score``) on
purpose: the CLI is the only path that can actually reach them — the emitter
feeds this from ``compute_grade``, whose score is range-guaranteed — so the text
is written for the operator who will see it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tree_lineage import LINEAGE_UNKNOWN, lineage_fields, resolve_tree_lineage

#: The keys no caller may supply, on ANY write route to the durable log. Owned
#: here because this module owns the shape; `record_event`'s `event_amended`
#: branch imports it so the two cannot drift — that branch was the door the
#: original producer audit missed
#: (iterate-2026-07-28-grade-snapshot-honest-subject).
ATTRIBUTION_KEYS = frozenset({"lineage", "branch", "base"})

def reject_asserted_attribution(fields: dict[str, Any]) -> None:
    """Refuse an ``event_amended`` overlay that would assert attribution.

    ``apply_amendments`` folds ``fields`` onto its target with a blind merge — no
    allowlist, no target-type check — so without this the "derived, never
    asserted" property held on the producer path and leaked through the log's own
    mutator: an amendment could overlay ``lineage`` onto a snapshot and every
    amendment-folding reader would honour it. Reproduced before the fix; this is
    the same shape as the ``tests``-block validation that already guards that
    branch for the same reason.
    """
    asserted = ATTRIBUTION_KEYS & set(fields)
    if asserted:
        raise ValueError(
            f"event_amended --fields may not set {sorted(asserted)}: "
            "grade_snapshot attribution is derived from the tree, never asserted"
        )


def apply_grade_snapshot(
    event: dict[str, Any],
    *,
    grade: str | None,
    score: float | None,
    project_root: Path | str,
    commit: str | None = None,
) -> dict[str, Any]:
    """Validate, then write the ``grade_snapshot`` payload into ``event``.

    Raises ``ValueError`` for a missing grade/score or a score outside
    ``[0, 100]`` — and raises **before** mutating ``event``, so a rejected
    snapshot never leaves a half-written record behind.

    ``commit`` stays optional and omitted by default: the finalize-time regen
    runs before the F6 commit, so HEAD would name the *previous* commit and
    mislabel the snapshot. ``base`` (from the attribution below) is the field
    that answers "which tree", without that defect.

    Attribution never fails the caller. A resolver that raises degrades to
    ``lineage="unknown"`` rather than taking down a compliance regen — the same
    best-effort posture as the rest of the emitter.
    """
    if not grade or score is None:
        raise ValueError("grade_snapshot requires --grade and --score")
    score = float(score)
    if not 0.0 <= score <= 100.0:
        raise ValueError(f"grade_snapshot --score must be in [0, 100], got {score}")

    event["grade"] = grade
    event["score"] = score
    if commit:
        event["commit"] = commit

    try:
        event.update(lineage_fields(resolve_tree_lineage(project_root)))
    except Exception:  # noqa: BLE001 - metadata must never break the producer
        event["lineage"] = LINEAGE_UNKNOWN

    return event


__all__ = ["ATTRIBUTION_KEYS", "apply_grade_snapshot", "reject_asserted_attribution"]
