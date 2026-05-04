# Sub-Iterate F — Runner Contract Mandates Reviews

> Part of campaign `iterate-skill-hardening`. **Depends on E** (stacked).
> Closes the meta-loop: this campaign exists because the runner contract
> let A/B/C/D ship without the reviews that would have caught the bugs E
> just fixed. F patches the runner contract so this can't happen again.

## Context

Sven asked after A/B/C/D shipped: *"hast du bei allen subagens die schritte
durchgemacht? plan review, external plan review, code review, external
code review?"* — answer was no. Investigation revealed the
`sub-iterate-runner.md` agent contract jumps from Step 3 (Build) directly
to Step 4 (Finalization F0–F7), skipping:

- SKILL.md Step 4 — External LLM Review (mandatory medium+)
- SKILL.md Step 8 — Full Code Review subagent + External Code Review
  cascade

The runner is a structurally-impoverished version of the SKILL.md
lifecycle. F brings the runner contract into parity.

## Scope

1. **Patch `plugins/shipwright-iterate/agents/sub-iterate-runner.md`**:
   - Add Step 3.5 "External Plan Review" between Build (Step 3) and
     Finalization (Step 4 in current numbering, becomes Step 4 still).
     Mandatory at medium+ complexity. Branches A/B/C as documented in
     `references/iteration-planning.md`.
   - Add Step 3.7 "Code Review Cascade" after Self-Review (which is part
     of Build per the runner contract today, but is implicit). Mandatory
     when: medium+, OR risk flags present, OR diff > 100 LOC. Both the
     code-reviewer subagent AND external_review.py --mode code, per
     `references/iteration-reviews.md` Section "External Code-Review
     Cascade".
   - Update the result-JSON contract so the runner returns a
     `reviews: {plan: {...}, code: {...}, external_code: {...}}` field
     summarizing what fired and what was deferred.
   - Update Step 4 (Finalization) to run AFTER the reviews, not before.
2. **Update `plugins/shipwright-iterate/skills/iterate/SKILL.md` Section
   5b (Campaign Mode)** to document the additional review steps in the
   autonomous-loop briefing.
3. **Update the JSON schema
   `plugins/shipwright-iterate/agents/sub_iterate_runner_contract.schema.json`**
   to add the new `reviews` field.
4. **Add a regression test** that statically parses the runner contract
   markdown and asserts both review steps are present + correctly
   gated (drift-protection over the contract itself, parallel to A's
   `boundary-probes.md` drift test pattern).

## Acceptance Criteria

- [ ] `plugins/shipwright-iterate/agents/sub-iterate-runner.md`:
      - Step 3.5 "External Plan Review" exists between Build and
        Finalization. Body documents Branch A/B/C from
        `references/iteration-planning.md`.
      - Step 3.7 "Code Review Cascade" exists after Self-Review.
        Body documents internal subagent + external_review.py --mode
        code per `references/iteration-reviews.md`.
      - Both steps explicitly state complexity gating (medium+
        mandatory; small with risk flag triggers cascade).
      - Skip-conditions are explicit (small + no risk flag + diff < 100
        LOC may skip the cascade).
      - The result-JSON contract documents the new `reviews` field.
- [ ] `sub_iterate_runner_contract.schema.json` has the new `reviews`
      field with sub-schemas for `plan`, `code`, `external_code`. Each
      sub-schema captures `status: "completed | skipped_<reason>"`,
      `findings_count`, `provider`, `reason` (when skipped).
- [ ] `plugins/shipwright-iterate/skills/iterate/SKILL.md` Section 5b
      autonomous-loop instructions reference the new review steps so
      orchestrators briefing runners include them.
- [ ] New test `plugins/shipwright-iterate/tests/test_sub_iterate_runner_contract.py`
      parses the runner contract markdown and asserts:
      - "Step 3.5" + "External Plan Review" + "Step 3.7" + "Code Review
        Cascade" headings exist.
      - "Branch A" / "Branch B" / "Branch C" cross-references exist.
      - Schema file has `reviews.plan`, `reviews.code`,
        `reviews.external_code` keys.
- [ ] Existing test suite remains green (1505+ from D + new E tests).
- [ ] DOG-FOOD applied: this very sub-iterate runner spawn does not need
      to invoke the new steps (the runner contract patch text is being
      added, not the runner code that consumes it). Document that
      meta-circular framing in the spec's Confidence Calibration section.

