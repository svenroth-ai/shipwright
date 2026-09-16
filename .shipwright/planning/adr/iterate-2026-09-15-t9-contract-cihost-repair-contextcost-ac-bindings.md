# t9 — FR-01.15 / FR-01.17 / FR-01.19 / FR-01.20 AC-binding disposition table

Run-ID: `iterate-2026-09-15-t9-contract-cihost-repair-contextcost`. Campaign
`req3-05-test-backfill-mono`, **final sub-iterate (t0-t9 all complete after
this run)**.

## FR-01.15 — cross-repo output contract (4/8 bound)

| AC | Bound? | Test | Notes |
|---|---|---|---|
| AC01 | yes | `test_contract_gate_git.py::TestPublishedBaseline::test_reads_the_contract_main_published`, `test_takes_the_highest_version_not_the_alphabetical_one` | real git-ref based immutability against a throwaway repo |
| AC02 | no | — | seam survey Exception 2: library unit test alone does not prove the gate runs on a real diff; no CLI gate script exists yet |
| AC03 | no | — | seam survey Exception 2, same reason as AC02 |
| AC04 | yes | `test_contract_skeleton.py::TestNullabilityIsBreaking::test_an_object_gaining_a_null_arm_demands_a_major`, `test_the_gate_rejects_a_newly_nullable_object_without_a_major` | |
| AC05 | yes | `test_contract_skeleton_weak_pins.py` (new file, split out to hold 300-line cap) — `TestNullOnlyPaths` (2) + `TestEmptyArrayPaths` (3) | `empty_array_paths` was previously untested |
| AC06 | no | — | seam survey Exception 2, same reason as AC02/AC03 |
| AC07 | yes | `test_cross_repo_contract_documented.py::TestTheSkillPointsAtTheConsumer`, `TestSkillStatesTheContract` (partial), `TestProducerCarriesTheWarning` | |
| AC08 | no (reverted) | — | first pass bound this to a doc sentence + drift-pin test both authored in this same run — a self-fulfilling test (external plan review, glm medium + openai high). Marker removed; seam survey Exception 2 amended 2026-09-15. Test kept unmarked as a guard. |

## FR-01.17 — independent re-check on the code host (6/7 bound)

| AC | Bound? | Test | Notes |
|---|---|---|---|
| AC01 | yes | `test_ci_reruns_the_full_verification_on_pr.py` (new file) — trigger, pytest/ruff/semgrep/codeql presence, no path-filter, no job-level `if:` excluding `pull_request` | strengthened post-review (openai medium) with the last two checks |
| AC02 | yes | `test_pr_review_fail_closed.py::test_stage1_owns_no_pr_review_context` | strengthened post-doubt-review: original assertion only checked each job's `name:` field, which a status posted under an innocuously-named job could bypass; added a negative assertion that no stage-1 shell body posts either producer's `context=` string under any job name |
| AC03 | no | — | seam survey Exception 10 (new this run): "automatic, no ask" is provable, "only owner can waive" is GitHub's own ACL, no in-repo seam |
| AC04 | yes | `test_pr_review_fork_trust.py::test_stage2_posts_the_verdict_onto_the_change` | strengthened post-doubt-review: original assertion only proved SOME status posts, not that its `description=` field (the "reasons" half of the AC) carries anything but a hardcoded string; added an assertion that the description is piped from a computed `desc` variable. A deeper proof that `desc`'s content is scenario-specific reasoning (not a placeholder) exists in `plugins/shipwright-security/tests/test_decide_pr_review_gate_cli.py::test_all_generated_pr_prints_success_and_the_reason` / `test_review_failure_prints_failure` (already asserting distinct `desc=...` text per scenario) — left uncited/untagged here because `plugins/shipwright-security/tests` is a 5th pytest root beyond the 4 the campaign owner pre-approved for t9 (`shared/tests`, `shared/scripts/tests`, `shared/scripts/tools/tests`, `plugins/shipwright-iterate/tests`); flagged to the operator rather than silently expanded |
| AC05 | yes | `test_pr_review_fail_closed.py::test_stage1_holds_no_secret`, `test_pr_review_fork_trust.py::test_stage2_never_checks_out_contributor_code` | |
| AC06 | yes | `test_required_checks_drift.py` (3 tests), `test_check_required_checks_cli.py` (2 tests, "actually filed once" half) | |
| AC07 | yes | `test_pr_review_fail_closed.py::test_waiver_cannot_cover_a_change_to_the_checks` | |

