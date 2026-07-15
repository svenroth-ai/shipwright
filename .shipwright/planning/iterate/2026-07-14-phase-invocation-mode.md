# Iterate: phase skills detect invocation mode from the dispatch token, not the v1 fields

- **Run ID**: `iterate-2026-07-14-phase-invocation-mode`
- **Type**: BUG (Path C — root cause first)
- **Complexity**: medium (`prior_source: history`, n=20)
- **Risk flags**: `touches_io_boundary`, `cross_component` (diff-recomputed:
  `get_phase_context.py` is FRAMEWORK cross-component machinery)
- **Spec Impact**: NONE (no FR changes — pipeline-internal control flow)
- **Origin**: Codex review of PR #369 (delta round)

---

## Symptom

A phase skill dispatched by the orchestrator concludes **standalone**, skips its
pipeline-state updates, and stamps its artifacts `"mode": "standalone"` — even
though it is part of a driven run.

## Root Cause (Iron Law: no fix without root cause)

The 7 orchestrator-driven phase skills classify pipeline-vs-standalone in their
First-Actions **step C ("Detect Invocation Mode")** by reading two fields of
`shipwright_run_config.json`:

```
pipeline  ⟺  status == "in_progress" AND current_step == "<my phase>"
```

`current_step` / `completed_steps` are the **v1** fields. The **v2** pipeline's
authority is `phase_tasks[]`. `phase_task_lifecycle.py` — the only writer of
phase state in a driven run — advances `phase_tasks[]`,
`completed_phase_task_ids` and the run `status`, and **never writes
`current_step`**. `orchestrator_pkg/config_factory.py` stamps `current_step` once
at run creation (`remaining[0]`, i.e. `"project"`) and nothing advances it after.

So for every driven run past the first phase, `current_step` is frozen at
`"project"` while the real frontier has moved on → the step-C predicate is
**false for every phase**, and every driven phase self-classifies as standalone.

**Two components, one contract, never agreed:** the *writer* (v2, `phase_tasks[]`)
and the *reader* (v1, `current_step`) were never wired to each other.

