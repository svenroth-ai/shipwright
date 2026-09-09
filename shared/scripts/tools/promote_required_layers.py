#!/usr/bin/env python3
"""Promote a requirement's ``Layers`` binding from advisory to explicit where
its own CI-CONFIRMED evidence justifies it (P3.5, campaign
req3-04c-ac-identity-wave2, restart round 2 —
``.shipwright/planning/iterate/2026-09-09-p3-5-promote-layers-per-fr-restart.md``).

Reads the manifest at the EXACT commit ``HEAD`` names (never the working-tree
copy — see :func:`_read_committed_manifest`) and the layer-promotion ledger,
decides EACH active requirement independently via ``lib.layer_promotion.
evaluate_fr`` (never a sweep — see that module), and writes exactly two kinds
of artifact: the promoted FRs' ``Layers`` cells in their owning ``spec.md``,
and one new ledger entry per FR actually promoted. An FR this run only SKIPS
or ESCALATES is never written to either place.

**What changed in the restart (round 2), and why:** the first attempt (PR
#690) evaluated ``coverage``/``tests`` straight out of the committed manifest
— an assertion, not evidence. This version REPLACES those two fields per FR
with what ``ci_execution_evidence.resolve_execution_evidence`` confirms was
produced by the exact GitHub Actions run ``ci_provenance.
resolve_ci_verification`` already trusts for that commit's manifest
STRUCTURE. The committed file's own ``coverage``/``tests`` values are never
read for the promotion predicate again once CI evidence is being consulted at
all — a hand-edited claim in that file cannot influence a promotion.

**Process contract, deliberately the same shape as
``plugins/shipwright-iterate/scripts/lib/diff_risk_recheck.py``** (sub-iterate
spec, "How an escalation is implemented"): ``0`` — the run decided everything
it looked at (some may still be promoted, most typically skipped, none
escalated). ``3`` — at least one FR hit one of the three named undecidable
cases; this is a valid hand-back, not a failure, and every FR that DID decide
cleanly this run is still written. Any other non-zero is an OPERATIONAL
failure (bad manifest, an unwritable spec, a ledger that fails to parse, OR
— round 2 — execution evidence itself could not be resolved at all
(``ExecutionEvidence.status == "error"``); this is deliberately distinct from
``"unavailable"`` (a defined, non-fatal "no CI confirmation yet," which
degrades every affected FR to a normal ``skip`` and still exits 0/3): an
unresolved query must never silently read as "everything decided as skip.").

**This tool never resolves its own escalation.** Clearing one needs the
human-operated ``record_layer_promotion_decision.py``, which is the only
writer allowed to record a ``"demoted"`` entry or to override a prior
decision — mirroring ``diff_risk_recheck``'s two load-bearing properties: the
automated run never authors its own permission slip, and a resolution is
trusted by content (an evidence fingerprint), not by mere presence.

Usage::

    uv run shared/scripts/tools/promote_required_layers.py \\
      --project-root . --run-id iterate-YYYY-MM-DD-slug

``--manifest`` is a READ-ONLY, DRY-RUN-ONLY override for local inspection
(e.g. "what would this decide against a locally-modified copy") — when set,
no ledger entry and no spec.md write ever happen, regardless of what the run
decides, because any manifest other than the one actually committed at
``HEAD`` makes the (HEAD-commit-bound) execution evidence describe a
different document than what would really be evaluated.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from ci_execution_evidence import ExecutionEvidence, resolve_execution_evidence  # noqa: E402
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
    load_ledger,
    load_ledger_with_snapshot,
    write_ledger,
)
from tools.verifiers._layer_coverage_core import collision_display_ids  # noqa: E402

DEFAULT_MANIFEST_RELPATH = ".shipwright/compliance/test-traceability.json"

#: Named, not inlined, and monkeypatchable by tests -- longer than
#: `file_lock`'s other short-append callers because this hold spans a full
#: load-decide-write span.
_LOCK_TIMEOUT_SECONDS = 10.0

_GIT_TIMEOUT_SECONDS = 15


class CommittedManifestReadError(Exception):
    """``HEAD`` could not be resolved, or the manifest could not be read at
    that exact commit via ``git show``."""


def _read_committed_manifest(project_root: Path) -> tuple[str, dict]:
    """Resolve ``HEAD`` ONCE, then read the manifest AT THAT EXACT SHA via
    ``git show`` — never the working-tree file. TOCTOU-free by construction
    (round 2, replaces the original design's "compare on-disk to `git show`,
    then read on-disk" guard, which still had a live race between its own
    check and its later read): there is exactly one commit-pinned read of
    the manifest in this whole tool, reused for BOTH the real evaluation
    input and (by the caller, unmodified) the content-binding check inside
    ``resolve_execution_evidence``, so they cannot disagree about which
    commit's manifest is in play.

    Deliberately NOT a reuse of ``ci_manifest_drift_check.
    capture_committed_manifest`` — that function hardcodes the literal
    ``HEAD:`` ref with no commit parameter, so it cannot be pinned to the SHA
    this call already resolved.
    """
    try:
        rev = subprocess.run(  # nosec B603,B607 - fixed argv, shell=False
            ["git", "-C", str(project_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=_GIT_TIMEOUT_SECONDS,
            encoding="utf-8", errors="replace", check=False, shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CommittedManifestReadError(f"could not run 'git rev-parse HEAD': {exc}") from exc
    if rev.returncode != 0:
        raise CommittedManifestReadError(f"'git rev-parse HEAD' failed: {rev.stderr.strip()}")
    sha = rev.stdout.strip()
    if not sha:
        raise CommittedManifestReadError("'git rev-parse HEAD' returned an empty SHA")

    try:
        show = subprocess.run(  # nosec B603,B607 - fixed argv, shell=False
            ["git", "-C", str(project_root), "show", f"{sha}:{DEFAULT_MANIFEST_RELPATH}"],
            capture_output=True, text=True, timeout=_GIT_TIMEOUT_SECONDS,
            encoding="utf-8", errors="replace", check=False, shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CommittedManifestReadError(f"could not run 'git show {sha}:...': {exc}") from exc
    if show.returncode != 0:
        raise CommittedManifestReadError(
            f"could not read {DEFAULT_MANIFEST_RELPATH!r} at {sha}: {show.stderr.strip()}"
        )
    try:
        manifest = json.loads(show.stdout)
    except ValueError as exc:
        raise CommittedManifestReadError(f"manifest at {sha} is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise CommittedManifestReadError(f"manifest at {sha} is not a JSON object")
    return sha, manifest


def _active_requirements(manifest: dict) -> dict[str, dict]:
    return {
        key: node
        for key, node in (manifest.get("requirements") or {}).items()
        if isinstance(node, dict) and node.get("status") == "active"
    }


def plan_promotions(
    manifest: dict, ledger: dict, project_root: Path, evidence: ExecutionEvidence,
) -> tuple[list[dict], dict[str, str]]:
    """One decision per active requirement, plus the exact spec.md content
    each decision was made against.

    ``evidence`` (round 2, restart): CI-confirmed per-FR ``tests``/
    ``coverage``, resolved ONCE by the caller for the whole run (never
    per-FR — the commit is the same for every FR this run looks at).
    ``evidence.requirements.get(fr_id)`` REPLACES — never merges with —
    the committed manifest node's own ``tests``/``coverage`` before
    ``evaluate_fr`` ever sees them: once CI evidence is being consulted at
    all, the committed file's own claims about those two fields are never
    read again. An FR absent from ``evidence.requirements`` (including the
    whole-run case, ``evidence.status == "unavailable"``, where it is
    always empty) evaluates against ``{}``/``{}`` — ``evaluate_fr``'s
    existing branches already treat that identically to "no evidence yet"
    (see the design doc's realistic-shape trace); no evaluator code change
    was needed for this.

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
    ci_by_fr = evidence.requirements or {}

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
        # REPLACE, never merge (round 2): the committed file's own coverage/
        # tests are never read again once CI evidence is being consulted at
        # all -- this is what makes a hand-edited `coverage: ok` in the
        # committed file irrelevant to the predicate, not merely harder to
        # abuse. `ci_node` is `None` for any FR CI has not (yet) confirmed;
        # `{} or {}` normalises both "absent" and an explicit `{}` the same.
        ci_node = ci_by_fr.get(fr_id)
        eval_node["coverage"] = (ci_node or {}).get("coverage") or {}
        eval_node["tests"] = (ci_node or {}).get("tests") or {}
        ledger_entry = latest_decision(ledger, fr_id)
        decision = evaluate_fr(
            eval_node, is_collision=fr_id in collisions, ledger_entry=ledger_entry,
            live_required_layers=live_layers.get(fr_id),
            live_cell_has_non_canonical_content=live_has_residual.get(fr_id, False),
        )
        decision["spec_path"] = node.get("spec_path", "")
        # CHANGED (round 2): was `node` (the raw committed node, whose
        # coverage/tests are exactly the untrusted claim this restart exists
        # to stop reading). Now `eval_node`, the CI-sourced node -- so the
        # ledger's `evidence_fingerprint` (layer_promotion_apply.
        # record_ledger_entries) durably records what was ACTUALLY used to
        # decide, not the committed file's own copy of the same fields.
        decision["_node"] = eval_node
        # NEW (round 2), report-only, never read back by any decision logic:
        # lets a report reader distinguish "no evidence exists anywhere" from
        # "evidence exists locally but CI hasn't confirmed it yet" without
        # either becoming a different action/reason_code (p3.4c's own
        # "Honesty rule": reported, never asserted).
        decision["ci_evidence"] = {
            "status": evidence.status, "run_id": evidence.run_id,
            "fr_confirmed": ci_node is not None,
        }
        # "Validated on content, not presence" (diff_risk_recheck) made real:
        # any FR with a prior ledger entry gets a report of whether today's
        # evidence still matches it. For a `promoted` entry this is purely
        # informational (the live-document comparison above already, more
        # strongly, catches drift); for a `demoted` entry it is what
        # `evaluate_fr` itself now consumes to decide whether the veto's
        # "exitable" wall re-escalates — corrected from the original "a
        # demotion is deliberately evidence-independent" assumption. Compared
        # against `eval_node` (round 2), not the raw `node`, so this report
        # field agrees with what `evaluate_fr` itself just compared
        # internally via the SAME `eval_node` it was called with.
        if ledger_entry is not None:
            decision["ledger_fingerprint_drifted"] = fingerprint_drifted(ledger_entry, eval_node)
        decisions.append(decision)
    return decisions, contents_by_path


def _strip_internal(decision: dict) -> dict:
    return {k: v for k, v in decision.items() if not k.startswith("_")}


def _plan_and_apply_locked(
    manifest: dict, project_root: Path, l_path: Path, run_id: str | None, evidence: ExecutionEvidence,
) -> dict:
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
        decisions, contents_by_path = plan_promotions(manifest, ledger, project_root, evidence)
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


def _build_result(decisions: list[dict], written_spec_paths: list[str], promoted: list[dict]) -> dict:
    escalated = [_strip_internal(d) for d in decisions if d["action"] == "escalate"]
    result = {
        "promoted": [_strip_internal(d) for d in promoted],
        "written_spec_paths": written_spec_paths,
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
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument(
        "--manifest", default=None,
        help="READ-ONLY, DRY-RUN-ONLY override for local inspection — points at a manifest "
             "OTHER than the one actually committed at HEAD. When set, no ledger entry and no "
             "spec.md write ever happen, regardless of what this run decides; the default "
             "(unset) reads the committed manifest at HEAD via 'git show', never the "
             "working-tree copy.",
    )
    parser.add_argument("--run-id", default=None,
                         help="recorded on every ledger entry this run writes")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()

    try:
        sha, committed_manifest = _read_committed_manifest(project_root)
    except CommittedManifestReadError as exc:
        print(json.dumps({"error": f"could not read the committed manifest at HEAD: {exc}"}))
        return 2

    dry_run = args.manifest is not None
    if dry_run:
        try:
            eval_manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(json.dumps({"error": f"could not read manifest {args.manifest}: {exc}"}))
            return 2
    else:
        eval_manifest = committed_manifest

    # Round 2 (blocking change 4b): resolved ONCE, against the TRUE committed
    # manifest regardless of `--manifest` -- the execution evidence's own
    # content-binding check is meaningless against anything else, and a
    # dry-run inspection is still informative when compared against real
    # committed structure.
    evidence = resolve_execution_evidence(sha, committed_manifest=committed_manifest, project_root=project_root)
    if evidence.status == "error":
        # OPERATIONAL failure, never a silent skip-all: `ci_by_fr = {}` on
        # ANY non-"confirmed" status would otherwise be indistinguishable
        # from the correct, honest "unavailable" steady state -- exit 2
        # here, before `plan_promotions` ever runs, same shape as every
        # other `{"error": ...}` exit-2 case in this CLI.
        print(json.dumps({"error": f"execution evidence could not be resolved: {evidence.detail}"}))
        return 2

    if dry_run:
        # No lock, no write: a plain read-only report of what WOULD happen.
        # Same try/except shape as `_plan_and_apply_locked`'s own two calls
        # to these functions (external code review, glm/medium, P3.5 restart
        # round 3: this branch had none, so a corrupted ledger or an
        # unreadable spec.md escaped here as a raw traceback instead of the
        # CLI's documented `{"error": ...}` exit-2 shape — the very shape
        # every OTHER path in this CLI guarantees).
        try:
            ledger = load_ledger(ledger_path(project_root))
        except (OSError, ValueError) as exc:
            print(json.dumps({"error": str(exc)}))
            return 2
        try:
            decisions, _contents_by_path = plan_promotions(eval_manifest, ledger, project_root, evidence)
        except (OSError, LayerCellWriteError) as exc:
            print(json.dumps({"error": f"could not read a spec.md: {exc}"}))
            return 2
        promoted = [d for d in decisions if d["action"] == "promote"]
        result = _build_result(decisions, written_spec_paths=[], promoted=promoted)
        result["dry_run"] = True
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 3 if result["escalated"] else 0

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
        outcome = _plan_and_apply_locked(eval_manifest, project_root, l_path, args.run_id, evidence)
    finally:
        # file_lock's cleanup (`_release`) is exception-agnostic -- no need to
        # forward the real exc_info the generator never inspects.
        lock_cm.__exit__(None, None, None)
    if outcome["exit_code"] is not None:
        return outcome["exit_code"]

    result = _build_result(outcome["decisions"], outcome["written_spec_paths"], outcome["promoted"])
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 3 if result["escalated"] else 0


if __name__ == "__main__":
    sys.exit(main())
