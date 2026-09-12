# Mini-Plan: t3 - plan-design (FR-01.03 + FR-01.04 AC backfill)

- **Run ID:** iterate-2026-09-12-t3-plan-design
- **Campaign:** req3-05-test-backfill-mono, sub-iterate t3
- **Type:** change (test backfill via `@pytest.mark.covers`, no production-behavior change)
- **Complexity:** small (Stage 1 `classify_complexity.py`). Step 3.4 diff-driven
  re-check: `effective_complexity=small`, `upgraded=false`, `risk_flags=["touches_io_boundary"]`
  (file writes in the new subprocess-driven tests), `plan_review_required=true`
  both because of that flag and because the merge-base diff exceeds 100 LOC
  once the regenerated compliance artifacts are included.

## Cited seam (binding, not re-decided)

Per the campaign header's binding-seam rule, this unit cites
`.shipwright/planning/iterate/2026-09-11-req3-05-seam-survey.md` (t0)'s row for
this cluster rather than re-deciding it:

> `FR-01.03 | /shipwright-plan | 21 / 21 | plugins/shipwright-plan/tests |
> test_integration.py (setup_planning_session.py pipeline);
> test_review_iterate.py / test_review_routing_contract.py for the
> external-review ACs (AC02-AC04, AC09-AC13, AC19-AC21) | none yet | t3`
>
> `FR-01.04 | /shipwright-design | 12 / 12 | plugins/shipwright-design/tests |
> test_setup_design.py (design-session pipeline); test_screen_registry.py
> (per-requirement screen mapping, AC01/AC04) | none yet | t3`

Root count table: `t3 | FR-01.03, FR-01.04 | plugins/shipwright-plan/tests,
plugins/shipwright-design/tests | 2` — the campaign's two-root budget, used in
full, no deviation needed.

## Re-derived work list (not copied from the spec)

`shipwright_ac_coverage_baseline.json` -> `unbound` at branch point (post-t2,
`0cea78813`): 205 total unbound, of which 21 start with `FR-01.03` (AC01-AC21)
and 12 start with `FR-01.04` (AC01-AC12) — 33 ACs, matching the spec's stated
count going in.

## Approach

Precedent-first where an existing test already proves the AC end to end
(most of both FRs' mechanised gates: `check-plan-gates.py`,
`check-design-gates.py`, `screen_registry.py`). Where the survey's suggested
harness files (`test_review_iterate.py`/`test_review_routing_contract.py`,
`test_setup_design.py`) did not yet contain a test proving the AC, new test
functions were added to those SAME files (no new test file/harness), each
invoking the real production entry point the phase's own SKILL.md instructs
running (`external_review.py --mode architecture`, `resolve_gate_policy.py`,
`record_requirement_impact.py` / `check_design_round_declarations.py`) rather
than re-implementing any of that logic. Two exceptions split into a new file
purely for the 300-LOC budget after growth
(`test_check_plan_gates_reviewers.py`, `test_requirement_writeback_gate.py`)
— same file, same root, same pattern as the existing
`test_check_plan_gates_sections.py` / `test_check_design_gates_tier3_review.py`
splits.

One AC — `FR-01.03/AC21` — is left unbound with a recorded reason: it names
DeepSeek-specific ZDR-endpoint routing for the plan review's OWN reviewer
roster, but `shared/scripts/lib/external_review_routing.py` documents that
"DeepSeek is no longer bound as a plan/code-review cascade identity ... GLM
replaced it there" (`iterate-2026-09-02-glm-plan-code-review-swap`). DeepSeek's
ZDR policy code still exists, but only for the Tier-3 PR-review gate's
operator-overridable model choice (FR-01.17's territory, not FR-01.03's) — no
current `/shipwright-plan` code path invokes DeepSeek at all. Binding AC21 to
either GLM's routing test (a different provider than the AC names) or the
Tier-3 gate's DeepSeek test (a different FR's behavior) would misrepresent
what is actually proven. Recorded here and in the F3 decision drop; a future
correction to AC21's own text (naming GLM, or generalizing to "the active
reviewer roster") is a spec-authoring question for the campaign/spec owner,
not something this unit can resolve by picking a nearby test.

## Per-AC seam mapping (executed)