**Not a regression from `iterate-2026-07-14-remove-multi-session` (#369).**
Verified against `origin/main`: the deleted `phase_session_stop.py` hook contains
no occurrence of `current_step`/`completed_steps` either, so the check was
equally blind under `multi_session`. This is the long-standing v1-compat vs v2
divergence, surfaced by a fresh-eyes reviewer.

## Blast radius (worse than mislabeling)

`plugins/shipwright-run/scripts/lib/phase_validators.py:281` — `_validate_test`
**rejects** test results carrying `mode == "standalone"`:

> "Test results were produced in standalone mode (not part of this pipeline run).
> Re-run /shipwright-test within the pipeline for accurate validation."

A driven test phase misclassifies → writes `mode: standalone` → the pipeline's own
validator discards its own results and demands a re-run *inside the pipeline* —
which misclassifies again. **Self-inflicted deadlock**, not a cosmetic label.

## Scope correction: 7 skills, not 8

`security` is **out-of-band** since `sec-report-and-orchestrator-decouple`:
`phase_state_machine` never materialises a `security` phase_task, and the security
skill's "Detect Mode" keys on the existence of `shipwright_project_config.json`,
not on `current_step`. It is **not affected**. In scope:

| Skill | File(s) carrying step C |
|---|---|
| project | `references/first-actions.md` (§D) |
| design | `SKILL.md` (§C) |
| plan | `SKILL.md` (§C, pointer) + `references/first-actions.md` (§C) |
| build | `SKILL.md` (§C, pointer) + `references/first-actions.md` (§C) |
| test | `SKILL.md` (§B2) + `references/first-actions.md` (§B2) |
| changelog | `SKILL.md` (§C) |
| deploy | `SKILL.md` (§B2) |

---

## Mini-Plan

### Alternative A — mirror the v1 fields (REJECTED)

Have `phase_task_lifecycle` write `current_step`/`completed_steps` alongside
`phase_tasks[]`. Zero skill changes; legacy readers refresh.

**Rejected for three reasons:**
1. **Structurally lossy.** v2 fans phase_tasks out per split (`build/01-core` and
   `build/02-ui` are concurrent frontier tasks). A scalar `current_step` cannot
   represent that frontier — it would be a lie in exactly the cases that matter.
2. **Re-creates the defect.** Two sources of truth for one fact is the drift that
   caused this bug; mirroring institutionalises it.
3. **It answers the wrong question.** Step C needs "was *I* dispatched by the
   orchestrator?" — a *per-invocation* fact. `current_step` answers "what phase is
   the run at?" — a *per-run* fact. Under A, a human running `/shipwright-test`
   out-of-band while the pipeline sits at `test` would self-classify as **pipeline**
   and stomp the driven run's state. A fixes the false-negative and adds a
   false-positive.

### Alternative B — key on the dispatch token (CHOSEN)

The orchestrator hands the phase-runner a `phaseTaskId` (`single-session-next` →
dispatch descriptor → `phase-runner.md` Input). **Possession of a resolving
`phaseTaskId` IS the definition of "I am a driven phase."** It is per-invocation,
maintained, and already the signal Step 0 (context recovery) uses.

`shared/scripts/tools/get_phase_context.py` **already computes exactly this** and
returns `mode: "pipeline" | "standalone"`, fail-closed to standalone on every
degenerate input (no id, no config, parse error, schema v1, id not found). The
skills simply don't consume it — step C re-derives the mode from stale fields
instead. So the fix is to **make step C consume the answer Step 0 already has**,
and delete the v1 decision tree.

Consequence: step C and Step 0 can no longer disagree, and 7 prose decision trees
over unmaintained fields collapse into 1 tested resolver + 7 thin consumers.

**Cost:** step C's clause 4 (out-of-sequence warning) also reads `current_step`,
so it needs a v2-native predicate — otherwise the fix would leave a second stale
read behind, or silently drop a safety warning.

---

## External Plan Review (GPT-5.6 + Gemini 3.1 Pro — both succeeded, not degraded)

Accepted, folded into the ACs below:

| # | Reviewer | Sev | Finding | Landing |
|---|---|---|---|---|
| 1 | GPT #2 | **high** | `standalone` is an **unsafe fallback for a token-bearing invocation**. A transient parse/read failure would make a genuinely-driven phase proceed as standalone — re-entering this very bug through the back door. | **AC1**: third outcome `mode: "error"` ⇒ STOP. Standalone is reserved for *no token*. |
| 2 | GPT #1, Gemini #3 | med | "a resolving id ⇒ pipeline" is too weak: a **terminal** task id, or one whose phase ≠ the invoked skill, would still grant pipeline mode and could stomp finalized state. | **AC2**: explicit validity contract — task must exist, match the caller's phase, and be in an actionable (non-terminal, claimed) state. |
| 3 | Gemini #1 | med | Don't make the LLM intersect `active_phases` against its own phase — models are unreliable at state-machine logic in prose. | **AC3**: the tool returns a ready-made boolean `requires_out_of_sequence_warning`; step C does a binary check. |
| 4 | GPT #4 | med | AC6 must cover the **concurrent split frontier** (`build/01-core` + `build/02-ui`) — the exact case that makes `current_step` structurally unfixable. | **AC6**. |
| 5 | GPT #6 | med | Define "live driven run" against the lifecycle state machine, not an ad-hoc status list. | **AC1**: `pipeline_active` uses `phase_task_lifecycle.TERMINAL_STATUSES` as SSoT. |
| 6 | GPT #8 | low | Prose-scanning for the absence of `current_step` gives false confidence. | **AC5**: assert the *canonical positive pattern* (mode assigned from the helper) + prohibit any run-config-field predicate in the section. |
| 7 | GPT #5 | med | New output fields = new public contract; audit call sites. | Audited: consumers are the phase-runner Step-0 prose + 2 test files. No schema/jq consumer. Fields are additive. |

**Rejected — Gemini #2** ("delete `current_step`/`completed_steps` generation from
`config_factory.py` as dead code"): **Chesterton's Fence.** Those fields still have
live readers — `phase_quality._resolution.resolve_source` keys on their *presence*
for audit telemetry, and compliance `mermaid.py` renders the dashboard phase strip
from `current_step`. Deleting the writer would silently flip every driven run's
audit source to `standalone` and blank the dashboard. That is a separate,
larger-blast-radius change; deferred to a triage follow-up, not bolted on here.

**Rejected — GPT #7** (`phaseTaskId` as a forgeable capability / signed nonce):
the trust model here is a single local repo whose `shipwright_run_config.json` is
git-tracked and readable by its owner. `phaseTaskId` is a **correlation id, not an
authorization token**. AC2's validity contract removes the dangerous cases (stale /
terminal / wrong-phase ids); a dispatcher-only nonce would be a security theatre
feature beyond spec (YAGNI). Documented as an explicit trust-model constraint.

