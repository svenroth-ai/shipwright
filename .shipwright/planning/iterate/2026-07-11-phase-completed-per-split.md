# Iterate Spec — per-split `phase_completed` (duration accuracy)

- **Run ID:** `iterate-2026-07-11-phase-completed-per-split`
- **Intent:** CHANGE (modify event-recording behavior) · **Complexity:** medium
- **Spec Impact:** NONE — internal pipeline observability (`change_type: infra`;
  no FR added/modified/removed). Direct follow-up to
  `iterate-2026-07-10-emit-phase-started` (B1 / M-Pre-1), same class.
- **Campaign:** `monorepo-wow-usability-2026-07-10` (sub-iterate B1 follow-up
  `trg-14d6ba20` — per-split duration accuracy).

## Problem

B1/M-Pre-1 emits `phase_started` per split (one per `phase_task`, **not**
deduped), but `record_event.py` dedups `phase_completed` by `phase` alone
(first-wins: `has_phase_event` + `append_event_idempotent`). A multi-split
pipeline phase (build/plan fan out one `phase_task` per split, all sharing the
same `phase`) therefore keeps only the FIRST split's `phase_completed` in the
tracked `shipwright_events.jsonl`. The tracked-log start+end pair reflects the
FIRST split and the per-phase duration **undercounts**; single-split phases are
exact.

The start side is *already* per-split (N un-deduped `phase_started`), so the log
is asymmetric (N starts / 1 end).

## Decision (user-confirmed 2026-07-11): Option 1 — per-split facts

Widen the `phase_completed` dedup key from `phase` to `(phase, splitId)` and
record one end **per split**. Rationale:

1. **Append-log-of-facts model.** Per-split start/end are atomic facts; the
   per-phase span is a *derived* view (earliest start → latest end). The
   dedup-by-phase was over-reaching — it collapsed genuinely distinct completion
   facts. `(phase, splitId)` is the true completion identity.
2. **Symmetry.** The start side is already per-split; this symmetrizes the end
   side rather than adding a second aggregation rule.
3. **Emit stays pure.** Option 2 ("emit only at final split") would couple the
   telemetry emit path back into lifecycle split-state ("am I the last split?"),
   which M-Pre-1 deliberately avoided. Option 1 needs no such coupling — the
   existing call-site `not idempotent` gate + `(phase, splitId)` dedup suffice.
4. **Strictly more information.** Enables the WebUI PhaseRail per-split
   breakdown (build genuinely fans out) AND a correct per-phase span, derived.

Single-split phases carry `splitId = None` → dedup by `(phase, None)`, identical
to the historical phase-only behavior (zero back-compat drift).

## Affected Boundaries

- `shipwright_events.jsonl` producer (`record_event.py`) — new top-level
  `splitId` field on phase events; widened dedup key. **io_boundary.**
- Phase-event emitters (3): single-session `orchestrator_pkg/events.py`,
  multi-session `phase_event_emit.py` + `phase_session_stop.py` hook. **hooks/
  `cross_component`.**
- Consumers with a phase-multiplicity assumption (all fixed after code review):
  compliance `compliance_report.py` phase-count, `generate_session_handoff.py`
  Recovery count, `update_build_dashboard.py` "Completed" timestamp,
  `verifiers/common.py::get_latest_phase_completed_event` (latest-by-`ts`).
- Producer: the plan SKILL `step-9-completion.md` per-split `phase_completed`
  gains `--split-id "{split_name}"` (plan fans out) so it aligns with the
  orchestrator's per-split end rather than leaving a phantom split-less end.
