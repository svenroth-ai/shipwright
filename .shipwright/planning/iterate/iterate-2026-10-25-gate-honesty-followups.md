# Iterate Spec: gate-honesty-followups

- **Run ID:** iterate-2026-10-25-gate-honesty-followups
- **Type:** change
- **Complexity:** medium
- **Status:** draft

## Goal
Three follow-ups the A5 review (campaign brief-driven-run-a-real-gates) left open, all about the driven run's phase records telling the truth afterwards:

1. A phase forced to `skipped` (`recover-phase-task` / `single-session-recover --force-status skipped`) leaves no trace of why. Today the task only flips status.
2. A phase whose gate PASSED leaves nothing durable: the `gate` block is in apply's stdout only, so afterwards "passed its checks" is not recorded anywhere (only an override writes `validation_overrides[]`).
3. A gate-rejected phase is retried by `single-session-next`, which re-claims the task idempotently with the SAME `version` and `sessionUuid`. A phase-runner from the earlier dispatch still holds a valid CAS pair and can apply its result after the phase was re-dispatched.

## Acceptance Criteria
- [ ] AC-1 (skip needs a reason): `recover_phase_task(force_status="skipped")` with no reason, an empty or a whitespace-only reason returns `ok:false, reason:"skip_reason_required"` and leaves `shipwright_run_config.json` byte-identical. The CLI `recover-phase-task --force-status skipped` without `--reason` exits 1 with that reason; `single-session-recover` behaves the same.
- [ ] AC-2 (skip reason persisted): with `--reason "<why>"` the task becomes `skipped` and carries `skipReason: "<why>"` (control characters and line breaks become spaces, whitespace collapsed, capped at 500 chars). Any later recover removes `skipReason`, the `gate` record and `redispatchedAt`.
- [ ] AC-3 (skip event): a successful skip through either CLI appends one `phase_skipped` event to the tracked `shipwright_events.jsonl` whose `detail` JSON carries `phaseTaskId`, `splitId`, `runId`, `reason` and `recoveredFrom`; `single-session-recover` also carries `reason` on its loop `recovery` event.
- [ ] AC-4 (passed gate record): an enforced `single-session-apply` whose gate passes writes `phase_tasks[i].gate = {result:"pass" (or "not_checked" when the gate could not check), checked, phase, splitId, runId, at, issueCount:0, informCount, overridden:false}` in the same locked write as the completion; `runId` is the id the canon check was run against (`gate_run_id.canon_run_id`). Inform notes themselves are still not persisted (count only).
- [ ] AC-5 (override record on the task too): an `--override-reason` apply writes the same `gate` block with `result:"fail"` (or `pass` / `not_checked` when nothing was waived) and `overridden:true`, beside the unchanged `validation_overrides[]` entry. A rejected apply (`phase_gate_failed`) writes no `gate` block.
- [ ] AC-6 (token rotation): `single-session-next` re-dispatching a task that is already `in_progress` (gate retry or crash resume) bumps the task's `version` and returns the new one in the descriptor; `executionCount` is unchanged and `idempotent` stays `true`.
- [ ] AC-7 (stale apply refused): after a gate rejection and a re-dispatch, an apply carrying the FIRST dispatch's `version` (ok:true or ok:false) is refused `stale_version` (CLI exit 2) and changes nothing — the task stays `in_progress`, no `gate` block, no completion, no re-frozen splits for a design task, also when the re-dispatch lands while the stale apply's gate runs; the second dispatch's apply then completes the phase.

## Spec Impact
- **Classification:** none
- **ADD:** none · **MODIFY:** none · **REMOVE:** none
- **NONE justification:** restores what FR-01.01 already requires: AC03 ("passed its checks" and "was waved through" can be told apart afterwards, which needs a pass record and a skip reason) and AC02 (a phase is never counted done on work that failed its own check — a stale result applied after a re-dispatch could do that). Requirement text unchanged. Affected FR: FR-01.01.

