# Iterate Spec: architecture-review-internal-arm

- **Run ID:** iterate-2026-09-28-architecture-review-internal-arm
- **Type:** feature
- **Complexity:** medium
- **Status:** implemented

## Goal
Add an internal architecture review pass — a fresh-context, in-process
reviewer that asks "should this be built at all, and what is the smallest
thing that would do" — to both `/shipwright-plan` and `/shipwright-iterate`,
running always-first (mirroring the existing Internal Plan Review's gating
exactly: unconditional on the plan side, medium+ only on the iterate side —
never trivial/small, by deliberate precedent, not an oversight), before the
external architecture call, on the Claude Agent-tool transport this change
supports. Today that question is asked only by the external pair of LLMs;
when external review is unavailable, declined, or not yet configured, it is
never asked at all. This closes that hole the same way the internal plan
reviewer already closed it for the plan-soundness question. A Codex-driven
session (no Agent tool) has no transport for this pass yet — it is not a
gap this run closes; see Out of Scope.

## Acceptance Criteria
- [x] AC1: On `/shipwright-plan` Step 5, a new Step 5-int-arch runs always,
      immediately after Step 5-int and before Branch A/B/C. It authors
      `{planning_dir}/architecture_brief.md` from
      `shared/templates/architecture_brief.md` (moved earlier from Step 5a),
      spawns `shipwright-plan:architecture-internal-reviewer` (a separate
      fresh-context agent, not `opus-plan-reviewer`) over that brief +
      `{spec_file}`, and resolves the `plan_review` model tier already
      computed for Step 5-int (no second `resolve_model_tier.py` call).
      Degraded handling (spawn failure, unparseable reply) and resume
      reconciliation mirror Step 5-int's own rules exactly (AC3 states the
      iterate-side equivalent; both sides share the same rules, only the
      directory-creation nuance differs).
- [x] AC2: `plan.md` gains a `## Internal Architecture Review` section with
      `Ran: yes|no`; a `Ran: no` retry REPLACES the section in place (never
      appends a second one). Every finding is triaged fix/disclose/decline
      with a reason (scope-ratchet guard: a finding that would add scope the
      spec calls out of scope is declined, not integrated); a declined or
      disclosed `severity: high` finding STOPs and asks the user before Step
      6. Every finding is logged to `decision_log.md` via
      `write_decision_log.py --section "Internal Architecture Review —
      {split_name}"`.
