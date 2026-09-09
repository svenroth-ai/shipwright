"""Apply the ``promote`` decisions :func:`layer_promotion.evaluate_fr`
returned: fold each one's cell into memory, then write the ledger and the
spec.md cells it names, in that order (P3.5, campaign
req3-04c-ac-identity-wave2). Split out of ``tools/promote_required_layers.py``
(same file, three review rounds of fixes) to keep that CLI a thin shell —
same "extract, don't except" precedent as prior sub-iterates' 300-LOC splits.

**Two-phase per file, always**: :func:`compute_promotion_writes` folds every
promoted FR's new cell into that file's content IN MEMORY ONLY; a caller
writes to disk (:func:`write_promotion_files`) only once every fold for a
given ``spec_path`` has succeeded, so a mid-fold failure never leaves a
half-edited spec.md.

**Ledger before spec.md, always** (external code review, openai/medium +
glm/high, P3.5 rounds 1–2, both the automated tool and the human CLI): the
reverse order let a ledger-write failure leave an FR explicit with NO ledger
entry — the exact state "cannot silently demote" relies on the ledger to
prevent. Ledger-first bounds a failure to the opposite, CAUGHT case: a
ledger entry whose write never reached spec.md, which the next run sees as a
live/ledger mismatch and escalates ``contradicts_recorded_decision`` for.

**Refuses a concurrent edit, decide→write, not just fold→write** (external
code review, openai/medium, P3.5 round 3; span widened Stage-3 doubt-review
Medium finding, post-push round): :func:`write_promotion_files` re-reads
each file immediately before writing and raises
:class:`ConcurrentSpecEditError` if it no longer matches what the write was
computed against. That alone only covered fold→write — a THIRD, independent
read inside :func:`compute_promotion_writes` meant an edit landing between
the decision-time read (``promote_required_layers.plan_promotions``) and
the fold could slip through undetected. ``compute_promotion_writes`` now
accepts the caller's own already-read content as its fold base, so one read
backs both the decision and the guard.
"""

from __future__ import annotations

from pathlib import Path

try:  # Package context (shared/tests: `shared/scripts` on sys.path).
    from .fr_layer_cell_writer import (
        LayerCellWriteError,
        atomic_write_text,
        resolve_spec_path_within_root,
        write_layers_cell,
    )
    from .fr_table_shape import render_layers
    from .layer_promotion_ledger import append_decision, evidence_fingerprint
except ImportError:  # Loaded by file path.
    from fr_layer_cell_writer import (  # type: ignore
        LayerCellWriteError,
        atomic_write_text,
        resolve_spec_path_within_root,
        write_layers_cell,
    )
    from fr_table_shape import render_layers  # type: ignore
    from layer_promotion_ledger import append_decision, evidence_fingerprint  # type: ignore


class ConcurrentSpecEditError(RuntimeError):
    """A spec.md changed on disk between planning a promotion and writing
    it — the write is refused rather than silently clobbering whatever a
    maintainer changed in between."""


def compute_promotion_writes(
    project_root: Path, decisions: list[dict], contents_by_path: dict[str, str] | None = None,
) -> dict:
    """Fold every ``promote`` decision's new cell into its owning file's
    content, IN MEMORY ONLY — nothing is written to disk here.

    ``contents_by_path`` — when given (``promote_required_layers.
    plan_promotions`` passes its own already-read content) — is used as the
    fold BASE instead of a fresh read (Stage-3 doubt-review Medium finding,
    P3.5 post-push round): a second, independent read here previously let a
    maintainer edit land between the decision-time read and this one
    UNDETECTED — round-3's ``ConcurrentSpecEditError`` only ever compared
    THIS read against :func:`write_promotion_files`'s later one, never
    against the read the decision was actually made from. ``None`` (the
    default — every direct caller that builds ``decisions`` by hand, as the
    tests do) falls back to reading fresh, unchanged from before.
    """
    promotions = [d for d in decisions if d["action"] == "promote"]
    by_path: dict[str, list[dict]] = {}
    for decision in promotions:
        if not decision["spec_path"]:
            raise LayerCellWriteError(
                f"requirement {decision['fr']!r} has no spec_path in the manifest"
            )
        by_path.setdefault(decision["spec_path"], []).append(decision)

    contents: dict[str, str] = {}
    originals: dict[str, str] = {}
    promoted_frs: list[dict] = []
    for rel_path, group in by_path.items():
        if contents_by_path is not None and rel_path in contents_by_path:
            content = contents_by_path[rel_path]
        else:
            full_path = resolve_spec_path_within_root(project_root, rel_path)
            content = full_path.read_text(encoding="utf-8")
        originals[rel_path] = content
        for decision in group:
            cell = render_layers(decision["required_layers"], inferred=False)
            content = write_layers_cell(content, decision["fr"], cell)
        contents[rel_path] = content
        promoted_frs.extend(group)

    return {"contents": contents, "originals": originals, "promoted": promoted_frs}


def write_promotion_files(
    project_root: Path, contents: dict[str, str], originals: dict[str, str],
) -> list[str]:
    """Write each precomputed spec.md content to disk. Call ONLY after the
    ledger entries for these same promotions are already durable — see
    module docstring."""
    written: list[str] = []
    for rel_path, content in contents.items():
        full_path = resolve_spec_path_within_root(project_root, rel_path)
        current = full_path.read_text(encoding="utf-8")
        if current != originals[rel_path]:
            raise ConcurrentSpecEditError(
                f"{rel_path} changed on disk since this promotion was planned "
                "— refusing to overwrite; re-run to recompute against the "
                "current content"
            )
        if content != current:
            atomic_write_text(full_path, content)
            written.append(rel_path)
    return written


def record_ledger_entries(ledger: dict, promoted: list[dict], *, run_id: str | None) -> None:
    for decision in promoted:
        node = decision["_node"]
        # P3.5 restart, round 2: `decision["ci_evidence"]["run_id"]` (when present --
        # only `promote_required_layers.py`'s CI-aware caller sets it; a bare
        # hand-built `decision` dict, as most of this module's own unit tests use,
        # has neither key) names the GitHub Actions run whose execution evidence
        # this promotion was decided against, additive on `append_decision`.
        ci_run_id = (decision.get("ci_evidence") or {}).get("run_id")
        append_decision(
            ledger, decision["fr"], action="promoted", decided_by="tool",
            required_layers=decision["required_layers"], run_id=run_id,
            reason=(
                f"highest observable layer {decision['highest_ok']!r} ran "
                "executed-passing this run; binding promoted to match evidence"
            ),
            evidence_fingerprint=evidence_fingerprint(node),
            ci_run_id=ci_run_id,
        )


__all__ = [
    "ConcurrentSpecEditError",
    "compute_promotion_writes",
    "write_promotion_files",
    "record_ledger_entries",
]
