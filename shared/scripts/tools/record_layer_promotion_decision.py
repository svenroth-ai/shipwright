#!/usr/bin/env python3
"""The HUMAN-ONLY way to resolve a ``Layers``-promotion escalation or to
demote a requirement's binding (P3.5, campaign req3-04c-ac-identity-wave2).

``promote_required_layers.py`` — the automated mechanism — never calls this
script and never writes what this script writes. That split is the same one
``record_ci_supplychain_ack.py`` draws for the CI trust boundary, for the
same reason: "a machine authoring its own permission slip is exactly what the
ack checker exists to prevent" (``diff_risk_recheck`` module docstring). Once
an FR has ANY entry in the layer-promotion ledger, the automated tool never
revisits it again on its own (``lib.layer_promotion.evaluate_fr``) — only
this CLI, run by an operator, can add the next entry.

Two actions, and only two:

* ``--action promoted`` — record a human decision that this FR's binding
  should be explicit at ``--required-layers``, and apply that write to the
  FR's own spec.md (the same mechanical write the automated tool performs
  for a clean case — this is what actually clears a
  ``layer_undeterminable`` / ``bound_test_absent_from_ci`` escalation, or
  overrides a prior ``demoted`` entry). Requires ``--required-layers``.
* ``--action demoted`` — record that this FR must NOT be auto-promoted going
  forward. Use this to veto a specific FR the automated predicate would
  otherwise promote (case: the evidence looks green but is misleading for a
  reason the manifest cannot express). ``--required-layers`` must be
  omitted. Leaves spec.md untouched UNLESS the live cell is already explicit
  right now, in which case it reverts that cell to ``(inferred)``: otherwise
  the demotion would leave the cell explicit forever, and `evaluate_fr`'s
  demoted-branch `already_explicit` check has no exitability qualifier —
  every future run would re-escalate `contradicts_recorded_decision` with no
  way to clear it.

Usage::

    uv run shared/scripts/tools/record_layer_promotion_decision.py \\
      --project-root . --fr-id FR-01.11 --action promoted \\
      --required-layers unit,integration \\
      --reason "operator reviewed the AC08 binding directly; layers confirmed" \\
      --escalation-reason-code layer_undeterminable
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
    atomic_write_text,
    is_layers_cell_explicit_live,
    live_required_layers,
    resolve_spec_path_within_root,
    write_layers_cell,
)
from lib.fr_table_shape import render_layers  # noqa: E402
from lib.layer_promotion import (  # noqa: E402
    LAYER_RANK,
    REASON_BOUND_TEST_ABSENT,
    REASON_CONTRADICTS_DECISION,
    REASON_LAYER_UNDETERMINABLE,
)
from lib.layer_promotion_apply import ConcurrentSpecEditError  # noqa: E402
from lib.layer_promotion_ledger import (  # noqa: E402
    ConcurrentLedgerEditError,
    append_decision,
    evidence_fingerprint,
    ledger_lock_path,
    ledger_path,
    load_ledger_with_snapshot,
    write_ledger,
)

_ESCALATION_REASON_CODES = (
    REASON_LAYER_UNDETERMINABLE, REASON_BOUND_TEST_ABSENT, REASON_CONTRADICTS_DECISION,
)

DEFAULT_MANIFEST_RELPATH = ".shipwright/compliance/test-traceability.json"

#: Named, not inlined, and monkeypatchable by tests -- matches
#: `promote_required_layers._LOCK_TIMEOUT_SECONDS` on the same lock path.
_LOCK_TIMEOUT_SECONDS = 10.0


def _parse_layers(raw: str) -> list[str]:
    layers = [tok.strip() for tok in raw.split(",") if tok.strip()]
    unknown = [layer for layer in layers if layer not in LAYER_RANK]
    if unknown:
        raise SystemExit(
            f"--required-layers names unrecognised layer(s) {unknown} — "
            f"expected a subset of {sorted(LAYER_RANK)}"
        )
    return sorted(set(layers), key=lambda layer: LAYER_RANK[layer])


def _find_active_nodes(manifest: dict, fr_id: str) -> list[dict]:
    """Every ACTIVE manifest node named ``fr_id`` (zero, one, or — for a
    collision fan-out — more than one). Never raises; callers decide what an
    unexpected count means for their action."""
    return [
        node for node in (manifest.get("requirements") or {}).values()
        if isinstance(node, dict) and node.get("id") == fr_id and node.get("status") == "active"
    ]


def _find_node_for_promotion(manifest: dict, fr_id: str) -> dict:
    """The one ACTIVE manifest node named ``fr_id`` a ``--action promoted``
    write may target.

    Refuses (rather than taking the first match) when more than one ACTIVE
    node shares this display id — precisely the collision fan-out the
    automated tool's own ``layer_undeterminable`` escalation exists to flag;
    an operator resolving it must say which underlying node they mean, not
    have this CLI guess.
    """
    matches = _find_active_nodes(manifest, fr_id)
    if not matches:
        raise SystemExit(f"no ACTIVE requirement {fr_id!r} found in the manifest")
    if len(matches) > 1:
        raise SystemExit(
            f"{len(matches)} ACTIVE requirements share id {fr_id!r} — this is "
            "a collision fan-out; a promoted decision cannot say which "
            "underlying node it resolves. Use --action demoted to veto the "
            "collision id instead, or resolve the underlying id collision "
            "first."
        )
    return matches[0]


def _plan_decision(args, manifest: dict, project_root: Path) -> dict:
    """Everything about this decision computable WITHOUT touching the
    ledger: which node it targets (``None`` for an ambiguous demote), the
    parsed ``required_layers`` (promoted only), and the spec.md
    content/new-content pair to write, if any. Returns ``{"node",
    "required_layers", "spec_path", "content", "new_content"}`` — the last
    three ``None`` when nothing needs writing.
    """
    required_layers = None
    node = None
    spec_path = None
    new_content = None
    content = None
    if args.action == "promoted":
        node = _find_node_for_promotion(manifest, args.fr_id)
        if not node.get("spec_path"):
            raise SystemExit(f"requirement {args.fr_id!r} has no spec_path in the manifest")
        required_layers = _parse_layers(args.required_layers)
        try:
            spec_path = resolve_spec_path_within_root(project_root, node["spec_path"])
            content = spec_path.read_text(encoding="utf-8")
            cell = render_layers(required_layers, inferred=False)
            new_content = write_layers_cell(content, args.fr_id, cell)
        except (OSError, LayerCellWriteError) as exc:
            raise SystemExit(str(exc)) from exc
        # Computed only, NOT written yet — the ledger entry below must land
        # first: the reverse order left an explicit cell with no durable
        # record on a ledger-write failure, exactly what "cannot silently
        # demote" depends on the ledger to prevent.
    else:
        # A demotion is a veto, not a write — a collision fan-out (more than
        # one ACTIVE match) is not an obstacle here (the only way to clear a
        # collision escalation for good); the fingerprint is recorded only
        # when exactly one node resolves the id.
        matches = _find_active_nodes(manifest, args.fr_id)
        if not matches:
            raise SystemExit(f"no ACTIVE requirement {args.fr_id!r} found in the manifest")
        node = matches[0] if len(matches) == 1 else None
        # Demoting an ALREADY-explicit FR must not leave it explicit forever
        # — revert to `(inferred)` so the demoted invariant `evaluate_fr`
        # relies on to ever exit still holds. Skipped for a collision
        # fan-out (`node is None`): that arm never re-escalates on
        # `already_explicit`, so there is no per-node cell to rewrite.
        if node is not None:
            if not node.get("spec_path"):
                raise SystemExit(f"requirement {args.fr_id!r} has no spec_path in the manifest")
            try:
                spec_path = resolve_spec_path_within_root(project_root, node["spec_path"])
                content = spec_path.read_text(encoding="utf-8")
            except (OSError, LayerCellWriteError) as exc:
                raise SystemExit(str(exc)) from exc
            if is_layers_cell_explicit_live(content, args.fr_id):
                current_layers = live_required_layers(content, args.fr_id) or []
                try:
                    cell = render_layers(current_layers, inferred=True)
                    new_content = write_layers_cell(content, args.fr_id, cell)
                except LayerCellWriteError as exc:
                    raise SystemExit(str(exc)) from exc
    return {
        "node": node, "required_layers": required_layers,
        "spec_path": spec_path, "content": content, "new_content": new_content,
    }


def _spec_write_failure_message(args, node: dict, detail: str) -> str:
    """The message an operator sees when THIS CLI's ledger entry already
    landed but the spec.md write it depends on did not (Low finding,
    Stage-3 doubt-review round 2, P3.5 post-push round).

    Unlike the automated tool's matching exit-2 message — which must warn
    an operator that a plain re-run will NOT clear the gap, only
    ``record_layer_promotion_decision.py`` can — this path already IS that
    CLI: re-running the exact same command recomputes the write fresh from
    the current on-disk state and retries it. For ``--action demoted``
    specifically, the ledger already carries the demotion, so a retry's
    second, redundant ``demoted`` entry is harmless
    (``evaluate_fr``'s ledger-drift branches always read the LATEST entry,
    never accumulate) — the opposite framing from the automated tool's
    message, not a copy of it.
    """
    if args.action == "demoted":
        return (
            f"ledger recorded the demotion for {node['id']} but reverting its "
            f"now-orphaned explicit cell to (inferred) failed: {detail} — this "
            "state IS exitable: re-run the same --action demoted command for "
            "this FR to retry the revert (a harmless duplicate demoted entry "
            "is appended on each retry, evaluate_fr always reads the latest one)"
        )
    return (
        f"ledger recorded the promotion for {node['id']} but writing its "
        f"spec.md cell failed: {detail} — re-run the same --action promoted "
        "command for this FR to retry the write"
    )


def _decide_and_write_locked(args, manifest: dict, project_root: Path, l_path: Path) -> dict:
    """Runs inside the ledger's ``file_lock`` — closes the same residual
    race on the human-operator side of the ledger the automated tool holds
    on its own load-decide-write span. Returns ``{"written_path": ...,
    "entry": ...}``.
    """
    try:
        ledger, ledger_snapshot = load_ledger_with_snapshot(l_path)
    except (OSError, ValueError) as exc:
        # Stage-3 doubt-review round 2 (P3.5 post-push round): same fix as
        # promote_required_layers.py's matching call site -- `read_bytes()`
        # after `is_file()` can still raise OSError; every OTHER read site in
        # this mechanism already catches it, this was the one place it
        # wasn't. Fail-safe in outcome (nothing written) -- fixes the error
        # SHAPE only, an operator now gets this CLI's normal message instead
        # of a raw traceback.
        raise SystemExit(str(exc)) from exc

    plan = _plan_decision(args, manifest, project_root)
    node, spec_path = plan["node"], plan["spec_path"]
    content, new_content = plan["content"], plan["new_content"]

    entry = append_decision(
        ledger, args.fr_id, action=args.action, decided_by="operator",
        required_layers=plan["required_layers"], run_id=args.run_id, reason=args.reason,
        escalation_reason_code=args.escalation_reason_code,
        evidence_fingerprint=evidence_fingerprint(node) if node is not None else None,
    )
    try:
        write_ledger(l_path, ledger, expected_snapshot=ledger_snapshot)
    except ConcurrentLedgerEditError as exc:
        raise SystemExit(str(exc)) from exc

    # Ledger is durable now — safe to apply the spec.md write it just
    # recorded evidence for.
    written_path = None
    if new_content is not None and new_content != content:
        # Re-read-and-compare guard, mirroring `write_promotion_files`'s
        # `ConcurrentSpecEditError` exactly — this write previously had none.
        try:
            current_on_disk = spec_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SystemExit(_spec_write_failure_message(args, node, str(exc))) from exc
        if current_on_disk != content:
            raise ConcurrentSpecEditError(_spec_write_failure_message(
                args, node,
                f"{node['spec_path']} changed on disk since this decision was computed",
            ))
        atomic_write_text(spec_path, new_content)
        written_path = node["spec_path"]

    return {"written_path": written_path, "entry": entry}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--fr-id", required=True)
    parser.add_argument("--action", required=True, choices=("promoted", "demoted"))
    parser.add_argument("--required-layers", default=None,
                         help="comma-separated canonical layers; required for "
                              "--action promoted, forbidden for --action demoted")
    parser.add_argument("--reason", required=True,
                         help="why an operator is making this call — becomes part "
                              "of the permanent ledger record")
    parser.add_argument("--escalation-reason-code", default=None,
                         choices=_ESCALATION_REASON_CODES,
                         help="which of the three named undecidable cases this "
                              "decision resolves, if any")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)

    if args.action == "promoted" and not args.required_layers:
        raise SystemExit("--action promoted requires --required-layers")
    if args.action == "demoted" and args.required_layers:
        raise SystemExit("--action demoted must not carry --required-layers "
                          "(a demotion blocks promotion, it does not set one)")

    project_root = Path(args.project_root).resolve()
    manifest_path = Path(args.manifest) if args.manifest else project_root / DEFAULT_MANIFEST_RELPATH
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # An operator CLI must fail with a message naming the actual problem,
        # not an uncaught traceback.
        raise SystemExit(f"could not read manifest {manifest_path}: {exc}") from exc

    l_path = ledger_path(project_root)
    # Whole load-decide-write span under one lock, on the same path the
    # automated tool locks — see `_decide_and_write_locked`'s docstring.
    # Entered manually so only a lock-ACQUISITION failure gets this CLI's
    # SystemExit shape; a body OSError not already caught still propagates.
    lock_cm = file_lock(ledger_lock_path(project_root), timeout_seconds=_LOCK_TIMEOUT_SECONDS)
    try:
        lock_cm.__enter__()
    except (LockTimeout, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    try:
        outcome = _decide_and_write_locked(args, manifest, project_root, l_path)
    except ConcurrentSpecEditError as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        # file_lock's cleanup (`_release`) is exception-agnostic -- no need to
        # forward the real exc_info the generator never inspects.
        lock_cm.__exit__(None, None, None)

    print(json.dumps(
        {"written_spec_path": outcome["written_path"], "ledger_entry": outcome["entry"]},
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