- [x] AC3: On `/shipwright-iterate`, the same pass runs as a new step
      immediately after the existing Internal Plan Review sub-step
      (`iteration-planning.md`) and before Branch A/B/C, gated at **medium+
      only** — it never runs at trivial/small, mirroring `plan_internal`'s
      existing gating exactly. It writes
      `.shipwright/planning/iterate/{run_id}/architecture_brief.md` (moved
      earlier from step 2a) and a `## Internal Architecture Review` section
      in the iterate spec. The outcome is noted in the iterate ADR — never
      written directly to `decision_log.md` (iterate defers all decision
      logging to F3's decision-drop mechanism).
- [x] AC4: Step 5a (plan) and step 2a (iterate) — the external architecture
      calls — read the already-authored brief file instead of re-writing it;
      the CLI's existing `--plan-file` refusal is untouched.
- [x] AC5: `record_review_pass.py` accepts `--review-type
      architecture_internal` (added to `REVIEW_TYPES` and
      `OPTIONAL_PRESENCE_TYPES` in `review_record_schema.py`, metadata-only
      row, no `--from` adapter — same shape as `plan_internal`). The
      `plan_review`-role model-tier floor verifier
      (`review_record_model_tier.py`) judges `architecture_internal` the
      same way it already judges `plan_internal`.
- [x] AC6: The campaign `sub-iterate-runner` permanently records
      `architecture_internal` as `not_run` (documented gap, identical
      wording pattern to its existing `plan_internal` row) so the F11
      review-record gate (`check_review_record`, generic over `REVIEW_TYPES`)
      stays green on campaign runs without activating the pass there.
- [x] AC7: `shared/config/gate_catalog.json` carries a sibling auto-default
      entry (`plan.architecture-internal-review-high-severity-declined`) for
      a declined/disclosed high-severity architecture-internal-review finding
      under `single_session`, alongside the existing
      `plan.internal-review-high-severity-declined` entry. This `plan.`-prefixed
      id is reused, unchanged, by `/shipwright-iterate`'s own STOP-and-ask for
      this pass too — the same reuse pattern `plan_internal`'s existing gate
      already established, since `gate_policy.py`'s `COVERED_PHASES` has no
      `iterate` entry and this arm does not mint one.
- [x] AC8: `docs/hooks-and-pipeline.md` documents the new agent, its two
      spawn sites, the corrected brief-authoring order, and the model-tier
      floor's extended scope. Existing shared tests asserting `REVIEW_TYPES`
      cardinality/membership (`test_review_record.py`,
      `test_record_review_pass_cli.py`,
      `test_review_record_model_tier_floor.py`,
      `test_campaign_review_contract_prose.py`) are updated to include
      `architecture_internal`.

## Spec Impact
- **Classification:** modify
- **ADD:** none
- **MODIFY:** FR-01.03 (`/shipwright-plan`) — new AC22, mirroring AC03's
  independent-reviewer-first pattern but for the architecture question.
  FR-01.11 (`/shipwright-iterate`) — new AC38, mirroring AC12's precedent
  (the prerequisite `iterate-2026-08-08-plan-reviewer-configurable` added
  AC12 for the internal plan reviewer the same way). Table-row summaries are
  left untouched, matching that same precedent (AC12 landed without a table
  edit).
- **REMOVE:** none
- **NONE justification:** n/a (classification is not solely none)

## Out of Scope
- Activating this pass inside campaign sub-iterates — deliberate, named gap
  (P2.17a / trg-14392ba5), same as the existing external architecture pass's
  campaign exclusion. The runner has no `Agent` tool and its STOP-and-ask
  contract has no meaning in an autonomous run.
- A Codex-model-specific role/config for the new `architecture-internal-reviewer`
  agent (Codex Light / Codextender parity). The operator flagged this as a
  future consideration only ("nichts spezielles, will es nur erwähnen") —
  recorded as a disclosed, not-acted-on-now limitation, not built here.
- Any change to the external architecture review's own verdict/reject
  mechanics — only where it reads its input brief from changes.
- A webui-specific change for the new `REVIEW_TYPES` member: `reviews.json`
  readers are already contractually required to tolerate an unknown review
  type gracefully (FR-01.11 AC14, established by
  iterate-2026-08-03-p2-33-deepseek-zdr-review), so this is additive,
  backward-compatible growth, not a cross-repo contract change — confirmed,
  not assumed; see Confidence Calibration.

## Design Notes
n/a — no UI surface; this is a skill/agent/shared-script change.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| New Step 5-int-arch / iterate internal-architecture step | `external_review.py --mode architecture` (Step 5a / step 2a) | Markdown (`architecture_brief.md`, per `shared/templates/architecture_brief.md`) |
| `architecture-internal-reviewer` agent reply | `record_review_pass.py record --review-type architecture_internal`; `plan.md` / iterate spec `## Internal Architecture Review` section | JSON (`{reviewer, severity, findings[], summary}`) |
| `record_review_pass.py record` | `reviews.json` (`REVIEW_TYPES`-keyed), read by F11's `check_review_record` and the model-tier floor verifier | JSON |

## Confidence Calibration
- **Boundaries touched:** the three pairs above. No `cross_component`
  framework machinery touched (`hooks.json`, pipeline validators, campaign
  drain, merge/churn/event-log resolver) — confirmed via
  `git diff main...HEAD` name-only scan against those patterns, zero matches
  — so no `category:"integration"` composition behavior is required.
- **Empirical probes run:**
  - Round-trip (clean): `record_review_pass.py record --review-type
    architecture_internal` → `show` in a scratch project — the new type
    persists (`recorded_by`, `model_tier`, `completed_at` all present) and
    reads back correctly; `pending` correctly excludes it once recorded.
  - Model-tier floor positive control (clean): seeded
    `shipwright_model_config.json` with `floors.plan_review=opus`, recorded
    `architecture_internal` at `model_tier=inherit` → `model_tier_note()`
    flagged it ("ran under session-inherit (tier not confirmed)") —
    confirms the `plan_review` floor now reaches the new type, not just
    `plan_internal`.
  - Model-tier floor negative control (clean): same floor,
    `architecture_internal` recorded at `model_tier=opus` (meets floor) →
    `model_tier_note()` returned `""` — no false positive.
  - Regression probe (found + fixed): full `shared/tests/` run surfaced
    `test_review_cascade_handoff.py::test_review_cascade_complete_when_self_terminal_and_nothing_pending`
    failing — a medium-complexity "everything terminal" fixture predated
    `architecture_internal`, which is now correctly tracked as pending
    (`OPTIONAL_PRESENCE_TYPES`) but wasn't seeded as completed. Fixed by
    adding it to the fixture's completed set; reran green (7/7).
  - Bloat-ratchet probe (found + fixed): the Stop-hook bloat gate caught
    `test_audit_e2e_integration.py` crossing its grandfathered 322-line cap
    by 1 line, a side effect of adding `architecture_internal` to a fixture
    tuple — trimmed one redundant blank line to restore parity.
  - Line-wrap probe (found + fixed): the spawn-instruction integration
    test's anchor for `architecture-internal-reviewer` initially failed
    because a markdown line-wrap in `step-5-int-arch.md` split the phrase
    across a newline — fixed the wrap; test passes.
  - Exhaustion check: the last probe (full `shared/tests/` rerun after the
    cascade-handoff fix) found nothing — 11963 passed, 0 failed, 45 skipped.
    Per the "yes-then-bug" rule, three probes above did find real bugs, so
    this clean full-suite rerun (plus the clean plan/integration-tests full
    runs below) is the required "one more probe" — condition 1 and 4 both
    now hold.
- **Test Completeness Ledger:**

  | Behavior | Disposition | Evidence |
  |---|---|---|
  | AC1: Step 5-int-arch runs always, right after 5-int, before Branch A/B/C; authors brief; spawns separate fresh-context agent; reuses the `plan_review` tier (no 2nd `resolve_model_tier.py` call) | tested | `shared/tests/test_architecture_internal_review_contract_prose.py::test_plan_step_5_int_arch_{runs_always_right_after_5_int,authors_the_brief_first,spawns_a_separate_agent_over_brief_and_spec,reuses_the_already_resolved_tier}` + `integration-tests/test_model_tier_spawn_instructions_present.py` (`STEP_5_INT_ARCH_MD` spawn anchor) |
  | AC2: `plan.md` `## Internal Architecture Review` section shape (`Ran: yes\|no`, replace-in-place), fix/disclose/decline triage w/ scope-ratchet guard, high-severity STOP, `decision_log.md` logging | tested | `test_plan_internal_architecture_review_{section_shape,triage_and_gate,logs_its_own_decision_log_section}` |
  | AC3: iterate step 0b runs medium+ only, right after the plan-review substep; writes brief + iterate-spec section; never writes `decision_log.md` directly | tested | `test_iterate_step_0b_{runs_right_after_the_plan_review_substep_medium_plus,writes_the_brief_and_the_spec_section,never_writes_decision_log_directly}` |
  | AC4: Step 5a / step 2a re-read the already-authored brief instead of re-writing it | tested | `test_plan_step_5a_re_reads_the_brief_instead_of_authoring_it`, `test_iterate_step_2a_re_reads_the_brief_instead_of_authoring_it` |
  | AC5: `record_review_pass.py` accepts `--review-type architecture_internal`; `plan_review`-role model-tier floor judges it like `plan_internal` | tested | `test_review_record.py`, `test_record_review_pass_cli.py`, `test_review_record_model_tier_floor.py`, `plugins/shipwright-security/tests/test_review_record_tier.py` **+ live CLI round-trip and floor positive/negative-control probes above** |
  | AC6: campaign `sub-iterate-runner` permanently records `architecture_internal` as `not_run` | tested | `test_review_record_campaign_shape.py` (17 cases), `test_campaign_cascade_record_roundtrip.py` |
  | AC7: `gate_catalog.json` carries `plan.architecture-internal-review-high-severity-declined`, reused unchanged by iterate's STOP-and-ask | tested | `shared/tests -k "gate_catalog or gate_policy"` (56 passed) |
  | AC8: `REVIEW_TYPES` cardinality/membership tests extended; docs updated | tested | `test_review_record.py`, `test_record_review_pass_cli.py`, `test_review_record_model_tier_floor.py`, `test_campaign_review_contract_prose.py`; `docs/hooks-and-pipeline.md`/`docs/guide.md` are human-facing narrative, not a serialized format — no independent behavior to test beyond the prose-contract assertions above |
  | Structural: `SKILL.md` ≤300 LOC, `step-5-external-review.md` ≤400 LOC after the split, `step-5-int-arch.md` linked from Kern | tested | `plugins/shipwright-plan/tests/test_skill_references_link.py` (7/7) |
  | Regression: review-cascade completion detection still correct with 8 review types | tested | `shared/tests/test_review_cascade_handoff.py` (7/7, incl. the fixed case) |

  No `untestable` rows — every AC has a direct mechanical assertion or a live
  probe; no `requires-*` structural exclusion applies. **Scope caveat (Stage-3
  doubt review, D5):** AC1-AC4's `tested` disposition covers PROSE and WIRING
  — anchor-based assertions against the skill text, and the CLI/schema round
  trips under AC5 — not the `architecture-internal-reviewer` agent's own live
  behavior. The agent has never been spawned: its actual JSON reply shape,
  and the skill's parse/degraded path when a real spawn returns something
  malformed, remain unexercised. Running it once here would either count as
  this run's own `architecture_internal` pass (already `not_run`, bootstrap
  gap — see below) or be a throwaway spawn outside that accounting, which
  this run declines rather than fabricate.
