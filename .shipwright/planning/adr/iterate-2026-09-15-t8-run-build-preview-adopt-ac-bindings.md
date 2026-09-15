# t8 — FR-01.01 / FR-01.05 / FR-01.12 / FR-01.13 AC-binding disposition table

Campaign `req3-05-test-backfill-mono`, sub-iterate t8. Run-ID
`iterate-2026-09-15-t8-run-build-preview-adopt`. Full per-AC mapping, mirroring
the disposition-table format t6/t7's external reviews requested.

## FR-01.01 — /shipwright-run (7/7 bound)

| AC | Disposition | Test(s) tagged | What it actually proves |
|---|---|---|---|
| AC01 | tested | `test_orchestrator.py::test_update_step_all_complete`; `test_single_session_loop.py::test_apply_success_advances_pointer_and_resolves_next` | Every `PIPELINE_STEPS` phase completes in fixed order until `get_next_step` returns `None`; and the single-session loop auto-resolves the NEXT dispatch after a phase completes — the operator never invokes the next phase by hand. |
| AC02 | tested | `test_validation_override_record.py::test_ask_issues_without_force_still_pause_the_run` | An unforced completion with a gate `ask`-severity issue sets `status: needs_validation` and the step is NOT added to `completed` — a phase that failed its own checks is never quietly counted as done. |
| AC03 | tested | `test_validation_override_record.py::test_a_waved_through_completion_is_recorded_with_what_and_why`, `::test_a_clean_completion_records_no_override` | A forced-through completion records `waived: true` + the overridden issues + the reason; a genuinely clean completion writes NO override record at all — "passed" and "waved through" stay distinguishable by the mere presence of a record. |
| AC04 | tested (1 new test) | `test_orchestrator.py::test_resume_midway`; `test_orchestrator_context_reload.py::test_reload_context_states_which_phase_was_interrupted` (NEW) | `get_next_step` after 4/7 phases resumes at the 5th, not the start; the new test proves the resume-time document (`reload_orchestrator_context`) distinguishes a `done`+`ok=True` phase from the one still `in_progress` with `ok=None`/`summary=None` — the existing suite proved "finished" and "failed" phase shapes but never the "interrupted" one this AC's second clause names. |
| AC05 | tested | `test_master_stop_check.py::test_in_progress_banner_tells_the_user_to_reinvoke_run` | The banner never renders a per-phase `--session-id` launch card (the removed multi-session engine's mechanism); the only resume instruction is "re-invoke `/shipwright-run`" — surface-agnostic, since nothing about that instruction depends on the assistant's host surface being able to open a second bound session. |
| AC06 | tested | `test_orchestrator.py::test_build_pipeline_never_includes_security_post_decouple`, `::test_compliance_runs_on_step_complete` | `PIPELINE_STEPS` never includes `security`/`compliance` as a phase (confirmed regardless of scanner-env state); compliance audit evidence is instead updated as a side effect of EVERY phase completion, not as a step of its own. |
| AC07 | tested | `test_non_drivable_config_guard.py::test_resolve_next_dispatch_refuses_stale_multi_session`, `::test_resolve_next_dispatch_refuses_mode_less_legacy_config`, `::test_read_only_lifecycle_commands_still_work_on_a_stale_config` | A pre-SS1 config (mode-less or the removed `multi_session` literal) is refused at every advancing entry point with a one-line migration message, never silently reinterpreted (a mode-less config is not inferred as `single_session`); read-only lifecycle commands still work, so a past run stays inspectable. |

## FR-01.05 — /shipwright-build (0/8 bound — see seam survey Exception 9)

`/shipwright-build` has no `scripts/` implementation of the build behavior
itself; the AC text (write working code, read the mockup, stay in scope,
deliver as one unit) is entirely `SKILL.md`/`agents/section-builder.md`
agent-executed prose, the same class the seam survey's Exception 1 already
established for `/shipwright-preview`. Full per-AC table: seam survey
Exception 9 (`.shipwright/planning/iterate/2026-09-11-req3-05-seam-survey.md`).
One new regression test was added
(`test_section_builder_contract.py::test_complete_without_test_counts_is_rejected`,
unmarked) proving the result-contract schema requires `tests_passed`/
`tests_total` on any `complete` payload — kept as a real guard, but NOT bound
to AC07 (external plan review, openai, high — corrected below).

## FR-01.12 — /shipwright-preview (4/9 — per t0 Exception 1)

t0's own Exception 1 (`shared-tests` seam, `/shipwright-preview`) already
pre-assigned this AC-by-AC split; this table executes it rather than
re-deciding it. `shared/tests/test_dev_server_multiservice.py` (and siblings)
is the existing, dense, already-passing suite the survey's harness column
names — it carried zero AC-qualified `@pytest.mark.covers` tags before this
run.

| AC | Disposition | Test(s) tagged | What it actually proves |
|---|---|---|---|
| AC01 | **unbound — split, both halves recorded** | `test_dev_server_multiservice.py::test_cli_legacy_invocation_still_works` (untagged for AC01; kept tagged for AC05 only) | The spawn/URL-return half is real and exercised (`running: True`, `pid`, `url`, `started_by_us: True`). The "at least one build section is complete" precondition has NO seam (`check_build_ready` exists only in the self-referential `test_preview_checks.py` and SKILL.md prose) — shares AC02's no-seam reason, and this AC's TEXT makes that precondition a REQUIRED conjunct, not an optional one. **Correction (external code review, openai HIGH + glm low, 2026-09-15):** an earlier pass of this ADR tagged AC01 as bound on the spawn half alone. Re-reading t0's own Exception 1 instruction — "record BOTH halves... never let the spawn half's test stand in as proof of the whole AC" — together with the campaign's own governing rule for conjunctive ACs (Exceptions 2/4: "do NOT tag when the primary/required clause is structurally unenforced even if a sub-clause is provable") makes clear the correct reading is: BOTH halves are recorded (the provable one AND the no-seam one), and the AC as a whole stays unbound, exactly like AC02. The `@pytest.mark.covers("FR-01.12/AC01")` marker was removed from `test_cli_legacy_invocation_still_works` (its `AC05` tag is unaffected); `FR-01.12/AC01` is back in `unbound` (`shipwright_ac_coverage_baseline.json`, 68 → 69). |
| AC02 | unbound (t0 Exception 1) | none | No seam — `check_build_ready` is self-referential/prose only. |
| AC03 | unbound (t0 Exception 1) | none | Conversational/agent behavior, no deterministic surface. |
| AC04 | tested | `test_dev_server_multiservice.py::test_start_already_running_only_when_pid_owned` | An already-running, PID-owned instance is reused (`started_by_us: False`) instead of starting a second one. |
| AC05 | tested | `test_dev_server_multiservice.py::test_cli_legacy_invocation_still_works`, `::test_start_already_running_only_when_pid_owned`, `::test_state_v2_round_trip` | The URL is returned and shown; state persists to disk (`shipwright_dev_server.json`) independent of any single process/conversation; a later, separate call reuses it. |
| AC06 | tested | `test_dev_server_multiservice.py::test_start_port_busy_no_state_errors_no_kill`, `::test_start_port_busy_state_file_mismatch_errors_no_kill` | A busy port with no owning state, or a state file naming a DIFFERENT service set, is refused rather than reused or killed — a stranger's process is never adopted as this project's own. |
| AC07 | unbound (t0 Exception 1) | none | Agent-behavior AC, no deterministic surface. |
| AC08 | tested | `test_dev_server_multiservice.py::test_profile_loader_reads_vite_hono_services_block`, `::test_vite_hono_topo_order_is_backend_then_frontend` | A second, structurally different stack profile (`vite-hono`, vs. the rest of the file's `supabase-nextjs`) loads and topo-orders correctly through the SAME `dev_server` code paths — no preview-capability code changed to support it. |
| AC09 | unbound (t0 Exception 1) | none | Policy/documentation guarantee, not executable behavior. |

## FR-01.13 — /shipwright-adopt (5/6 bound)

| AC | Disposition | Test(s) tagged | What it actually proves |
|---|---|---|---|
| AC01 | tested (4 tests, one per clause) | `test_adopt_pipeline_subprocess.py::test_full_pipeline_e2e_via_subprocess` (guidance `CLAUDE.md` + requirements catalogue `spec.md`, real subprocess CLI); `shared/tests/test_stamp_adopted_evidence.py::test_stamps_every_markdown_member_with_the_supplied_base` (audit evidence — a real, execution-based stamp of every evidence document with the actual onboarding commit, not a doc-text check); `test_e2e_baseline_generator.py::test_write_to_filesystem` (starting test set — a real Playwright spec file written to `e2e/flows/`) | All four conjuncts of "enough for the change workflow to take over": guidance, requirements catalogue, audit evidence, and a starting set of tests. No single existing test proved all four; four were needed (see correction below). **Correction (Stage-1 spec-reviewer REJECT, 2026-09-15):** the audit-evidence clause was originally bound to `test_adopt_evidence_disclosure.py::test_step_h_stamps_before_committing_and_verifies_after`, which only reads `step-h-validate-commit-handoff.md` as text and asserts `--stamp-adopted`/`--verify-commit`/`--base` appear in order — proving the SKILL.md *instructs* stamping, never that evidence is actually produced on disk. The seam survey's own Exception 8 already ruled this doc-text pattern insufficient for a behavior-bearing clause. Fixed by tagging `test_stamp_adopted_evidence.py::test_stamps_every_markdown_member_with_the_supplied_base` instead, which drives `compliance_adopt_stamp`'s real CLI (`refresh_compliance_docs.main(["--stamp-adopted", ...])`) and asserts every evidence document on disk is actually stamped with the correct base commit — an already-passing, execution-based test in this unit's own declared `shared/tests` root that had simply not been tagged. **Second correction (Stage-1 spec-reviewer REJECT, re-verification pass):** the first correction above added the new binding but the orchestrator failed to actually remove the old, rejected `@pytest.mark.covers("FR-01.13/AC01")` marker from `test_step_h_stamps_before_committing_and_verifies_after` — it stayed present (alongside its unrelated, unaffected `AC08` tag) and the regenerated traceability manifest still listed the doc-text-only test as an AC01 prover. The stale marker has now been removed from that test (its `AC08` tag is untouched); the manifest was regenerated again and confirms only the two real tests (`test_full_pipeline_e2e_via_subprocess`, `test_stamps_every_markdown_member_with_the_supplied_base`) plus `test_write_to_filesystem` now carry `ac_id: "AC01"` for this test file. |
| AC02 | tested (2 tests, one per clause) | `test_derived_catalogue.py::test_nothing_adopt_derives_today_counts_as_confirmed` (every derived row is marked unconfirmed); `::test_banner_states_the_count_and_that_nobody_confirmed_it` (the count is reported in the handover-visible banner) | Both clauses: every `code`/`observed`/`assumed` row is `confirmed: False`, and the banner a person reads at handover states the count. |
| AC03 | tested (new unit tests + existing integration test) | `test_catalogue_followup.py` (3 new tests: files a card when unconfirmed>0, files none when fully confirmed, states counts as-of-onboarding); `test_record_inherited_baseline.py::test_onboarding_leaves_exactly_one_confirmation_follow_up` (real onboarding-step wiring: the card is actually filed into the Triage Inbox with the real count) | `catalogue_followup.confirmation_triage` was a real, wired (`record_inherited_baseline.py`), but completely untested function. Unit tests prove its own logic; the existing integration test (newly tagged) proves it is actually reached and its output actually persisted during the real onboarding step — external plan review, openai, medium, asked for exactly this pairing rather than a unit-only proof. |
| AC04 | tested (2 tests, one per branch) | `test_inherited_baseline.py::test_an_observed_red_baseline_is_recorded_as_inherited` (failing-tests branch); `::test_a_requirement_with_no_tagged_test_is_an_inherited_gap` (untested-capability branch) | Both branches of the disjunction ("failing tests, OR capabilities no test covers") are recorded as inherited, not as this project's own failures. |
| AC06 | **unbound** | none | No deterministic seam anywhere in `feature_inferrer.py`/`spec_document.py`: a detected route/label is used verbatim in the rendered spec with no "plain business language" transformation or check. Prose quality is agent-authored and unmeasured. |
| AC07 | tested (3 tests) | `test_review_runner_gateway_reachable.py::test_gateway_only_env_does_not_skip_before_llm_review_runs` (gateway-only env is not skipped, via a fully-mocked `llm_review` module — proves the skip-gate, not the actual routing); `shared/tests/test_llm_review_gateway_routing.py::test_run_review_gateway_success_uses_model_1_model_2_role_pair` (real routing: `run_review()` genuinely dispatches through `_review_gateway` and returns `provider == "gateway"` with both model roles populated); `::test_run_review_gateway_failure_never_falls_back_to_openrouter_or_direct` (fail-closed — a gateway failure never silently falls back to OpenRouter/direct even when those keys are present) | Both clauses of the AC: the gateway route is genuinely used (not merely not-skipped), and its failure fails the review rather than silently violating the egress policy. **Correction (Stage-3 doubt-reviewer, low severity):** the original two-test binding proved the skip-gate and the fail-closed path but never a real dispatch through the gateway — added the adjacent, already-passing, untagged `test_run_review_gateway_success_uses_model_1_model_2_role_pair` to close that gap directly under this AC's own tag. |

## Regeneration provenance

`shipwright_ac_coverage_baseline.json` was regenerated by: (1) running
`plugins/shipwright-compliance/scripts/lib/collectors/test_links.py`'s
`generate_file()` against the worktree to produce a FRESH (uncommitted)
`.shipwright/compliance/test-traceability.json`; (2) running
`shared/scripts/tools/check_ac_coverage_ratchet.py --write --project-root .`
against that fresh manifest. `unbound_count` progression: 85 (start) -> 67
(first tagging pass) -> 68 (after `FR-01.05/AC07`'s marker was reverted,
external plan review, openai, HIGH) -> **69** (after `FR-01.12/AC01`'s marker
was ALSO reverted, external code review, openai HIGH + glm low — see the
External Code-Review Findings table below). **Final: 16 of this unit's 30
ACs bound** (FR-01.01 7/7, FR-01.05 0/8, FR-01.12 4/9, FR-01.13 5/6); 14 stay
unbound with a concrete, evidenced, disclosed reason each. The manifest is
left uncommitted-but-present in the worktree per t3-t7's identical,
established precedent — CI's own "Check traceability manifest against a
fresh regeneration" step rebuilds it from real JUnit output before the
AC-coverage gate reads it.

Exact roots exercised this run (4 of the 5 declared; `shared/scripts/tests`
was not touched — no proving seam for this unit's ACs lives there, contrary
to the survey's harness-column suggestion for FR-01.12, where the real seam
turned out to be `shared/tests/test_dev_server_multiservice.py` instead), each
with its own `--junitxml` per ADR-044 (external code review, openai, medium):

| Root | Command | JUnit output | Result |
|---|---|---|---|
| `plugins/shipwright-run/tests` | `uv run pytest tests/ -q --junitxml=/tmp/t8-run.xml` | `/tmp/t8-run.xml` | 572 passed |
| `plugins/shipwright-build/tests` | `uv run pytest tests/ -q --junitxml=/tmp/t8-build.xml` | `/tmp/t8-build.xml` | 149 passed |
| `plugins/shipwright-adopt/tests` | `uv run pytest tests/ -q --junitxml=/tmp/t8-adopt.xml` | `/tmp/t8-adopt.xml` | 673 passed |
| `shared/tests` | `uv run pytest tests/ -q --junitxml=/tmp/t8-shared.xml` | `/tmp/t8-shared.xml` | 10901 passed, 43 skipped, 20 deselected |

## External Plan Review Findings

Ran per Step 3.5 against the mini-plan + this ADR (`--mode iterate`). GLM
verdict: approve (7 findings, medium×2/low×5). OpenAI verdict: revise (6
findings, HIGH×3/medium×3). Raw output:
`.shipwright/planning/iterate/iterate-2026-09-15-t8-run-build-preview-adopt/external-plan-review-raw.json`.

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | HIGH | FR-01.12/AC01 counted as bound although its precondition half is unproven — a spawn/URL test proves only half a conjunctive AC. | **initially rejected-with-reason, later reversed at the code-review stage.** At this plan-review pass the disposition argued t0's Exception 1 instruction ("record BOTH halves") meant tag-and-disclose. The subsequent external CODE review (openai HIGH, independently, plus glm low) re-flagged the identical concern against the actual committed marker, prompting a closer re-read: Exception 1's own AC01 row phrase — "never let the spawn half's test stand in as proof of the whole AC" — combined with the campaign's own conjunctive-AC rule (Exceptions 2/4: don't tag when the required clause is unenforced even if a sub-clause is provable) means AC01 should have stayed unbound like AC02, not merely disclosed-while-bound. **Accepted-and-fixed at the code-review pass:** the `@pytest.mark.covers("FR-01.12/AC01")` marker was removed; `FR-01.12/AC01` is back in `unbound` (68 -> 69). See the External Code-Review Findings table below for the corrected reasoning. |
| 2 | openai | HIGH | FR-01.05/AC07 treated as proven by requiring `tests_passed`/`tests_total` fields on a `complete` payload; a self-reported required field does not prove tests actually ran or passed. | **accepted-and-fixed.** The `@pytest.mark.covers("FR-01.05/AC07")` marker was removed; the test is kept, unmarked, as a real contract-shape regression guard. `FR-01.05/AC07` moved into the seam survey's Exception 9 alongside its 7 siblings. `shipwright_ac_coverage_baseline.json` regenerated accordingly (67 -> 68 unbound). |
| 3 | openai | HIGH | Exception 9 (`/shipwright-build`) is a new no-seam finding the unit records unilaterally; the binding constraint says cite t0's row rather than re-decide the seam — t0 should approve this first. | **rejected-with-reason.** The seam survey's own established pattern is a unit recording a NEW no-seam finding, unilaterally, during its own execution, with a decision-drop/ADR as the durable record — Exceptions 5 (`t2`, FR-01.14/AC26), 6 (`t3`, FR-01.03/AC20-21), 7 (`t3`, FR-01.04/AC10), and 8 (`t3`, FR-01.03/AC03/AC11) are all exactly this shape, none gated on a t0 pre-approval. That precedent is distinct from the ROOT-COUNT question (Exception 3's addenda), which genuinely does require campaign-owner sign-off because it is a resource/scope decision, not a does-this-AC-have-a-seam judgement call. Exception 9 follows the Exceptions-5-8 shape, not the Exception-3 shape. |
| 4 | openai | medium | `catalogue_followup.confirmation_triage`'s new tests are unit-only; AC03 needs proof the real adoption workflow creates and persists the follow-up. | **accepted-and-fixed.** Tagged the existing, already-passing `test_record_inherited_baseline.py::test_onboarding_leaves_exactly_one_confirmation_follow_up`, which drives the REAL onboarding step (`record_inherited_baseline.py`, which calls `confirmation_triage` at its real call site) and asserts the card actually lands in the Triage Inbox with the correct count — the missing integration-level half. |
| 5 | openai | medium | Execution plan didn't name exact pytest/JUnit invocations per root, leaving ADR-044 compliance and reproducibility ambiguous. | **accepted-and-fixed.** Exact command + result per root now recorded in this ADR's "Regeneration provenance" table (4 roots, all green; `shared/scripts/tests` explicitly noted as untouched and why). |
| 6 | openai | medium | "Uncommitted-but-present" traceability manifest risks drift if CI regenerates differently. | **rejected-with-reason.** Identical, already-externally-reviewed convention from t3-t7 (see each of their own ADRs' "Regeneration provenance" sections): CI's own fresh-regen step rebuilds the manifest from real JUnit output before the AC-coverage gate reads it, so a locally-partial manifest cannot under- or over-state what CI computes. Not re-litigated per unit. |
| 7 | glm | medium | The two new-test-against-never-exercised-code risk (`test_reload_context_states_which_phase_was_interrupted`, `test_catalogue_followup.py`) should be pre-run and pre-classified as tagging-vs-bugfix before claiming bound. | **accepted-and-verified, no code change needed.** Both were run locally before tagging (`plugins/shipwright-run/tests -q` and `plugins/shipwright-adopt/tests -q`, both green) — no latent bug surfaced; classified as tagging, not a bugfix. |
| 8 | glm | low | Ensure the 3 new `test_catalogue_followup.py` tests cover the AC02 handover-count clause too, not just the happy path. | **rejected-with-reason (scope).** AC02's handover-count clause is a different AC, already separately bound to `test_banner_states_the_count_and_that_nobody_confirmed_it` (a different mechanism, the provenance banner, not the triage card). `test_catalogue_followup.py` is scoped to AC03 only, per its own docstring. |
| 9 | glm | low | Counting AC01 as bound "slightly overstates coverage"; the baseline's reason field should say "half-bound" rather than a plain tag. | **moot, superseded.** AC01 no longer counts as bound at all (see finding #1's reversal above) — there is no "half-bound" state left to label; AC01 is a plain `unbound` entry like AC02. |
| 10 | glm | low | Verify the section-builder schema validator is the SOLE enforcement point before implying FR-01.05/AC07 is proven. | **moot.** AC07 was unbound per finding #2 above; the question no longer applies. |
| 11 | glm | low | The two-step regen order (collector, then ratchet `--write`) is load-bearing but unenforced by tooling. | **rejected-with-reason.** Same two-step, tool-unenforced order t3-t7 already used without incident; out of scope for a test-tagging unit to change the regeneration tooling itself. |

## External Code-Review Findings

Ran per Step 3.7 item 2 (`touches_build` risk flag), against the full
uncommitted diff (excluding the derived traceability manifest and
`triage.jsonl`) plus the sub-iterate spec. Both reviewers verdict: revise.
Raw output:
`.shipwright/planning/iterate/iterate-2026-09-15-t8-run-build-preview-adopt/external-code-review-raw.json`.

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | HIGH | `FR-01.12/AC01` removed from `unbound` though its tagged test only proves spawn/URL output, not the required "at least one build section is complete" precondition — a conjunctive AC treated as fully proven. | **accepted-and-fixed.** See the External Plan Review Findings table's finding #1 for the full reversal: the `AC01` marker was removed, the AC is back in `unbound` (68 -> 69), and the per-AC table above now reads "unbound — split, both halves recorded." |
| 2 | glm | medium | The mini-plan's Result section (and step 3's AC07 description) still reflected the PRE-correction state after the plan-review's AC07 fix, contradicting the ADR. | **accepted-and-fixed.** `.shipwright/planning/iterate/2026-09-15-t8-run-build-preview-adopt-miniplan.md`'s Result section and steps 3-4 rewritten to match the final, twice-corrected state (16/30 bound, 69 unbound repo-wide, AC07 and AC01 both explicitly called out as corrections). |
| 3 | glm | medium | Multi-arg `@pytest.mark.covers("FR-A", "FR-B")` usage (`test_dev_server_multiservice.py`) is unverified against the `test_links` collector — if it only reads the first arg, the second AC silently loses its binding. | **rejected-with-reason, verified false by direct code read.** `shared/scripts/lib/fr_tag_grammar.py::parse_python` (lines ~154-167) iterates `for arg in dec.args:` inside the decorator loop — every positional arg is parsed and turned into its own `TagHit`, not just the first. Independently confirmed by the regenerated baseline itself: `FR-01.12/AC04` and `AC05` (both carried as a second arg on a two-arg `covers(...)` call) are NOT in `unbound` after regeneration, which would be impossible if only the first arg were read. |
| 4 | openai | medium | Recorded test commands omit `--junitxml` for every root, violating ADR-044's "one JUnit XML per root" evidence expectation and leaving the regeneration unreproducible. | **accepted-and-fixed.** All 4 roots re-run with an explicit `--junitxml` path each (scratch dir, not committed — matches the "never commit raw JUnit/XML" binding constraint); pass counts re-confirmed identical (572 / 149 / 673 / 10901+43+20). Table updated in "Regeneration provenance" above. |
| 5 | openai | medium | Final accounting ("18 of 30 bound", "12 unbound") did not match the baseline's actual delta (only 17 removed from `unbound`, one of which — AC01 — was itself only partial). | **accepted-and-fixed, superseded by the AC01 reversal.** Corrected accounting is now 16/30 bound, 14 unbound (30 - 16), matching `shipwright_ac_coverage_baseline.json`'s 69 unbound repo-wide exactly. Miniplan and this ADR's "Regeneration provenance" section both updated. |
| 6 | glm | low | Decorative separator-comment removals in `test_validation_override_record.py` / `test_section_builder_contract.py`, made purely to stay under the 300-line bloat cap, are readability-neutral-at-best churn unrelated to the AC work. | **rejected-with-reason.** No functional change; a comment-only edit made to satisfy an explicit, unrelated repo constraint (Self-Review item 6) is exactly the trade-off `references/skill-creation-checklist.md`-adjacent bloat guidance expects (trim decoration, not assertions) — not scope creep against the AC-binding work itself. |
| 7 | glm | low | The new `test_reload_context_states_which_phase_was_interrupted` fixture hand-writes `"result": None` for the in-progress task without confirming production ever produces that exact shape (vs. omitting the key). | **rejected-with-reason, verified true by direct code read.** `plugins/shipwright-run/scripts/lib/phase_task_lifecycle.py` (task-creation site, ~line 674) writes `"result": None` explicitly into every new phase task dict at creation time, only overwriting it with a real value when the task later completes (~line 429) — an in-progress task's `result` key is genuinely `None` in production, not merely locally-green by coincidence. |
| 8 | glm | low | `test_catalogue_followup.py`'s digit assertions (`"3" in card["title"]`, `"5" in card["detail"]`) are bare substring checks vulnerable to coincidental matches and don't pin the semantic claim. | **accepted-and-fixed.** Tightened to the exact production phrase in each case (`"(3 unconfirmed at onboarding)"`, `"3 had been confirmed by nobody"`, `"These figures are as of onboarding"`, `"5 had been confirmed by nobody"`) rather than a bare digit or a loose phrase fragment; re-run green (3 passed). |

## Self-Review

Run per `references/iteration-reviews.md`'s 7-point checklist, after
implementation, before commit.

| # | Item | Verdict | Note |
|---|---|---|---|
| 1 | Spec Compliance | pass | 16 of 30 ACs bound to real, existing (or, where genuinely absent, newly written) passing tests; the remaining 14 are recorded unbound with a concrete, evidenced reason each (seam survey Exceptions 1 and 9), per this sub-iterate's own binding constraint. Two of the original 18 taggings (`FR-01.05/AC07`, `FR-01.12/AC01`) were retracted after external review found each proved less than the full AC. |
| 2 | Error Handling | n/a | Pure test-tagging + 3 new small test functions/files — no new production error-handling surface. |
| 3 | Security Basics | n/a | No new user input, auth surface, or secrets — decorator edits, one marker registration (`shipwright-build/pyproject.toml`), a handful of new pure-function tests, two regenerated JSON files (one committed count bump, one left uncommitted). |
| 4 | Test Quality | pass | Every binding targets the real enforcing code path (never a wrapper/renderer-only proxy); conjunctive and disjunctive ACs have every clause/branch proven against the spec text read verbatim; no proxy binding was accepted for FR-01.05 despite the temptation to reach a higher bound count. |
| 5 | Performance Basics | n/a | No runtime code changed. |
| 6 | Naming & Structure | pass | All touched files at or under their 300-line cap (`test_validation_override_record.py` and `test_section_builder_contract.py` were trimmed of decorative separator comments to stay under, rather than shrinking assertions); four pre-existing grandfathered files (`test_dev_server_multiservice.py` 1104→1111, `test_adopt_pipeline_subprocess.py` 472→473, `test_orchestrator.py` 605→611, `test_single_session_loop.py` 349→352) had their bloat-baseline `current` honestly bumped by the exact new-line delta each marker addition cost, not hand-inflated. **Correction (Stage-2 code-reviewer, verified by direct `wc -l`):** this claim was inaccurate for `test_section_builder_contract.py` — the earlier comment trim was insufficient and the file sat at 305 lines (5 over cap), unregistered in the bloat baseline. Fixed by trimming `test_complete_without_test_counts_is_rejected`'s docstring to a single-line comment (299 lines final); re-verified green (16 passed) and ruff-clean. |
| 7 | Affected Boundaries | n/a | No serialized-format producer/consumer pair changed; the coverage-baseline's shape is unchanged, only its `unbound` list shrank. |

All checklist items pass or are not applicable; no self-review blocker was found.