## FR-01.19 — recovery of a broken shared branch (8/10 bound, AC09/AC10 recorded as exceptions)

| AC | Bound? | Test | Notes |
|---|---|---|---|
| AC01 | yes | `test_main_health_attribution.py` (2), `test_main_attribution_workflows.py` (2) | |
| AC02 | yes | `test_main_health_attribution.py`, `test_main_health_tool.py` (3) | |
| AC03 | yes | `test_main_health_attribution.py` (2), `test_main_health_tool.py` (3) | |
| AC04 | yes | `test_repair_gate_bites.py`, `test_main_attribution_workflows.py` (base-not-branch clause) | |
| AC05 | yes | `test_repair_gate_bites.py::test_the_honest_repair_is_allowed_and_still_asked_to_explain_itself` | |
| AC06 | yes | `test_main_health_diagnosis.py` (4) | |
| AC07 | yes | `test_main_health_diagnosis.py` (5) | |
| AC08 | yes | `test_main_attribution_workflows.py` (2, bloat-crossing-on-merge visibility) | |
| AC09 | no | — | seam survey Exception 11, corrected post-spec-review: Stage-1 spec-reviewer verified the original "already bound via FR-01.18/AC08" claim was false (AC08's test proves consent-gating, not AC09's disclosure clause) — no test anywhere proves this text; `spec.md` authoring defect, not a main-repair seam |
| AC10 | no | — | seam survey Exception 11, same correction: the original "already bound via FR-01.18/AC07" claim was false (AC07's test proves completeness-of-reporting, not AC10's scope-disclaimer clause) — no test anywhere proves this text |

## FR-01.20 — context-cost meter (6/6 bound)

| AC | Bound? | Test | Notes |
|---|---|---|---|
| AC01 | yes | `test_context_cost_core_phase_labels.py::test_multi_record_single_response_dedups_to_one_call` | dedup-by-request-id; split out of `test_context_cost_core.py` to hold the 300-line cap |
| AC02 | yes | `test_context_cost_core_phase_labels.py::test_call_after_a_mark_gets_that_phase` | |
| AC03 | yes | `test_context_cost_core_phase_labels.py::test_call_before_first_mark_is_unphased`, `test_no_run_id_means_every_call_is_unphased` | |
| AC04 | yes | `test_context_cost_summary.py::test_show_prints_the_existing_summary`, `test_show_breaks_the_running_total_down_by_phase_on_demand` (new test); `test_context_cost_statusline.py::test_prints_calls_and_cost_when_data_exists` | statusline running-total (1st clause) + on-demand phase breakdown (2nd clause) |
| AC05 | yes | `test_context_pressure.py::TestEstimatePressure::test_below_threshold`, `TestEstimatePressureContextCost::test_reads_current_session_only_by_env_var`, `TestCLIDefaultSource` (new class, 2 tests, subprocess-level `main()` dispatch) | opt-in/default-toolcall dispatch; both branches of the disjunctive AC now proven at the one real CLI caller |
| AC06 | yes | `test_context_cost_readiness.py` (8 tests) | |

## Regeneration provenance

`.shipwright/compliance/test-traceability.json` was regenerated via
`uv run --project plugins/shipwright-compliance
plugins/shipwright-compliance/scripts/tools/update_compliance.py
--project-root . --phase iterate` (the `test_links` collector script cannot
run standalone via relative import — this wrapper is the correct entry
point). `shipwright_ac_coverage_baseline.json` was then regenerated via
`uv run shared/scripts/tools/check_ac_coverage_ratchet.py --project-root .
--write`, run **twice**: once after the initial 25-AC tagging pass
(`unbound_count`: 69 -> 44), and again after `FR-01.15/AC08`'s marker was
reverted following external plan review (`unbound_count`: 44 -> **45**,
final). Both regenerations are left uncommitted-but-present in the worktree
per t3-t8's identical, established precedent (see the External Plan Review
Findings table below for the disposition of this convention as re-raised
against this, the campaign's final unit).

