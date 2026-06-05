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
    "phaseQualityBacklog",  # phase_quality/_triage_bundle.py
    "testEvidence",         # plugins/shipwright-compliance/.../test_evidence.py
})

# Exact machine auto-resolve tokens. A human free-text reason (even one that
# starts with one of these) will not match — exact equality only.
MACHINE_REASONS = frozenset({
    "sbomResolved",
    "auditResolved",
    "driftResolved",
    "f05Resolved",
    "githubResolved",
    "complianceResolved",
    "phaseQualityResolved",
    "testEvidenceResolved",
})


def is_machine_churn(item: dict) -> bool:
    """True iff ``item`` is a pure producer auto-resolve dismissal."""
    return (
        item.get("status") == "dismissed"
        and item.get("statusBy") in MACHINE_DISMISSERS
        and item.get("statusReason") in MACHINE_REASONS
    )


def plan_gc(project_root: Path | str) -> dict:
    """Compute the GC plan without writing anything.

    Returns ``{"drop_ids": set, "dropped": [item...], "kept_count": int,
    "total": int}``.
    """
    items = triage.read_all_items(project_root)
    dropped = [i for i in items if is_machine_churn(i)]
    drop_ids = {i["id"] for i in dropped}
    return {
        "drop_ids": drop_ids,
        "dropped": dropped,
        "kept_count": len(items) - len(dropped),
        "total": len(items),
    }


def _validate_after(project_root: Path | str, drop_ids: set[str]) -> None:
    """Fail loudly if the rewrite produced an inconsistent log."""
    raw = triage._iter_raw_lines(project_root)
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
    survivors = {i["id"] for i in triage.read_all_items(project_root)}
    if survivors & drop_ids:
        raise RuntimeError("post-GC validation: a dropped item resolved as surviving")


def apply_gc(project_root: Path | str, drop_ids: set[str], backup: bool = True) -> Path:
    """Rewrite the log without the ``drop_ids`` lines. Returns the backup path
    (or the live path when ``backup`` is False). Holds the store's file lock.

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
        raw = triage._iter_raw_lines(project_root)
        kept = [
            r for r in raw
            if r.get("event") not in ("append", "status") or r.get("id") not in drop_ids
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
    _validate_after(project_root, drop_ids)
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
