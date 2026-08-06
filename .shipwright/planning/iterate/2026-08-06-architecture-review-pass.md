# Iterate Spec: architecture-review-pass

- **Run ID:** iterate-2026-08-06-architecture-review-pass
- **Type:** feature
- **Complexity:** medium
- **Status:** draft
- **Card:** trg-e3f041e8 (P2.17, split out of anchor trg-fc173418)

## Goal

Give the external review a second question it currently never asks: *should this
be built at all?* Every review today judges a change **within** the frame its
plan set — the cascade checks the diff against the spec, and the Step-3.5 plan
review judges the plan's internals. Add one extra external call, in the same
review step, whose input is a short **architecture brief** rather than the plan,
so the two reviewers answer without being handed the plan's own conclusion first.

## Why a second call and not one more paragraph

The card claims "its own mode, NOT one more paragraph in the plan prompt". What
was measured compared *plan-prompt-over-the-plan* against
*architecture-brief-over-a-brief* — two variables at once. The paragraph-only
variant was never tested, so the card's stated reason is not the proven one.

The proven mechanism is the **input**. The mini-plan contains
`Alternative approach — rejected because X` (mandatory at medium+). A reviewer
reading that document has already been handed the answer, with a justification
attached. Adding a paragraph to the same prompt over the same document asks the
model to re-affirm a conclusion it is holding. Removing the justification from
the input is what changes the answer — so this change buys a second **call with
a different document**, and treats the mode name as packaging.

Measured evidence (from the card, two independent observations):
`iterate-2026-07-28-derived-snapshots-refresh` — three review rounds, 25+
findings, none asking whether the mechanism should exist; the same two models
over a brief both `reject` and both independently name a simpler alternative the
plan had discarded. Reproduced on PR #498.

## Scope — deliberately small

The card also asks for a `Standing mechanism:` declaration, a conditional
trigger, a new `architecture` review-record type, and an F11 verifier that
recomputes the trigger from the diff. **None of that is built.** The first
version of this change did build the declaration, the trigger and the record
type; it was then reviewed by its own mechanism, and both external reviewers
independently said the same thing — the trigger is bypassable by the author and
the record type is disproportionate. The operator's call (2026-08-06) was to
keep it simple and pragmatic. So:

- **No trigger, no declaration.** The pass runs on every medium+ Branch A of a
  standalone iterate, and every `/shipwright-plan` Branch A. A trigger the author
  sets fails first on exactly the changes that most need the question asked.
- **What keeps that affordable is the brief, not a gate.** A change that adds
  nothing permanent gets a *three-line* brief (`Nothing. This changes machinery
  that already exists: …`), which the reviewers confirm in a sentence.
- **No new review-record type, no new marker, no F11 verifier.** Verdicts,
  findings and the reconciliation land in the iterate spec's
  `## Architecture Review` section and the ADR (plan side: `plan.md` +
  `decision_log.md`) — NOT in the `plan` review row, which takes one payload
  that the first call already fills and is immutable once completed. The
  review-record contract, its 118 immutable records and the campaign runner are
  untouched.
- **No diff-driven detector.** "A new write surface" has no path set to
  recompute from, unlike `CI_SUPPLYCHAIN_FILE_PATTERNS`; a fail-closed check
  over a fuzzy subject STOPs runs that did nothing wrong.

The residual is stated rather than hidden: nothing forces the brief to be
honest. A brief that quietly restates the plan defeats the pass, and only review
of the diff catches it.

## Acceptance Criteria

- [x] **AC1** — `external_review.py` accepts `--mode architecture` with
  `--brief-file`, and rejects the mode without it (usage error), symmetric with
  how `code` requires `--diff-file`.
- [x] **AC2** — architecture mode loads prompts from
  `shared/prompts/architecture_reviewer/{system,user}`, falling back to an
  inline default carrying the same `SHIPWRIGHT_VERDICT` instruction.
- [x] **AC3** — `{BRIEF}` is substituted with the brief and is a *known*
  placeholder (no stderr warning); an unknown placeholder still warns.
- [x] **AC4** — the mode uses the same two-reviewer path (DeepSeek + GPT in
  parallel), the same degraded gate, and the same envelope with
  `verdicts`/`contradiction`, so disagreement stays visible.
- [x] **AC5** — passing a flag belonging to another mode is a usage error, not a
  silent fall-through, and is diagnosed AS a foreign flag. **This guards the flag
  NAME, not the document**: `--mode architecture --brief-file "{miniplan_path}"`
  passes every check and reverts the pass to a second anchored review with no
  detectable difference anywhere in the record. It stops a typo, not the failure
  mode. An earlier draft of this AC called it "the structural half of the
  anti-anchoring guarantee", which overclaimed (Stage-3 doubt review, medium);
  there is no structural half. The guarantee is the author's discipline, the
  template that states it, and the brief shipping in the diff where a reviewer
  can see what it contains.
- [x] **AC6** — a brief template exists at
  `shared/templates/architecture_brief.md`, stating the anti-anchoring rule and
  the three-line shape for a change that adds nothing permanent.
