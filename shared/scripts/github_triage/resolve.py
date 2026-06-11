"""Auto-resolve + legacy-migration sweeps.

Consumer-side helpers, split out of ``consumer.py`` so each file stays
under the 300-LOC budget. Both functions iterate the triage inbox and
mark items dismissed:

- ``_resolve_stale`` — ADR-052 auto-resolve. An OPEN action-unit item is
  stale when (a) its dedup key belongs to one of the three owned prefixes,
  (b) that prefix's fetch SUCCEEDED this run, and (c) the key is absent
  from the current finding set. Scoped strictly to OWNED prefixes —
  other producers' items are left alone.
- ``_migrate_legacy_items`` — one-shot migration from the iterate-2026-05-19
  per-finding model. Per-source-gated: a failed fetch for source X leaves
  source-X legacy items UNTOUCHED, even if other sources succeeded
  (review finding #3). Idempotent — items already dismissed / promoted /
  snoozed are skipped (review finding #12).

Both helpers fail-soft on per-item ``mark_status`` errors (write to
stderr, continue). The orchestrator wraps each sweep in its own
exception handler so a catastrophic failure can't take down the import.
"""

from __future__ import annotations

import sys

from triage import mark_status, read_all_items

from .producer import _OWNED_PREFIXES, PREFIX_PR_CI

SOURCE = "github"

# Legacy per-finding prefixes from iterate-2026-05-19. Migrated on the
# first successful fetch of the corresponding source; never resolved from
# a failed fetch (review finding #3).
_LEGACY_CODE_SCANNING = "github:code-scanning:"
_LEGACY_DEPENDABOT = "github:dependabot:"
_LEGACY_SECRET_SCANNING = "github:secret-scanning:"
_LEGACY_CI = "github-ci:"

# Map: which legacy prefix gets migrated when which producer source succeeds.
_LEGACY_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("code_scanning", _LEGACY_CODE_SCANNING),
    ("dependabot", _LEGACY_DEPENDABOT),
    ("secret_scanning", _LEGACY_SECRET_SCANNING),
    ("runs", _LEGACY_CI),
)


def resolve_stale(
    project_root,
    resolvable_prefixes: set[str],
    current_keys: set[str],
) -> int:
    """Dismiss this producer's stale OPEN action-unit items.

    An item is stale when its dedup key belongs to one of the three owned
    action-unit prefixes, that prefix's fetch SUCCEEDED this run, and the
    key is absent from ``current_keys``. Scoped per ADR-052 — items from
    other producers and prefixes whose fetch failed are left alone.
    Legacy items are handled separately by ``migrate_legacy_items``.
    """
    resolved = 0
    for item in read_all_items(project_root):
        if item.get("source") != SOURCE or item.get("status") != "triage":
            continue
        dedup_key = item.get("dedupKey") or ""
        prefix = next(
            (p for p in _OWNED_PREFIXES if dedup_key.startswith(p)), None
        )
        if prefix is None or prefix not in resolvable_prefixes:
            continue
        if dedup_key in current_keys:
            continue
        try:
            mark_status(
                project_root,
                item["id"],
                new_status="dismissed",
                by="githubImporter",
                reason="githubResolved",
            )
            resolved += 1
        except Exception as exc:  # noqa: BLE001 — best-effort
            sys.stderr.write(
                f"[github-triage] resolve failed for {item.get('id')}: "
                f"{type(exc).__name__}: {exc}\n"
            )
    return resolved


def migrate_legacy_items(
    project_root,
    fetch_succeeded: dict[str, bool],
) -> int:
    """Dismiss legacy per-finding items whose original source fetch succeeded.

    One-shot migration from the per-finding model (iterate-2026-05-19) to
    the action-unit model (iterate-2026-05-20). Per-source-gated — a failed
    fetch for source X leaves source-X legacy items UNTOUCHED, even if
    other sources succeeded (review finding #3).

    Idempotent: items already at status ``dismissed`` / ``promoted`` /
    ``snoozed`` are skipped (review finding #12) — only items whose
    current resolved status is ``triage`` get a fresh ``schemaMigration``
    event.
    """
    migrated = 0
    for item in read_all_items(project_root):
        if item.get("source") != SOURCE or item.get("status") != "triage":
            continue
        dedup_key = item.get("dedupKey") or ""
        for source_name, legacy_prefix in _LEGACY_MIGRATIONS:
            if not dedup_key.startswith(legacy_prefix):
                continue
            if not fetch_succeeded.get(source_name):
                # Per-source-gating — that source's fetch failed; leave
                # the item alone so a transient outage never mass-resolves.
                break
            try:
                mark_status(
                    project_root,
                    item["id"],
                    new_status="dismissed",
                    by="githubImporter",
                    reason="schemaMigration",
                )
                migrated += 1
            except Exception as exc:  # noqa: BLE001
                sys.stderr.write(
                    f"[github-triage] legacy migration failed for "
                    f"{item.get('id')}: {type(exc).__name__}: {exc}\n"
                )
            break  # one prefix per item
    return migrated


def resolve_pr_ci(
    project_root,
    *,
    open_pr_numbers: set[int],
    failing_pr_numbers: set[int],
    pr_state_fetcher,
) -> int:
    """Differentiated auto-resolve for ``gh-pr-ci:{n}`` items (B4.5 loop-closing).

    Called ONLY when the PR-CI fetch fully succeeded (the consumer gates this on
    ``open_prs_with_failed_checks`` not being ``None`` — symmetry with emit, so a
    network blip never mass-resolves). Distinct from the generic
    ``resolve_stale`` sweep, which intentionally leaves ``gh-pr-ci:`` alone.

    Per open ``gh-pr-ci`` item, keyed on its PR number:

    - still in ``failing_pr_numbers`` → keep (still failing)
    - still in ``open_pr_numbers`` but not failing → ``prChecksResolved``
    - gone from the open set → ``pr_state_fetcher(n)``: merged → ``prMerged``;
      confirmed closed → ``prClosed``; UNKNOWN (fetch failed / ambiguous) →
      KEEP OPEN and retry next cycle. Refusing to guess ``prClosed`` from an
      unfetchable state prevents mis-resolving a still-open PR that an incomplete
      open-set fetch could have omitted (external review HIGH).

    Fail-soft per item (write to stderr, continue); returns dismissed count.
    """
    resolved = 0
    for item in read_all_items(project_root):
        if item.get("source") != SOURCE or item.get("status") != "triage":
            continue
        dedup_key = item.get("dedupKey") or ""
        if not dedup_key.startswith(PREFIX_PR_CI):
            continue
        try:
            pr_number = int(dedup_key[len(PREFIX_PR_CI):])
        except (TypeError, ValueError):
            continue
        if pr_number in failing_pr_numbers:
            continue
        if pr_number in open_pr_numbers:
            reason = "prChecksResolved"
        else:
            state = pr_state_fetcher(pr_number)
            if state and state.get("merged"):
                reason = "prMerged"
            elif state and state.get("state") == "closed":
                reason = "prClosed"
            else:
                # State unknown / still racing — keep the item open, resolve it
                # on a later cycle rather than guess.
                continue
        try:
            mark_status(
                project_root,
                item["id"],
                new_status="dismissed",
                by="githubImporter",
                reason=reason,
            )
            resolved += 1
        except Exception as exc:  # noqa: BLE001 — best-effort
            sys.stderr.write(
                f"[github-triage] pr-ci resolve failed for {item.get('id')}: "
                f"{type(exc).__name__}: {exc}\n"
            )
    return resolved