### FR-01.03 (/shipwright-plan)

| AC | Root | Test file :: function |
|---|---|---|
| AC01 | plan | `test_check_sections.py::test_check_all_sections_written` |
| AC02 | plan | `test_missing_key_stop_and_ask_drift.py::test_missing_review_key_stop_and_ask_instruction_present` |
| AC03 | plan | `test_review_routing_contract.py::test_self_review_fallback_only_runs_when_no_independent_review_completed` (new — drift-pin, same D7 judgement-criterion class as AC02) |
| AC04 | plan | `test_check_plan_gates.py::test_no_marker_blocks_section_splitting` |
| AC05 | plan | `test_check_plan_gates_sections.py::test_an_uncovered_requirement_fails` |
| AC06 | plan | `test_check_plan_gates_sections.py::test_a_section_serving_no_requirement_fails` |
| AC07 | plan | `test_check_plan_gates_sections.py::test_an_ill_formed_section_fails_even_in_a_new_plan` |
| AC08 | plan | same test (shares the 4-problem assertion: purpose, steps, tests, prerequisites) |
| AC09 | plan | `test_review_routing_contract.py::test_architecture_mode_requires_a_brief_not_the_plan` (new — real `external_review.py --mode architecture` CLI, the actual Step 5a entry point) |
| AC10 | plan | same test (`--plan-file` refused as a foreign flag) |
| AC11 | plan | `test_review_routing_contract.py::test_architecture_reject_stops_and_asks_the_user_to_choose` (new — drift-pin, judgement criterion) |
| AC12 | plan | `test_check_plan_gates_sections.py::test_findings_count_matched_by_logged_entries_passes` / `test_findings_count_unmatched_by_logged_entries_fails` |
| AC13 | plan | `test_check_plan_gates.py::test_an_undecided_reviewer_disagreement_blocks` / `test_recording_the_decision_unblocks_it` |
| AC14 | plan | `test_check_plan_gates_sections.py::test_an_e2e_file_naming_a_flow_passes` / `test_missing_e2e_file_fails_when_a_plugin_root_is_given` |
| AC15 | plan | `test_check_sections.py::test_prerequisite_after_its_user_fails_the_gate` |
| AC16 | plan | `test_setup_planning_session.py::test_setup_resume_forces_step5_when_marker_missing` / `test_setup_resume_advances_when_marker_present` |
| AC17 | plan | `test_check_plan_gates.py::test_boundary_fails_on_a_production_path` |
| AC18 | plan | `test_check_plan_gates_sections.py::test_no_planning_decision_logged_fails` |
| AC19 | plan | `test_check_plan_gates_reviewers.py::test_a_reviewer_that_never_answered_is_recorded_unavailable_not_reviewed` / `test_neither_reviewer_answering_fails_loudly_not_a_pass` (new) |
| AC20 | **not bound — recorded reason (Stage-1 spec-review REJECT, corrected)** | AC20 names DeepSeek/OpenAI as the current roster; both tests below actually prove the CURRENT roster (glm/openai), not the AC's named one — same obsolete-provider situation as AC21. See seam survey Exception 6. The two tests remain (unmarked) as genuine, valuable coverage of the current-roster guarantee: `test_check_plan_gates_reviewers.py::test_a_historical_schema_marker_is_still_read_truthfully` / `test_a_current_schema_marker_cannot_borrow_a_historical_reviewer_name` |
| AC21 | **not bound — recorded reason** | see "Approach" above; DeepSeek is no longer part of `/shipwright-plan`'s reviewer roster |

### FR-01.04 (/shipwright-design)