**Final: 24 of this unit's 31 ACs bound** (FR-01.15 4/8, FR-01.17 6/7,
FR-01.19 8/10, FR-01.20 6/6); 7 stay unbound with a concrete, evidenced,
disclosed reason each (FR-01.15 AC02/AC03/AC06/AC08, FR-01.17 AC03, FR-01.19
AC09/AC10).

Exact roots exercised this run (3 of the 4 pre-authorized by the t0 seam
survey's per-unit root-count table; `plugins/shipwright-iterate/tests` was
never touched — see the mini-plan's root-list note), each with its own
`--junitxml` per ADR-044:

| Root | Command | Result |
|---|---|---|
| `shared/tests` | `uv run pytest shared/tests -q --junitxml=.ci-junit-t9/shared-tests.xml` | 10913 passed, 43 skipped, 20 deselected |
| `shared/scripts/tests` | `uv run pytest shared/scripts/tests -q --junitxml=.ci-junit-t9/scripts-tests.xml` | 517 passed, 2 skipped |
| `shared/scripts/tools/tests` | `uv run pytest shared/scripts/tools/tests -q --junitxml=.ci-junit-t9/tools-tests.xml` | 993 passed, 11 skipped, 2 deselected |

Raw JUnit XML output is not committed (kept under the gitignored
`.ci-junit-t9/` scratch directory, deleted before commit).

## Self-found fix: ADR index regeneration

Adding this very file under `.shipwright/planning/adr/` made
`shared/tests/test_adr_index_producers.py`'s two drift checks fail
(`test_committed_index_is_not_stale`, `test_every_adr_file_in_this_repo_is_listed`)
against the committed `.shipwright/planning/adr/INDEX.md`. Fixed by running
`uv run shared/scripts/tools/rebuild_adr_index.py --project-root .`, which is
a tracked, committed producer (unlike the compliance/traceability derived
files) — `INDEX.md` is added to F6's commit paths.

## External Plan Review Findings

Ran per Step 3.5 against the mini-plan + this ADR (`--mode iterate`). GLM
verdict: approve (6 findings, medium×2/low×4). OpenAI verdict: revise (6
findings, HIGH×3/medium×2/low×1). Raw output:
`.shipwright/planning/iterate/iterate-2026-09-15-t9-contract-cihost-repair-contextcost/external-plan-review-raw.json`.

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | HIGH | `FR-01.15/AC08`'s proof is a documentation sentence plus a drift-pin test, both authored in this same run — proves the sentence persists, not that the contract binds only the intended side. | **accepted-and-fixed.** The `@pytest.mark.covers("FR-01.15/AC08")` marker was removed from `test_cross_repo_contract_documented.py::TestSkillStatesTheContract::test_it_states_the_contract_binds_this_side_only`; docstring rewritten to disclaim the binding and cite Exception 8's precedent for unmarked drift-pin guards. Seam survey's Exception 2 amended with a dated correction paragraph. `shipwright_ac_coverage_baseline.json` regenerated (44 -> 45 unbound). |
| 2 | glm | medium | Same finding as #1, independently — "the same self-fulfilling test the plan itself rejects for FR-01.19 AC09/AC10." | **accepted-and-fixed.** Same fix as #1; both reviewers' independent agreement is recorded as the reason this was treated as the highest-priority correction. |
| 3 | openai | HIGH | Test-root declarations conflict: the sub-iterate spec's own scope line names 2 roots while the mini-plan named 4 — the authoritative root list needs resolving before ADR-044 compliance can be verified. | **accepted-and-fixed.** Mini-plan's Problem statement rewritten to state both the pre-authorized ceiling (t0 seam survey per-unit root-count table, 4 roots) and the roots actually used this run (3 — `plugins/shipwright-iterate/tests` was never touched, because every FR-01.19 AC this unit bound had its real proving test under `shared/tests` instead). This ADR's "Regeneration provenance" table lists the exact 3 roots, commands, and results. |
| 4 | glm | medium | Exceptions 10 and 11 are new this run and granted by the same unit that benefits from them, citing itself — is campaign-owner pre-approval needed first (the same standing question the root-count exceptions required)? | **rejected-with-reason.** t8's plan-review disposition #3 already settled this exact question: a unit recording a new no-seam finding during its own execution, backed by a decision-drop/ADR, follows the Exceptions-5-9 shape (no pre-approval required), distinct from the Exception-3 root-count shape (which is a resource/scope decision, not a does-this-AC-have-a-seam judgment call). Cited, not re-argued, in both Exception 10's and Exception 11's own Provenance paragraphs (added to the seam survey). |
| 5 | openai | medium | The FR-01.17/AC01 test could become a superficial workflow-text assertion — finding four command names in YAML does not prove they run for pull requests specifically, given path filters or job conditions. | **accepted-and-fixed.** Two new tests added: `test_the_pull_request_trigger_has_no_path_filter` (asserts no `paths:`/`paths-ignore:` narrows any of the 3 workflows' `pull_request` trigger — verified none exists) and `test_no_job_is_conditioned_out_of_the_pull_request_event` (asserts no job-level `if:` excludes `pull_request` — verified none exists). File re-run green (11 passed), 130 lines. |
| 6 | openai | low | Result accounting said "FR-01.19: 8/8" despite 10 stated ACs — ambiguous vs. an incomplete mapping. | **accepted-and-fixed.** Reworded throughout (mini-plan, this ADR) to "8/10 bound, AC09/AC10 recorded as exceptions." |
| 7 | openai | HIGH | Regenerating derived artifacts but leaving them "uncommitted-but-present" risks CI/review seeing stale coverage data on the campaign's terminal unit specifically. | **rejected-with-reason.** Identical, already twice-externally-reviewed convention from t3-t8 (see t8's own disposition #6, same wording): CI's own fresh-regeneration step rebuilds the manifest from real JUnit output before the AC-coverage gate reads it, so a locally-partial manifest cannot under- or over-state what CI computes. The final repo-wide number (45 unbound) is explicitly recorded in this ADR, this run's decision-drop, and `result.json` regardless, addressing GLM's "final unit" framing (finding below) without changing the convention. |
| 8 | glm | low | For the *final* unit of the campaign specifically, an uncommitted regeneration means the repo-wide unbound_count claim exists only on this machine's working tree — a reviewer diffing the branch can't see the campaign's terminal state. | **rejected-with-reason, same convention as #7, final numbers recorded explicitly.** See #7's disposition — the terminal repo-wide state (45 unbound, down from 69 at the start of this unit and from campaign-start's higher count) is written into this ADR, the F3 decision-drop, and `result.json`, giving a reviewer a durable, git-tracked number even though the regenerated JSON file itself is not committed. |
| 9 | glm | low | `test_ci_reruns_the_full_verification_on_pr.py` creates maintenance coupling — a future workflow refactor could break it, and it only checks workflow files, not that checks are GitHub-side *required*. | **accepted, follow-up recorded, no code change to this unit's scope.** The test's own module docstring already states it pins workflow files, not branch protection. Whether "required" is part of AC01's text (and therefore needs a branch-protection-API-level assertion) is a spec-reading question out of scope for a test-tagging unit to resolve unilaterally; recorded here as a tracked follow-up rather than left as tribal knowledge. |
| 10 | glm | low | The `test_links` collector "cannot run standalone via relative import" tribal knowledge, restated in this and prior units' mini-plans, should be a tracked follow-up rather than repeated prose. | **accepted, follow-up recorded, no code change to this unit's scope.** Same as t8's and earlier units' identical finding; out of scope for a test-tagging unit to fix the regeneration tooling itself. |
| 11 | glm | low | New split files (`test_contract_skeleton_weak_pins.py`, `test_context_cost_core_phase_labels.py`) must land in already-declared roots and appear in per-root JUnit output for ADR-044 compliance. | **accepted-and-verified, no code change needed.** Both files are under `shared/tests`, an already-declared root; both were exercised in the `shared/tests` run recorded in "Regeneration provenance" above (10913 passed total, which includes their tests) — confirmed by direct collection, not merely inferred. |

## External Code-Review Findings

Ran per Step 3.7 item 2 (diff > 100 lines). Both reviewers verdict: revise.
Raw output:
`.shipwright/planning/iterate/iterate-2026-09-15-t9-contract-cihost-repair-contextcost/external-code-review-raw.json`.

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | medium | `test_no_job_is_conditioned_out_of_the_pull_request_event`'s substring check for `"pull_request"` in a job-level `if:` would wrongly PASS a condition like `if: github.event_name == 'push'`, which excludes PRs without ever naming them. | **accepted-and-fixed.** Replaced with `test_the_gate_job_itself_carries_no_conditional`, which asserts the gate job's `if:` is `None` outright (any condition, of any shape, is now rejected) — sound regardless of wording. Re-run green. |
| 2 | openai | medium | AC05's two test classes call `null_only_paths`/`empty_array_paths` directly; they don't exercise the publishing/gate path, so a broken integration that stopped calling these helpers would still pass. | **rejected-with-reason, with a docstring clarification added.** The seam survey's own quick-decide table (line ~260) already names these two functions as AC05's real seam ("fixture provenance") — distinct from AC02/AC03/AC06, where the survey explicitly ruled a library-only test insufficient. No wired "publish" call site exists yet to drive end-to-end; building one would be new production wiring, not test backfill, and would re-decide a seam t0 already assigned. `test_contract_skeleton_weak_pins.py`'s docstring now states this explicitly. |
| 3 | glm | medium | `test-traceability.json`/`shipwright_ac_coverage_baseline.json` appeared as changed hunks in the code-review diff, contradicting the ADR's "uncommitted-but-present" claim — the reviewer read this as the files being committed. | **rejected-with-reason, reviewer artifact, not a real defect.** The code-review diff was generated via `git diff HEAD` against a branch with NO commits yet (this unit had made none at review time) — every uncommitted working-tree change, derived files included, necessarily appears in that diff. It does not mean the derived files will be part of the eventual F6 commit; F6's explicit per-path `git add` (this ADR, this file) does not list them, matching t3-t8's convention exactly. No baseline hunk is staged or committed. |
| 4 | glm | medium | `test_show_breaks_the_running_total_down_by_phase_on_demand` writes the per-session summary itself, then asserts `show` echoes it back — proves display passthrough only, not that the real Stop hook ever writes `by_phase` into the live file. | **accepted-and-fixed.** Added `test_the_real_hook_writes_phase_buckets_show_then_actually_prints`, which drives the actual `track_context_cost.py` Stop hook (real run pointer, real phase marks, real transcript) and reads the resulting on-disk file back through `show` — no hand-authored dict. Re-run green (9 passed in the file). |
| 5 | glm | low | `test_no_job_is_conditioned_out_of_the_pull_request_event` checks only job-level `if:`; a step-level `if:` on the specific pytest/ruff/semgrep-invoking step would defeat the guarantee while every test in the file stayed green. | **accepted-and-fixed.** Added `test_no_gate_carrying_step_is_conditioned_out`, narrowly checking only the steps whose own `run:`/`uses:` body names a gate tool (pytest/ruff/semgrep for ci.yml/security.yml, `codeql-action/analyze` for codeql.yml) — verified none carries a step-level `if:`. |
| 6 | glm | low | Four tests moved to `test_context_cost_core_phase_labels.py`; verify no dead imports were left behind in `test_context_cost_core.py` (ruff F401 risk). | **rejected-with-reason, verified false.** `uvx ruff@0.15.15 check shared/tests shared/scripts/tests shared/scripts/tools/tests` reports zero findings; `ipg` (`iterate_phase_groups`) remains genuinely used by a test that stayed in the original file. |
| 7 | glm | low | Mini-plan's Approach step 4 said "one new assertion added to an existing test" for the phase-breakdown clause, but the diff adds a new standalone test. | **accepted-and-fixed.** Mini-plan wording corrected to describe a new test, matching the diff. |

## Orchestrator Review Cascade (Stage 1/2/3, campaign-mode.md 3f-bis)

Run by the campaign orchestrator after the sub-iterate runner pushed (the
runner has no Agent tool). Spec-reviewer required 2 rounds; code-reviewer and
doubt-reviewer each ran once against the fixed diff. Tier-3 (PR #760, external,
`openai/gpt-5.6-luna`) BLOCKed once after push; both its findings are recorded
below alongside the internal cascade for one complete record.

| # | Stage | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | spec (round 1) | REJECT | `FR-01.19/AC09`/`AC10` were recorded unbound with a justification claiming they were "already bound elsewhere" via `FR-01.18/AC08`/`AC07` — verified false: those FR-01.18 tests prove consent-gating and completeness-of-reporting, neither of which is AC09's disclosure clause or AC10's scope-disclaimer clause (confirmed via `spec.md` text comparison, the cited tests' actual assertions, and a repo-wide grep for AC09/AC10's real language returning zero hits outside `spec.md`). | **accepted-and-fixed.** Seam survey Exception 11 and the ADR's AC09/AC10 rows rewritten to retract the false claim and record an honest no-seam finding (no test anywhere, under either FR, proves either AC's actual clause). |
| 2 | spec (round 2) | REJECT | The fix in round 1 corrected the seam survey and ADR but left the sibling mini-plan (`2026-09-15-t9-contract-cihost-repair-contextcost-miniplan.md`) asserting the same retracted "already bound there" claim in two places — an internal contradiction within the same commit. | **accepted-and-fixed.** Both mini-plan passages rewritten to match the corrected finding. Re-verified clean (round 3, PASS) with a repo-wide grep confirming no other occurrence of the retracted phrasing survives as asserted fact anywhere in the diff's touched files. |
| 3 | code | — | No findings. Verified via literal `wc -l`/grep-count on every new/modified test file (all under the 300-line cap), no stale `@pytest.mark.covers` markers left double-bound, and read-through of the two most novel new tests against the real production YAML/hook they claim to pin (not tautological). | **APPROVE, no action.** |
| 4 | doubt | medium | `FR-01.17/AC02`'s cited test (`test_stage1_owns_no_pr_review_context`) checks only each job's `name:` field, never the commit-status `context=` string GitHub's required-check mechanism actually keys on — a future stage-1 edit could post the required context under an innocuously-named job and this test would stay green. | **accepted-and-fixed.** Added a negative assertion to the same test: no stage-1 shell body may contain `context="PR Review"` / `context="Claude Code Review"` under any job name. Verified against the real `.github/workflows/*.yml` (currently none post such a context, so this closes a latent gap without changing today's passing status). |
| 5 | doubt | medium | `FR-01.17/AC04`'s cited test only proved SOME commit status posts, never that the `description=` field (the AC's "reasons" clause) carries real content rather than a hardcoded string. A deeper test proving the reasoning text is scenario-specific exists (`plugins/shipwright-security/tests/test_decide_pr_review_gate_cli.py`), and the production shell code does pipe a computed `desc` variable into the posted description (confirmed by reading `.github/workflows/pr-review-run.yml`) — but no test connected the two. | **partially accepted-and-fixed, remainder disclosed.** Added an assertion that the posted description is piped from a computed `desc` variable, not a hardcoded string. Did NOT tag `test_decide_pr_review_gate_cli.py`'s existing reason-content tests, because `plugins/shipwright-security/tests` is a 5th pytest root beyond the 4 the campaign owner pre-approved for t9 (Exception-3-shape root-count decision, not a does-this-AC-have-a-seam judgment call — the same distinction Exceptions 10/11 draw) — flagged to the operator rather than silently expanded. |
| 6 | Tier-3 (blocking) | — | `test_ci_reruns_the_full_verification_on_pr.py`'s bare substring checks (`"pytest" in body`, `"ruff" in body`, `"semgrep" in ci_body.lower() or ...`) would pass a workflow that merely `echo`ed the tool names instead of running them. | **accepted-and-fixed.** Added a `_real_commands()` helper stripping comment (`#`) and bare `echo` lines before searching; strengthened each assertion to a real-invocation-shape regex (`\bpytest\b\s+\S`, `\bruff@[\w.]+\s+check\b`). Verified the exact counterexample Tier-3 gave (`echo "pytest ruff semgrep"`) now fails both regexes. Separately discovered while fixing this: the semgrep check was matching only `pip install semgrep` and comment prose in `security.yml` (semgrep never appears as a literal command there — it runs through `scan.py --scan-types sast,...`) — rewritten to check for the real `scan.py --scan-types ...sast...` invocation instead. The CodeQL check was switched from raw-text search to reading the parsed `uses:` step field, which a comment/echo cannot imitate. |
| 7 | Tier-3 (blocking) | — | The two sensitive skill-doc additions (`cross-repo-contract.md:21-25`, `grade/SKILL.md:76-81` — the FR-01.15/AC08 scope-disclaimer sentence) require a maintainer to manually confirm the wording is accurate and does not weaken the producer/consumer contract boundary before merging a sensitive-path change. | **maintainer confirmed, no code change.** Asked Sven directly (this is exactly the class of decision the campaign's own constitution reserves to a human — confirming contract-defining documentation is accurate, not a does-this-AC-have-a-seam judgment call). Confirmed 2026-09-15: the sentence accurately describes the contract's existing one-way nature (this repo's publish-side obligations only; no promise about the WebUI's behavior on an unrecognized version) and is safe to keep as written. |

## Reflection (F3a)

No new `conventions.md` entry needed. The two candidate learnings from this
run are both already-recorded, established precedents, cited rather than
re-recorded: (1) the self-fulfilling-test pattern (a doc sentence + drift-pin
test authored in the same run proving persistence, not enforcement) is
Exception 8's own precedent, applied here to FR-01.15/AC08; (2) the
ADR-index-regeneration requirement for a new `.shipwright/planning/adr/`
file is already `conventions.md`'s own `(2026-09-15) iterate/F0` entry, from
t8, this same campaign. No architecture.md edit: this unit adds/tags tests
and two documentation sentences only — no new route, component, schema,
service, or write/read-surface.

## Self-Review

Run per `references/iteration-reviews.md`'s 7-point checklist, after
addressing every finding above.

1. **Spec Compliance** — pass. All 31 ACs re-derived directly from
   `shipwright_ac_coverage_baseline.json` (not the spec's stale count);
   every bound AC ties to a real, already-existing or newly-added test
   exercising the actual enforcing code path; every unbound AC carries a
   concrete, evidenced reason recorded in the seam survey.
2. **Error Handling** — pass. No production error-handling paths were
   touched; this unit adds/tags tests and two documentation sentences only.
3. **Security Basics** — pass. No secrets, no new inputs, no new attack
   surface. `test_ci_reruns_the_full_verification_on_pr.py` reads local YAML
   files only.
4. **Test Quality** — pass, after the AC08 fix. Every remaining bound AC's
   test proves a real enforcing path (git-ref immutability, actual CI
   workflow files, real dedup/phase-attribution logic, real CLI dispatch),
   not a renderer, wrapper, or shape-only check on an identifier. The one
   self-fulfilling exception found by external review was reverted before
   this checklist ran.
5. **Performance Basics** — pass. No perf-sensitive code touched; tests run
   in well under a second each (workflow-file parsing, small object
   comparisons).
6. **Naming & Structure** — pass. New files follow the existing
   `test_<subject>.py` convention; split files (`*_weak_pins.py`,
   `*_phase_labels.py`) name what they hold, not merely "part 2".
7. **Affected Boundaries (ADR-024)** — pass, not applicable. No serialized
   format producer/consumer pair was changed by this unit; the cross-repo
   contract's OWN documentation (FR-01.15/AC07/AC08) was touched, but no
   field, schema, or wire shape changed — round-trip probing does not apply
   to a documentation-only edit that a drift-pin test already guards.

Checklist items 1-7 above are each marked pass or not-applicable individually, with the reason stated per item.
