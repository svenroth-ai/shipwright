# Iterate Spec — Triage is for "later", not for tracking current work

- **Run ID:** `iterate-2026-06-13-triage-not-current-work`
- **Intent:** CHANGE (Path B)
- **Spec Impact:** MODIFY (removes a side-effect behavior from two iterate-pipeline producers)
- **Complexity:** medium
- **Risk flags (diff-driven, authoritative):** `cross_component` (touches `shared/scripts/hooks/plugin_sync_reminder_on_stop.py`, matches `(^|/)hooks/.+\.py$`)
- **Risk flags (prose, NON-authoritative / false-positive):** `touches_auth` — Stage-1 keyword match only; the diff touches **no** auth path (`src/middleware.ts`, `**/auth/**`, `src/lib/supabase/`). Recorded in `degraded[]`.

## Problem (user directive, 2026-06-13)

The triage backlog is being polluted with items that track **work we are doing right
now** instead of genuine **deferred follow-ups ("later")**. Two concrete sources:

1. **Plugin-cache sync reminder** (`plugin_sync_reminder_on_stop.py`) appends a durable
   `source="plugin-sync"` triage item every time plugin-side files were edited this
   session. But re-syncing the plugin cache is a **routine maintenance step that normally
   just happens** as part of the workflow — it is a "do it now" reminder, not a backlog
   item. Result today: **19 duplicate `plugin-sync` items** in the live backlog.

2. **F0.5 surface-verification gate** (`surface_verification.py`) appends a `critical`
   `source="f0.5"` triage item on every fail-closed condition — but the gate **already
   STOPs the iterate via its non-zero exit code**. The triage item mirrors the current
   run's own blocked work; it is not a "later" item.

**Principle (user):** *Triage logs things for later. The board / events log tracks what we
are doing now.* An iterate must not file triage items about its own current run.

There is also a **behavioral** half: with no guardrail, the agent itself sometimes files
`iterate-self-review` / `iterate-analysis` items about the change it is currently making.

## Goal / Acceptance Criteria

- **AC1** — `plugin_sync_reminder_on_stop.run()` no longer appends ANY triage item
  (neither tracked `triage.jsonl` nor the `triage.outbox.jsonl`), in the worktree or the
  main repo. The **once-per-session Stop-block reminder still fires** (the "do it now"
  surface) and the once-per-session sentinel is still written.
- **AC2** — `surface_verification.main()` no longer appends a triage item on any
  fail-closed condition (`tests_zero`, `exit_nonzero`, `surface_none_no_just`). The
  **fail-closed exit codes are unchanged** (the gate still STOPs) and the evidence block
  is still written.
- **AC3** — A prose guardrail in the iterate `reflection.md` reference tells the agent NOT
  to file triage items that track the current iterate's own work (the board/events log
  owns "now"; triage is for genuine deferred follow-ups).