- [x] **AC7** — the prompt asks for findings in the `Category:`/`Severity:`/
  `Finding:`/`Suggestion:` shape `lib/review_prose` parses, pinned for the
  on-disk prompt *and* the inline default.
- [x] **AC8** — `/shipwright-iterate` Step 3.5 runs the second call in Branch A
  and, on a `reject` verdict, STOPs and asks the operator (take the alternative
  / keep the plan with a recorded reason / rework).
- [x] **AC9** — `/shipwright-plan` Step 5a runs the same call, appends
  `## Architecture Review` to `plan.md` and logs findings to `decision_log.md`.
- [x] **AC10** — docs updated in the same diff: `docs/guide.md` (external review
  chapter + Appendix B) and `docs/hooks-and-pipeline.md` (the brief artifact).

## Spec Impact

- **Classification:** modify
- **ADD:** none
- **MODIFY:** FR-01.03 (`/shipwright-plan`) — the requirement already governs
  "no plan reaches the build phase unreviewed: two independent external language
  models review it by default", including how their verdicts and disagreements
  are handled. This change adds a **second question to that same review step**,
  not a new capability class, so the MINT-vs-FOLD gate resolves to FOLD. Three
  acceptance criteria appended: the second question is asked over a brief rather
  than the plan; handing the reviewers the plan instead is refused outright; a
  "should not be built this way" answer stops the run and asks a person before
  any code exists.
- **REMOVE:** none

*(An earlier draft declared `ADD: FR-08.14`. That was wrong twice over — this
repo has no split `08`, and a second question inside an existing review step is
not a new requirement. Caught by the Stage-1 spec-reviewer, which also noted F11
would have blocked the run for a feature/change iterate whose commit touches no
`spec.md`.)*

## Out of Scope

- The `Standing mechanism:` declaration, the conditional trigger, the
  `architecture` review-record type and the diff-driven F11 verifier — built,
  then removed after this change's own architecture review (rationale above).
- **Campaign sub-iterates.** `agents/sub-iterate-runner.md` carries its own
  inlined copy of Step 3.5 Branch A and is NOT wired to the second call, so the
  pass does not run for a campaign unit. Deliberate, for two reasons: the runner
  sits at exactly its ADR-119 bloat cap (497 lines), and it is autonomous — the
  `reject` → ask-the-operator contract has no answer there. Named here rather
  than left as a silent divergence (Stage-2 code review, medium); the prose in
  the spec, the guide and the skill was corrected to stop claiming otherwise.
  Follow-up card to be filed at F12.
- Any change to `MARKER_SCHEMA` or the `external_review_state.json` family.
- Any change to the existing plan/iterate/code prompts. Strictly additive.
- A glossary entry: `shared/glossary.md` is at its 540-line cap, and raising it
  for this would be the complication this scope decision rejects. The vocabulary
  lives in `docs/guide.md`, the template and the two skills.

## Design Notes

n/a — no UI surface.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `external_review.py:main` (envelope on stdout) | `record_review_pass.py --from external-review-json` | JSON |
| `external_review_prompts.py:_load` (prompt files) | `external_review.py:main` | text |
| the agent (architecture brief) | `external_review.py --brief-file` | markdown |

The third row is the one that matters and the one nothing can enforce: the
brief's value is entirely in what the author leaves out.

## Architecture Review

This change ran its own pass, twice — the first live use of the mechanism, on
itself.

- **Brief:** `.shipwright/planning/iterate/{run_id}/architecture_brief.md`
- **Round 1** (over the first design: declaration + trigger + record type):
  deepseek `approve`, openai `revise`.
- **Round 2** (same brief, after the finding-format fix): deepseek `revise`,
  openai `revise` — **unanimous**, and both independently recommending the same
  thing: drop the declaration, the trigger and the record row; run the call
  every time; fold the result into the existing plan-review record.
- **Outcome:** put to the operator, who directed the simpler build. **Adopted.**
  That is what this spec now describes, and it is roughly a third of the first
  version's surface.

Two findings were *not* adopted:

- **deepseek MEDIUM — "the brief duplicates author effort; embed it in the
  mini-plan and strip the rejection reasons mechanically."** Rejected; the
  reviewer itself flagged it as not clearly better. Mechanical stripping is a
  fragile text transform standing between the author and the single property the
  pass depends on. A separate file makes the omission visible in the diff.
- **openai — "make the architecture result a named section of the existing
  plan-review record."** Partially adopted: the findings do ride in the `plan`
  row, but as ordinary findings rather than a new named sub-field, because a new
  sub-field is the same cross-repo schema growth the finding objects to.

**What the pass proved about itself:** round 1 recorded `findings_count: 0,
parse_status: unstructured` — five real findings, none itemized, because the
prompt asked for prose where `lib/review_prose` parses labels. Fixed (AC7) and
re-run: 4 findings, `structured`. The pass found a defect in its own delivery
that no other review had.

## Confidence Calibration