- **Confidence-pattern check:**
  - **Asymptote (depth):** exhausted — the last probe (full `shared/tests/`
    rerun) found nothing, and every probe that *did* find something was
    followed by a fix + a clean rerun (cascade-handoff, bloat-ratchet,
    line-wrap), satisfying the "yes-then-bug → one more probe" rule.
  - **Coverage (breadth):** all 8 ACs have a `tested` row; no
    `could-test-but-didn't` gaps. Full suites all green: `plugins/shipwright-plan/tests`
    (110 passed), `integration-tests/` (562 passed, 2 deselected),
    `shared/tests/` (11963 passed, 45 skipped).
  - **Integration composition:** n/a — no `cross_component` machinery
    touched (see Boundaries touched above).

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** no (bootstrap gap)
- **Severity:** n/a
- **Summary:** `architecture_internal` did not exist as a review type when
  this run's own iteration-planning phase (step 0/0b) executed — this very
  iterate is what builds the review type, the agent, and the wiring that
  step 0b relies on. Retroactively spawning the reviewer after Branch A/B/C
  had already completed (see Architecture Review below) would violate the
  pass's own always-and-first ordering contract — it must see the brief
  before any external verdict, and the external verdict already landed.
  Closed `not_run`; the medium complexity of this run does not exempt it —
  the gap is temporal (the capability postdates the step), not a medium+
  carve-out. `plan_internal` itself predates this run and did execute
  normally (see Internal Plan Review below), confirming the gap is
  specific to the type being newly minted, not a general bypass.
