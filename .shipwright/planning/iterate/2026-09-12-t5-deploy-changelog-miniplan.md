# Mini-Plan: t5 - deploy-changelog (FR-01.08 + FR-01.09 AC backfill)

- **Run ID:** iterate-2026-09-12-t5-deploy-changelog
- **Campaign:** req3-05-test-backfill-mono, sub-iterate t5
- **Type:** change (test backfill via `@pytest.mark.covers`, no production-behavior change)
- **Complexity:** small (Stage 1 `classify_complexity.py`). Step 3.4 diff-driven
  re-check: `effective_complexity=small`, `upgraded=false`, `risk_flags=["touches_build"]`
  (pyproject.toml marker registration touched), `plan_review_required=true`
  (merge-base diff is 213 LOC, over the 100-LOC threshold).

## Cited seam (binding, not re-decided)

Per the campaign header's binding-seam rule, this unit cites
`.shipwright/planning/iterate/2026-09-11-req3-05-seam-survey.md` (t0)'s row for
this cluster rather than re-deciding it:

> `FR-01.08 | /shipwright-deploy | 15 / 15 | plugins/shipwright-deploy/tests |
> test_smoke_e2e_cli.py, test_rollback_e2e_cli.py — genuine subprocess E2E CLI
> harnesses already exist here; prefer them over the narrower
> test_validate_deploy.py/test_rollback.py unit files where an AC is itself
> about the CLI's observable behavior | none yet | t5`
>
> `FR-01.09 | /shipwright-changelog | 15 / 15 | plugins/shipwright-changelog/tests;
> shared/tests for the aggregation/idempotency surface (Finding 1) |
> test_integration.py; shared: test_changelog_aggregation_idempotency.py,
> test_changelog_aggregation_refusal.py, test_aggregate_changelog.py,
> test_changelog_sections_shared.py | none AC-bound yet (only bare-FR tags
> found) | t5`

**Root count — 3, waived** (`.shipwright/planning/iterate/2026-09-11-req3-05-seam-survey.md`,
"Per-unit ADR-044 root count" table + "Flagged deviation" section): the
campaign owner (Sven) ruled 2026-09-12 that option (a) — accept the deviation,
the roots are forced by where the behavior lives, not chosen — applies to t5
(and t4/t8/t9) exactly as already accepted for t1. Roots touched:
`plugins/shipwright-deploy/tests`, `plugins/shipwright-changelog/tests`,
`shared/tests` — one `pytest` invocation per root (ADR-044 governs pytest
*processes*, not roots per unit), one `--junitxml` per root, results merged by
hand afterward.