---

## Acceptance Criteria

- **AC1** — `get_phase_context.py` resolves **three** outcomes, not two:
  - `pipeline` — a valid dispatch token for this phase;
  - `standalone` — **no token was supplied** (the only standalone trigger);
  - `error` — a token *was* supplied but does not resolve to a valid, actionable
    task for this phase (missing/corrupt/v1 config, unknown id, wrong phase,
    terminal task). The caller **STOPs**; it must never silently degrade to
    standalone, because that is the failure this iterate exists to remove.

  The standalone payload additionally reports whether a driven run is nonetheless
  live: `pipeline_active` (bool), `active_phases` (non-terminal phases, deduped),
  and the ready-made `requires_out_of_sequence_warning`. Liveness is defined
  against the lifecycle's terminal statuses and reads only v2 fields — never
  `current_step`.

  > **AC1 amended during build (honesty).** The AC first said "SSoT *import*, no
  > ad-hoc list", and the external code reviewer correctly flagged that the code
  > keeps a pinned *copy* instead. The copy is deliberate and the AC was wrong:
  > this resolver runs in EVERY driven phase, including from a shared-only plugin
  > cache where `plugins/shipwright-run/` may not be on disk at all, so a hard
  > cross-plugin import would turn a missing sibling tree into a crash on every
  > phase (ADR-044). That is exactly the precedent
  > `shared/scripts/tools/verifiers/integration_coverage.py` already sets. The
  > copy is pinned to the SSoT, both directions, by `test_terminal_statuses_sync`.
- **AC2** — Validity contract for a token: the task must (a) exist in
  `phase_tasks[]`, (b) have `phase == --phase` when the caller declares its phase,
  and (c) be in an actionable state (`in_progress` — i.e. claimed by the
  orchestrator before dispatch). A terminal or unclaimed task yields `error`.
- **AC3** — All 7 phase skills' step C keys on the dispatch token and consumes the
  tool's verdict verbatim; no phase skill's invocation-mode section reads
  `current_step`/`completed_steps` or re-derives the mode from run-config fields.
  The out-of-sequence warning survives on v2 fields as a **binary check** of
  `requires_out_of_sequence_warning` (gate `<phase>.out-of-sequence-continue`
  keeps its id and policy).
- **AC4** — `shared/config/gate_catalog.json`'s 5 `*.out-of-sequence-continue`
  summaries no longer describe the removed `current_step` predicate; the GENERATED
  `docs/gate-catalog.md` is regenerated from the JSON.
- **AC5** — Drift protection (both directions, registry ⇄ files): for every
  orchestrator-driven phase skill, its invocation-mode section (a) exists,
  (b) contains the **canonical positive pattern** — the mode is *assigned from*
  `get_phase_context.py`'s verdict — and (c) contains **no** run-config-field
  predicate (`current_step`, `completed_steps`, or a bare `status ==
  "in_progress"` mode test). Reverse: no skill outside the driven-phase registry
  carries an invocation-mode section. Prose-scanning alone is explicitly *not*
  treated as behavioral coverage — AC6 carries that.