| AC | Root | Test file :: function |
|---|---|---|
| AC01 | design | `test_check_design_gates.py::test_an_orphan_fr_fails_fr_coverage` |
| AC02 | design | `test_check_design_gates.py::test_missing_visual_guidelines_fails_tokens` |
| AC03 | design | `test_check_design_gates.py::test_multi_screen_with_no_flow_fails` / `test_multi_screen_with_a_flow_passes` |
| AC04 | design | `test_screen_registry.py::test_generate_manifest_renders_linked_frs_in_the_table` |
| AC05 | design | `test_check_design_gates.py::test_no_chrome_definition_fails_when_a_screen_uses_nav_markup` / `test_a_screen_diverging_from_chrome_fails` |
| AC06 | design | `test_check_design_gates.py::test_an_external_script_reference_fails` / `test_an_allowed_font_cdn_reference_passes` |
| AC07 | design | `test_setup_design.py::test_preview_approval_gate_always_stops_for_a_human` (new — real `resolve_gate_policy.py` CLI, `design.preview-approval`) |
| AC08 | design | `test_setup_design.py::test_review_loop_finalize_gate_always_stops_for_a_human` (new — `design.review-loop-finalize`) |
| AC09 | design | `test_check_design_gates.py::test_a_modified_upload_fails` |
| AC10 | **not bound — recorded reason (Stage-1 spec-review REJECT, corrected)** | AC10 says "the others are left untouched"; the gate it calls (`iteration_touched_flagged_screens`) deliberately treats extra touched screens as a warning, not a failure (Chrome Change Propagation legitimately touches every screen). The production code cannot make AC10's full claim true, so binding it would be a test shaped around the implementation, not the AC. See seam survey Exception 7. `test_check_design_gates.py::test_a_flagged_screen_left_untouched_fails` / `test_a_flagged_screen_actually_touched_passes` remain (unmarked) as genuine coverage of the narrower, actually-enforced behavior |
| AC11 | design | `test_requirement_writeback_gate.py::test_declaring_a_behaviour_change_without_correcting_the_requirement_is_refused` / `test_declaring_a_behaviour_change_after_correcting_the_requirement_is_accepted` (new — real `record_requirement_impact.py` / `check_design_round_declarations.py` CLIs) |
| AC12 | design | `test_check_design_gates.py::test_boundary_fails_on_a_production_path` |

## Third-root discovery, NOT acted on (flagged, not self-authorized)

While reading the actual implementation for AC09/AC10 (architecture-review
input contract) and AC11 (requirement write-back), a MORE end-to-end proving
test already exists for both in `shared/tests`
(`test_architecture_review_mode.py`, `test_design_round_declarations.py`,
`test_record_requirement_impact.py`, `test_requirement_impact.py`) — a third
root beyond this unit's assigned two. Per Exception 3's precedent (t1's first
submission was Stage-1-REJECTed for self-authorizing exactly this kind of
deviation by citing a recommendation scoped to other units), this unit does
NOT tag those shared/tests files and does not touch the per-unit root-count
table. Instead, the SAME real production entry points are invoked from NEW
tests that live inside this unit's own two assigned roots (see per-AC table
above) — a materially real, executing proof of the AC, not a duplicate
harness, just recorded under this unit's own root rather than the
already-existing but out-of-budget one. If a future reviewer judges the
in-root tests too thin relative to the shared/tests originals, the fallback
is the same escalation Exception 3 used: ask the campaign owner to accept a
3rd root for this cluster too, rather than self-granting it.

## No new test harness

No new pytest fixture pattern, mocking approach, or test-double strategy was
introduced. Two new files were created purely to keep an existing file under
its 300-LOC budget after adding real subprocess-driven tests
(`test_check_plan_gates_reviewers.py` splits out of `test_check_plan_gates.py`,
mirroring the pre-existing `test_check_plan_gates_sections.py` split;
`test_requirement_writeback_gate.py` is new content, not a split, but reuses
the exact fixture/subprocess idiom `test_requirement_writeback_integration.py`
(shared/tests) already established for the same two CLIs).

## External-Plan-Review-Findings (Step 3.5)

