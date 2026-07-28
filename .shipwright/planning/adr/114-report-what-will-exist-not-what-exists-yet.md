# ADR-114 — Report against what will exist, and assert only what you have evidence for

**Run-ID:** `iterate-2026-07-27-handoff-tally-and-gate-honesty`
**Date:** 2026-07-27
**Status:** accepted
**Predecessor:** ADR-113 / `iterate-2026-07-27-phase-gate-override-evidence` (PR #438)

---

## Context

ADR-113 shipped two things whose entire purpose is telling a person the truth about
state: a `## Pipeline Phases` block in the session handoff, and a durable
`validation_overrides[]` record. A Stage-2 code review and a Stage-3 doubt review,
run **after** that PR merged, found that both said things that were not so.

The reviews are the reason this ADR exists. They had been closed `not_run` on the
predecessor under a session rule barring subagents, with the substitution recorded
as "external code review + self-review + red-check covers it". **It did not.** The
external LLM reviews and the self-review found none of the defects below. That is
recorded here so the substitution is not claimed again.

## Decision

Two rules, each generalising past its own bug.

### 1. Denominate against what will exist, not what exists yet

`phase_tasks[]` is materialised one entry at a time — `config_factory` seeds a
single project task and `plan_next_phase` appends each successor as its predecessor
completes. Counting `finished of len(phase_tasks)` therefore reported a run one
phase into seven as **"1 of 2"**, and the block called itself *authoritative*. The
overstatement was worst at the start, exactly when someone is resuming.

The denominator is now `max(len(pipeline) + 2·(splits−1) + off_pipeline, planned)`:

- `pipeline` is the real step list;
- `plan` and `build` expand once per frozen split, so a 3-split run has 4 extra
  tasks — without this a fully-built 3-split run rendered **"8 of 8"**, a
  categorical 100%-complete claim with three phases unplanned;
- a phase present as a task but absent from `pipeline` (`legacy_migration` drops
  `security` from the pipeline while leaving its task) is counted explicitly,
  because the `max` fallback only catches it *after* the extra task exists — i.e.
  never while the overstatement is on screen.

### 2. Assert only what you have positive evidence for

The dispatch pointer proves nothing on its own: `advance_pointer` moves it to the
**successor** and resets `attempt` to 0 after every completed phase, so "pointer
set" is the normal between-phases state.

The attempt counter proves nothing either. It records that a dispatch *happened*,
not that one is *live*: `recover-phase-task --force-status awaiting_launch` (the
default, and exempt from the drivability guard) releases the claim without touching
`run_loop_state.json`, so a recovered task keeps `attempt >= 1`. Treating that as
evidence printed `Currently dispatched: build (status awaiting_launch, attempt 2)`
— a line contradicting itself one recovery after the claim was released.

**The task's own status decides.** `in_progress` (set under CAS at claim time) is
dispatched; terminal is finished-or-dead; everything else is *Next up*. A terminal
task under the pointer renders as a stale pointer, not as work in flight — otherwise
`recover --force-status skipped` printed the same phase as banked *and* in flight.

The same rule applied to the override record: `validate_phase` returns `(True, [])`
for a step with no validator, and `security` is an accepted `--step` with none. That
minted `gate_result: "pass"` — a durable claim that a gate had been satisfied where
none exists. `gate_result` now has three values, the third being `not_checked`.

And to a status the renderer cannot read: `| project | — | unknown | no |` asserted
*not finished* about a status it had just admitted it could not parse. The verdict
cell now says `unknown` too.

### 3. A drift guard must force the classification, not a set membership

The predecessor's guard asserted `FINISHED_STATUSES <= declared` — a subset check
that stays green when a *new* status is added while the renderer silently classifies
it as not-finished. Replacing it with a verdict map plus four independent status
literals was no better: the cheapest way to green was to add a verdict and nothing
else, leaving the newcomer out of the tally, out of every bullet, and non-terminal
for the pointer — silently rebuilding the very defects being fixed.

`shared/scripts/lib/handoff_phase_status.py` now derives **every** set from one
bucketed map. Adding a key IS classifying it, and a bucket nobody defined is a
`KeyError` at import rather than a wrong sentence in someone's handoff.

## Consequences

- `handoff_pipeline.py` shrinks to 259 LOC; the vocabulary lives in a 90-LOC module
  with a single responsibility.
- `gate_result: "not_checked"` is a new enum value in the v2 schema.
- `validation_notes` dedups on `(step, message)` rather than replacing per step —
  per-split findings from `plan/01` are not superseded by `plan/02`'s.
- `validation_issues` is now filtered by the same predicate as the status reset, so
  completing step B no longer strips step A's findings while leaving the run parked.
- `--force` on a non-completion status needs no reason (it overrides nothing), and a
  driven `single_session` run stays inert instead of exiting 2.

## Rejected

**A public `has_validator()` on `phase_validators.py`** (Stage-2 review). Correct in
principle — reaching for a private `_VALIDATORS` from another package is coupling.
But that file is grandfathered at 495 LOC and the addition ratcheted its bloat
baseline; cutting unrelated lines to make room would game the metric, which this
repo's own convention forbids. Kept the private import with the reason in code; the
coupling is pinned by a test. Revisit when `phase_validators.py` is split.

**Removing `record_validation_override`'s unused return** (Stage-2 review suggested
it; external code review objected). Reverted — removing a return is a compatibility
change with no defect behind it, and this is a bug iterate.

**Fixing the corrupt-config standalone demotion** (doubt review, medium).
`_read_standalone_flag` returns `True` whenever the config cannot be parsed, so the
whole override guarantee switches off and `_load_or_bootstrap` can overwrite a real
config. Real, but it predates ADR-113, its blast radius is every v1 caller, and
fixing it means deciding what a corrupt config should do to a run. Its own iterate.

## Verification

- Every fix has a reproduction that fails against `f6179f6e`: 9 of 13 handoff tests
  and 9 of 14 gate tests were red before the fix.
- Suites: 5584 shared · 393 shipwright-run · 422 integration · ruff clean ·
  anti-ratchet clean.
- Ledger: 42 behaviours, 41 tested, 1 untestable (docs prose), 0 testable-but-untested.
