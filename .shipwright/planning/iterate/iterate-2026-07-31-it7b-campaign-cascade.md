# Iterate Spec — IT-7b: a campaign sub-iterate runs the same lifecycle as a standalone one

- **Run ID:** `iterate-2026-07-31-it7b-campaign-cascade`
- **Date:** 2026-07-31
- **Intent:** CHANGE
- **Complexity:** medium (Stage 2; Stage 1 said `small` on the message alone)
- **Risk flags:** `cross_component` (`campaign-mode.md` matches
  `CROSS_COMPONENT_FILE_PATTERNS`) → integration coverage + full test suite
- **Spec Impact:** NONE — no FR behaviour changes. This wires an existing
  contract (ADR-029) that was decided but never given a step.
- **Anchor:** trg-fc173418 (IT-7, member 7b). 7a shipped as PR #508 / ADR-117.

## Problem

Two independent gates were conflated in the anchor, and only one was closed by
the `CLAUDE.md` standing-request section (#496, `bbdd2ada`):

1. **Permission** — "Claude Code withholds subagent spawning until the user
   asks." #496 *is* that request. **Closed.**
2. **Capability** — `sub-iterate-runner.md` declares
   `tools: Read, Write, Edit, Bash, Glob, Grep`. No `Agent`. A standing grant
   in a project file cannot give a subagent a tool it was not declared with.
   **Open.**
3. **Wiring** — the autonomous loop (`campaign-mode.md`, steps 3a–3i) has no
   step that spawns the cascade. **Open.**

ADR-029 already decided (2) and (3): it rejected giving the runner the `Agent`
tool ("would double-spend tokens") and named the **orchestrator** the delegate.
The delegate was never given a step. So `spec-reviewer` (HARD-GATE) and
`doubt-reviewer` never run for runner-built sub-iterates.

Investigating that exposed a second, larger instance of the same defect: the
runner's Step 4 **re-enumerates** the finalization phases instead of deriving
them from SKILL.md's canonical index. That divergent copy has silently fallen
behind by four phases.

| Phase | Standalone (SKILL.md) | Runner (before this change) |
|---|---|---|
| F0.5 E2E verification gate | mandatory medium+ | **absent** |
| F2 `architecture.md` | on structural impact | **absent** — the label `F2` is reused for Browser Verify |
| F3a Reflection | mandatory | **absent** |
| F5 `iterate_latest` | mandatory small+ | **absent** — found by the Stage-2 review |

F0.5 and F5 matter most, and they are coupled: `verify_iterate_finalization.py`
— the same verifier the runner runs at F6-verify — fails closed when the
`surface_verification` block is missing at medium+, and F5 is the step that
writes it.

## Decision

Make a campaign sub-iterate congruent with a standalone one on **every
dimension that is not a consequence of autonomy**, and add drift protection so
the two lists cannot silently diverge again.

Differences that REMAIN, by design (autonomy, not defects): no interview, no
user-approval gate, no own worktree, no self-armed auto-merge, no F12 prompt.

### AC1 — the orchestrator runs the delegated cascade before merging
`campaign-mode.md` gains step **3f-bis**, between `3f` (record) and `3g`
(merge): `spec-reviewer` (HARD-GATE) → `code-reviewer` → conditional
`doubt-reviewer`, against the merge-base diff. This is the last point at which
a REJECT can still stop delivery, because `3g` merges.

### AC2 — the verdict is recorded under the actor that produced it
The runner writes `spec`/`code`/`doubt` as `not_run` (true when it wrote them).
After the cascade runs, the orchestrator re-records each row with `--force`,
then commits and pushes so the record ships with the PR. `--force` already
exists for exactly this ("overwrite an already-terminal record").

### AC3 — a REJECT is a non-delivery, using the path that already exists
A Stage-1 REJECT (or an unaddressed Stage-2 high finding) STRICT-STOPs the
loop, identically to `3f` exit 3 and a failed check at `3g`: do not merge, do
not build the next; merged sub-iterates stay durable. No new state machine —
the "bounded retry / repair" design `campaign-mode.md` named as a prerequisite
is a refinement, not a precondition.

### AC4 — the runner runs the missing finalization phases
Step 4 gains **F0.5**, **F2 (`architecture.md`)**, **F3a** and **F5**, and stops
reusing the label `F2` for Browser Verify.

F5 was added after the Stage-2 review: it is the producer of the
`iterate_latest` block that `check_test_completeness_ledger` and the F0.5
`surface_verification` gate both read, so a small+ sub-iterate was failing its
own F6-verify for want of it. It had first been *excluded* on the reasoning
that F11 rewinds the results file to HEAD — a route trg-ad29a709 had already
closed. Every `RUNNER_EXCLUDED` reason is now one a reader can check.

### AC5 — the two lists cannot diverge again
A bidirectional drift test asserts the runner's finalization set matches
SKILL.md's mandatory set (the registry-driven SSoT meta-test rule, SKILL.md
Step 6): forward — every phase SKILL.md marks mandatory appears in the runner;
reverse — every F-phase the runner names is one SKILL.md knows.