- **AC6** — Integration coverage (`cross_component`, non-dodgeable): a real-scenario
  test drives a v2 run_config through the actual `phase_task_lifecycle` transitions
  (claim → complete → plan-next) and asserts the step-C resolver returns `pipeline`
  for the dispatched `phaseTaskId` at **every** frontier phase — the scenario that
  is broken today — and that the old v1 predicate returns *standalone* at each of
  them (the regression pin). Plus the out-of-band direction and the token-bearing
  `error` path.

  > **AC6 amended during build (honesty).** The AC originally demanded a
  > **concurrent** split frontier (`build/01-core` and `build/02-ui` in flight at
  > once). Driving the real lifecycle proved that is **unreachable**: splits are
  > SERIAL (`plan/01 → build/01 → plan/02 → build/02`), and `_plan_next_inplace`
  > only materialises the successor *after* its predecessor completes, so at most
  > one task is non-terminal at a time. Rather than fake a scenario the machine
  > cannot produce, the integration test drives the **real** serial split fan-out
  > and pins the property that actually matters: the frontier is
  > **split-qualified**, so the two `plan` tasks share a phase name but are
  > distinct tasks — which is why a phase-scoped scalar `current_step` could not
  > have identified "which task am I" even if it *were* maintained. The dedupe of
  > `active_phases` across same-phase tasks stays covered as a defensive unit test.
- **AC7** — `docs/hooks-and-pipeline.md` context-loading matrix reflects that phase
  skills resolve invocation mode via `get_phase_context.py` (mandated by CLAUDE.md
  when what a plugin reads at startup changes).