**A FOURTH root was needed, found during execution — flagged, not decided
unilaterally.** Two FR-01.09 ACs (AC12: manifest version write is checked
against the committed blob; AC13: a manifest carrying its version in more
than one place gets every occurrence written together) are proven only by
`shared/scripts/tools/tests/test_sync_release_manifests_git.py` and
`test_sync_release_manifests_marketplace.py` — a distinct ADR-044 root the
seam survey's own row for FR-01.09 did not list. This mirrors t1's own
Exception 3 precedent exactly (a root discovered mid-execution, not chosen):
the behavior these two ACs describe is implemented in
`shared/scripts/tools/sync_release_manifests.py`, whose own tests live under
that tool's root (`shared/scripts/tools/tests`), not under `shared/tests`
(the aggregator's root) or the plugin's own root. No new test harness was
introduced — both bindings are `@pytest.mark.covers` additions to two
already-existing, already-passing test functions in that root. Following the
same "(a) accept the deviation — forced by where the behavior lives, not
scope creep chosen by the unit" reasoning the campaign owner already applied
to t1's discovered third root and to this unit's own three waived roots, this
unit proceeds with the fourth root and flags it here for the orchestrator /
campaign owner to ratify, rather than either inventing a new test harness
inside an already-covered root to avoid it, or leaving AC12/AC13 unbound when
a real, fitting, already-passing seam exists. One `pytest` invocation for this
root too, its own `--junitxml`.

## Re-derived work list (not copied from the spec)

`shipwright_ac_coverage_baseline.json` -> `unbound` at branch point (fresh
`origin/main`): 15 ACs start with `FR-01.08/` (AC01-AC15, all of them) and 15
start with `FR-01.09/` (AC01-AC15, all of them) — 30 ACs total, matching the
spec's stated count going in. Confirmed via `check_ac_coverage_ratchet.py`'s
own `unbound` list before any edit, not copied from the spec file.

## Approach

Precedent-first per the campaign's own binding rule, but Finding 2 (t0's seam
survey) already established this cluster is virgin ground: neither FR-01.08
nor FR-01.09 had ANY existing `/ACnn`-qualified binding before this unit —
only bare `FR-01.09` tags on several already-passing changelog aggregation
tests (Finding 6). For every AC: first checked whether an EXISTING,
already-passing test in the assigned root already exercises the exact
behavior the AC describes (true for the large majority — the deploy plugin's
rollback/data-drift/smoke-liveness suites and the changelog plugin's shared
aggregation suite are unusually dense and precise already). Where a bare
`FR-01.09` tag already sat on the exact right test, it was UPGRADED in place
to the qualified form (Finding 6's instruction), never left stacked alongside
a new one. Where no existing test proved an AC's specific claim, a new test
function was added to the SAME file already covering that production module
(never a new file), invoking the real production entry point (subprocess CLI
for `rollback.py`/`smoke_test.py`; direct function call for
`deploy_from_git`) rather than re-implementing any logic. Two new test
functions were added in total (`test_deploy_from_git_creates_the_project_
then_updates_when_absent` and `test_more_than_one_hosting_target_kind_is_
offered`, both in `test_jelastic_client.py`) — every other binding is either
a tag upgrade or a new `@pytest.mark.covers` decorator on an existing test.

**Before binding any AC, the standing question was asked and answered
in the per-AC table below:** if the production code broke in the specific
way this AC describes, would the cited test actually fail? Two classes of
near-miss were caught and rejected during this pass, per the t3/t4 lesson in
this unit's own briefing:

1. `plugins/shipwright-deploy/scripts/tools/verifiers/deploy_checks.py`'s
   `check_test_gate_passed` LOOKS like it proves FR-01.08/AC02 ("a release
   with failing tests is refused until a person confirms"), but it is a
   POST-HOC phase-completion verifier (`shared/scripts/tools/verify_phase.py`
   calls it to audit a deploy AFTER it ran), never a live pre-deploy gate
   that refuses to call `jelastic_client.deploy_from_git`/`vcs_update`. The
   actual refusal-until-confirmed behavior is SKILL.md Step B4's agent-level
   `AskUserQuestion` prose. Binding AC02 to this verifier's tests would be
   exactly the "renders/inspects a related but different code path" defect
   class t3's PR-Review REJECT and t4's Stage-1 REJECT both hit — not bound.
2. `plugins/shipwright-deploy/tests/test_rollback_e2e_cli.py::
   test_the_cli_sends_the_requested_version_to_the_host` proves the
   version-reaches-the-host mechanism, but it does so via the ROLLBACK path
   (`rollback.py --strategy git`), not the RELEASE path FR-01.08/AC01
   describes. Citing it for AC01 would be binding a release AC with a
   rollback test — a materially different code path, even though the wire
   mechanics are similar. AC01 is instead bound with a genuine new unit test
   driving `jelastic_client.deploy_from_git` directly (the actual release
   entry point), so a regression in the RELEASE path specifically would be
   caught.

**Seven ACs are left unbound with a recorded reason** — five in FR-01.08,
two in FR-01.09 (originally eight; FR-01.09/AC11 was reclassified and bound
during Step 3.5 external plan review — see External-Plan-Review-Findings
below). Every one was checked against a concrete production module or
reference doc before being declared unprovable; none is a convenience skip.
Full per-AC reasoning is in the table below; the pattern in every case is
the same class already established in this campaign's own Exception 1
(Preview) and Exception 7/8 (t3, FR-01.03/FR-01.04) and t4's own seven
exceptions: the AC describes agent-executed SKILL.md prose, or a
conjunctive claim whose second clause has no code artifact a deterministic
test can invoke and assert on.

## Per-AC seam mapping (executed)

### FR-01.08 (/shipwright-deploy)

| AC | Root | Test file :: function |
|---|---|---|
| AC01 | deploy | `test_jelastic_client.py::test_deploy_from_git_creates_the_project_then_updates_when_absent` (new) — the release entry point actually creates/updates the VCS project and sends the git ref; `test_jelastic_client.py::test_more_than_one_hosting_target_kind_is_offered` (new) — reads the real, shipped `shared/profiles/deploy/*.json` directory and asserts more than one `target_kind` is offered (not tied to one hosting company) |
| AC02 | **not bound — recorded reason** | Conjunctive AC: "refused until a person explicitly confirms" is SKILL.md Step B4 agent prose (`AskUserQuestion`); the only code-level artifact (`deploy_checks.check_test_gate_passed`) is a POST-HOC phase-completion verifier, never a live pre-deploy gate — confirmed by reading `verify_phase.py`'s call site. No code path refuses to call the release CLI when tests failed. |
| AC03 | deploy | `test_smoke_e2e_cli.py::test_the_liveness_cli_reads_the_whole_policy_from_the_target_profile` (live app answers → success) + `::test_the_liveness_cli_keeps_asking_until_the_deadline` (unreachable → failed release, not a finished one) |
| AC04 | deploy | `test_smoke_e2e_cli.py::test_the_liveness_cli_keeps_asking_until_the_deadline` (polls using the target's own deadline) + `::test_the_liveness_cli_without_a_deadline_asks_once` (no deadline configured → asked once) |
| AC05 | **not bound — recorded reason** | "The previously working version is put back without a person having to intervene" — no code wires a smoke-test failure to an automatic `rollback.py` invocation; SKILL.md's "Smoke Test Failed → Rollback" section is the agent's own next-step prose, not a coded trigger. |
| AC06 | deploy | `test_rollback.py::test_readback_confirming_the_ref_reports_confirmed` / `::test_readback_returning_a_different_ref_is_a_failure` / `::test_unavailable_readback_downgrades_the_claim_and_says_why` / `::test_a_raw_transport_failure_also_downgrades_rather_than_escaping` (confirmed/mismatch/unconfirmed three-way) + `test_rollback_e2e_cli.py::test_the_cli_sends_the_requested_version_to_the_host` (E2E: version actually sent, host acknowledges) |
| AC07 | deploy | `test_data_drift.py::test_drift_refuses_and_names_the_targets_strategy` / `::test_an_unresolvable_ref_refuses_rather_than_guessing` / `::test_acknowledging_the_drift_lifts_the_refusal` / `::test_an_undeclared_strategy_still_refuses_and_says_it_is_undeclared` + `test_rollback_e2e_cli.py::test_drifted_data_refuses_without_contacting_the_host` / `::test_acknowledging_the_drift_proceeds` (E2E) |
| AC08 | **not bound — recorded reason** | Conjunctive AC: `migration_verifier.py`'s own docstring/tests say it "provides the failure signal... does NOT itself perform the rollback" — the "same return-to-previous-state path is offered, and continuing regardless requires a written record" is SKILL.md Step 1's `AskUserQuestion` + a manually-invoked `write_decision_log.py` call, not a coded gate. |
| AC09 | deploy + shared | `shared/tests/tools/test_validate_deploy_profile.py::TestRealProfilesAreValid` (all three real, offered targets validate against the ONE common schema, whose `rollback` block is a required field set — checked before the target is offered, not during an incident) + `::TestStructuralViolations::test_missing_rollback_block_fails` (**added after external plan review**: the negative case — a target declared without its `rollback` block is rejected by the same schema, proving the check would catch an incomplete offering, not only that the three already-complete profiles happen to pass) |
| AC10 | deploy | `test_rollback_clone.py::test_clone_strategy_reports_stopping_not_restoring` + `test_rollback_e2e_cli.py::test_a_stop_only_clone_rollback_says_so` (stopping reported as stopping, `restored=False`, never a completed restore) |
| AC11 | **not bound — recorded reason** | The CLI always "announces itself" (non-empty `message`/`operator_message`), but "recorded with its cause" is a `decision_log.md` write SKILL.md instructs the agent to make manually — `rollback.py` itself writes no durable record. It also cannot know whether it was auto-triggered or person-requested (not passed as an argument), so it cannot record that half of the claim either. |
| AC12 | **not bound — recorded reason** | "Requires explicit confirmation and afterwards proves the restored application is alive" (Manual Rollback SKILL.md section) — the confirmation is agent-level `AskUserQuestion`, and nothing in `rollback.py` chains a smoke-test call afterward; that is a separate SKILL.md step, not a coded sequence. |
| AC13 | deploy | `test_rollback.py::test_update_failure_reports_the_changed_configuration_and_the_previous_ref` + `test_rollback_clone.py::test_clone_stop_failure_halts_and_names_the_state` + `test_rollback_e2e_cli.py::test_a_failed_update_halts_with_a_distinct_exit_code` (halt reported as a halt, never swallowed nor read as restored) |
| AC14 | deploy | `test_rollback.py::test_update_failure_reports_the_changed_configuration_and_the_previous_ref` / `::test_invalid_ref_forms_are_rejected_before_any_host_call` / `::test_unreadable_project_config_refuses_instead_of_writing` + `test_rollback_e2e_cli.py::test_a_failed_update_halts_with_a_distinct_exit_code` / `::test_a_failed_pin_never_issues_the_update` / `::test_an_invalid_ref_is_rejected_before_anything_is_contacted` (halted vs. refused-before-contact distinction, both directions) |
| AC15 | deploy | **Re-bound after external plan review** (both prior citations proved *refusal*, i.e. a rollback that never happened, not a *completed* one — the AC's own "when it completes" clause): `test_rollback_e2e_cli.py::test_acknowledging_the_drift_proceeds` (the rollback completes — `success=True` — while `data_drift.drifted` stays `True`, proving the completed code path never silently marks the data as reverted too) + `plugins/shipwright-deploy/tests/test_data_drift.py::test_a_target_whose_data_never_moves_skips_the_question` (the module docstring's "it detects the mismatch, it never undoes data" plus the target's own declared strategy — `none-app-only` — being what answers the question, named by `target_id`) |

### FR-01.09 (/shipwright-changelog)

| AC | Root | Test file :: function |
|---|---|---|
| AC01 | **not bound — recorded reason** | "Three things exist: a release note, a version marking, and an open request to deliver it" — the release note half is code-provable (`aggregate_changelog.py`), but the version tag (`git tag`) and the PR (`gh pr create`) are raw shell steps in SKILL.md Step 6/7, not a single deterministic seam that produces all three together. Binding only the release-note half would be exactly the partial-clause defect class this campaign's own precedent (Exception 7/8) rejects. |
| AC02 | changelog | `test_changelog.py::test_categorize_commits` (entries grouped by kind, human-readable form) |
| AC03 | shared | `test_changelog_aggregation.py::TestAggregateEndToEnd::test_no_drops_produces_empty_section_and_no_update` (no pending work → no bytes written, reported as empty rather than an empty release) |
| AC04 | changelog | `test_git_utils.py::test_suggest_version_first_release` / `::test_suggest_version_feat` / `::test_suggest_version_fix_only` / `::test_suggest_version_breaking` / `::test_suggest_version_breaking_pre_1` (every branch of the exact semver rule, including the pre-1.0 exception and the from-nothing case) |
| AC05 | shared | `test_aggregate_decisions.py::test_aggregates_drops_into_decision_log` (two decision records, each keyed by run_id not a pre-assigned number, get sequential numbers assigned at this ONE aggregation point) |
| AC06 | shared | `test_changelog_aggregation.py::TestStructuralInsert::test_inserts_above_first_version_section` (new release lands above the most recent released one; title and older entries survive) |
| AC07 | shared | `test_changelog_aggregation_idempotency.py::test_rerun_after_interrupted_release_writes_the_version_once` / `::test_replacing_changed_content_reports_replaced` / `::test_rerunning_a_completed_release_is_a_clean_noop` + `test_changelog_aggregation_refusal.py::test_duplicate_sections_refuse_with_the_count` (replaced rather than duplicated; more than one existing section for a version stops and says why) |
| AC08 | shared | `test_changelog_aggregation_refusal.py::test_hand_edited_section_refuses` (recorded section doesn't match what the pending entries say) / `::test_yanked_marker_on_the_heading_refuses` (a heading marking — e.g. `[YANKED]` — that a replace would erase) |
| AC09 | shared | `test_changelog_aggregation.py::TestAggregateEndToEnd::test_legacy_unreleased_bullets_preserved_and_warned` (entries written the older way are named back to the operator, not folded in silently) |
| AC10 | shared | `test_changelog_aggregation_refusal.py::test_dry_run_reports_the_replace_without_writing_or_unlinking` / `::test_dry_run_still_refuses_a_state_that_would_be_refused` (full preview, nothing on disk changes either way) |
| AC11 | shared | **Bound after external plan review** (both reviewers independently rejected the original "absence is unprovable" reasoning, correctly — this campaign's own seam already proves other absences via fail-if-called spies and dry-run byte-identity checks): `shared/tests/test_changelog_aggregation.py::TestAggregateEndToEnd::test_aggregation_never_shells_out_to_git_or_gh` (new test — `subprocess.run`/`Popen`/`check_call`/`check_output` are monkeypatched to raise `AssertionError` if called, then a full end-to-end `aggregate()` release is run; the release still succeeds while the spy is never triggered — a regression that added a `git push`/`gh pr create` call to `aggregate()` would fail this test the moment it reached for that seam) |
| AC12 | shared/scripts/tools (4th root, flagged above) | `test_sync_release_manifests_git.py::test_verify_commit_passes_when_write_landed_in_commit` / `::test_verify_commit_catches_omitted_manifest_regression` (the commit is checked afterward to confirm the write landed; a manifest still at its previous version in the commit stops the release) |
| AC13 | shared/scripts/tools (4th root, flagged above) | `test_sync_release_manifests_marketplace.py::test_sync_marketplace_manifest_bumps_root_and_nested_entries` (root + every nested catalog entry written together in the same pass) |
| AC14 | shared | `test_validate_release_notes.py::test_bad_heading_fails` / `::test_missing_version_string_fails` / `::test_normal_release_footer_carries_compare_link` (checked against a fixed, expected shape; version marking + link constructed directly from recorded facts) + `test_create_github_release.py::test_reports_exists_without_creating` / `::test_success_argv_shape` (the release page is actually created, carrying the summary + link) |
| AC15 | **not bound — recorded reason** | Two-scenario AC: the first ("release-page failure doesn't undo the release, is reported not swallowed") IS well-provable and is exactly what `publish_release_notes.py`'s always-non-raising, always-JSON-reporting contract does — but the second ("a version released before this capability existed does not get a page created for it retroactively") has no code seam: nothing in `create_github_release.py`/`publish_release_notes.py` distinguishes an "old" version from a "new" one; that guarantee is purely that SKILL.md Step 7 only ever calls it once, with the version just tagged. Per this campaign's own precedent (a partially-provable clause does not make the whole AC provable), not bound. |

## No new test harness

No new pytest fixture pattern, mocking approach, or test-double strategy was
introduced. Four new test FUNCTIONS were added in total, each using its own
file's existing idioms rather than a new one:

- `test_jelastic_client.py::test_deploy_from_git_creates_the_project_then_updates_when_absent`
  and `::test_more_than_one_hosting_target_kind_is_offered` (original pass,
  AC01) — that file's existing mock-`urlopen`/read-real-profile-directory idioms.
- `test_changelog_aggregation.py::TestAggregateEndToEnd::test_aggregation_never_shells_out_to_git_or_gh`
  (added during Step 3.5 external plan review, AC11) — `monkeypatch`, already
  used throughout this file's `TestAggregateEndToEnd` class.
- `test_validate_deploy_profile.py::TestStructuralViolations::test_missing_rollback_block_fails`
  (added during Step 3.5 external plan review, AC09) — `copy.deepcopy` +
  `validate()`, the exact pattern every other test in `TestStructuralViolations`
  already uses.

Every other binding is either a `@pytest.mark.covers` addition to an
existing, already-passing test, or an in-place upgrade of an existing bare
`FR-01.09` tag to its qualified form (Finding 6).

## Verification performed

**Interim runs, during binding work (superseded by the final run below once
all Step 3.5 fixes landed — numbers here are historical, kept for the audit
trail per external-review round 2's accounting-consistency finding):**

1. `uv run pytest plugins/shipwright-deploy/tests -q` — 104 passed (root 1),
   re-confirmed after the AC15/AC09 re-bindings.
2. `uv run pytest plugins/shipwright-changelog/tests -q` — 89 passed (root 2).
3. `uv run pytest shared/tests -q` — full green run (waived root 3),
   re-confirmed after the AC11 test (both the first and the hardened
   `os.system`/`os.popen` version) — `test_changelog_aggregation.py` alone: 19 passed.
4. `uv run pytest shared/scripts/tools/tests -q` — full green run (4th root,
   flagged above; forced by AC12/AC13's real seam).
5. `uv run pytest shared/tests/tools/test_validate_deploy_profile.py -q` —
   36 passed (includes the new `test_missing_rollback_block_fails`).

**Final, authoritative run (one `--junitxml` per ADR-044 root, after every
Step 3.5 fix landed):**

6. `uv run pytest plugins/shipwright-deploy/tests --junitxml=<scratch>/deploy.xml -q`
7. `uv run pytest plugins/shipwright-changelog/tests --junitxml=<scratch>/changelog.xml -q`
8. `uv run pytest shared/tests --junitxml=<scratch>/shared.xml -q`
9. `uv run pytest shared/scripts/tools/tests --junitxml=<scratch>/tools.xml -q`

   (`<scratch>` = this session's scratchpad directory, per the runner
   environment's convention — these are transient CI-shaped artifacts, never
   committed, same as every prior sub-iterate in this campaign; their pass
   counts feed F5's `test_completeness` merge directly.) Exact pass counts
   for each root are recorded in `result.json.tests_passed`/`tests_total`
   and in F5's `iterate_latest` block, not duplicated here to avoid the
   double-bookkeeping openai's round-2 review flagged.

10. `uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py
    --project-root . --phase build --run-id iterate-2026-09-12-t5-deploy-changelog`
    — regenerated `.shipwright/compliance/test-traceability.json` from the
    FINAL tree (after all Step 3.5 fixes) before touching the AC baseline.
11. `uv run shared/scripts/tools/check_ac_coverage_ratchet.py --project-root .
    --write` → `unbound_count: 129` (from 152) — 23 FR-01.08/FR-01.09 entries
    resolved (22 in the original pass + 1 more, FR-01.09/AC11, bound during
    Step 3.5 review), 7 excepted with recorded reason. Verified directly
    (read back from the regenerated `shipwright_ac_coverage_baseline.json`):
    ```
    FR-01.08 remaining unbound: AC02, AC05, AC08, AC11, AC12
    FR-01.09 remaining unbound: AC01, AC15
    ```
    — exactly the seven exceptions named in the per-AC tables above and no
    other FR-01.08/FR-01.09 entry (this is the corrected, final count; the
    mini-plan's earlier "eight exceptions" text described the state before
    Step 3.5's AC11 fix and has been updated throughout).
12. `git checkout -- .shipwright/compliance/{change-history.md,ci-security.json,
    dashboard.md,sbom.md,test-evidence.md,test-traceability.json,
    traceability-matrix.md} shipwright_compliance_config.json` — reverted the
    compliance-report regen sweep (step 10) after it had done its one job,
    per t1/t3/t4 precedent. Verified via `git status --short` afterward: only
    the test files, two `pyproject.toml` marker registrations, the AC
    coverage baseline, and (below) the bloat baseline remained modified.
13. `uvx ruff@0.15.15 check plugins/shipwright-deploy/tests
    plugins/shipwright-changelog/tests shared/tests shared/scripts/tools/tests` —
    clean.
14. Downstream-consumer check (t4 precedent, external plan review, glm):
    `grep -rln "pytest.mark.covers\|fr_tag_grammar" shared/scripts/tools/verifiers
    shared/scripts/lib plugins/shipwright-compliance/scripts` — every consumer
    of `@covers` tags routes through `fr_tag_grammar.parse_python`, which
    already treats a bare→qualified upgrade as backward-compatible (P3.2). No
    downstream tool special-cases a bare tag differently in a way this
    sweep could regress.

## External-Plan-Review-Findings

Step 3.5, Branch A (`available`). Both providers reviewed the mini-plan
against the spec; `verdicts: glm=approve, openai=revise` (not a contradiction
— one step apart). All medium/high findings dispositioned below; the fixes
described are already reflected in the per-AC tables above and were
re-verified (see Verification performed).

| # | Provider | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | high | Verification commands omitted `--junitxml`, and "merged by hand" is not a reproducible artifact flow. | **accepted-and-fixed** — re-ran all four roots with `--junitxml`, one process each, output paths recorded under Verification performed. |
| 2 | glm + openai | medium | FR-01.09/AC11 ("publishes nothing by itself") was excepted as an unprovable absence-of-behavior, but this campaign's own seam already proves absences via fail-if-called spies / byte-identity dry-run checks — the reasoning was too broad. | **accepted-and-fixed** — added `test_aggregation_never_shells_out_to_git_or_gh` (fail-if-called `subprocess` spy around a full `aggregate()` run); AC11 is now bound, not excepted. |
| 3 | openai | medium | FR-01.08/AC15's citations proved drift *refusal* (a rollback that never ran), not that a *completed* rollback leaves data untouched. | **accepted-and-fixed** — re-bound to `test_acknowledging_the_drift_proceeds` (completed rollback, `data_drift.drifted` still `True` afterward) + `test_a_target_whose_data_never_moves_skips_the_question` (module never mutates data; target's own strategy answers the question). |
| 4 | openai | medium | FR-01.08/AC09 was bound only to the 3 real profiles validating (positive case); no test proved an *invalid* rollback declaration is rejected before a target is offered. | **accepted-and-fixed** — added `test_missing_rollback_block_fails` (deletes the `rollback` block from a real profile, asserts the schema rejects it). |
| 5 | openai | medium | The 4th root's operator ratification is pending; if rejected, the baseline/bindings need rollback together. | **rejected-with-reason** — this is exactly the flagged-deviation status already stated in "Root count — 3, waived" above; it is the orchestrator's/operator's decision to make, not something this unit can pre-resolve, and re-stating it as a new finding does not change the disposition already on record. |
| 6 | glm | low | The AC01 pair (release-path test + static profile-directory test) looked like a partial-clause binding. | **rejected-with-reason** — re-read against the spec text (quoted in the mini-plan): AC01 is itself a two-clause AC ("put onto target and made to run" + "more than one kind can be configured, not tied to a single company"); the two tests correctly cover the two clauses together, which is the campaign's own established multi-test-per-AC pattern, not the single-clause partial-proof defect. |
| 7 | glm | low | Reverting compliance reports after the baseline write might orphan the four `--junitxml` outputs. | **rejected-with-reason** — the JUnit XML files are transient CI/local artifacts, never committed (same as every other sub-iterate in this campaign); they are not compliance-report inputs the revert step touches, and the counts they report are what feeds F5's `test_completeness` directly, not the reverted `.shipwright/compliance/*` files. |
| 8 | glm | low | `test_sync_release_manifests_git.py` was trimmed to exactly 300 LOC — the next docstring addition there will trip the hook. | **rejected-with-reason** (deferred, not a defect in this diff) — correct observation, but fixing it would mean touching that file beyond this unit's AC-binding scope (adding a baseline entry or restructuring it), which is out of scope per the "touch only files required by AC-binding work" instruction; noted here for a future unit that touches that file again. |
| 9 | glm | low | Confirm the two `pyproject.toml` diffs are pure `covers`-marker additions. | **accepted (no fix needed)** — confirmed via `git diff HEAD -- plugins/shipwright-deploy/pyproject.toml plugins/shipwright-changelog/pyproject.toml`: each diff is a single added line in the `markers` list, nothing renamed or removed; both plugins' full suites (104 + 89 tests) still collect and pass. |

### External-Plan-Review, round 2 (re-run against the fixed mini-plan)

Re-reviewing after round-1 fixes landed surfaced two real issues (both fixed)
plus confirmation of round 1's remaining items. `verdicts: glm=approve,
openai=revise` again (one step apart, not a contradiction).

| # | Provider | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | high | AC accounting was internally inconsistent — the Verification section still said "eight exceptions" and `130` after the mini-plan text elsewhere said AC11 was now bound. | **accepted-and-fixed** — re-ran `update_compliance.py` (build phase) then `check_ac_coverage_ratchet.py --write` against the final tree; corrected count is `129` (was `152`), 7 exceptions (not 8), and the Verification section above now states the final numbers only, with the interim numbers explicitly marked historical. |
| 2 | glm + openai | medium | The AC11 spy only patched `subprocess.run/Popen/check_call/check_output` — a regression via `subprocess.call`, `os.system`, or `os.popen` would not trip it. | **accepted-and-fixed** — added `subprocess.call`, `os.system`, `os.popen` to the patched set; docstring rewritten to state the guarantee honestly ("does not invoke any of Python's stdlib process-launch primitives", not "does not shell out" unconditionally — a dedicated non-stdlib client library is explicitly out of scope, and none exists in this codebase's changelog tooling today). |
| 3 | openai + glm | medium/dependency | Fourth-root ratification still pending. | **rejected-with-reason (repeat)** — unchanged from round 1's disposition #5; this is the orchestrator's/operator's call, already flagged prominently in "Root count" above and in `result.json`. |
| 4 | glm | low | `test_missing_rollback_block_fails` might mutate the real shipped profile file if it doesn't copy first. | **rejected-with-reason** — verified directly: `jelastic_profile` is a function-scoped fixture returning a fresh `json.loads()` per test, and the test itself does `copy.deepcopy(jelastic_profile)` before `del broken["rollback"]` — never writes back to `shared/profiles/deploy/jelastic.json`. No mutation risk exists. |
| 5 | openai | low | Plan said "two new test functions," inconsistent with the two more added for AC09/AC11 during review. | **accepted-and-fixed** — "No new test harness" section rewritten to enumerate all four new test functions by file and by which review round added them. |
| 6 | glm | low | AC02/AC05 (deploy) have zero automated coverage of any kind — a real product gap, not something this backfill can fix. | **acknowledged, out of scope** — correct observation; recorded as a candidate follow-up in F3a (reflection), not actioned in this unit (would require new production code — a `--confirm-failed-tests` flag or a coded smoke-failure→rollback trigger — which is out of this unit's test-backfill scope). |
| 7 | glm | low | Bloat-baseline `current` bumps compound across sub-iterates with no forcing function to split the files. | **acknowledged, out of scope** — valid systemic observation about the campaign's own tooling, not a defect in this diff; not actioned here. |

## Self-Review (Step 3.6, always runs)

1. **Spec Compliance** — PASS. Every bound test cites the exact spec AC text
   (quoted inline in the per-AC tables); every unbound AC has a reason tied to
   a concrete production module, not a convenience skip.
2. **Error Handling** — PASS (N/A for production code — this unit adds no
   production code paths). The one new production-adjacent surface, the
   `subprocess`-spy test, correctly distinguishes "no call made" from "call
   made and happened to succeed," which is the actual failure mode it guards.
3. **Security Basics** — PASS. No secrets, no credentials, no new inputs
   trusted; the spy test does not weaken any existing validation.
4. **Test Quality** — PASS. Every new/edited test was run and confirmed
   passing (104 + 89 + full `shared/tests` + full `shared/scripts/tools/tests`,
   see Verification performed); no test was accepted on the strength of the
   AC text alone without checking it against the actual production code path
   (this unit's own stated discipline; see Approach's two rejected near-misses
   plus the three post-review re-bindings).
5. **Performance Basics** — PASS (N/A). Test-only diff; no runtime hot path
   touched. The one new production-adjacent read (`subprocess` monkeypatch)
   is scoped to the single test via `monkeypatch`, auto-reverted per test.
6. **Naming & Structure** — PASS. New test names describe the AC's observable
   behavior (`test_aggregation_never_shells_out_to_git_or_gh`,
   `test_missing_rollback_block_fails`), matching this suite's existing
   naming convention; no new file, no new fixture pattern.
7. **Affected Boundaries (ADR-024)** — PASS. Two serialized-format boundaries
   are touched by this unit's own new/upgraded tests: (a) the deploy profile
   JSON schema (producer: `shared/profiles/deploy/*.json` authors; consumer:
   `deploy_profile_validator.py` + every module reading `rollback`/`smoke_test`
   blocks) — round-trip probed directly by `test_missing_rollback_block_fails`
   (a structurally-broken producer output is rejected by the consumer-side
   validator); (b) the two manifest formats (`package_json`,
   `marketplace_json`) in `manifest_sync_core.py` — round-trip probed by the
   pre-existing `test_sync_marketplace_manifest_bumps_root_and_nested_entries`
   this unit bound to AC13 (write via `sync()`, read back via `json.loads`,
   asserting every nested occurrence matches). No new serialized format was
   introduced by this unit.

`reviews.self_review`: all 7 items passed, 0 failed.

## Internal Review Cascade (Step 3.7)

Trigger conditions met: diff > 100 LOC (well over — 213+ LOC at Step 3.4,
larger now after the post-review fixes) AND `touches_build` risk flag set.
Cascade fires.

1. **Internal reviewer cascade** (`spec-reviewer` → `code-reviewer` →
   `doubt-reviewer`) — this runner has no `Agent` tool and cannot spawn them.
   Recorded `not_run` / `delegated_to_orchestrator` for `spec`, `code`,
   `doubt`; the orchestrator runs the real cascade at campaign-mode.md
   3f-bis before merge, per the runner contract's explicit note that this is
   a fact about this subagent, not about iterates.
2. **External LLM code review** — run against the full working-tree diff
   (`git diff HEAD`; no interim commit exists yet, same as t4's precedent).
   `verdicts: glm=revise, openai=revise` (agreement, not a contradiction).

### External-Code-Review-Findings

| # | Provider | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | glm | medium | The seven recorded reasons for unbound ACs live only in this mini-plan, not in `shipwright_ac_coverage_baseline.json` itself — a reader of the baseline alone can't see why. | **rejected-with-reason** — this is exactly Finding 5 of the campaign's own t0 seam survey: schema_version 1 has no field for recording a reason; the mini-plan/decision-drop is the only place it can live today. Not a defect introduced by this unit. |
| 2 | glm | medium | Bloat-baseline `current` for `test_changelog_aggregation.py` (362 at review time) didn't match the mini-plan's stated final size (356). | **accepted-and-fixed** — the file grew again after this same review round's own finding #3 fix (positive-control assertion); baseline now reads 377, matching `wc -l` exactly, and the mini-plan's bloat table now shows all four passes explicitly so the numbers can't drift apart silently again. |
| 3 | glm | medium | The AC11 subprocess/os spy only catches module-attribute call sites; a `from subprocess import run` binding taken before the patch would bypass it silently. | **accepted-and-fixed** — verified directly (grepped `aggregate_changelog.py` and its full import chain: `changelog_splice`, `changelog_sections`, `write_changelog_drop`, `atomic_write`, `file_lock`) that none of them import `subprocess`/`os.system`/`os.popen` in any form, so no such binding exists to bypass; added this verification to the test's own docstring plus a positive-control assertion (`pytest.raises` on the patched functions before the real call) so a future refactor that broke the patch target would fail loudly instead of silently passing. |
| 4 | openai | medium | The AC01 release-path test never inspected the request body — a hard-coded/wrong ref would still pass. | **accepted-and-fixed** — captured `request.data` per call and asserted the `createproject` call body carries the actual requested repo URL and branch (changed the fixture to use distinctive non-default values so a hard-coded ref could not coincidentally match). |
| 5 | openai | medium | The AC01 target-kind test only counts static `target_kind` values; it doesn't prove the deploy path actually dispatches to the selected target. | **rejected-with-reason** — verified there is no runtime target-selection dispatcher in this codebase to exercise: `vercel.json`/`compose-vps.json` both declare `implementation_status: stub`, and `JelasticClient` is the only implemented client. AC01's own text says "can be *configured*," not "is dispatched at runtime" — the configurability claim is what's bound; a dispatch test would be testing code that doesn't exist yet. Added this to the test's docstring. |
| 6 | glm + openai | medium | The AC15 rollback test has no data-tier mutation spy — a rollback that mutated stored data while leaving `data_drift.drifted` unchanged would still pass. | **rejected-with-reason** — verified `rollback.py`'s complete import list (`data_drift`, `rollback_report`, `deploy_profile` — no database/migration-execution client at all); there is no runtime call to spy on because the guarantee is architectural (no data-tier client exists in this code path), not decision-based. A mutation spy would require inventing a new production-code seam (a data-tier dependency injection point) that doesn't exist today — out of scope for a test-backfill unit. Re-read against the AC's own wording: the testable clause is "nobody assumes the data went back too" — a *reporting* guarantee, which `data_drift.drifted is True` persisting after completion directly proves. Rewrote the test's docstring to state this precisely rather than imply a stronger, unachievable guarantee. |
| 7 | glm | low | The AC01 release test's exact-sequence assertion (`endpoints == ["update", "createproject", "update"]`) over-constrains to today's call order; a functionally-equivalent reorder would fail the test even though the AC doesn't require this specific order. | **acknowledged, not changed** — correct observation; left as-is because the exact order IS part of `deploy_from_git`'s actual documented behavior ("First creates a VCS project if needed, then updates" — its own docstring), so pinning it is intentional, not incidental; a deliberate future reorder should indeed touch this test consciously, which is the point. |
| 8 | glm | low | The fourth-root ratification is still pending; rejecting the finding doesn't remove the dependency. | **rejected-with-reason (repeat)** — unchanged from round 1/round 2 disposition; operator/orchestrator call, already flagged prominently. |

`reviews.external_code`: `completed`, provider `openrouter`+`codex` (both
legs), 12 findings total across both providers, all dispositioned above.

### Post-PR fixes (PR #747)

Two independently-verifiable changes were made to the pushed diff after PR
creation; a maintainer should confirm both against the current code rather
than take this note as settling either:

1. `shared/tests/test_changelog_aggregation.py` — removed a direct
   `os.system("true")` positive-control call in
   `test_aggregation_never_shells_out_to_git_or_gh` (flagged as a dangerous
   pattern even though monkeypatched to a no-op); the existing
   `subprocess.run(["true"])` positive control remains.
2. `plugins/shipwright-deploy/tests/test_rollback.py` —
   `test_completed_rollback_touches_no_data_tier_capability` replaces an
   earlier, weaker AC15 test that only scanned `rollback.py`'s static
   imports against a denylist of known database packages (gameable by an
   unlisted client, a dynamic import, or reuse of an already-imported
   module). The new test monkeypatches `subprocess.*`, `os.system`,
   `os.popen`, `socket.socket`, and `socket.create_connection` to
   fail-if-called (with a positive control proving the spies actually
   fire), then completes a real rollback through the fake hosting client
   fixture — verifiable directly by reading the test and running it.

## Confidence Calibration (Step 3.8)

Does not fire: effective complexity is `small` (Step 3.4), and the only risk
flag set is `touches_build` — `touches_io_boundary` is not set. No
calibration probe was invoked ad hoc. `reviews.confidence_calibration`:
`skipped_complexity_and_no_io_boundary`, 0 probes run.

(Note: this unit's own binding discipline — verifying each test would
actually fail against the AC's described regression before binding it — is
the Self-Review's Test Quality item, not a substitute for this step; the two
serve different gates and neither was skipped in place of the other.)

## Reflection (F3a)

- **Reusable pattern**: a fail-if-called spy on every stdlib process-launch
  primitive (`subprocess.run/Popen/call/check_call/check_output`,
  `os.system`/`os.popen`), wrapped around a full end-to-end call, is a valid
  way to bind an "absence of behavior" AC that this campaign had previously
  been treating as categorically unprovable — but only after grepping the
  full call chain for an import-time `from X import Y` binding the patch
  cannot see, and only with a positive-control assertion proving the spy is
  actually reachable. Recorded as a one-line Learning in `conventions.md`.
- **Gotcha**: the schema-driven `TestRealProfilesAreValid` pattern (asserting
  the 3 real shipped profiles validate) proves a positive-only claim; an AC
  phrased as "checked against a common shape" also needs its negative case
  (a deliberately broken profile is rejected) to prove the schema is doing
  real work, not just agreeing with already-correct files.
- **Product gap surfaced, not fixed**: FR-01.08/AC02 (refuse a release on
  failing tests) and AC05 (auto-rollback on smoke failure) are both pure
  SKILL.md agent prose with no coded gate — filed as `trg-7a6a9562` (F3a
  follow-up rule: genuine, deferrable, distinct from this unit's own work).
- **No F2 architecture.md impact**: `--architecture-impact none` — this unit
  added/upgraded test-only bindings; no new route, component, schema,
  service, write/read surface, or convention was introduced.

## Bloat baseline (F6 pre-commit hook)

Two files crossed their `grandfathered` (`state: grandfathered`, `adr: null`)
LOC baseline as a direct result of the new/upgraded `@pytest.mark.covers`
tags and their doc-comments added in this unit — each file was measured
EXACTLY at its baseline `current` before this unit's edits (confirmed via
`git show HEAD:<path> | wc -l`), so every added line is this unit's own
legitimate growth, not pre-existing debt resurfacing. A THIRD bump to both
files followed the Step 3.5 external-review fixes (the new AC11 spy test
landed in `test_changelog_aggregation.py`; the new AC09 negative case landed
in `test_validate_deploy_profile.py`). Bumped `current` for both (no ADR
needed — that gate applies to `state: exception` entries, not
`grandfathered`; precedent: t4's PR #744 bumped four `grandfathered` entries
the same way for the same reason):

| File | Before (start of unit) | After first pass | After plan-review fixes | After code-review fixes |
|---|---|---|---|---|
| `shared/tests/test_changelog_aggregation.py` | 325 | 332 | 362 | 377 |
| `shared/tests/tools/test_validate_deploy_profile.py` | 371 | 379 | 391 | 391 |

(`test_changelog_aggregation.py`'s growth across all three passes is entirely
the AC11 spy test — widened at plan review to cover `os.system`/`os.popen`,
then widened again at code review to add a positive-control assertion and a
docstring naming which import forms it cannot see. `test_jelastic_client.py`
and `test_rollback_e2e_cli.py` also grew during code-review fixes — 218 and
297 lines respectively — both still comfortably under 300, no new baseline
entry needed.)

No file NOT already in the baseline crossed 300 lines; the closest,
`shared/scripts/tools/tests/test_sync_release_manifests_git.py`, was trimmed
back to exactly 300 (the limit, not over it) by shortening two added
docstrings.