- **AC4** — Historical `f0.5` backlog items still render and GC correctly: `KNOWN_SOURCES`
  keeps `"f0.5"`, and `triage_gc` keeps `f05Resolved`/`f05Detector` as recognized
  machine-churn tokens (both annotated "legacy — producer removed, retained for historical
  items"), matching the existing `auditResolved` precedent.
- **AC5** — `docs/hooks-and-pipeline.md` is updated so the producer/artifact matrices no
  longer claim plugin-sync or F0.5 emit triage items.

## Out of scope (explicit)

- The genuine background **detective** producers (drift, compliance, phaseQuality, sbom,
  security, performance) stay — they find real "later" issues across the repo, which is
  exactly what triage is for. This iterate only removes the two producers that track the
  **current run's own work**.
- **Backfill cleanup** of the existing 19 `plugin-sync` + N `f0.5` backlog items is NOT
  done here (would be a data mutation of the tracked log mid-iterate). Once the producers
  stop, no new items accrue; the existing items GC or are operator-dismissed via the WebUI.

## Mini-Plan

**Chosen approach — remove the two producers at the source; keep the gates.**
1. `plugin_sync_reminder_on_stop.py`: delete `_emit_triage()` + its call in `run()`;
   rewrite the reminder body (drop "a triage item has been filed"); update the docstring.
2. `surface_verification.py`: delete the `main()` triage-emit + resolve blocks and the now
   dead helpers (`_EXIT_TO_CONDITION`, `_f05_dedup_key`, `_emit_failure_to_triage`,
   `_detail_for_condition`, `_resolve_stale_f05_items`). Keep exit codes + evidence.
3. `reflection.md`: add the "triage = later, not now" guardrail.
4. `triage.py` / `triage_gc.py`: legacy-annotate the retained `f0.5` registry entries.
5. `docs/hooks-and-pipeline.md`: update the producer matrices.
6. Tests: rewrite the plugin-sync test (no-emit + reminder fires; real-git-worktree
   end-to-end = the `category:"integration"` behavior); delete `test_f0_5_triage_emit.py`;
   add an F0.5 fail-closed "no triage, still STOPs" regression test.

**Alternative considered — keep the producers but flip severity to `info` / make them
opt-out via env var.** Rejected: it leaves the conceptual error in place (current-work
items still in the "later" backlog), still accrues noise, and adds config surface. The
user's directive is that this class of item *does not belong in triage at all*, so removal
at the source is the correct fix — not suppression.

**Alternative considered — route these two to the events log / board instead.** Rejected:
the F0.5 STOP (exit code) and the plugin-sync block-once reminder already ARE the "now"
surfaces; the work record (`work_completed` event) already captures the run. No new board
write is needed — the items were simply redundant.

## Review responses (external LLM + code review)

- **plugin-sync needs NO registry retention** (asymmetry vs `f0.5` is correct):
  `plugin-sync` was never in `KNOWN_SOURCES` and never had an auto-resolve reason
  / `*Detector` token (its append used a `dedup_key`, no `mark_status`). The 19
  historical items already render without a registry entry (the registry is not a
  strict validation enum — many live sources are absent from it). So there is
  nothing to legacy-annotate for plugin-sync. Only `f0.5` had a `f05Resolved` /
  `f05Detector` GC vocabulary, which IS retained (AC4).
- **F0.5 stale auto-resolve removal is intentional.** Removing
  `_resolve_stale_f05_items` means a green re-run no longer auto-dismisses old
  `f0.5` items. This loses nothing for the existing items: the resolve pass was
  scoped to the SAME `(run_id, surface)`, and historical items carry old run_ids
  that never re-run — so they could never have been auto-resolved anyway.
- **Existing orphaned backlog items (19 plugin-sync + 4 open `f0.5`/P0) are left
  for operator dismissal** (WebUI), NOT mutated in this iterate. Rationale:
  mid-iterate mutation of the tracked, main-durable `triage.jsonl` from a worktree
  is the exact operation that has repeatedly caused tracked-triage drift; its
  value (clearing already-existing noise) does not justify that risk in the same
  change that removes the producers. Open items are not machine-churn, so
  `triage_gc` will not auto-reap them — operator dismissal is the intended path.
  (No triage item is filed to track this — that would be the very anti-pattern
  this iterate removes; it is recorded here + in the ADR instead.)
- **Auditability preserved:** F0.5 still writes its evidence block + the run's
  `work_completed` event records the stop; the plugin-sync reminder + the iterate
  work record remain. Triage was never the audit trail for these.
- **Guardrail placed authoritatively:** the "triage = later, not now" rule is in
  both the iterate `reflection.md` reference AND the always-loaded
  `shared/constitution.md` NEVER tier (higher precedence / broader reach).

## Affected Boundaries

- Stop-hook → triage store (`plugin_sync_reminder_on_stop` → `triage.append_*`): append
  path **removed**. Reminder (stdout block decision) path unchanged.
- F0.5 orchestrator → triage store (`surface_verification.main` → `triage.append_*` /
  `mark_status`): append + resolve paths **removed**. Exit-code + evidence paths unchanged.
- Registry SSoT (`triage.KNOWN_SOURCES`, `triage_gc.MACHINE_REASONS/DISMISSERS`): entries
  retained (read-compat for historical items), comment-only edit.

## Confidence Calibration
- **Boundaries touched:** Stop-hook→triage append (removed); F0.5→triage append+resolve
  (removed); triage source/GC registries (retained, annotated). No auth/RLS/migration/IO
  boundary touched (`is_io_boundary_change` = False).
- **Empirical probes run:**
  - `risk_detectors.is_cross_component_change([hook]) == True` → `cross_component` real;
    `is_io_boundary_change(diff) == False` → no round-trip owed. (run pre-build)
  - `KNOWN_SOURCES` used only by `test_triage_launch_payload` (forward parametrize, no
    reverse "every source has a live producer" test) → retaining `f0.5` is safe.
  - F0.5 helpers (`_emit_failure_to_triage` et al.) referenced ONLY in
    `surface_verification.py` + `test_f0_5_triage_emit.py` → removal is self-contained.
  - {post-build: full suite green; F0.5 cli surface green}
- **Test Completeness Ledger:** see `shipwright_test_results.json.iterate_latest.test_completeness`
  (recorded at F5). Includes one `category:"integration"` behavior (cross_component gate).
- **Confidence-pattern check:** asymptote (depth) — each removed path has a direct
  no-emit assertion; coverage (breadth) — plugin-sync + all three F0.5 conditions covered;
  **integration composition** — real-git-worktree end-to-end Stop-hook run proves the hook
  composes with the triage store without polluting it.