- **AC8 (added during build — the fix's own blast radius)** — `orchestrator.py
  update-step` is **inert in a driven run**: it makes no run-state write when the
  config is drivable (`is_single_session`), while still triggering the between-phase
  compliance refresh.

  > **Why this became mandatory.** The Stage-3 doubt reviewer found that correcting
  > the classification would *activate* a latent v1 path. The phase skills define
  > pipeline mode as "update orchestrator state" and their completion steps call
  > `orchestrator.py update-step` unconditionally; `run/SKILL.md` forbids exactly
  > that in a driven run, but only in prose. It stayed harmless **by accident** —
  > the phases misclassified as standalone and skipped the call. Fixing the
  > misclassification would have made them start calling it for real, and
  > `update_step` writes `status = "needs_validation"` on any ask-level issue —
  > the same key `resolve_next_dispatch` reads *before* the phase_tasks frontier.
  > One ask-level issue (a split with no unit tests) would then halt a structurally
  > healthy run, **permanently** (nothing resets `needs_validation` → `in_progress`).
  >
  > So the invocation-mode fix could not ship alone: without AC8 it would have
  > traded a mislabeling bug for a run-wedging one. The guard is mechanical, not
  > prose — a driven run cannot be wedged by a phase skill regardless of what any
  > SKILL.md says. Verified by negative control: with the guard removed, the wedge
  > test reproduces `status == "needs_validation"`.

  The 7 skills' `pipeline` bullet is corrected to match: *do not* call `update-step`;
  `single-session-apply` records your status when it applies your result.

## Affected Boundaries

- **Producer/consumer boundary:** `shipwright_run_config.json` — v2 writer
  (`phase_task_lifecycle`) vs skill-side reader (step C). This is the boundary that
  broke. Round-trip probe required (`touches_io_boundary`).
- **Cross-component composition:** `get_phase_context.py` (pipeline-validator class)
  × `phase_task_lifecycle.py` (state authority) × the skills' step C (consumer).

## Confidence Calibration

- **Boundaries touched:**
  - Producer/consumer: `shipwright_run_config.json` — v2 writer (`phase_task_lifecycle`)
    vs skill-side reader (step C). The boundary that broke.
  - Cross-component composition: `get_phase_context.py` × `phase_task_lifecycle.py` ×
    step C × the `update-step` CLI (the guard's blast radius).
  - CLI contract: `get_phase_context.py` gained a third exit code (2) and `--phase`;
    `orchestrator.py update-step` gained a driven-run no-op branch.

- **Empirical probes run:**
  - *Reproduce* (`scratchpad/probe1.py`): drove `project→design→plan` through the REAL
    `phase_task_lifecycle`; confirmed `current_step` frozen at `project`, so the old
    step-C predicate returned STANDALONE for design + plan while the token predicate
    returned pipeline. The bug, reproduced.
  - *Not-a-regression*: `git show origin/main:…/phase_session_stop.py` — the deleted hook
    contained no `current_step` write, so the check was equally blind under multi-session.
  - *Wedge, negative control*: disabled the guard → the integration wedge test reproduced
    `status == "needs_validation"` on a healthy run; re-enabled → gone. The HIGH finding,
    reproduced and then closed.
  - *Drift gate, negative control*: re-introduced the v1 predicate under a renamed heading
    in `build/SKILL.md` → `test_registered_file_never_names_a_v1_state_field` failed as
    required; restored → green. The gate actually gates.

- **Test Completeness Ledger:** every behavior this diff introduces →
  `tested` (evidence) or `untestable` (closed-vocab reason). 0 testable-but-untested.

  | Behavior | Disposition | Evidence |
  |---|---|---|
  | no token → standalone (+ live-run snapshot) | tested | `test_get_phase_context::test_no_phase_task_id_*`, `test_phase_invocation_mode_edges::test_none_token_is_standalone` |
  | empty / placeholder token → error (not standalone) | tested | `test_phase_invocation_mode_edges::test_empty_or_blank_token_is_error`, `…placeholder_is_error` |
  | valid actionable token for this phase → pipeline | tested | `test_get_phase_context::test_pipeline_mode_*` |
  | wrong-phase / terminal / unclaimed / unknown token → error | tested | `test_get_phase_context::test_*_is_error`, `test_phase_invocation_mode_edges::test_*_names_the_*_remedy` |
  | corrupt v2-shaped config never raises → error / not-live | tested | `test_phase_invocation_mode_edges::test_structurally_corrupt_*` |
  | `active_phases` dedupes same-phase tasks | tested | `test_get_phase_context::test_active_phases_dedupes_concurrent_split_tasks` |
  | exit code 2 on error | tested | resolver returns `mode:error`; `get_phase_context.main` maps to 2 (asserted via CLI in guard tests' sibling patterns) |
  | **composition: every dispatched frontier phase resolves pipeline through the real lifecycle** | tested (`category: integration`) | `integration-tests/test_phase_invocation_mode_integration.py::test_every_dispatched_phase_resolves_as_pipeline` |
  | `update-step` inert in a driven run; v1 path intact otherwise | tested (`category: integration`) | `test_update_step_driven_run_guard.py` (CLI subprocess), `test_shipwright_run_e2e.py` (v1 path) |
  | all 7 skills resolve mode via the resolver; none name v1 fields | tested | `test_phase_skill_invocation_mode_canon.py` (both directions + negative control) |
  | `TERMINAL_STATUSES` copy pinned to SSoT | tested | `test_get_phase_context::test_terminal_statuses_sync` |
  | gate-catalog summaries + generated doc updated | tested | catalog re-validated + doc re-rendered by `resolve_gate_policy.py` (drift-guarded in CI) |

- **Confidence-pattern check:**
  - *Depth (asymptote):* the resolver's branch set is closed — {absent, empty, placeholder,
    no-config, unreadable, unknown-id, wrong-phase, non-actionable, valid} — each with a
    test; further probes return no new failure modes.
  - *Breadth (coverage):* all 7 driven skills updated + drift-gated; `security` explicitly
    excluded with a lifecycle-verified reason.
  - *Integration composition (`cross_component`):* two `category:"integration"` behaviors —
    the resolver composed with the real `phase_task_lifecycle` frontier, and the
    `update-step` guard composed with the driven loop — satisfy the non-dodgeable
    `check_integration_coverage` gate.
