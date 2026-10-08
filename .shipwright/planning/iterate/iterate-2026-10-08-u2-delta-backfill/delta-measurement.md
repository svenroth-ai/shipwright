# U2 delta backfill: measurement and outcome

Run-ID: iterate-2026-10-08-u2-delta-backfill (campaign 2026-10-07-finalization-claims-hardening, unit U2)

## Measurement (step 1)

Method: production collector (`_layer_coverage_regen._build`) run on the tree archived at 8daa50b22 (last main commit before 2026-09-17) and on HEAD (1b3204b21); delta = head `untagged_tests` ids not present in base `untagged_tests`. Renames reconciled: `git diff -M` between the two SHAs shows 0 renamed files among the delta's files, and only 15 delta ids share a test name with a base untagged test (in different files, so new definitions), so 1,440 is exact for practical purposes, not an inflated upper bound.

| Quantity | Base 2026-09-16 | HEAD 2026-10-08 |
|---|---|---|
| untagged tests | 15,546 | 16,969 |
| invalid_tags | 0 | 0 |

Untagged tests added since 2026-09-16: **1440** in **160** files.

| Test root | Untagged added |
|---|---|
| shared/tests | 983 |
| shared/scripts/tools/tests | 243 |
| plugins/shipwright-iterate/tests | 166 |
| integration-tests | 20 |
| plugins/shipwright-adopt/tests | 17 |
| plugins/shipwright-compliance/tests | 7 |
| plugins/shipwright-build/tests | 2 |
| plugins/shipwright-project/tests | 2 |

## Engine results (steps 2-3)

- `backfill_test_links.py --dry-run` (all 12 test roots, 18,085 tests scanned): **auto_written 0**, proposals 14 (all `commit_set` confidence 0.4 fanning to 4-21 FRs, so not high-confidence), orphans: 13 confirmed + 1 possible, all in deliberately tag-bearing `fixtures/` trees (not real orphans), unmapped 16,987.
- `backfill_ac_provenance.py --write` (mechanical Run-ID -> added-test-file join): 6 candidate files overlapping the delta (FR-01.11 AC30/AC31), **0 tags written**: the tool declines 6x `ambiguous_multiple_untagged_tests_in_file` and 2x `ambiguous_multiple_bare_tags_same_fr`. No file changed.
- Bloat: no test file was edited, so no file crossed its cap and no exception ADR is needed. The delta files at or over their cap are listed in the next section (derived from the delta, not from examples).
- Counting unit: test definitions (function-level ids, as the collector reports them), not collected pytest cases. Baseline SHA 8daa50b22, HEAD SHA 1b3204b21.
- Result: the deterministic engines find no high-confidence tag for any of the delta. Hand-mapping 1,440 tests to FRs would be guessing; per the unit contract the rest goes to ONE triage card. Nothing is deleted.

## Manifest regenerates clean (step 4)

`_layer_coverage_regen.regenerate_base_head(project_root, HEAD, with_evidence=False)` run on HEAD 1b3204b21 (the commit this unit branches from; the unit adds only docs and a triage card, no test or spec file): exit 0, returned base and head manifests, `invalid_tags: []` for both, 16,969 untagged at head (equal to the measurement above). The regeneration is re-run on the final unit commit before the handback.

## Delta files in `shipwright_bloat_baseline.json` (at or over their cap)

Derived from the 160-file delta table below crossed with the baseline (6 files). Adding a decorator line to any of these needs a same-line tag or an exception ADR; a delta file absent from the baseline is under its cap. This is the list the later tag backfill (trg-067e08fa) must plan around.

| File | Untagged added | current / limit | state | ADR / plan |
|---|---|---|---|---|
| shared/scripts/tools/tests/test_codex_hooks_sync.py | 10 | 323 / 300 | grandfathered | - |
| shared/tests/test_campaign_graph.py | 36 | 325 / 300 | exception | ADR-pending: .shipwright/planning/adr/iterate-2026-09-21-r1-depends-on-schema-test-campaign-graph-bloat.md |
| shared/tests/test_campaign_step_3f_bis.py | 28 | 1079 / 300 | exception | ADR-pending: .shipwright/planning/adr/iterate-2026-09-22-r3-review-diff-fix-test-3f-bis-bloat-exception.md |
| shared/tests/test_review_attribution.py | 35 | 640 / 300 | exception | ADR-pending: .shipwright/planning/adr/iterate-2026-09-22-r3-review-diff-fix-test-review-attribution-bloat-exception.md |
| shared/tests/test_review_marker_companion_verdicts.py | 3 | 311 / 300 | grandfathered | - |
| shared/tests/test_test_gate_e2e_specs_generated.py | 16 | 340 / 300 | grandfathered | - |

