"""Compliance triage → one rolling backlog action-unit.

Replaces the prior per-failing-check mirror (one ``source=compliance`` item per
failing Group A-G check) with a single rolling ``compliance:backlog:<sig>``
action-unit. Per ``project_triage_launch_surface_redesign`` / ADR-057 —
producers emit action-units, not finding-mirrors; mirrors the phaseQuality
backlog shape (``shared/scripts/lib/phase_quality/_triage_bundle.py``).

Kept compliance-local (two callers is not three — Simplicity First); a shared
helper waits for a third producer.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from scripts.audit.triage_bundle_render import (
    BACKLOG_PREFIX, SEVERITY_RANK, build_detail, build_launch_payload,
    max_severity, mentions_group, normalize_fails, protected_by, signature,
)


def _triage_api():
    """(append_idempotent, mark_status, amend, read_all_items, should_route_to_outbox,
    AUTO_RESOLVABLE_STATUSES, StatusPreconditionError).

    Returns a 7-tuple of ``None`` when the shared triage module can't be
    imported (best-effort producer — never blocks the audit). All names come
    off the SAME import so an ``except`` can never bind a mismatched
    ``StatusPreconditionError`` from a different ``triage`` module object
    under this repo's plugin sys.path layout (external plan review, finding #3).
    """
    shared_scripts = Path(__file__).resolve().parents[4] / "shared" / "scripts"
    if str(shared_scripts) not in sys.path:
        sys.path.insert(0, str(shared_scripts))
    try:
        import triage  # noqa: PLC0415
        return (
            triage.append_triage_item_idempotent,
            triage.mark_status,
            triage.amend_triage_item,
            triage.read_all_items,
            triage.should_route_to_outbox,
            triage.AUTO_RESOLVABLE_STATUSES,
            triage.StatusPreconditionError,
        )
    except (ImportError, AttributeError):
        # AttributeError: a stale `triage` (partially-synced plugin cache
        # already bound in sys.modules) predating `expected_status` must
        # disable this producer cleanly rather than raise TypeError on every
        # flip with the refusal arm never matching (doubt review, doubt 2).
        return None, None, None, None, None, None, None


def emit_compliance_backlog(
    project_root: Path,
    report: Any,
    *,
    run_id: str | None,
    commit: str | None,
    preserve_groups: frozenset[str] = frozenset(),
) -> dict[str, int]:
    """Emit/refresh ONE ``compliance:backlog:<sig>`` item + retire legacy items.

    * No failing findings → dismiss every open/parked ``compliance:backlog:*``
      (``complianceResolved``) and append nothing.
    * Else → dismiss stale-signature items (``complianceRefreshed``), reopen
      an auto-dismissed matching item on regression, and append only when no
      durable item represents the current condition.
    * One-shot, unconditional: any legacy per-check ``compliance`` item
      (dedupKey outside the backlog shape) is dismissed
      (``supersededByBacklog``) — AC-4. Terminal decisions are untouched.
    * ``preserve_groups`` (merge scope only): a rolling card naming a
      release-owned group is amended in place instead of dismissed as stale.

    Best-effort: returns ``{"appended","dismissed","open_fails","amended"}`` —
    all four keys, every exit (``amended`` is 0 outside the preserve-groups path).
    """
    (append_idempotent, mark_status_fn, amend_item, read_all_items, route,
     AUTO_RESOLVABLE_STATUSES, precondition_error) = _triage_api()
    if append_idempotent is None:
        return {"appended": 0, "dismissed": 0, "open_fails": 0, "amended": 0}

    # D1 (campaign 2026-06-08-triage-outbox-delivery): idle main routes to the
    # gitignored outbox (no tracked-log drift); an iterate/* branch writes the
    # tracked log directly (ships in the PR). read_all_items is union-aware.
    to_outbox = bool(route(project_root)) if route is not None else False

    fails = normalize_fails(report)

    def _dismiss(item_id: str, reason: str) -> int:
        try:
            # Residence-derived (writes to the same store the item lives in);
            # expected_status re-checks under the store's lock since this list
            # came from an unlocked read (trg-93ceb2b0).
            mark_status_fn(
                project_root, item_id, new_status="dismissed",
                by="complianceBacklog", reason=reason,
                expected_status=AUTO_RESOLVABLE_STATUSES,
            )
            return 1
        except precondition_error as exc:  # item was decided — KEPT, not failed
            try:
                sys.stderr.write(f"[compliance] {exc.kept_note}\n")
            except Exception:  # noqa: BLE001 - reporting must never break the sweep
                pass
            return 0
        except Exception:  # noqa: BLE001
            return 0

    try:
        open_compliance = [
            it for it in read_all_items(project_root)
            if it.get("source") == "compliance"  # artifact-path-canon: legacy (triage source enum, not a path)
            and it.get("status") in AUTO_RESOLVABLE_STATUSES
        ]
    except Exception:  # noqa: BLE001
        open_compliance = []
    open_backlog = [
        it for it in open_compliance
        if str(it.get("dedupKey") or "").startswith(BACKLOG_PREFIX)
    ]
    legacy = [
        it for it in open_compliance
        if not str(it.get("dedupKey") or "").startswith(BACKLOG_PREFIX)
        and not mentions_group(it, preserve_groups)
    ]
    # AC-4 — one-shot legacy retirement; unconditional, a protected card below cannot gate it.
    dismissed = sum(_dismiss(it["id"], "supersededByBacklog") for it in legacy)

    # Sorted by id: >1 protected card always amends the SAME survivor.
    protected = sorted((item for item in open_backlog if protected_by(item, preserve_groups)),
                       key=lambda item: str(item.get("id") or ""))
    if protected:
        survivor = protected[0]
        # Severity for the escalate-only decision below is computed from the
        # REAL, newly-observed fails only — the fold-back below can only add
        # entries with a fabricated placeholder severity, and mixing that into
        # max_severity() would let fabricated data permanently escalate a
        # genuinely low-severity card (an escalate-only rule never lowers it
        # back down; doubt review round 5, LOW).
        current = max_severity(fails)
        # Amend the survivor in place; fold in preserved lines from every
        # protected card — for DISPLAY only — the rest are retired below as
        # duplicates.
        for source in protected:
            for line in str(source.get("detail") or "").splitlines():
                if line.startswith("- ") and ":" in line:
                    key, body = line[2:].split(":", 1)
                    if key.split("/", 1)[0] in preserve_groups and not any(f["key"] == key for f in fails):
                        name, _, detail = body.strip().partition(" — ")
                        fails.append({"key": key, "name": name, "sev": "medium", "detail": detail})
        fails.sort(key=lambda item: item["key"])
        existing = str(survivor.get("severity") or "low").lower()
        amendment = {"title": f"Compliance: {len(fails)} open finding(s)"[:160], "detail": build_detail(fails)}
        if SEVERITY_RANK.get(current, 1) > SEVERITY_RANK.get(existing, 1):
            amendment["severity"] = current
        # A no-op amend still appends a timestamped event to the append-only
        # backlog — an unchanging Group-E card open across N deliveries would
        # otherwise accumulate N identical events (code review LOW).
        unchanged = (amendment.get("title") == survivor.get("title")
                    and amendment.get("detail") == survivor.get("detail")
                    and "severity" not in amendment)
        amended = 0
        if not unchanged:
            try:
                amend_item(project_root, survivor["id"], by="complianceBacklog", **amendment)
                amended = 1
            except Exception as exc:  # noqa: BLE001 — best-effort, but surface it
                sys.stderr.write(f"[compliance] protected-card amend failed: {type(exc).__name__}: {exc}\n")
                return {"appended": 0, "dismissed": dismissed, "open_fails": len(fails), "amended": 0}
        # Stale-signature and duplicate-protected cards alike are superseded.
        dismissed += sum(_dismiss(stale["id"], "complianceRefreshed")
                         for stale in open_backlog if stale["id"] != survivor["id"])
        return {"appended": 0, "dismissed": dismissed, "open_fails": len(fails), "amended": amended}

    if not fails:
        dismissed += sum(_dismiss(it["id"], "complianceResolved") for it in open_backlog)
        return {"appended": 0, "dismissed": dismissed, "open_fails": 0, "amended": 0}

    cur_key = BACKLOG_PREFIX + signature(fails)
    dismissed += sum(
        _dismiss(it["id"], "complianceRefreshed")
        for it in open_backlog if it.get("dedupKey") != cur_key
    )

    new_id: str | None = None
    try:
        prior = next(
            (
                item for item in read_all_items(project_root)
                if item.get("source") == "compliance"
                and item.get("dedupKey") == cur_key
                and item.get("status") == "dismissed"
                and item.get("statusBy") == "complianceBacklog"
            ),
            None,
        )
        if prior is not None:
            mark_status_fn(
                project_root, prior["id"], new_status="triage",
                by="complianceBacklog", reason="complianceRegressed",
                expected_status="dismissed", expected_by="complianceBacklog",
                block_matching_terminal=("compliance", cur_key),
            )
            # `prior` may have been amended in place (merge scope) before it
            # was dismissed — amend cannot touch dedupKey, so its rendered
            # content can lag what dedupKey==cur_key means now. Re-render on
            # reopen rather than excluding amended items from this match:
            # exclusion left NO path to reopen OR re-append them (append_idempotent
            # no-ops on any matching dedupKey regardless of status), silently
            # dropping a real regression (doubt review round 4, HIGH).
            amend_item(project_root, prior["id"], by="complianceBacklog",
                      title=f"Compliance: {len(fails)} open finding(s)"[:160],
                      detail=build_detail(fails), severity=max_severity(fails))
    except Exception:  # noqa: BLE001
        pass
    try:
        new_id = append_idempotent(
            project_root,
            source="compliance",  # artifact-path-canon: legacy (triage source enum, not a path)
            severity=max_severity(fails),
            kind="compliance",  # artifact-path-canon: legacy (triage kind enum, not a path)
            title=f"Compliance: {len(fails)} open finding(s)"[:160],
            detail=build_detail(fails),
            dedup_key=cur_key,
            run_id=run_id,
            commit=commit,
            match_commit=False,
            window_seconds=None,
            launch_payload=build_launch_payload(fails),
            to_outbox=to_outbox,
        )
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[audit_detector] backlog emit failed: {type(exc).__name__}: {exc}\n")

    return {
        "appended": 1 if new_id else 0,
        "dismissed": dismissed,
        "amended": 0,
        "open_fails": len(fails),
    }
