#!/usr/bin/env python3
"""Promote a requirement's ``Layers`` binding from advisory to explicit where
its own evidence justifies it (P3.5, campaign req3-04c-ac-identity-wave2).

Reads the already-generated ``test-traceability.json`` manifest (this tool
never regenerates it — that stays the compliance refresh's job) and the
layer-promotion ledger, decides EACH active requirement independently via
``lib.layer_promotion.evaluate_fr`` (never a sweep — see that module), and
writes exactly two kinds of artifact: the promoted FRs' ``Layers`` cells in
their owning ``spec.md``, and one new ledger entry per FR actually promoted.
An FR this run only SKIPS or ESCALATES is never written to either place.

**Process contract, deliberately the same shape as
``plugins/shipwright-iterate/scripts/lib/diff_risk_recheck.py``** (sub-iterate
spec, "How an escalation is implemented"): ``0`` — the run decided everything
it looked at (some may still be promoted, most typically skipped, none
escalated). ``3`` — at least one FR hit one of the three named undecidable
cases; this is a valid hand-back, not a failure, and every FR that DID decide
cleanly this run is still written. Any other non-zero is an operational
failure (bad manifest, an unwritable spec, a ledger that fails to parse).

**This tool never resolves its own escalation.** Clearing one needs the
human-operated ``record_layer_promotion_decision.py``, which is the only
writer allowed to record a ``"demoted"`` entry or to override a prior
decision — mirroring ``diff_risk_recheck``'s two load-bearing properties: the
automated run never authors its own permission slip, and a resolution is
trusted by content (an evidence fingerprint), not by mere presence.

Usage::

    uv run shared/scripts/tools/promote_required_layers.py \\
      --project-root . --run-id iterate-YYYY-MM-DD-slug
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.file_lock import LockTimeout, file_lock  # noqa: E402
from lib.fr_layer_cell_writer import (  # noqa: E402
    LayerCellWriteError,
    live_cell_has_non_canonical_content,
    live_declared_layers,
    live_required_layers,
    resolve_spec_path_within_root,
)
from lib.layer_promotion import evaluate_fr  # noqa: E402
from lib.layer_promotion_apply import (  # noqa: E402
    ConcurrentSpecEditError,
    compute_promotion_writes,
    record_ledger_entries,
    write_promotion_files,
)
from lib.layer_promotion_ledger import (  # noqa: E402
    ConcurrentLedgerEditError,
    fingerprint_drifted,
    latest_decision,
    ledger_lock_path,
    ledger_path,
    load_ledger_with_snapshot,
    write_ledger,
)
from tools.verifiers._layer_coverage_core import collision_display_ids  # noqa: E402

DEFAULT_MANIFEST_RELPATH = ".shipwright/compliance/test-traceability.json"

#: Named, not inlined, and monkeypatchable by tests -- longer than
#: `file_lock`'s other short-append callers because this hold spans a full
#: load-decide-write span.
_LOCK_TIMEOUT_SECONDS = 10.0


def _active_requirements(manifest: dict) -> dict[str, dict]:
    return {
        key: node
        for key, node in (manifest.get("requirements") or {}).items()
        if isinstance(node, dict) and node.get("status") == "active"
    }


def plan_promotions(
    manifest: dict, ledger: dict, project_root: Path,
) -> tuple[list[dict], dict[str, str]]:
    """One decision per active requirement, plus the exact spec.md content
    each decision was made against.

    Reads each referenced ``spec.md`` ONCE (grouped by ``spec_path``) to
    re-derive ``required_layers_source`` LIVE rather than trusting the
    manifest's own stale copy (it can still say ``inferred_legacy`` for an
    FR a PRIOR run of this tool already promoted this session — see
    ``fr_layer_cell_writer.is_layers_cell_explicit_live``).

    The manifest's ``required_layers`` is NOT used as-is: it is unioned with
    ``live_declared_layers`` — what the cell ACTUALLY declares right now,
    inferred or explicit — before evaluation. A stale manifest can only
    under-report what a live cell already declares, never over-report it, so
    this union only ever WIDENS ``required_before`` — the same "widen, never
    narrow" direction the evaluator already commits to elsewhere. Without
    it, an inferred cell reading ``unit, e2e (inferred)`` against a stale
    manifest still saying ``["unit"]`` let a promotion silently drop the
    hand-declared ``e2e`` on rewrite.

    Also detects, per FR, whether the live cell carries any text a
    promotion's rewrite would delete (``fr_layer_cell_writer.
    live_cell_has_non_canonical_content``) — the same "widen never narrow"
    direction applied to the cell's raw TEXT, not just its canonical layer
    SET (Stage-3 doubt-review round 2, P3.5 post-push round); ``evaluate_fr``
    skips rather than promotes when it is set (Stage-1 spec-review REJECT,
    P3.5 post-push round, corrected the fix from an escalation to a named
    skip — see ``layer_promotion.SKIP_LIVE_CELL_HAS_RESIDUAL_TEXT``).

    The returned content map is the SAME read used to decide — the caller
    passes it to :func:`layer_promotion_apply.compute_promotion_writes` as
    ``contents_by_path`` so the concurrency guard spans decide→write, not
    merely fold→write (a second, independent read there previously let a
    maintainer edit land between the two undetected).
    """
    collisions = collision_display_ids(manifest)
    active = _active_requirements(manifest)

    by_path: dict[str, list[dict]] = {}
    for node in active.values():
        by_path.setdefault(node.get("spec_path", ""), []).append(node)
    live_explicit: dict[str, bool] = {}
    live_layers: dict[str, list[str] | None] = {}
    live_declared: dict[str, list[str] | None] = {}
    live_has_residual: dict[str, bool] = {}
    contents_by_path: dict[str, str] = {}
    for rel_path, nodes in by_path.items():
        full_path = resolve_spec_path_within_root(project_root, rel_path)
        content = full_path.read_text(encoding="utf-8") if full_path.is_file() else ""
        contents_by_path[rel_path] = content
        for node in nodes:
            # `is_layers_cell_explicit_live` is literally `live_required_layers(...)
            # is not None` -- reuse this call's result instead of a second,
            # redundant parse of the same (content, fr_id) pair.
            layers = live_required_layers(content, node["id"]) if content else None
            live_layers[node["id"]] = layers
            live_explicit[node["id"]] = bool(content) and layers is not None
            live_declared[node["id"]] = live_declared_layers(content, node["id"]) if content else None
            live_has_residual[node["id"]] = (
                live_cell_has_non_canonical_content(content, node["id"]) if content else False
            )

    decisions = []
    for node in active.values():
        fr_id = node["id"]
        eval_node = dict(node)
        if live_explicit.get(fr_id):
            eval_node["required_layers_source"] = "explicit"
        elif eval_node.get("required_layers_source") == "explicit":
            # The manifest claims explicit but the live document does not —
            # never trust the stale claim UPWARD; fall back to the coarser
            # legacy label so the branch below evaluates it fresh, not as
            # already-settled on data this run knows is out of date.
            eval_node["required_layers_source"] = "inferred_legacy"
        eval_node["required_layers"] = sorted(
            set(node.get("required_layers") or []) | set(live_declared.get(fr_id) or []),
        )
        ledger_entry = latest_decision(ledger, fr_id)
        decision = evaluate_fr(
            eval_node, is_collision=fr_id in collisions, ledger_entry=ledger_entry,
            live_required_layers=live_layers.get(fr_id),
            live_cell_has_non_canonical_content=live_has_residual.get(fr_id, False),
        )
        decision["spec_path"] = node.get("spec_path", "")
        decision["_node"] = node
        # "Validated on content, not presence" (diff_risk_recheck) made real:
        # any FR with a prior ledger entry gets a report of whether today's
        # evidence still matches it. For a `promoted` entry this is purely
        # informational (the live-document comparison above already, more
        # strongly, catches drift); for a `demoted` entry it is what
        # `evaluate_fr` itself now consumes to decide whether the veto's
        # "exitable" wall re-escalates — corrected from the original "a
        # demotion is deliberately evidence-independent" assumption.
        if ledger_entry is not None:
            decision["ledger_fingerprint_drifted"] = fingerprint_drifted(ledger_entry, node)
        decisions.append(decision)
    return decisions, contents_by_path


def _strip_internal(decision: dict) -> dict:
    return {k: v for k, v in decision.items() if not k.startswith("_")}


def _plan_and_apply_locked(manifest: dict, project_root: Path, l_path: Path, run_id: str | None) -> dict:
    """Runs inside the ledger's ``file_lock``: ``write_ledger``'s
    ``expected_snapshot`` compare-and-swap alone only narrows the race (its
    re-read is not atomic WITH the replace) — holding this lock across the
    whole load→decide→write span is what closes it.

    Returns a dict with an ``"exit_code"`` key: 2 means an operational error
    already printed to stdout; 0/3 means the caller should build and print
    the normal decisions report.
    """
    try:
        ledger, ledger_snapshot = load_ledger_with_snapshot(l_path)
    except (OSError, ValueError) as exc:
        # Stage-3 doubt-review round 2 (P3.5 post-push round): `read_bytes()`
        # after `is_file()` can still raise OSError (a permissions error, or
        # the path becoming a directory between the two calls) -- every OTHER
        # read site in this mechanism (the manifest, both spec.md reads,
        # write_ledger's own OSError) already catches it; this was the one
        # place it wasn't, escaping as a raw traceback instead of this CLI's
        # normal JSON error shape. Fail-safe in outcome either way (nothing
        # written, the lock still releases via `finally`) -- this only fixes
        # the error SHAPE.
        print(json.dumps({"error": str(exc)}))
        return {"exit_code": 2}

    try:
        decisions, contents_by_path = plan_promotions(manifest, ledger, project_root)
    except (OSError, LayerCellWriteError) as exc:
        print(json.dumps({"error": f"could not read a spec.md: {exc}"}))
        return {"exit_code": 2}

    try:
        computed = compute_promotion_writes(project_root, decisions, contents_by_path)
    except (OSError, LayerCellWriteError) as exc:
        print(json.dumps({"error": f"could not compute a promotion write: {exc}"}))
        return {"exit_code": 2}

    # Ledger BEFORE spec.md, deliberately (see write_promotion_files'
    # docstring): a failure between the two must never leave an explicit
    # cell with no durable evidence record behind it.
    written_paths: list[str] = []
    if computed["promoted"]:
        record_ledger_entries(ledger, computed["promoted"], run_id=run_id)
        try:
            write_ledger(l_path, ledger, expected_snapshot=ledger_snapshot)
        except OSError as exc:
            print(json.dumps({"error": f"could not write the ledger: {exc}"}))
            return {"exit_code": 2}
        except ConcurrentLedgerEditError as exc:
            print(json.dumps({"error": str(exc)}))
            return {"exit_code": 2}
        try:
            written_paths = write_promotion_files(
                project_root, computed["contents"], computed["originals"],
            )
        except (OSError, ConcurrentSpecEditError) as exc:
            print(json.dumps({
                "error": f"ledger recorded but could not write a promoted spec.md: {exc} "
                         "— NOT a transient failure to retry: the ledger already carries "
                         "a promoted entry for the affected FR(s), so any subsequent run "
                         "sees a live/ledger mismatch and escalates "
                         "contradicts_recorded_decision until an operator resolves it via "
                         "record_layer_promotion_decision.py. Not a local failure: the "
                         "enforcement gate this ledger feeds reads the SAME mismatch "
                         "repo-wide, reddening the whole CI suite, not only this FR",
            }))
            return {"exit_code": 2}
    return {
        "exit_code": None, "decisions": decisions,
        "written_spec_paths": sorted(written_paths), "promoted": computed["promoted"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--manifest", default=None,
                         help=f"defaults to {DEFAULT_MANIFEST_RELPATH!r} under --project-root")
    parser.add_argument("--run-id", default=None,
                         help="recorded on every ledger entry this run writes")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    manifest_path = Path(args.manifest) if args.manifest else project_root / DEFAULT_MANIFEST_RELPATH

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": f"could not read manifest {manifest_path}: {exc}"}))
        return 2

    l_path = ledger_path(project_root)
    # Whole load-decide-write span under one lock — see
    # `_plan_and_apply_locked`'s docstring. Entered manually, not via a plain
    # `with`, so only a lock-ACQUISITION failure (LockTimeout, or open()'s/
    # mkdir()'s OSError) gets this CLI's error shape; a body OSError
    # `_plan_and_apply_locked` does not already catch still propagates.
    lock_cm = file_lock(ledger_lock_path(project_root), timeout_seconds=_LOCK_TIMEOUT_SECONDS)
    try:
        lock_cm.__enter__()
    except (LockTimeout, OSError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    try:
        outcome = _plan_and_apply_locked(manifest, project_root, l_path, args.run_id)
    finally:
        # file_lock's cleanup (`_release`) is exception-agnostic -- no need to
        # forward the real exc_info the generator never inspects.
        lock_cm.__exit__(None, None, None)
    if outcome["exit_code"] is not None:
        return outcome["exit_code"]

    decisions = outcome["decisions"]
    escalated = [_strip_internal(d) for d in decisions if d["action"] == "escalate"]
    result = {
        "promoted": [_strip_internal(d) for d in outcome["promoted"]],
        "written_spec_paths": outcome["written_spec_paths"],
        "skipped": [_strip_internal(d) for d in decisions if d["action"] == "skip"],
        "escalated": escalated,
    }
    # Sub-iterate spec's own safety valve, made a REPORT rather than a fourth
    # machine-enforced exit code (external plan review, glm/low, P3.5: "most"
    # is undefined) — escalating over half of what this run looked at is a
    # signal the PREDICATE is wrong, not that twenty FRs each independently
    # need a person. This never changes the exit code: every clean decision
    # this run made is still applied, and the human reading this report is
    # the one who decides whether to keep routing per-FR or to stop and
    # revisit the mechanism.
    if decisions and len(escalated) > len(decisions) / 2:
        result["sweep_signal_warning"] = (
            f"{len(escalated)} of {len(decisions)} requirements escalated this "
            "run — over half. Expected volume is zero to a handful; this many "
            "suggests the predicate itself needs revisiting, not that each one "
            "independently needs an operator."
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 3 if escalated else 0


if __name__ == "__main__":
    sys.exit(main())
