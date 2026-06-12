# Iterate Spec — triage GC union-residence recompute (a1-6/F19 follow-up)

- **Run ID:** `iterate-2026-06-12-triage-gc-union-residence`
- **Intent:** CHANGE (correctness/security hardening of existing GC behavior)
- **Complexity:** medium (locked) — multi-file, concurrency correctness, `touches_io_boundary`
  (triage store JSON round-trip), security-adjacent sanitizer extraction, and a
  behavioral GC-coverage change surfaced by source-derivation.
- **Spec Impact:** MODIFY — no new FRs; hardens the triage tooling shipped by
  the 2026-06-10 deep-audit WP9 (a1-6, PR #204).
- **Tracks triage item:** `trg-c6853c9d` (source: codeReview, kind: improvement).

## Problem

a1-6/F19 (PR #204) closed the tracked-route TOCTOU in `triage_gc.apply_gc` by
**recomputing the droppable set under the lock** and intersecting it with the
caller's plan. But that recompute reads the **tracked store only**
(`plan_gc` → `_resolve_tracked_only`). On idle-main-with-origin, a concurrent
re-open of a planned item routes (via `mark_status` → `should_route_to_outbox`)
to the **gitignored outbox**, which the tracked-only recompute cannot see. The
item is therefore still dropped from the tracked log, and its outbox `status`
event orphans (its `append` is gone, so `read_all_items` skips the status as an
unknown-id event). a1-6 documented this exact gap as an operator constraint
("do not run `--apply` while idle-main outbox writes are possible").

## Root cause

The under-lock recompute uses tracked-only residence. An item's *true* final
status is its **union residence** (tracked ∪ outbox, last-status-wins —
`triage.read_all_items`). A re-open in the outbox makes the item no-longer
`dismissed`, so it is not machine-churn under union residence and must not be
dropped — even though the tracked-only view still shows it as droppable.

## Fix (MAIN)

1. **Union-residence recompute.** In `apply_gc`, compute the fresh droppable set
   under the lock over **union residence** (`triage.read_all_items` →
   `is_machine_churn`) instead of tracked-only. Intersect with the caller's plan
   exactly as today (`effective = union_droppable & caller_drop_ids`), so the
   operator-facing report stays an upper bound (apply never drops MORE than the
   report announced). **Still rewrite only the tracked file** — the outbox is the
   D2 sweep's concern (D1 boundary preserved; `test_apply_does_not_fold_outbox_into_tracked`
   must stay green). The report (`plan_gc`) remains tracked-only by design.
2. **Replace the operator-constraint note** in `triage_gc.py` with a note that
   the recompute is now union-residence-aware (limitation closed).
3. **Outbox-route survival test** (TDD red-first): a tracked machine-churn
   dismissal whose re-open is routed to the outbox (force `should_route_to_outbox`)
   survives `apply_gc`; the tracked `append` is retained; the outbox is unchanged.

## Fix (LOW)

4. **Source-derive the drift meta-test.** Replace the hand-copied
   `PRODUCER_RECURRING_DISMISS_TOKENS` frozenset with a set **derived from
   producer source** (scan `shared/` + `plugins/` `*.py`, excluding test trees
   and `triage_gc.py`, for `*Resolved`/`*Refreshed` dismissal-reason literals).
   The hand-copy was a tautology (== `MACHINE_REASONS`) that hid real drift in
   both directions. Source-derivation surfaces:
   - **`prChecksResolved`** (github_triage PR-CI resolver, `by="githubImporter"`)
     — emitted but **missing** from `MACHINE_REASONS`. It is recurring
     machine-churn (a tracked PR's checks flip green → auto-dismiss), so the
     reconciliation is to **add it** to `MACHINE_REASONS`. (`prMerged`/`prClosed`/
     `schemaMigration` are deliberately NOT `*Resolved`-named: terminal
     per-PR/one-shot lifecycle markers kept as real history, not churn — they
     stay out of the recurring vocabulary and out of the scan.)
   - **`auditResolved`** — in `MACHINE_REASONS` with **no live emitter**
     (audit now routes through `complianceBacklog`).
5. **Resolve the `auditResolved` orphan.** Keep it in `MACHINE_REASONS` (a
   removal would silently stop GC'ing any legacy/pending `auditResolved`
   dismissals — one is buffered in the outbox today) and record it in an explicit,
   documented `LEGACY_RETAINED_TOKENS` allowlist the reverse-drift test honors.
6. **Extract `_strip_control_chars` to `shared/`.** The identical copies in
   `aggregate_triage.py` and `triage_cli.py` move to `shared/scripts/lib/tty_sanitize.py`
   (`strip_control_chars`); both tools import it as `_strip_control_chars` (name
   preserved → existing behavior + tests unchanged).
7. **Cover the GC dry-run report render surface.** Add a unit test asserting
   `_print_report` renders header/counts/by-reason/ids and the `>40` truncation.

## Acceptance Criteria

- [ ] AC1: An outbox-routed re-open of a planned tracked item survives
      `apply_gc` (tracked `append` retained, outbox byte-unchanged). Red before
      the fix, green after.
- [ ] AC2: The tracked-route F19 cases (`test_apply_recomputes_plan_under_lock_*`,
      consent-surface guard) stay green; `test_apply_does_not_fold_outbox_into_tracked`
      stays green (still rewrite tracked-only).
- [ ] AC3: `triage_gc.py` documents the recompute as union-residence-aware
      (operator-constraint note removed/replaced).
- [ ] AC4: The drift meta-test derives producer tokens from source; forward +
      reverse drift both pass; `prChecksResolved` ∈ `MACHINE_REASONS`;
      `auditResolved` resolved via documented `LEGACY_RETAINED_TOKENS`. The
      derived set is non-empty-guarded (no vacuous green).
- [ ] AC5: `_strip_control_chars` is a single shared implementation imported by
      both tools; `test_triage_wp9_sanitize_outbox.py` stays green.
- [ ] AC6: `_print_report` dry-run render is covered by a test.
- [ ] AC7: Full F0 suite green; no new bloat crossing; ruff clean.

## Mini-Plan

**Chosen approach:** union-residence recompute inside `apply_gc` via
`triage.read_all_items` (the canonical union resolver), intersected with the
caller plan; tracked-file rewrite unchanged. Reuses the existing, externally
reviewed two-pass `(ts, file-order)` union resolution — no new resolution logic,
no new D1 boundary risk.

**Alternative considered & rejected:** make `plan_gc`/the report itself
union-aware. Rejected — the report must stay tracked-only (D1: the CLI never
claims authority over the gitignored outbox; the operator sees the durable
store). Only the *safety* recompute needs union awareness; widening the report
would blur the D1 ownership line the boundary test pins.

**Alternative considered & rejected:** drop `auditResolved` from
`MACHINE_REASONS`. Rejected — narrows GC for legacy/pending dismissals (one
buffered in the outbox); keep + allowlist is regression-free and makes the
legacy retention explicit.

## Affected Boundaries

- Triage store IO: tracked `.shipwright/triage.jsonl` ∪ gitignored
  `.shipwright/triage.outbox.jsonl` (JSON round-trip; `touches_io_boundary`).
- GC destructive rewrite (under file lock; atomic temp+replace).
- Terminal rendering (TTY control-char sanitize) — shared extraction.

## Confidence Calibration
- **Boundaries touched:** triage tracked store (`.shipwright/triage.jsonl`),
  gitignored outbox (`.shipwright/triage.outbox.jsonl`), GC destructive rewrite
  under file lock, TTY control-char render.
- **Empirical probes run:**
  1. TDD red — `test_apply_honors_outbox_routed_reopen` FAILED on the
     tracked-only recompute (`assert m in survivors` → empty dict: item dropped,
     outbox status orphaned), GREEN after the union-residence recompute.
  2. Source-derivation diff probe — derived set = the 10 live producer tokens;
     `forward gap (src − MACHINE_REASONS) = []`, `reverse gap (MR − src −
     legacy) = []`. Confirmed the hand-copy hid `prChecksResolved` (forward) and
     `auditResolved` (reverse).
  3. Round-trip integrity probe — realistic store (unicode title, tracked
     sbom/prChecks churn + open + human-dismiss, outbox re-open between plan and
     apply): after `apply_gc`, `a` (outbox re-open) survives as `triage`, `b`
     (prChecksResolved) GC-dropped, open + human-dismiss kept, **zero tracked
     orphan-status events**, header intact, survivor count == 3. ALL PASS.
  4. Sanitizer extraction smoke — `aggregate_triage._strip_control_chars is
     triage_cli._strip_control_chars is lib.tty_sanitize.strip_control_chars`;
     C0+C1 stripped, `>= 0xA0` preserved; 14 sanitize tests green.
- **Test Completeness Ledger:** (testable ⇒ tested; 0 untested-testable)

  | Behavior (AC) | Disposition | Evidence |
  |---|---|---|
  | Outbox-routed re-open survives apply (AC1) | tested | `test_apply_honors_outbox_routed_reopen` (red→green) |
  | Tracked-route re-open still survives (AC2) | tested | `test_apply_recomputes_plan_under_lock_preserving_concurrent_reopen` |
  | Outbox NOT folded into tracked, D1 (AC2) | tested | `test_apply_does_not_fold_outbox_into_tracked` |
  | Report stays tracked-only upper bound (AC2) | tested | `test_apply_does_not_drop_item_churned_after_the_consented_plan` |
  | Forward-drift source-derived (AC4) | tested | `test_machine_reasons_covers_every_producer_recurring_token` |
  | Reverse-drift source-derived + legacy allowlist (AC4) | tested | `test_machine_reasons_has_no_unknown_tokens` |
  | Vacuous-green guard (AC4) | tested | `test_source_derivation_finds_known_anchor_tokens` |
  | Legacy token has no live emitter (AC4/AC5-orphan) | tested | `test_legacy_retained_tokens_have_no_live_emitter` |
  | prChecksResolved actually GC'd (AC4) | tested | `test_prchecks_resolved_github_dismissal_is_machine_churn` |
  | refresh/prChecks tokens pinned (AC4) | tested | `test_machine_reasons_pins_refresh_and_prchecks_tokens` |
  | Single-source sanitizer, identical behavior (AC5) | tested | `test_triage_wp9_sanitize_outbox.py` (14, behavioral) |
  | Dry-run report render, populated + empty (AC6) | tested | `test_print_report_dry_run_renders_full_surface`, `test_print_report_empty_omits_breakdown` |
  | Operator-constraint note updated (AC3) | tested | grep gate at F0 (no `LIMITATION (follow-up)` / `do not run --apply` in triage_gc.py) + code review |

- **Confidence-pattern check:** depth — the fix reuses the canonical,
  externally-reviewed union resolver (`read_all_items`) rather than a new
  resolution path, so correctness asymptotes to an already-trusted component;
  the round-trip probe confirms no orphan/corruption at the destructive-rewrite
  boundary. Breadth — every AC behavior has a dedicated test (both drift
  directions now do real work, not a tautology); the only non-unit-asserted AC
  (the note removal, AC3) is covered by an F0 grep gate + review.