## Untagged delta by file (for the triage card)

| File | Untagged added |
|---|---|
| integration-tests/test_codex_bundle_hook_root_composition.py | 1 |
| integration-tests/test_codex_review_dispatch_sites_present.py | 11 |
| integration-tests/test_external_review_driver_prose_contract.py | 6 |
| integration-tests/test_external_review_key_consistency_contract.py | 2 |
| plugins/shipwright-adopt/tests/test_agents_md_renderer.py | 15 |
| plugins/shipwright-adopt/tests/test_review_runner_driver.py | 2 |
| plugins/shipwright-build/tests/test_cleanup_review_scratch_on_code_reviewer_failure.py | 2 |
| plugins/shipwright-compliance/tests/test_audit_honors_amendments.py | 1 |
| plugins/shipwright-compliance/tests/test_evidence_resume_tag.py | 6 |
| plugins/shipwright-iterate/tests/test_campaign_init_depends_on.py | 17 |
| plugins/shipwright-iterate/tests/test_codex_hooks_ac0_combined.py | 2 |
| plugins/shipwright-iterate/tests/test_codex_hooks_noop_under_claude.py | 12 |
| plugins/shipwright-iterate/tests/test_codex_hooks_project_root_guards.py | 2 |
| plugins/shipwright-iterate/tests/test_codex_pretooluse_denial.py | 13 |
| plugins/shipwright-iterate/tests/test_codex_pretooluse_matcher.py | 31 |
| plugins/shipwright-iterate/tests/test_codex_pretooluse_tokenization.py | 16 |
| plugins/shipwright-iterate/tests/test_iterate_worktree_gate.py | 21 |
| plugins/shipwright-iterate/tests/test_iterate_worktree_gate_hardening.py | 10 |
| plugins/shipwright-iterate/tests/test_iterate_worktree_gate_lifecycle.py | 22 |
| plugins/shipwright-iterate/tests/test_skill_references_link.py | 1 |
| plugins/shipwright-iterate/tests/test_sub_iterate_runner_architecture_review.py | 19 |
| plugins/shipwright-project/tests/test_write_project_config_artifacts.py | 2 |
| shared/scripts/tools/tests/test_build_codex_plugin.py | 6 |
| shared/scripts/tools/tests/test_build_codex_plugin_safety.py | 13 |
| shared/scripts/tools/tests/test_check_ac_ratchet_f0.py | 18 |
| shared/scripts/tools/tests/test_codex_activation_helper.py | 11 |
| shared/scripts/tools/tests/test_codex_activation_helper_guards.py | 18 |
| shared/scripts/tools/tests/test_codex_hook_inventory_runtime_scope.py | 4 |
| shared/scripts/tools/tests/test_codex_hook_merge.py | 6 |
| shared/scripts/tools/tests/test_codex_hook_merge_ordering.py | 3 |
| shared/scripts/tools/tests/test_codex_hooks_launcher_direct.py | 12 |
| shared/scripts/tools/tests/test_codex_hooks_sync.py | 10 |
| shared/scripts/tools/tests/test_codex_hooks_sync_confirm.py | 6 |
| shared/scripts/tools/tests/test_codex_hooks_sync_direct.py | 13 |
| shared/scripts/tools/tests/test_codex_hooks_sync_errors.py | 8 |
| shared/scripts/tools/tests/test_f0_failed_only_real_pytest.py | 4 |
| shared/scripts/tools/tests/test_f0_resume_real_pytest.py | 3 |
| shared/scripts/tools/tests/test_run_test_suite_basetemp.py | 3 |
| shared/scripts/tools/tests/test_stage_f0_evidence_resumed.py | 7 |
| shared/scripts/tools/tests/test_suite_failed_only.py | 16 |
| shared/scripts/tools/tests/test_suite_resume.py | 13 |
| shared/scripts/tools/tests/test_suite_resume_exec.py | 15 |
| shared/scripts/tools/tests/test_suite_resume_report.py | 13 |
| shared/scripts/tools/tests/test_suite_resume_state.py | 19 |
| shared/scripts/tools/tests/test_suite_retry.py | 18 |
| shared/scripts/tools/tests/test_verify_codex_plugin_bundle.py | 4 |
| shared/tests/test_agents_md_claude_md_parity.py | 5 |
| shared/tests/test_agents_md_completion_check.py | 8 |
| shared/tests/test_agents_md_greenfield_scaffolding.py | 2 |
| shared/tests/test_architecture_internal_review_contract_prose.py | 16 |
| shared/tests/test_architecture_review_anchoring_defense.py | 2 |
| shared/tests/test_architecture_review_fence_masking.py | 10 |
| shared/tests/test_audit_compliance_on_stop.py | 1 |
| shared/tests/test_audit_compliance_on_stop_wiring.py | 2 |
| shared/tests/test_audit_phase_quality_stop_hook_direct.py | 1 |
| shared/tests/test_automerge_readiness.py | 1 |
| shared/tests/test_autonomous_loop_depends_on.py | 7 |
| shared/tests/test_autonomous_loop_finalize_record_compat.py | 4 |
| shared/tests/test_autonomous_loop_lease_reconcile.py | 5 |
| shared/tests/test_autonomous_loop_record_runs_dir_safety.py | 3 |
| shared/tests/test_autonomous_loop_section_full_cycle.py | 1 |
| shared/tests/test_campaign_dag_integration.py | 3 |
| shared/tests/test_campaign_dag_scheduler_integration.py | 1 |
| shared/tests/test_campaign_drain.py | 18 |
| shared/tests/test_campaign_drain_cli.py | 5 |
| shared/tests/test_campaign_graph.py | 36 |
| shared/tests/test_campaign_r5b_merge_lane_prose.py | 17 |
| shared/tests/test_campaign_r5b_merge_lane_prose_drain.py | 7 |
| shared/tests/test_campaign_r5b_merge_lane_prose_finalize.py | 7 |
| shared/tests/test_campaign_r5b_merge_lane_prose_rebase_guard.py | 3 |
| shared/tests/test_campaign_r5b_merge_lane_prose_review_fixes.py | 9 |
| shared/tests/test_campaign_status_depends_on.py | 16 |
| shared/tests/test_campaign_step_3f_bis.py | 28 |
| shared/tests/test_campaign_unit_worktree.py | 22 |
| shared/tests/test_campaign_wave.py | 23 |
| shared/tests/test_campaign_wave_serialization_prose.py | 6 |
| shared/tests/test_capture_session_id.py | 1 |
| shared/tests/test_check_required_checks_cli.py | 1 |
| shared/tests/test_check_review_attribution.py | 8 |
| shared/tests/test_check_review_attribution_composition.py | 1 |
| shared/tests/test_check_review_attribution_invalidate.py | 9 |
| shared/tests/test_check_unit_attempt.py | 7 |
| shared/tests/test_check_unit_lease.py | 6 |
| shared/tests/test_cmd_finalize_lock_race.py | 5 |
| shared/tests/test_codex_activation_record.py | 21 |
| shared/tests/test_codex_activation_record_consume.py | 7 |
| shared/tests/test_codex_activation_record_validation.py | 8 |
| shared/tests/test_codex_envelope_grammar.py | 15 |
| shared/tests/test_codex_review_model_resolution.py | 12 |
| shared/tests/test_codex_review_prompt.py | 7 |
| shared/tests/test_codex_review_schemas_typed.py | 1 |
| shared/tests/test_codex_review_transport.py | 16 |
| shared/tests/test_codex_review_transport_model_override.py | 6 |
| shared/tests/test_codex_review_transport_reasoning_effort.py | 9 |
| shared/tests/test_codex_runtime.py | 10 |
| shared/tests/test_condense_release_notes.py | 1 |
| shared/tests/test_derived_snapshots_wave_concurrency.py | 3 |
| shared/tests/test_ensure_shared_cache_vendored_reverse.py | 1 |
| shared/tests/test_external_review_driver.py | 5 |
| shared/tests/test_external_review_driver_enforcement.py | 10 |
| shared/tests/test_external_review_opus_leg.py | 15 |
| shared/tests/test_external_review_opus_leg_dispatch.py | 12 |
| shared/tests/test_generate_handoff_cache_race_retry.py | 7 |
| shared/tests/test_held_merge_reconciliation.py | 16 |
| shared/tests/test_held_merge_reconciliation_cli.py | 13 |
| shared/tests/test_hooks_pep723_isolation.py | 7 |
| shared/tests/test_hooks_uv_run_pinned.py | 3 |
| shared/tests/test_hooks_uv_run_project_isolation.py | 2 |
| shared/tests/test_llm_review_driver_codex.py | 6 |
| shared/tests/test_loop_claim.py | 13 |
| shared/tests/test_loop_claim_concurrency_integration.py | 3 |
| shared/tests/test_loop_claim_load_state_retry.py | 8 |
| shared/tests/test_loop_claim_mark_dispatch.py | 2 |
| shared/tests/test_loop_claim_next_batch.py | 14 |
| shared/tests/test_loop_claim_release_cleanup.py | 16 |
| shared/tests/test_loop_mark.py | 21 |
| shared/tests/test_loop_readiness.py | 13 |
| shared/tests/test_loop_state.py | 31 |
| shared/tests/test_loop_state_fencing.py | 21 |
| shared/tests/test_loop_state_init_reconcile.py | 10 |
| shared/tests/test_loop_state_transitions.py | 21 |
| shared/tests/test_loop_state_v1_compat.py | 4 |
| shared/tests/test_marketplace_atomic_sync_dir.py | 8 |
| shared/tests/test_marketplace_excludes_python_version.py | 2 |
| shared/tests/test_marketplace_lock_guards.py | 8 |
| shared/tests/test_marketplace_lock_ownership.py | 5 |
| shared/tests/test_marketplace_lock_reclaim_paths.py | 2 |
| shared/tests/test_marketplace_orphan_recovery.py | 3 |
| shared/tests/test_marketplace_sync_lock.py | 8 |
| shared/tests/test_model_pricing.py | 2 |
| shared/tests/test_model_tier_config_codex_and_fable.py | 12 |
| shared/tests/test_phase_quality_newest_run_per_phase.py | 11 |
| shared/tests/test_plan_gate_extras.py | 1 |
| shared/tests/test_plugin_root.py | 8 |
| shared/tests/test_pointer_run_id_wave_collision.py | 2 |
| shared/tests/test_prepare_architecture_internal_spec.py | 11 |
| shared/tests/test_project_root.py | 6 |
| shared/tests/test_r2_worktree_capability_integration.py | 10 |
| shared/tests/test_r2_worktree_capability_prose.py | 3 |
| shared/tests/test_r3_review_diff_fix_integration.py | 2 |
| shared/tests/test_rebase_cascade.py | 17 |
| shared/tests/test_record_review_pass_transport.py | 6 |
| shared/tests/test_required_checks_drift.py | 8 |
| shared/tests/test_resolve_run_id_pointer_composition.py | 1 |
| shared/tests/test_resumed_evidence_provenance.py | 5 |
| shared/tests/test_review_attribution.py | 35 |
| shared/tests/test_review_attribution_probes.py | 11 |
| shared/tests/test_review_marker_companion_verdicts.py | 3 |
| shared/tests/test_review_record_model_tier_floor.py | 4 |
| shared/tests/test_review_record_transport.py | 7 |
| shared/tests/test_review_via_codex_cli.py | 11 |
| shared/tests/test_review_via_codex_model_resolution.py | 6 |
| shared/tests/test_rollout_resolution.py | 14 |
| shared/tests/test_setup_unit_worktree.py | 8 |
| shared/tests/test_test_gate_e2e_specs_generated.py | 16 |
| shared/tests/test_tier_literal_drift.py | 1 |
| shared/tests/test_unit_lease.py | 17 |
| shared/tests/test_unit_lease_conflict_and_worktree.py | 6 |
| shared/tests/test_wave_launch_failure_and_reconcile.py | 3 |
| shared/tests/test_write_terminal_marker_wave_sentinel.py | 3 |

## Cross-check of the zero (plan-review finding)

The engines did process the delta: all 1,440 delta test ids appear in the dry-run report's `unmapped` list (0 in `proposals`, 0 missing; the 14 proposals are all pre-existing tests in `plugins/shipwright-iterate/tests/test_hooks_json_registration.py` and `shared/tests/test_hooks_json_quoting.py`, none of them in the delta), the run scanned 18,085 tests and honoured 1,070 existing tags, so "0 auto-written" is a real zero, not an engine that failed to run. The unit contract allows hand-mapping only where deterministic; none qualified.