- Cross-repo: WebUI PhaseRail consumer (separate iterate — triage follow-up).
- **Secondary finalization-integrity fix (found during F5c):** the iterate-entry
  reader (`lib/iterate_entry.py::_is_entry_file`) accepted the gitignored WebUI
  session-plan sidecar `<run_id>.plan.json` (#358, same dir) as an entry; being
  date-less it sorted as the retention "oldest" and its
  `unlink(entry_file_for(run_id))` deleted the REAL entry (and shadowed
  `find_entry_by_run_id`). Fixed by excluding secondary-extension sidecars
  (canonical stems carry no `.`). Unblocks this run's own F5c/F11.

## Acceptance Criteria

- **AC1** — `phase_completed` events with the same `phase` but different
  `splitId` are ALL persisted (multi-split phase records one end per split).
- **AC2** — `phase_completed` events with the same `(phase, splitId)` are deduped
  (crash-resume backstop preserved per split); `splitId=None` (single-split)
  preserves the exact prior phase-only dedup + skip payload.
- **AC3** — `splitId` is a first-class top-level phase-event field, set via a new
  `--split-id` CLI arg; all three emitter wrappers pass it (derived from the
  `splitId` they already carry in `detail`), so the dedup + consumers can see it.
- **AC4** — the compliance phase-count consumer counts DISTINCT phase names, so a
  multi-split build no longer overcounts `completed_phases` (`len ≤ 7`).

## Test Plan

- Unit: `has_phase_event(phase, split_id)`; `build_event --split-id` → top-level
  `splitId`; different-split not deduped; same-split deduped (skip carries
  `splitId`); `splitId=None` back-compat (existing exact-equality tests unchanged).
- Wrapper argv pass-through (fast, subprocess.run captured): each of the 3
  emitters forwards `--split-id` from `detail.splitId`.
- **Integration (`category: integration`, gating):** multi-split build scenario
  via the real `record_event.main` CLI + `read_events` reader + the consumer
  reduction — N per-split starts+ends persist, same-split re-emit skipped,
  derived span covers all splits, compliance counts `build` once.
- Consumer: compliance `completed_phases` dedup unit test.

## Confidence Calibration

- **Boundaries touched:** `shipwright_events.jsonl` producer (`record_event.py`,
  new top-level `splitId` field + widened dedup key); 3 phase-event emitters
  (single-session `events.py`, shared `phase_event_emit.py`, and the
  `phase_session_stop` hook → `cross_component`); compliance phase-count consumer.
- **Empirical probes run:**
  - Round-trip: a per-split `phase_completed` written via the real
    `record_event.main` CLI → read back via `read_events` → `splitId` preserved
    as a top-level field (`test_phase_completed_different_splits_not_deduped`).
  - Multi-split dedup end-to-end: 3 distinct splits all persist; a same-split
    re-emit is skipped (integration `test_multi_split_build_records_every_split_end`).
  - Single-split back-compat: `splitId=None` dedups by `(phase, None)` and the
    skip payload is byte-identical to the historical shape (existing
    `test_skips_duplicate_phase` unchanged + `test_single_split_phase_unchanged`).
  - Wrapper pass-through: all 3 emitters forward `--split-id` from the `splitId`
    they already carry (`test_emit_phase_event_forwards_split_id_from_detail`,
    `test_run_plugin_emitters_forward_split_id`, integration via the stop hook).
  - Consumer: compliance renders `7/7` (distinct phases), not `9/7`
    (`test_multi_split_phase_counted_once`).
- **Test Completeness Ledger:** 13 `tested` code behaviors (incl. one
  `category:integration` composition behavior + the 3 review-found consumer fixes)
  and 1 `untestable` (the plan SKILL `--split-id` edit — a runtime-prompt change
  whose downstream per-split dedup path is `covered-by-existing-test` in
  `record_event`); 0 untested-testable; ACs 4/4 enumerated. Full block persisted
  at F5 in `shipwright_test_results.json.iterate_latest.test_completeness`.
- **Confidence-pattern check:**
  - *Asymptote (depth):* dedup identity probed at 3 levels — new-vs-new (both
    persist), new-vs-existing-same-split (skip), split-tagged-vs-untagged
    (distinct). No remaining "what if the key collides" question.
  - *Coverage (breadth):* every emit site (3 orchestrator wrappers + the plan
    SKILL producer), the writer (CLI + `append_event_idempotent`), and ALL FOUR
    phase-multiplicity consumers are covered. (Code review disproved the initial
    "one overcount-prone consumer" assumption — 3 more consumers were found and
    fixed: session-handoff count, dashboard timestamp, latest-by-`ts` verifier.)
  - *Integration composition (`cross_component`):* the hook-emit → record_event
    dedup → consumer-reduction chain is proven to compose on a real 3-split build
    (`category:integration`), satisfying the F11 `check_integration_coverage` gate.
