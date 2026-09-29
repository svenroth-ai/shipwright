# Iterate Spec: campaign-runner-architecture-review

- **Run ID:** iterate-2026-09-29-campaign-runner-architecture-review
- **Type:** feature
- **Complexity:** medium
- **Status:** implemented

## Goal
Wire the external architecture review (`external_review.py --mode architecture`,
P2.17 / PR #582) into the campaign `sub-iterate-runner`, closing the divergence
PR #582 named in its Out of Scope (P2.17a): the skill, the guide and the spec all
claimed "every medium+ Branch A" while the runner — which carried its own inlined
copy of Step 3.5 — never made the second call. Two decisions, both made by the
operator on 2026-09-06 and adopted verbatim:

1. **The 497-line cap is paid for by extraction, not an exception.** The runner's
   inlined copy of Step 3.5 Branch A moves to
   `references/campaign-step-3-5-plan-review.md`; the runner keeps a pointer, the
   branch labels and the halt rule. No bloat-baseline exception is minted or
   raised — both capped files (`sub-iterate-runner.md`, `campaign-mode.md`) end at
   or below their `current`, and the runner's `current` is LOWERED.
2. **A `reject` in a campaign HALTS THE UNIT.** The interactive contract is
   "STOP and ask the operator"; the autonomous runner cannot ask. It returns
   `status:"escalated"`, `reason_code:"architecture_review_rejected"` with both
   verdicts + the recommended alternative inline; the orchestrator surfaces it at
   campaign end. Reuse of the Branch B shape (record, don't block), not an
   invention.

## Acceptance Criteria
- [x] AC1: `agents/sub-iterate-runner.md` Step 3.5 no longer inlines Branch A's
      commands; it points at the new reference, keeps the Branch A/B/C labels, and
      states the halt rule. The runner file ends **below** its previous line count
      (528 → 510) and the baseline `current` is lowered to match — no exception
      minted, no cap raised.
- [x] AC2: The reference carries both Branch A calls (`--mode iterate`, then
      `--mode architecture` over a brief, never `--plan-file`) with a
      self-resolving `--driver` (no `{driver}` placeholder), the brief-authoring
      instruction, and the branch B / C behavior for both calls.
- [x] AC3: A `reject` from EITHER reviewer HALTS the unit: `escalated` /
      `architecture_review_rejected`, `architecture_review{verdicts,
      recommended_alternative, findings}` inline; nothing is finalized, committed
      or pushed. A non-reject verdict (`approve`, `revise`, `unknown`,
      `unavailable`) does not halt.
- [x] AC4: `sub_iterate_runner_contract.schema.json` accepts the new reason code
      and REFUSES a reject escalation that lacks `architecture_review`, carries an
      empty `recommended_alternative`, or names no `reject` verdict; the success
      shape gains an optional `reviews.architecture`.
- [x] AC5: The orchestrator (`campaign-mode.md`) points at the new Step 3.5,
      treats the escalation through the existing 3f STRICT-STOP (`record` exits 3,
      full `result.json` persisted at `result_path`), and prints the halted unit's
      `architecture_review` + the operator's choices at campaign end (finalize
      step 5). `campaign-mode.md` stays at or below its `current` (1708).
- [x] AC6: The stale "campaign sub-iterates do not run it yet" statements
      (`iteration-planning.md` step 2a, `docs/guide.md`) and
      `docs/hooks-and-pipeline.md` describe the wired behavior; the INTERNAL arm
      (`architecture_internal`) stays a documented `not_run` gap — the runner has
      no `Agent` tool.
- [x] AC7: Composition is proven end to end: real verdict parser → the runner's
      escalation result → the contract schema → the real `autonomous_loop.py
      record` subprocess (exit 3, result persisted). Drift-protection tests that
      counted the runner's inlined `external_review.py` blocks / parse mentions
      follow the moved text.

## Spec Impact
- **Classification:** modify
- **ADD:** none
- **MODIFY:** FR-01.11 (`/shipwright-iterate`) — new AC39: a campaign unit whose
  outside architecture review answers "reject" is stopped and surfaced at campaign
  end, mirroring AC38's architecture-review requirement for the unattended path.
- **REMOVE:** none
- **NONE justification:** n/a (classification is not solely none)

## Out of Scope
- An INTERNAL architecture arm for campaigns (`architecture_internal` /
  `plan_internal` stay permanent `not_run` rows): the runner has no `Agent` tool
  and there is still no campaign-level spawn site — unchanged, named gap.
- Auto-retrying or auto-resolving a halted unit (an operator decides between the
  alternative, keeping the plan, or reworking; `escalated` stays terminal).
- Changing the external architecture review's verdict/reject mechanics
  (`external_review.py`, its prompts).
- Real Codex-driven campaigns (trg-a27ab4d9): the runner keeps resolving its own
  `--driver` from `CODEXTENDER_ACTIVE`.
- Halting a campaign on Branch B/C or a `revise`: unchanged — both proceed.

## Design Notes
n/a — no UI surface; agent/reference prose, one JSON schema, tests.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `external_review.py --mode architecture` stdout | runner Step 3.5 (verdict read, halt decision) | JSON (`verdicts{glm, openai\|opus}`, `reviews.*.feedback`) |
| runner's escalated result | `sub_iterate_runner_contract.schema.json`; `autonomous_loop.py record`; campaign-mode finalize step 5 | JSON |
| `autonomous_loop.py record` | orchestrator (`unit.result_path` → `result.json`) | JSON |

## Confidence Calibration
- **Boundaries touched:** the three pairs above; `cross_component` machinery (`campaign-mode.md`) IS touched, so a `category:"integration"` behavior is recorded.
- **Empirical probes run:**
  - Production-shape probe (found + fixed): the internal plan review showed the first integration test used a legacy `kind:"iterate"` row, hiding that a claimed R5a row collapses `escalated` to `failed` (verified in `loop_state.resolve_record_status`), so step 5's row filter found nothing. Rewrote on `kind:"sub_iterate"` + `attempt_id`; step 5 now scans `result_path`.
  - Sibling-order probe (found + fixed): the doubt review showed a reject in a unit recorded AFTER a failing one never gets a `result_path` (3f STRICT-STOPs first); step 5 falls back to the runner's `a{attempt}/result.json`; integration case added and green.
  - Shell-quoting probe (found + fixed): reviewer prose crossed a single-quoted `--result '{json}'`; 3f now passes `"$(cat ...)"`; hostile prose (`'`, `$(`) round-trips through `record`.
  - Schema probes (clean): 8 non-actionable reject shapes refused (missing block, no/blank alternative, no reject, empty/one-sided verdicts, no findings).
  - Full-suite reruns (clean): iterate plugin 1066 passed, integration-tests 567+ passed, ruff clean; the last probe found nothing after the last fix.
- **Test Completeness Ledger:** recorded machine-readably in the F5 block / F5c entry (every AC `tested`, no `untestable` rows except the disclosed prose-execution gap of the LLM orchestrator, classed `tested` via the pinned persisted-result scan).
- **Confidence-pattern check:** asymptote reached (last probe clean after three yes-then-bug rounds); breadth: all 7 ACs covered; integration composition proven (real verdict parser -> schema -> real `autonomous_loop.py record` -> step-5 scan, incl. stale attempt and later-sibling cases).

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes (spawned `model=opus` over spec + mini-plan; the change was already built in the working tree, so its findings were integrated before commit)
- **Severity:** high
- **Summary:** The extraction keeps the old Step 3.5 behavior and the line counts hold, but the halt contract did not survive the real R5a orchestrator path as first drafted (row collapse, unwritten result.json, shell quoting) and the first integration test used a legacy state shape that hid all three.
- **Findings:**
  - high · architecture · step 5 filtered on the row, but `resolve_record_status` collapses `escalated` → `failed` for a claimed row (verified in `loop_state.py`) → **fixed** (step 5 scans every non-complete unit's `result_path`)
  - high · completeness · integration test seeded `kind:"iterate"` without `attempt_id`, skipping fencing + the collapse → **fixed** (rewritten on `kind:"sub_iterate"`, claimed row, `--attempt-id`, stale-attempt case)
  - high · architecture · runner never told to write Step 6's `result.json`; 3e reads the file, a missing one becomes a synthetic `failed` and the payload is lost → **fixed** (reference, runner bullet, prose test)
  - medium · security · reviewer prose crossed a single-quoted `--result '{json}'` → **fixed** (3f passes `"$(cat "<result.json>")"`; test data carries `'` and `$(`)
  - medium · architecture · reject arrives after Build; built work would be lost → **disclosed + mitigated** (`halted.patch` saved beside the result, named in `halted_patch`); moving the call before Build **declined**: its trigger reads the diff (Step 3.4) and the spec fixes it inside Step 3.5
  - medium · completeness · baseline not yet lowered → **fixed** (528 → 510, last step)
  - medium · architecture · schema "REFUSES" is test-only; no-alternative bind; whitespace passes minLength → **fixed** (`"none named by the reviewers - see findings"` fallback, `pattern: \S`, reworded: schema checks shape, runner is the enforcement point)
  - low · "either reviewer" ambiguous → **fixed** ("either ARCHITECTURE reviewer"; the plan review carries no halt)
  - low · drift vs standalone 2a (spec section vs decision-drop; Call-2 failure branch) → **fixed** (F3 decision-drop; `unavailable` status)
  - low · bare `sys.path` import in the integration test → **fixed** (importlib under a unique module name)
- **Known limitations:** post-Build placement of the reject (mitigated by `halted.patch`); `autonomous_loop.py record` does not validate reason-code fields.
- **Status:** 10 fixed, 1 disclosed (mitigated)

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes (over `architecture_brief.md` + the sanitized spec copy; `model=opus`)
- **Severity:** medium
- **Summary:** Worth building; option A is the smallest that respects both hard constraints, but it re-creates a second copy of the step unless a drift test pins the two together, and the whole-wave halt must be stated plainly.
- **Findings:**
  - low · necessity · close the gap rather than keep the documented gap → accepted (this run)
  - medium · smallest-option · A leaves a second copy that can drift again → **fixed** (`test_campaign_reference_does_not_drift_from_the_interactive_step`); option C (point at the interactive step, deltas only) **declined**: that step is written around STOP-and-ask, and the runner needs literal runnable commands with a self-resolving `--driver`
  - medium · completeness · one reject halts the WHOLE wave; is a plan-review reject new? → **fixed** (stated in the reference; the halt is scoped to the two architecture verdicts, plan review unchanged)
  - low · security · runner authors the brief it is judged on; reviewer prose printed at campaign end → **disclosed** (self-authored brief, named limitation) + **fixed** (printed as quoted data, never instructions)
  - low · complexity-cost · proportionate → no change
- **Known limitations:** brief authored by the agent that built the change; the internal arm stays `not_run`.
- **Status:** 3 fixed, 1 disclosed, 1 declined (option C)

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-09-29-campaign-runner-architecture-review/architecture_brief.md`
- **Verdicts:** glm=approve · openai=revise (`--mode architecture`); plan review (`--mode iterate`): glm=approve · openai=revise
- **Smallest thing that would do (per reviewers):** as proposed (option A); both architecture reviewers suggested option C (deltas only) or a drift test.
- **Findings:** option C → **rejected-with-reason** (see above), drift test → **accepted-and-fixed**; halted-unit working-tree isolation → per-unit worktree + `halted.patch` (**accepted-and-fixed**); a non-halting `revise` must be recorded → **accepted-and-fixed** (`reviews.architecture` for every outcome); no-alternative reject → **accepted-and-fixed** (fallback string); unparseable verdict silently not halting → **rejected-with-reason** (only a real `reject` halts, parity with the standalone contract; the verdicts are recorded); no-driver negative test → **rejected-with-reason** (`--driver` is always passed; a CLI failure now maps to `unavailable`); orchestrator end-to-end test → **disclosed** (finalize step 5 is prose the LLM orchestrator executes; the test pins the persisted-result scan it describes).
- **Reconciliation:** the plan rejected keeping the inlined copy behind a new bloat exception (it records the duplication as permanent); neither reviewer disputed that. The reviewers' pull toward option C is answered by the drift test plus the reference declaring itself a delta on `iteration-planning.md` step 2/2a.