### AC6 — the docs stop asserting a gap that no longer exists
`test_campaign_review_contract_prose.py` currently pins the gap
("the internal cascade does not run", "carries the code pass alone"). Closing
the gap inverts those assertions.

## The cost trade-off (the decision this run was asked to write down)

ADR-029's real objection was token cost, not feasibility. Nested spawning was
measured 2026-07-28 (nested child → `NESTED_OK`).

**This run does not overturn ADR-029 — it finishes it.** ADR-029 rejected
option (a) *"add Agent tool to the runner"* because the runner would spawn
reviewers inside its own context while the orchestrator still held the campaign
context — a genuine double-spend. It accepted delegation to the orchestrator.
Running the cascade in the orchestrator is the option ADR-029 chose; its cost
was accepted on 2026-05-04. Only the step was missing.

**Cost of running it:** bounded by the trigger the runner contract already
defines (medium+ OR risk flag OR diff > 100 LOC). Campaign sub-iterates are
scoped trivial–medium by construction, so a share skip entirely. One cascade
per firing sub-iterate, in the process that already holds the campaign context.
Stage 3 stays conditional on a Stage 2 pass.

**Cost of not running it:** already measured, in this repo. ADR-029 exists
*because* campaigns A/B/C/D shipped without reviews and "forced Sub-Iterate E to
retroactively fix HIGH-severity bugs the reviews would have caught earlier."
The external review cannot substitute: per `iteration-reviews.md` the
spec-compliance and doubt roles are deliberately **not** cascaded to external
providers, so Stage 1 and Stage 3 have no stand-in. Campaign mode is how this
repo lands its largest multi-part changes — the surface with the most to lose
was running through the one mode missing the spec-compliance gate.

**Resolution:** run it. The cost is bounded by an existing trigger; the risk it
removes has a measured precedent.

## Affected Boundaries

- `record_review_pass.py` record store (`reviews.json`) — re-recording a
  terminal row via `--force`
- `verify_iterate_finalization.py` → `check_review_record` (row states) and
  `check_integration_coverage` (recomputes `cross_component` from the diff)
- The campaign loop's non-delivery path (`3f` exit 3 / `3g` failed check)
- The `## Bloat Checklist` parity invariant between `code-reviewer.md` and
  `sub-iterate-runner.md` (byte-identical; must survive any restructure)
- The bloat anti-ratchet: the runner crosses its baseline, so ADR-119 grants
  the exception and the entry is bumped in the same commit
- Campaign loop step 3g: 3f-bis pushes a commit, which restarts CI, so the
  merge is head-pinned rather than trusting the prior rollup

## Out of scope (declared)

- `.github/workflows/**` — anchor IT-9
- `plugins/shipwright-iterate/scripts/lib/**` — IT-5
- Runtime enforcement of 3f-bis. It is prose, exactly like `3g` (merge) and
  every other loop step. A merge gate reading a durable Stage-1 verdict is a
  separate concern.
- Giving the runner the `Agent` tool — rejected; see the trade-off above.

## Confidence Calibration

- **Boundaries touched:** `record_review_pass.py` record store (terminal-row
  overwrite via `--force`); `check_review_record` row-state + stage-ordering;
  `check_integration_coverage` (recomputes `cross_component` from the diff);
  the campaign loop's non-delivery path; the 3f-bis → 3g handover; the bloat
  anti-ratchet; the `## Bloat Checklist` parity invariant (untouched).