Both reviewers (glm, openai via codex) returned `revise` against the first
submission of this mini-plan.

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | glm, openai | medium | AC02/AC03/AC11 are bound to "drift-pin" tests asserting an instruction STRING is present, not that the pipeline behaves per the AC | rejected-with-reason — AC02's drift test predates this unit and follows the campaign's own established D7 convention (`test_missing_key_stop_and_ask_drift.py`'s own header: a judgement criterion with no mid-session artifact a deterministic check can observe has NO legitimate enforcement other than pinning the instruction verbatim; building an LLM-judgement gate is explicitly forbidden). AC03 and AC11 are the same class, verified directly: `self_review_fallback_ran` is written into the review marker (`review_marker.py`) but is READ by nothing anywhere in the codebase (`grep -rn self_review_fallback_ran shared/ plugins/` finds only the write site) — there is no mechanised check that could validate "fallback only ran because nothing else did," so a stronger binding does not exist to switch to. AC11 (STOP-and-choose on architecture reject) is equally agent-conversational; the deterministic boundary gate (AC17) already covers "no code exists yet" generally and is bound separately. Kept as-is. |
| 2 | glm, openai | high/medium | Duplicating already-existing, more end-to-end `shared/tests` coverage into new in-root tests (AC09/AC10/AC11's cousins) to avoid a 3rd-root deviation, rather than escalating for the 3rd root | acknowledged, escalation filed rather than self-granted — per the Exception-3 precedent (t1 was Stage-1-REJECTed for self-authorizing a 3rd root by citing a recommendation scoped to other units), this unit does not grant itself `shared/tests`. The mini-plan's "Third-root discovery" section already names the exact files and asks the campaign owner for the same ruling t1 eventually received; the in-root tests stand as the current valid (not fake — they invoke the real production CLIs) binding until/unless that ruling arrives. Filed as a discussion point in this run's final report rather than left silent. |
| 3 | openai | high | Verification commands did not name `--junitxml` per ADR-044 | accepted-and-fixed — re-ran both roots with `--junitxml`: `plugins/shipwright-plan/tests` (108 passed) and `plugins/shipwright-design/tests` (75 passed); see "Verification performed" below. |
| 4 | openai | medium | AC21's "recorded reason" is prose only; the baseline schema has no per-entry reason field to verify it survives regeneration | rejected-with-reason — same documented, campaign-wide gap as t0's seam-survey Finding 5 and t2's identical finding (disposition #11/#17 in that unit's mini-plan): `shipwright_ac_coverage_baseline.json` (schema_version 1) is a flat `unbound` list with no reason field for ANY exception in this campaign (Exception 1, 4, 5 all have the same limitation). A schema change is cross-cutting, not scoped to this unit. |
| 5 | glm | low | New subprocess tests should confirm temp-dir isolation, matching `test_requirement_writeback_integration.py`'s idiom | accepted-and-fixed — confirmed by re-reading: every new subprocess test uses pytest's `tmp_path` fixture as `--project-root` (never the repo tree), matching that file's pattern exactly; noted explicitly here per the reviewer's ask. |
| 6 | glm | low | AC08/AC10/AC14 share one test across two ACs — verify both criteria are truly, distinctly asserted | accepted-and-fixed — re-verified: AC07/AC08's shared test asserts exactly 4 distinct shape problems (purpose, steps, tests, prerequisites — `plan_section_quality.quality_problems`), so AC08's prerequisites clause is independently asserted, not incidental; AC09/AC10's shared test makes two separate subprocess calls with two separate assertions (missing-brief usage error, then plan-file-as-foreign-flag usage error), so AC10's "plan refused in the brief's place" is its own assertion, not inferred from AC09's. |
| 7 | glm | low | Spot-check that new `covers` markers resolve, not merely exist | accepted-and-fixed — both roots' full `--collect-only` runs match the passing-test counts (108, 75) with no collection errors; every new test function is present in the collected tree. |

## Verification performed

1. `uv run pytest plugins/shipwright-plan/tests -q --junitxml=<scratch>/plan-tests.xml`
   — full green run (108 tests, ADR-044 one-root-per-invocation) of the
   FR-01.03 root.
2. `uv run pytest plugins/shipwright-design/tests -q --junitxml=<scratch>/design-tests.xml`
   — full green run (75 tests) of the FR-01.04 root.
3. `uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py
   --project-root . --phase build --run-id iterate-2026-09-12-t3-plan-design`
   — regenerated `.shipwright/compliance/test-traceability.json` from the
   live tree before touching the baseline (pitfall #5 in this unit's own
   spec).
4. `uv run shared/scripts/tools/check_ac_coverage_ratchet.py --project-root .
   --write` -> `unbound_count: 173` (from 205) — exactly 32 FR-01.03/FR-01.04
   entries resolved (AC21 excepted, recorded reason); verified via
   `git diff` that every removed baseline line starts with `FR-01.03/` or
   `FR-01.04/` and nothing else moved.
5. `uvx ruff@0.15.15 check plugins/shipwright-plan/tests
   plugins/shipwright-design/tests` — clean.
6. Post-code-review fixes (below) re-verified: `plugins/shipwright-plan/tests`
   109 passed (was 108, +1 for AC09's new `_render_user_prompt` proof),
   `plugins/shipwright-design/tests` unchanged at 75 passed; both roots
   re-linted clean.
7. `git checkout -- .shipwright/compliance/{change-history.md,ci-security.json,
   dashboard.md,sbom.md,test-evidence.md,test-traceability.json,
   traceability-matrix.md} shipwright_compliance_config.json` — reverted the
   compliance-report regen sweep (step 3) after it had done its one job
   (feeding step 4's baseline write a fresh manifest), per t1/t2 precedent
   (t2's commit `0cea78813` does the identical revert with the identical
   rationale). Verified via `git status --short` afterward: only
   `shipwright_ac_coverage_baseline.json` remains modified from that sweep.

## External-Code-Review-Findings (Step 3.7)

Diff reviewed: working tree vs `origin/main` (no commit exists yet at this
step — F6 comes after; ADR-044 one invocation per root does not apply to the
review CLI itself, which takes one diff file). GLM answered (via
openrouter); the `openai`/codex leg errored — the raw diff exceeded codex's
1,048,576-character input limit (1,317,770 chars, driven by the accompanying
compliance-report regen noise, not the actual test-file changes) — recorded
below as `unavailable`, not silently dropped.

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | glm | high | Committed `test-traceability.json` shows the newly-bound FR-01.03/FR-01.04 entries as `"executed": "not_run"` / coverage `"unit": "MISSING"`, seemingly contradicting the ADR's "green runs" claim | accepted-and-fixed, more thoroughly than requested — the underlying structural point is real (`execution_evidence.build_index` only sets `executed` from a `--junit` feed `update_compliance.py`'s local CLI does not expose; `test_links.py:58-66` fail-closes new markers to `not_run` until a CI cycle ingests a report), but the fix is not to explain the staleness — it is to not commit the stale-by-construction file at all. Per t1's and t2's own precedent (t2's commit `0cea78813` explicitly reverts this same regen noise), `test-traceability.json` and its five downstream `.md`/`.json` reports were `git checkout --`-reverted after being used transiently to derive a correct `shipwright_ac_coverage_baseline.json`. This diff no longer contains the file the finding is about. |
| 2 | glm, openai | high | AC02/AC03/AC11's drift-pin bindings cite a "D7 campaign convention" the reviewer could not verify from the diff alone, and reassert the Step 3.5 concern that these prove a string, not behavior | partially accepted — the *reasoning* was never wrong (D7 is real: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md` lines 28-34, 97, 131, 192-193 explicitly define and apply it, and predates this unit), but the reviewer only received the diff file, not the repo, so it had no way to see that document — the disposition record now cites D7's primary source path explicitly (this line) instead of naming the convention without a citation, closing the "not visible" gap. The substantive ask (reclassify AC03/AC11 as unbound) is rejected-with-reason again, unchanged from Step 3.5 disposition #1: `self_review_fallback_ran` is verified write-only (`grep -rn self_review_fallback_ran shared/ plugins/`), so no stronger mechanised binding exists to switch to. |
| 3 | glm | medium | AC09/AC10's test proves only CLI arg-validation (exit 2 on missing/foreign flag), never that the brief's actual content is what reaches the outgoing review request | accepted-and-fixed — added `test_architecture_review_prompt_carries_the_brief_not_the_plan_reasoning` (`test_review_routing_contract.py`), importing `external_review._render_user_prompt` directly (the exact function the CLI calls to build the request) and asserting a brief string and a distinct spec string both survive, unswapped, into their named placeholders — the same production function `shared/tests/test_brief_placeholder_is_substituted` already exercises, now also proven from this unit's own assigned root rather than only in `shared/tests`. |
| 4 | glm | medium | Duplicating already-existing `shared/tests` end-to-end coverage into new in-root tests instead of escalating first | rejected-with-reason — unchanged from Step 3.5 disposition #2: the "Third-root discovery" section above already files this as a flagged, not self-granted, escalation; re-litigating it a second time in code review does not change the campaign's own precedent (t1 / PR #730) against self-authorizing a 3rd root. |
| 5 | glm | medium | AC21's recorded reason is prose-only; the baseline schema has no per-entry reason field | rejected-with-reason — unchanged from Step 3.5 disposition #4: documented, campaign-wide schema gap (t0 seam-survey Finding 5; t2's identical disposition), not scoped to this unit. |
| 6 | glm | low | `dashboard.md`/`test-evidence.md`'s reported "latest full suite" count dropped from 18613/18671 to 11604/11647 with no stated reason | accepted-and-fixed, same remedy as #1 — verified the drop was pre-existing/structural (the *committed* state already read a stale `iterate-2026-09-11-e1-checks-plan-design` snapshot; `update_compliance.py --phase build` correctly refreshed it from the most recently completed iterate's own F5 ledger), then reverted both files along with the rest of the compliance-report regen sweep, per t1/t2 precedent. Neither file is part of this diff. |
| 7 | glm | low | AC20's historical-schema test hardcodes `deepseek`/`gemini`/`glm`/`openai` a second time instead of deriving from the production roster | accepted-and-fixed — `test_check_plan_gates_reviewers.py` now imports `REVIEWERS` / `HISTORICAL_REVIEWER_PAIRS` from `shared/scripts/lib/review_verdict.py` and derives every reviewer name used in its four tests from those constants, so a future roster change (as already happened once: deepseek → glm) cannot leave these tests silently pinning a name the production code no longer recognizes. |

## Stage-1 spec-review REJECT (2026-09-12) — 2 bindings corrected

The orchestrator's spec-reviewer, checking every marker against `spec.md`'s
actual AC text and each test's actual body, REJECTed the first push with two
findings. Neither external plan review (Step 3.5) nor external code review
(Step 3.7) caught either one — #7 above addressed only *how* AC20's test
derived its roster names, never *whether* binding to the current roster
instead of the AC's named one was faithful in the first place.

| # | AC | Finding | Fix |
|---|---|---|---|
| 1 | FR-01.04/AC10 | AC10 says "the others are left untouched"; the bound test only asserts the flagged screen was touched, asserting nothing about the others. The gate it calls (`iteration_touched_flagged_screens`, `shared/scripts/lib/design_gate_extras.py:279-300`) explicitly treats extra touched screens as a warning, not a failure (Chrome Change Propagation legitimately touches every screen in one round) — production code cannot make AC10's full claim true. A test shaped around what the implementation checks, not what the AC requires. | Removed `@pytest.mark.covers("FR-01.04/AC10")` from `test_a_flagged_screen_left_untouched_fails`. Left unbound with a recorded reason: seam survey **Exception 7** (new). The test itself is unchanged and still runs — it just isn't claimed as AC10's proof. |
| 2 | FR-01.03/AC20 | AC20 names "DeepSeek and OpenAI" as the default outside reviewers; the two bound tests actually assert the CURRENT roster (glm/openai) is identified truthfully — a silent retarget to a different, current roster instead of the AC's named one. Identical obsolete-provider situation to this same unit's own AC21 (Named Exception 6), given the opposite treatment: quietly rebound instead of left unbound. | Removed `@pytest.mark.covers("FR-01.03/AC20")` from both `test_a_historical_schema_marker_is_still_read_truthfully` and `test_a_current_schema_marker_cannot_borrow_a_historical_reviewer_name`. Left unbound with a recorded reason: seam survey **Exception 6**, amended to cover AC20 alongside AC21. Both tests are unchanged and still run. |

**Baseline re-regenerated** (fresh `test-traceability.json` manifest via
`update_compliance.py --phase build`, then `check_ac_coverage_ratchet.py
--write`, then the 8 transient compliance-report files reverted, per t1/t2/t3's
own precedent): `unbound_count` moved from 173 to **175** (the 2 ACs above
returning to `unbound`). Per-AC tables above and the seam survey rows updated
to match; no other binding changed. Re-ran both test roots after the marker
removals (`plugins/shipwright-plan/tests`: 4/4 passed;
`plugins/shipwright-design/tests`: 21/21 passed) — no test logic changed,
only which AC each one is claimed to prove.