## Out of Scope
- Requiring a reason for `--force-status failed` / `awaiting_launch` (accepted, recorded in events only).
- A runtime "skip" choice offered by the master in the ask-human menu (the skip stays an operator command).
- Rotating `sessionUuid` itself (it is pre-bound at planning time and documented as fixed; `version` is the CAS counter that already fences recover).
- Fixing the documented `phase_completed` dedup event loss.

## Design Notes
n/a (no UI).

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `phase_task_recovery.recover_phase_task` | `shipwright_run_config.json` readers (handoff, WebUI, phase_quality) | `phase_tasks[].skipReason` (string) |
| `single_session_apply` via `complete_phase_task(on_complete=…)` | same | `phase_tasks[].gate` object |
| `orchestrator_pkg.events.record_phase_skipped` → `record_event.py --type phase_skipped` | tracked `shipwright_events.jsonl` readers | event `{type:"phase_skipped", phase, splitId?, detail:<json string>}` |
| `phase_task_recovery.redispatch_phase_task` (version bump) | `single-session-apply` / `complete_phase_task` CAS | `phase_tasks[].version` integer |

## Confidence Calibration
- **Boundaries touched:** the four rows above.
- **Empirical probes run:** filled during build (real CLI subprocess round-trips: recover → run_config → events.jsonl; apply → run_config `gate`; stale apply via the CLI exit code).
- **Test Completeness Ledger:** filled at F5.
- **Confidence-pattern check:** filled at F5; integration behavior: next → reject → next → stale apply → fresh apply through the real CLI composes lifecycle + loop + gate (category `integration`).