- **Boundaries touched:** the three rows above.
- **Empirical probes run:**
  1. *Does the brief actually reach the model, rather than the plan?* Ran the
     CLI in-process with the provider replaced and captured what was sent —
     `Options on the table` present, `{BRIEF}` substituted, `{SPEC}` rendered,
     architecture system prompt (not iterate's) in use, both arms asked.
     (`integration-tests/test_architecture_review_composition.py`)
  2. *Can the plan get in by accident?* Passing `--plan-file` in architecture
     mode → exit 2, `--plan-file belongs to --mode plan`. Probed, not assumed.
  3. *Does the envelope survive the recorder?* Real envelope → real
     `record_review_pass.py` → row read back with 4 findings and both verdicts.
  4. *Does the prompt produce parseable findings?* Ran the live pass twice.
     First prompt: `unstructured`, 0 of 5 findings itemized. After the label fix:
     `structured`, 4 findings. This is the probe that found a real defect.
  5. *Is a backgrounded pytest's exit code trustworthy here?* No — measured. Two
     background runs reported exit 0 with an empty output file while the suite
     actually had 12 failures. Verified by reading the output file: 690 s,
     8140 passed.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | `--mode architecture` requires `--brief-file` | tested | `test_architecture_mode_requires_brief_file` PASSED |
  | 2 | a flag from another mode is a usage error, in architecture mode, and is diagnosed AS a foreign flag | tested | `test_architecture_mode_rejects_plan_file_as_a_foreign_flag`, `test_plan_file_is_refused_in_architecture_mode` PASSED |
  | 2b | …and in the three PRE-EXISTING modes, which the `_MODE_INPUT` table tightened as a side effect (`--mode code --plan-file X` used to be ignored) | tested | `test_foreign_flag_is_rejected_in_a_pre_existing_mode_too` PASSED |
  | 3 | a missing brief path reports itself | tested | `test_architecture_mode_missing_brief_path_reports_it` PASSED |
  | 4 | `{BRIEF}` substitutes and warns on nothing | tested | `test_brief_placeholder_is_substituted`, `..._emits_no_unknown_warning` PASSED |
  | 5 | an unknown placeholder still warns | tested | `test_unknown_placeholder_still_warns` PASSED |
  | 6 | prompts load from disk; missing dir → `("","")` | tested | `test_architecture_prompts_explicit_root`, `..._missing_returns_empty` PASSED |
  | 7 | shipped prompts exist and carry `{BRIEF}`/`{SPEC}` | tested | `test_architecture_prompts_ship_and_are_non_empty` PASSED |
  | 8 | the system prompt states the withholding | tested | `test_architecture_system_prompt_states_the_withholding` PASSED |
  | 9 | the user template pulls no plan | tested | `test_architecture_user_template_pulls_no_plan` PASSED |
  | 10 | findings are asked for in the parseable label shape (file + default) | tested | `test_architecture_prompt_mandates_the_parseable_finding_labels[file,default]` PASSED |
  | 11 | the inline default carries the verdict instruction | tested | `test_architecture_inline_default_carries_the_verdict_instruction` PASSED |
  | 12 | the mode emits the standard envelope (keyless path) | tested | `test_architecture_mode_emits_the_standard_envelope` PASSED |
  | 13 | the brief — not the plan — reaches both model arms | tested | `test_the_brief_is_what_reaches_the_model` PASSED |
  | 14 | the envelope is itemizable into findings the agent can write into the spec section | tested | `test_the_envelope_is_itemizable_into_findings` PASSED (`PARSE_STRUCTURED`, 2 findings) |
  | 14b | the `plan` row is NOT this pass's destination — a second write is silently treated as a marker repair and the findings are discarded | tested | `test_the_plan_row_is_not_this_passs_destination` PASSED |
  | 14c | `_render_user_prompt` renders one pass over the TEMPLATE, so a `{SPEC}` inside a diff no longer injects the spec — behaviour this diff changes for the three PRE-EXISTING modes | tested | `test_injected_content_is_never_rescanned_for_placeholders` PASSED |
  | 14d | an empty-looking brief carrying only a UTF-8 BOM is still an error | tested | `test_empty_brief_is_an_error_not_a_skip` PASSED (BOM+CRLF leg) |
  | 15 | the template carries the anti-anchoring rule + three-line shape | tested | `test_brief_template_ships_with_the_anti_anchoring_rule` PASSED |
  | 16 | Step 3.5 / Step 5a run the call and STOP on `reject` | untestable | requires-interactive-tty (the STOP is an operator question; the prose is the contract, as for every other skill step) |

- **Ledger integrity:** row 2 cited `test_architecture_mode_ignores_plan_file`,
  renamed by the Stage-2 fix and therefore a PASSED citation that resolved to
  nothing; rows 14b-14d were behaviour this diff introduced with no row at all.
  Both found by the Stage-3 doubt review, not by any gate — nothing checks that
  a cited test name exists.
- **Confidence-pattern check:** asymptote — probe 4 found a real defect, it was
  fixed and re-probed, and the re-run came back clean; probe 5 falsified an
  earlier green claim I had already reported, which is why the suite result is
  now quoted from the output file rather than an exit code. Breadth — 16 rows,
  15 tested, 1 `untestable` with a closed-vocabulary reason, 0 untested-testable.