- **Empirical probes run** (every claim below was executed, not reasoned):
  1. `--force` promotes a terminal row and the gate accepts the result → exit 0,
     `check_review_record.ok` True. Without `--force` → **exit 3**, confirming
     the flag is required rather than stylistic.
  2. `code` promoted while `spec` is still `not_run` → gate **fails**. The
     spec→code→doubt order in 3f-bis is load-bearing, not cosmetic.
  3. Mutation probe on `campaign-mode.md`: deleting `--force`, the STRICT-STOP
     paragraph, or swapping Stage 1/2 each fails exactly one prose test; the
     file restores clean. Before the fix all three mutations passed — the
     assertions were vacuous because the parser matched a prose mention.
  4. Mutation probe on the runner: deleting the F0.5 / F2 / F3 / F5c / F0 bullet
     heads each fails the forward test. Before the fix all five passed, because
     `references/F0.5.md` and the section heading supplied the tokens.
  5. Mutation probe on the subject pins: restoring F4's pre-fix wording, or
     stripping F5's subject, each fails. A phase number without its subject is
     how F2 pointed at Browser Verify for years.
  6. `RESTORABLE_SNAPSHOTS` inspected directly: `= DERIVED_SNAPSHOTS -
     {TEST_RESULTS}`. The F5-exclusion reason drafted here was factually wrong;
     F5 is required.
  7. Pre-change runner measured against the drift test: reports F0.5/F3a/F5
     missing, **never F2** — the collision is invisible to a token check.

- **Test Completeness Ledger:** see the machine-readable block at F5
  (`iterate_latest.test_completeness`) and the F5c entry. Enumeration: 22
  behaviors, all `tested`, 0 untested-testable. Full suite on this branch:
  **13149 passed / 0 failed / 29 skipped across 18 roots** (one root per
  pytest process, ADR-044).

- **Confidence-pattern check:**
  - *Asymptote (depth)* — the three reviewer stages returned 0 → 10 → 13
    findings; Stage 1 REJECTED once on a defect (an unconditional `$sha` pin)
    that would have strict-stopped every below-threshold sub-iterate. Findings
    were still arriving at Stage 3, so depth had **not** flattened; the residuals
    below are recorded rather than claimed absent.
  - *Coverage (breadth)* — prose contract, real CLI subprocess, in-process gate,
    and the drift tests are each exercised, plus mutation probes proving each
    guard fails when its subject is removed.
  - *Integration composition* — `cross_component` is set, so
    `test_campaign_cascade_record_roundtrip.py` composes the contract, the CLI
    and the gate in one real round-trip (`category: "integration"`).

## Residual gaps — found by Stage 3, declared not fixed

Recorded because an undocumented omission is exactly how the four missing
phases survived. Each is real and each is out of this run's scope:

1. **The runner has no Stage-2 Repo Scout** (highest residual). It classifies
   from its spec text, so diff-driven flags are structurally never set for it,
   and IT-5 caps a no-keyword fall-through at `small`. *Mitigated here:* 3f-bis
   computes its own trigger from the merge-base diff instead of inheriting that
   verdict. *Not fixed:* the runner's own complexity — and therefore the F5c
   entry `check_integration_coverage` reads — is still message-only.
2. **`gh pr create` has no owner.** 3g reads the PR and 3f-bis now resolves it
   one step earlier. Pre-existing; 3f-bis fails closed on an empty `pr_url`
   rather than hanging, but the hole itself remains.
3. **`ensure_current.py` is not in the runner's contract.** F11's branch-current
   half is unassigned, and 3f-bis lengthens the window between the runner's last
   commit and the merge.
4. **`touches_ci_supplychain` ack is unnamed in the runner contract**, though
   the gate applies at every complexity and fails closed.
5. **F0's leak-guard half** is absent from the runner's F0 bullet without a note
   (arguably correct — the runner has no worktree — but undocumented).
6. **`F5a`** appears in SKILL.md's MANDATORY prose but has no table row, heading
   or reference file. *Partly closed after external review:* `_skill_phases()`
   now also reads the `(incl. ...)` prose, so F5a is visible, and it is
   classified in `RUNNER_EXCLUDED` as unimplementable-as-written rather than
   left invisible. *Not fixed:* SKILL.md still declares mandatory a phase it
   never defines. Correcting it belongs with 7c.
7. **`result.json` keeps `delegated_to_orchestrator`** after 3f-bis promotes the
   rows; `reviews.json` is the record of record, the loop's own artifact is not
   rewritten.

(1)-(5) belong with 7c, which owns these same files. (6) is a SKILL.md
correction. (7) is a one-line contract note.

## External code review (openrouter)

Four medium findings; three fixed in this diff — the REJECT path now carries
its concrete `--force` record + checked commit/push; the reverse drift
direction now tests the DOCUMENT (`_runner_phases() - _skill_phases()`) rather
than only the two hand-maintained Python sets, so an invented or
excluded-but-listed bullet fails; and `F5a` is visible and classified per (6).
The fourth — that a `cross_component` run must show the FULL suite, not two
roots — was correct and is answered by running every remaining test root on
this branch rather than by narrowing the claim.

**Degraded:** the gemini leg returned an empty reply, so the external pass
rests on one provider. Recorded in `iterate_latest.degraded[]` rather than
reported as a clean two-provider review.