## Implementation Plan

1. Read current `sub-iterate-runner.md` (Step 1–6 + Output sections).
2. Insert new Steps 3.5 + 3.7 with body text directly modeled on
   `references/iteration-planning.md` Step 4 (External LLM Review)
   and `references/iteration-reviews.md` "External Code-Review Cascade"
   so we don't drift between the two sources.
3. Update Step 4 (Finalization F0-F7) to remain numerically Step 4 but
   note it runs after Steps 3.5 + 3.7 in the lifecycle.
4. Update Output schema section (success / failure / escalation) to
   include the new `reviews` field.
5. Update `sub_iterate_runner_contract.schema.json` accordingly. (Verify
   schema file exists at the path noted; if not, just patch the
   markdown.)
6. Update SKILL.md Section 5b: in the autonomous-loop briefing template,
   add a one-line "include review steps gating" reminder.
7. Test: parse markdown headings + cross-references via a small regex
   parser; assert presence.

## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| `sub-iterate-runner.md` Step 3.5 + 3.7 (NEW) | every future sub-iterate-runner spawn (Claude Code agent system) | Markdown agent definition |
| `sub_iterate_runner_contract.schema.json` (UPDATED) | `autonomous_loop.py::_validate_result` (and any external schema validator) | JSON schema |
| Result JSON `reviews.{plan,code,external_code}` (NEW field) | campaign orchestrator + result.json consumers | JSON shape |
| SKILL.md Section 5b briefing template | orchestrator drafting runner prompts | Plain text snippet |

## Confidence Calibration

- **Boundaries touched:** see Affected Boundaries.
- **Empirical probes (to be filled by runner):**
  - Drift-protection test: parse `sub-iterate-runner.md` and assert the
    new headings + their gating language exist.
  - Schema-file test: load the JSON schema; validate a fixture result
    JSON with all three review sub-fields present.
  - Negative probe: a result JSON without the `reviews` field passes
    schema validation if the field is `additionalProperties: true` —
    confirm intent. If we WANT to require `reviews`, the schema needs
    `required: ["reviews"]` and we need to update existing successful
    result.json fixtures (A/B/C/D's already-shipped result.json files)
    OR mark the field optional. Pick one and document.
  - Recursive-circumstance probe: F itself does NOT (cannot) practice
    Step 3.5 / 3.7 — its runner uses the OLD contract. That's the
    boundary that always exists in a contract-changing iterate; the
    next iterate after F merges will be the first to actually exercise
    the new contract. Document as an explicit deferred-self-application.
- **Edge cases NOT probed + why** (to be filled by runner)
- **Confidence-pattern check** (to be filled by runner)

## Runner Overrides

1. NO push.
2. NO amend.
3. After F7, write result.json.
4. F2 Browser Verify does NOT apply.
5. Suggested ADR: `ADR-029: Runner Contract Mandates Reviews`.
6. Branch name: `iterate/skill-hardening-F-runner-contract-mandates-reviews`.
   Branched from `iterate/skill-hardening-E-review-driven-hardening`.

## DOG-FOOD Notes

- **Boundary Tests (A):** Affected Boundaries table populated; runner
  contract markdown drift-protection test added.
- **Confidence Calibration (B):** template populated by runner; the
  meta-circular self-application caveat is documented above.
- **Multi-Session Discipline (C):** orchestrator canonical, no push.
- **Boundary-Coverage (D):** D's scanner now sees this iterate's
  boundaries (after E's HIGH-4 fix wires the merge).

## What's NOT in scope

- Backporting the new review steps to retroactively review A/B/C/D —
  already done manually as part of this campaign's review pass; the
  reviews are recorded in `.shipwright/tmp/reviews/` (gitignored
  scratch) and their findings drove Sub-Iterate E.
- Rewriting the runner contract beyond inserting Steps 3.5 + 3.7 + the
  result-JSON field. Other refactors stay out of scope.
- The complementary fix to the **Build skill** runner contract
  (`plugins/shipwright-build/agents/section-builder.md`) — analogous
  problem class but separate plugin, separate iterate. Track as
  `section-builder-mandates-reviews` follow-up.
