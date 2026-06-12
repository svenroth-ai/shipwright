# Mini-Plan — iterate-2026-06-12-triage-tooling-hardening (WP9, audit-1)

## Problem
WP9 of the 2026-06-10 deep audit: four defects in the triage tooling.

- **F30 (MED):** `triage_gc.MACHINE_REASONS` omits `phaseQualityRefreshed`
  (emitted by `phase_quality/_triage_bundle` on every signature change) →
  phase-quality rollup churn is never GC'd. Same decoupled-SSoT class as the
  already-fixed `complianceRefreshed`.
- **F19 (LOW):** the GC plan is computed OUTSIDE the lock; `apply_gc` drops all
  lines for planned ids — including a status flip appended between plan and
  apply (TOCTOU → lost operator decision).
- **F31 (MED, SECURITY):** `_strip_control_chars` is wired only to
  `launchPayload`; `title`/`detail` get only `_escape_md` → terminal-escape
  injection into `triage_inbox.md` and `triage_cli list` from an
  attacker-influenceable GitHub workflow name / branch.
- **F29 (LOW):** `triage_promote.promote`/`dismiss` pre-check only the TRACKED
  file → outbox-only items (D1 union model) are listable but cannot be
  promoted/dismissed.

## Approach
1. **F30** — add `phaseQualityRefreshed` to `MACHINE_REASONS`; add a
   registry-driven forward+reverse-drift meta-test enumerating the producer
   recurring auto-resolve tokens, asserting MACHINE_REASONS == that set.
2. **F19** — recompute the droppable set UNDER the lock in `apply_gc` and
   intersect with the caller's planned ids (apply never drops MORE than the
   dry-run report announced; a re-opened item drops out of the fresh set and
   survives). Validate against the effective (actually-dropped) set, under the
   lock.
3. **F31** — wire `_strip_control_chars` into `title`/`detail`/`evidence` in
   `aggregate_triage._render_item` and into `title` in `triage_cli._format_item`
   (before `_escape_md`). Preserve non-ASCII (>= 0x80).
4. **F29** — relax the promote/dismiss pre-check to tracked-OR-outbox (mirror
   `triage.mark_status`); keep FileNotFoundError when NEITHER exists.

## Tests (TDD, written first, confirmed red)
- GC token coverage meta-test (both drift directions) + phaseQualityRefreshed GC.
- Concurrent re-open between plan and apply is not dropped; item churned after
  the consented plan is NOT silently dropped (consent surface).
- Control-char title/detail renders sanitized in triage_inbox.md + triage_cli list.
- Outbox-only item promotable/dismissable (lib + CLI); FileNotFoundError when
  neither store exists; KeyError for unknown id with outbox present.

## Files
- `shared/scripts/tools/triage_gc.py`
- `shared/scripts/tools/aggregate_triage.py`
- `shared/scripts/tools/triage_cli.py`
- `shared/scripts/tools/triage_promote.py`
- tests: `shared/tests/test_triage_gc.py`, `test_triage_aggregator.py`,
  `test_triage_cli.py`, `test_triage_promote.py`

## Risk flags
`touches_io_boundary` (triage.jsonl), security (F31), concurrency (F19).