- **Findings:** none — not run.
- **Known limitations:** none beyond the disclosed bootstrap gap above.
- **Status:** not_run (bootstrap)

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** high
- **Summary:** The plan follows the `plan_internal` precedent faithfully, but its
  work breakdown badly under-counted where the change ripples: ~10 unlisted
  tests plus an integration registry would have gone red, three touched files
  sit at bloat-anti-ratchet caps, and the Codex dispatch path was neither
  built nor disclosed. It also needed explicit statements that the new pass
  does not carry the Pre-5b gate and that its reviewer must not read the
  rationale-bearing plan documents.
- **Findings:**
  - completeness/high: ~10 hand-enumerated `REVIEW_TYPES`/`plan_internal`
    test files plus `integration-tests`' two registries were missing from
    the file list — **fixed** (mini-plan Files table + work breakdown item 2
    expanded to all of them).
  - architecture/high: reusing Codex's `role=plan_review` for the new pass
    would overwrite the real Internal Plan Review's reply file and mismatches
    the `--plan-file`-required contract — **disclosed**, user-confirmed
    in-session 2026-09-28: ship the Claude-Agent-tool path now (no shared
    file, no collision risk); Codex records `Ran: no (no Codex transport for
    architecture_internal yet)`; a fifth Codex role is an explicit follow-up
    card (mini-plan item 9).
  - completeness/high: three touched files sit at/near their bloat
    anti-ratchet caps (`sub-iterate-runner.md`, `review_record_schema.py`,
    `test_review_record_campaign_shape.py`) — **fixed** (mini-plan item 10:
    line-neutral edits, fold rows rather than add lines where grandfathered).
  - architecture/medium: the new agent's Read/Grep/Glob access could read
    `plan.md`'s withheld rejection rationale, defeating the anchoring
    defense — **fixed** (mini-plan item 1: explicit prohibition in the
    agent's prompt).
  - architecture/medium: moving brief-authoring earlier means Step
    5a/step 2a could read a stale brief after Branch A integration —
    **fixed** (mini-plan item 4: re-read/refresh before the external call,
    never adding rejection reasons).
  - completeness/medium: interaction with the Pre-5b Checkpoint/Step 5b gate
    was unspecified — **fixed** (mini-plan item 4: explicit "does not carry
    the gate" sentence).
  - completeness/medium: six iterate-side wiring gaps (F11.md, Step 7
    disposition text, degraded-handling reasons, `mkdir -p`, resume
    reconciliation, stale comment) — **fixed** (mini-plan item 5).
  - completeness/medium: AC1–AC4 had no mechanical verification — **fixed**
    (mini-plan item 8: new prose-contract test + registry entries).
  - completeness/medium: the Step 8/11 boundary probe didn't actually
    exercise the model-tier floor verifier (no `floors` configured) —
    **fixed** (mini-plan item 8/11: seeded config + negative control).
  - architecture/low: the mini-plan's Alternative-approach section examined
    the wrong alternative (role reuse) and not the real one (section-only,
    no `REVIEW_TYPES` row, like the external pass) — **declined** (low
    severity, no STOP required): the operator's card explicitly decided a
    `REVIEW_TYPES` row is required so F11 can mechanically verify the pass
    ran, and named this "unchanged and binding." Mini-plan §6 rewritten to
    record this as the actual alternative considered and why it's rejected.
  - security/low: no credential/unsafe-eval exposure; the existing
    single-session auto-default wording must be copied verbatim into the new
    gate_catalog entry — **fixed** (mini-plan item 3).
- **Known limitations:** Codex transport for `architecture_internal` is
  deferred to a follow-up card (disclosed finding above).
- **Status:** 9 fixed, 1 disclosed, 1 declined

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-09-28-architecture-review-internal-arm/architecture_brief.md`
- **Verdicts:** glm=approve · openai=reject
- **Smallest thing that would do (per reviewers):** GLM: as proposed (Option
  A — separate fresh-context reviewer, additive review-type member); OpenAI:
  Option B — merge into the existing Internal Plan Review reviewer, one
  combined pass, one record type.
- **Findings:** GLM (low, proportionality): the architecture question is now
  asked twice in the common case (internal + external) — accepted as the
  same deliberate redundancy the plan-review pair already carries, no action.
  OpenAI (medium, simpler-alternative): recommends Option B — **declined**,
  reason below.
- **Reconciliation:** OpenAI's `reject` recommends folding this pass into
  the existing `opus-plan-reviewer` (Option B) rather than adding a
  separate agent + review type. The operator's original requirement had
  already explicitly decided against exactly this merge: "a separate
  fresh-context agent, not an extension of opus-plan-reviewer... that agent
  reviews the plan WITHIN its frame, and escaping the frame is the whole
  point of the architecture question." GLM's review reached the same
  conclusion: "the architecture reviewer must *not* read the plan or its
  withheld rejection rationale... while the plan reviewer is defined by
  reading the plan. Merging them reintroduces exactly the anchor the
  fresh-context split exists to remove." (GLM was handed this spec, whose
  AC1 already states the separate-agent decision and rationale — not an
  independent corroboration, a reviewer agreeing with text it had already
  read; Stage-3 doubt review, D3.) The decision itself rests on the
  operator's own confirmation, not on GLM's agreement. Put to the operator
  in-session (2026-09-28): **keep it separate, record why** — confirmed.
  Proceeding as designed (Option A); the merge alternative is declined, not
  integrated.
- **Status:** proceeding as planned

## Verification (medium+)
- **Surface:** cli
- **Runner command:** `uv run shared/scripts/tools/record_review_pass.py record --project-root <tmp-project> --run-id <tmp-run> --review-type architecture_internal --status completed --recorded-by architecture-internal-reviewer --model-tier inherit` followed by `record_review_pass.py show` to confirm the round-trip, plus the relevant `uv run pytest` invocations for the touched shared/plugin test roots.
- **Evidence path:** `shipwright_test_results.json.iterate_latest.surface_verification` (F0.5), plus pytest junit output per touched root.