## Verification (medium+)
- **Surface:** cli
- **Runner:** pytest subprocess tests driving `orchestrator.py` subcommands against a temp project.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** sound plan fitting the CAS design; a stale design apply re-froze splits and a recover kept an old gate record.
- **Findings:** (1) stale design apply re-freezes splits, high - fixed (freeze only when the task is current and open) + test; (2) recover keeps old `gate`, medium - fixed (every recover drops `skipReason`/`gate`/`redispatchedAt`) + test; (3) `not_checked` recorded as pass, medium - fixed (`gate_record` reuses `gate_summary`'s result) + test, AC-4 reworded; (4) LOC near 300 in phase_gate/apply, medium - fixed by measurement (291 / 293 LOC); (5) composed hook must not wrap `OverrideRefused`, medium - fixed (override first, no try/except) + test; (6) claim and rotation are two locks, low - fixed (rotation before any loop-state write; refusal surfaces as `claim_failed`) + test; (7) read-only `next` descriptors carry the pre-rotation version, low - fixed in docs (apply only with the latest `single-session-next`); (8) `startedAt` kept on re-dispatch, low - decided and documented, pinned by test; (9) legacy security migration skip has no `skipReason`, low - fixed (`security-decouple-migration`); (10) free-text reason, low - fixed (normalised one line, help text and docs warn it is committed); (11) two emit sites could double the event, low - fixed by tests asserting exactly one event per CLI; (12) new event type acceptance + docs matrix, low - fixed (new shared test file, artifact-write matrix row).
- **Known limitations:** none beyond the ones under Internal Architecture Review.
- **Status:** 12 fixed

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes
- **Severity:** low
- **Summary:** approve option A; all three gaps are real and nothing that exists covers them.
- **Findings:** (1) necessity - accepted; (2) smallest option A (B redundant, C blurs the override list, D leaves a never-gated skip untraced) - accepted, the always-required rule is option A; (3) a stale worker re-reading its version through claim/get_phase_context could pick up the new one, medium - disclosed: a phase-runner never applies (phase-runner.md forbids apply/claim/recover), the master applies with the descriptor of the dispatch it briefed, and the docs now say only the latest `single-session-next` version is valid; (4) a late failure refused `stale_version` could go unseen, low - disclosed: the CLI returns the refusal (exit 2) to the master, which surfaces it; no new loop event type; (5) `skipReason` is operator free text, low - fixed (normalised; schema says render as data); (6) consumers must tolerate `phase_skipped`, low - fixed (schema + docs; record_event accepts it).
- **Known limitations:** a stale runner that obtains the newer version by reading the task (not through its own dispatch) is fenced only by the phase-runner contract, not by the CAS.
- **Status:** 2 fixed, 2 disclosed, 2 accepted

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-10-25-gate-honesty-followups/architecture_brief.md`
- **Verdicts:** glm=approve - openai=approve
- **Smallest thing that would do (per reviewers):** as proposed (option A).
- **Findings:** glm (low): `phase_skipped` is the only genuinely new standing thing - accepted; glm (low): keep the reason refusal a plain argument check - done (checked before the lock, no new layer); openai: no findings.
- **Reconciliation:** both reviewers chose A, the plan's option; nothing to reconcile.

## External Plan Review (glm, openai)
- **Verdicts:** glm=revise - openai=revise
- **Findings:** glm: rotating on every idempotent re-entry would supersede a live runner on a duplicate `next` call, medium - rejected-with-reason: phase-runners never call `next`; only the master does, and a second `next` IS a new dispatch whose descriptor supersedes the earlier one by design (documented: do not call `next` again while a runner is out); glm: 600-char truncation test - accepted-and-fixed; glm: event append after the config write, low - disclosed: the reason is on the task in the same write as the skip, the append is best-effort and reports a failure on stderr (same contract as the other phase events); glm: `executionCount` semantics - accepted-and-fixed (schema: fresh claims only); glm: `gate_record` reads `run_id` from the verdict - accepted-and-fixed; glm: run the shared suites for exact-dict assertions - done (F0); glm: reason escaping - record_event JSON-encodes the detail. openai: recover leaves a stale `gate` record, medium - accepted-and-fixed; openai: event-write failure and retry, medium - disclosed as above (a second skip after a re-open is a new decision with its own event, by design not deduped); openai: race between a re-dispatch and an older apply, medium - accepted-and-fixed: the completion CAS re-reads under the same lock, pinned by a test whose gate triggers a re-dispatch mid-apply.

## External Code Review (glm, openai)
- **Round 1:** openai=revise (high: a stale design apply could still freeze splits when its re-dispatch landed while its gate ran), glm=approve. Accepted-and-fixed: first a fenced `freeze_splits`; openai then named the window between the freeze lock and the completion lock, so the freeze moved INTO the completion's locked write (`completion_hook`: override, then `apply_frozen_splits`, then the gate record), pinned by `test_a_design_redispatch_landing_while_the_gate_runs_freezes_nothing`. No residual window remains.
- **Final round (full merge-base diff):** openai=approve, glm=revise.

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | glm | medium | the freeze is conditioned on `gate_due`, so an ungated (`enforce_gate=False`) design completion would no longer freeze | rejected-with-reason: `gate_due` is the CAS check (current version + `in_progress`), independent of `enforce_gate`; pinned by the new `ungated` case of `test_a_current_design_apply_still_freezes_in_the_completion_write` |
| 2 | glm | low | freeze failure lost the structured `blockMessage` shape | rejected-with-reason: the lock-timeout that produced the structured failure is now the completion's own (`complete_phase_task` is `@_guard_lock_timeout`), and `_resolve_splits_with_fallback` returns the 3-tuple on every path (missing/corrupt configs fall back to `[]` with a warning, as `freeze_splits` always did) — the `except` is a defensive guard for an unexpected raise; the existing `freeze_splits_failed` test now injects the raise |
| 3 | glm | low | the idempotent claim result is replaced, dropping fields | accepted-and-fixed: merged (`{**claim, **rotated, "idempotent": True}`); the descriptor is built from a fresh config read either way |
