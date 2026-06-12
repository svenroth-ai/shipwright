#!/usr/bin/env python3
"""Compact the triage backlog by dropping pure machine-churn dismissals.

Sub-iterate B of campaign ``2026-06-05-track-triage-jsonl`` — a one-off
maintenance tool run **before** ``.shipwright/triage.jsonl`` becomes
git-tracked (sub-iterate C), so the churn produced by background producers
does not enter permanent history.

Policy (decided 2026-06-05): **machine-churn ONLY**. The dismissed pile is
~half *human-curated* (hand-written reasons: re-prioritisations, "resolved
by PR #N", supersessions) — that is real audit history and is **kept**. An
item is droppable iff its final status is ``dismissed`` AND it was dismissed
by a background producer (``statusBy`` in the producer set) AND its
``statusReason`` is an exact machine auto-resolve token. Both conditions
must hold, so a human dismissal that happens to reuse a token survives.

``promoted`` and open (``triage``/``snoozed``) items are never dropped.

The triage store is an append-only event log (``append`` + ``status``
events, both carrying ``id``). "Dropping" an item means rewriting the log
without that item's lines — a destructive compaction. Therefore:

- **dry-run is the default**; ``--apply`` is required to rewrite.
- ``--apply`` writes a ``.bak`` backup first and re-validates the result
  (header intact, no orphan ``status`` events, no droppable item survives).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Make the triage store importable whether invoked from the repo root or
# elsewhere (mirrors the audit_detector lazy-import shim).
_SHARED_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import triage  # noqa: E402

# Pure background-producer dismissers (NOT user/operator/webui/cli/manual).
MACHINE_DISMISSERS = frozenset({
    "sbomGenerator",
    "auditDetector",
    "driftDetector",
    "f05Detector",
    "githubImporter",
    "complianceBacklog",
    "phaseQualityBacklog",  # phase_quality _triage_bundle producer
    "testEvidence",         # shipwright-compliance test_evidence producer
})

# Exact machine auto-resolve tokens. A human free-text reason (even one that
# starts with one of these) will not match — exact equality only.
MACHINE_REASONS = frozenset({
    "sbomResolved",
    "auditResolved",  # legacy: pre-bundle audit dismissals; no current emitter (audit now → complianceBacklog)
    "driftResolved",
    "f05Resolved",
    "githubResolved",
    "complianceResolved",
    "complianceRefreshed",  # stale-signature backlog rollup superseded (triage_bundle ~L165)
    "phaseQualityResolved",
    "phaseQualityRefreshed",  # F30: stale-signature phase-quality rollup superseded (phase_quality/_triage_bundle ~L268)
    "testEvidenceResolved",
    "prChecksResolved",  # github_triage PR-CI: a tracked PR's failing checks went green (resolve_pr_ci, by=githubImporter). prMerged/prClosed are terminal lifecycle markers, kept as history (not *Resolved churn).
})


def is_machine_churn(item: dict) -> bool:
    """True iff ``item`` is a pure producer auto-resolve dismissal."""
    return (
        item.get("status") == "dismissed"
        and item.get("statusBy") in MACHINE_DISMISSERS
        and item.get("statusReason") in MACHINE_REASONS
    )


def _resolve_tracked_only(project_root: Path | str) -> list[dict]:
    """Resolve items from the TRACKED store only (ignore the outbox).

    D1: GC compacts the durable tracked log; the gitignored outbox is the D2
    sweep's concern. Mirrors ``triage.read_all_items`` resolution (append +
    last-status-wins) but over a single file so GC never touches outbox state.
    """
    resolved: dict[str, dict] = {}
    for raw in triage._iter_raw_lines_at(triage._triage_path(project_root)):
        if not isinstance(raw, dict):
            continue
        event = raw.get("event")
        if event == "append":
            item_id = raw.get("id")
            if not isinstance(item_id, str):
                continue
            item = {k: v for k, v in raw.items() if k != "event"}
            item["statusBy"] = None
            item["statusReason"] = None
            resolved[item_id] = item
        elif event == "status":
            item_id = raw.get("id")
            if not isinstance(item_id, str) or item_id not in resolved:
                continue
            item = resolved[item_id]
            new_status = raw.get("newStatus")
            if new_status in triage.STATUSES:
                item["status"] = new_status
            item["statusBy"] = raw.get("by")
            item["statusReason"] = raw.get("reason")
    return list(resolved.values())


def plan_gc(project_root: Path | str) -> dict:
    """Compute the GC plan without writing anything.

    Operates on the TRACKED store only (D1) — the outbox is GC'd by the D2
    sweep, never by this CLI.

    Returns ``{"drop_ids": set, "dropped": [item...], "kept_count": int,
    "total": int}``.
    """
    items = _resolve_tracked_only(project_root)
    dropped = [i for i in items if is_machine_churn(i)]
    drop_ids = {i["id"] for i in dropped}
    return {
        "drop_ids": drop_ids,
        "dropped": dropped,
        "kept_count": len(items) - len(dropped),
        "total": len(items),
    }


def _union_droppable_ids(project_root: Path | str) -> set[str]:
    """Ids that are machine-churn by UNION residence (tracked ∪ outbox,
    last-status-wins — :func:`triage.read_all_items`).

    The under-lock recompute in :func:`apply_gc` uses THIS, not the tracked-only
    :func:`plan_gc`, so a concurrent re-open routed to the gitignored OUTBOX
    (idle-main-with-origin) flips the item out of the set and survives. The
    report stays tracked-only (D1); the intersection keeps it an upper bound.
    """
    return {
        i["id"] for i in triage.read_all_items(project_root)
        if is_machine_churn(i)
    }


def _validate_after(project_root: Path | str, drop_ids: set[str]) -> None:
    """Fail loudly if the rewrite produced an inconsistent TRACKED log.

    D1: GC compacts the tracked store only, so validation reads the tracked
    path directly (NOT the union ``read_all_items`` / ``_iter_raw_lines``) —
    otherwise an OUTBOX-resident status whose append GC just dropped from the
    tracked log would false-trip the orphan-status check, and an outbox item
    would count as a survivor.
    """
    raw = triage._iter_raw_lines_at(triage._triage_path(project_root))
    if not raw or raw[0].get("schema") != "triage":
        raise RuntimeError("post-GC validation: header missing or malformed")
    append_ids = {r.get("id") for r in raw if r.get("event") == "append"}
    for r in raw:
        if r.get("event") == "status" and r.get("id") not in append_ids:
            raise RuntimeError(
                f"post-GC validation: orphan status event for id={r.get('id')}"
            )
        if r.get("id") in drop_ids:
            raise RuntimeError(
                f"post-GC validation: dropped id={r.get('id')} still present"
            )
    survivors = {i["id"] for i in _resolve_tracked_only(project_root)}
    if survivors & drop_ids:
        raise RuntimeError("post-GC validation: a dropped item resolved as surviving")


def apply_gc(project_root: Path | str, drop_ids: set[str], backup: bool = True) -> Path:
    """Rewrite the log dropping the machine-churn lines. Returns the backup path
    (or the live path when ``backup`` is False). Holds the store's file lock.

    F19 (TOCTOU): the ``drop_ids`` argument is the plan the CALLER computed
    outside the lock (the dry-run report / ``main()`` short-circuit). The drop
    decision is **recomputed under the lock** here over UNION residence (tracked
    ∪ outbox, last-status-wins), intersected with the caller's plan, so a status
    flip appended BETWEEN plan and apply is honored regardless of which file it
    landed in — the tracked log (WebUI/producer on a branch) OR the gitignored
    outbox (idle-main-with-origin re-open). A re-opened item is no longer
    machine-churn under the fresh union plan and is NOT dropped. We still rewrite
    only the tracked file (D1); intersecting with the caller's set keeps the
    operator-facing report (printed from the stale tracked-only plan) an upper
    bound — apply never drops MORE than the report announced, only same-or-fewer.

    Refuses to rewrite if any non-blank line is malformed JSON — the tolerant
    reader would otherwise silently compact a corrupt line away (data loss). The
    rewrite is atomic (temp file + ``os.replace``) so a crash never truncates the
    live log; the ``.bak`` backup is written first.
    """
    path = triage._triage_path(project_root)
    with triage._FileLock(triage._lock_path(project_root)):
        original_text = path.read_text(encoding="utf-8") if path.exists() else ""
        for n, line in enumerate(original_text.splitlines(), start=1):
            if line.strip():
                try:
                    json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"triage_gc: refusing to rewrite — malformed JSON at line "
                        f"{n} ({exc.msg}); fix or remove it first"
                    )
        # Recompute UNDER the lock over union residence (see docstring): a
        # concurrent re-open in the tracked log OR the gitignored outbox flips
        # the item out of the set and survives. Closes the a1-6/F19 outbox-route
        # gap. Intersect with the caller's plan; rewrite only the tracked file.
        fresh_drop_ids = _union_droppable_ids(project_root)
        effective_drop_ids = fresh_drop_ids & set(drop_ids)
        # Tracked store only — never read/rewrite the gitignored outbox (D1).
        raw = triage._iter_raw_lines_at(triage._triage_path(project_root))
        kept = [
            r for r in raw
            if r.get("event") not in ("append", "status") or r.get("id") not in effective_drop_ids
        ]
        backup_path = path.with_suffix(path.suffix + ".bak")
        if backup and path.exists():
            backup_path.write_text(original_text, encoding="utf-8")
        new_text = "\n".join(
            json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in kept
        ) + "\n"
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fp:
            fp.write(new_text)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp, path)
        # Validate against the SET WE ACTUALLY DROPPED (F19): an id present in the
        # caller's stale plan but re-opened (so excluded from effective_drop_ids)
        # is legitimately still present — validating against the stale plan would
        # false-fail. Run under the lock so no concurrent writer interleaves.
        _validate_after(project_root, effective_drop_ids)
    return backup_path if backup else path


def _safe(value: object) -> str:
    """Console-encoding-safe string — triage titles/reasons can carry
    chars (e.g. ``→``) the Windows cp1252 console cannot encode, which
    would otherwise crash the report mid-print.
    """
    enc = sys.stdout.encoding or "utf-8"
    return str(value).encode(enc, errors="replace").decode(enc)


def _print_report(plan: dict, *, applied: bool) -> None:
    dropped = plan["dropped"]
    header = "APPLIED" if applied else "DRY-RUN (no changes written)"
    print(f"triage_gc [{header}]")
    print(f"  total items:   {plan['total']}")
    print(f"  droppable:     {len(dropped)} (machine-churn dismissals)")
    print(f"  kept:          {plan['kept_count']}")
    if dropped:
        from collections import Counter
        by_reason = Counter(i.get("statusReason") for i in dropped)
        print("  by reason:")
        for reason, n in sorted(by_reason.items(), key=lambda kv: -kv[1]):
            print(f"    {n:>4}  {_safe(reason)}")
        print("  ids (first 40):")
        for i in dropped[:40]:
            print(f"    {i['id']}  {_safe(i.get('statusBy')):<14} {_safe((i.get('title') or ''))[:48]}")
        if len(dropped) > 40:
            print(f"    ... +{len(dropped) - 40} more")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project-root", required=True, type=Path)
    ap.add_argument(
        "--apply", action="store_true",
        help="rewrite the log (default: dry-run report only)",
    )
    ap.add_argument(
        "--no-backup", action="store_true",
        help="skip the .bak backup on --apply (NOT recommended)",
    )
    args = ap.parse_args(argv)

    plan = plan_gc(args.project_root)
    if not args.apply:
        _print_report(plan, applied=False)
        return 0
    if not plan["drop_ids"]:
        _print_report(plan, applied=False)
        print("triage_gc: nothing to drop — no rewrite performed.")
        return 0
    backup_path = apply_gc(args.project_root, plan["drop_ids"], backup=not args.no_backup)
    _print_report(plan, applied=True)
    if not args.no_backup:
        print(f"  backup:        {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
