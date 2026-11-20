# R0a survey inventory (companion to section 11 of the root-files BRIEF)

Run `iterate-2026-11-20-r0a-survey`, tree `origin/main` at `be981a42b`. Machine-derived from the AST and token passes described in BRIEF 11.0; the read/write hint (R, W, RW, -) is a function-level regex, NOT dataflow. Treat it as a starting checklist for the R0b guard, not as an allowlist. Message text and docstrings are excluded; `(collection)` = the string sits inside a tuple/list/set/dict; `(path-join)` = `root / "name"`.

Base commit: `origin/main` `be981a42b`. Dated snapshot; the generator scripts were throwaway and are not checked in. To re-check at a later base run `git grep -n "shipwright_[a-z_]*\.\(json\|yaml\|lock\)" -- plugins shared scripts .github integration-tests` and diff the file set against this file.

## A. Python sites (non-test): file, line, basename token, class, enclosing function, R/W hint

```
plugins/shipwright-adopt/scripts/checks/setup_adopt.py:91 | shipwright_sync_config.json | literal(collection) | <module> | -
plugins/shipwright-adopt/scripts/checks/setup_adopt.py:92 | shipwright_project_config.json | literal(collection) | <module> | -
plugins/shipwright-adopt/scripts/checks/setup_adopt.py:93 | shipwright_plan_config.json | literal(collection) | <module> | -
plugins/shipwright-adopt/scripts/checks/setup_adopt.py:94 | shipwright_build_config.json | literal(collection) | <module> | -
plugins/shipwright-adopt/scripts/checks/setup_adopt.py:95 | shipwright_compliance_config.json | literal(collection) | <module> | -
plugins/shipwright-adopt/scripts/checks/setup_adopt.py:143 | shipwright_run_config.json | literal(path-join) | run_preflight | R
plugins/shipwright-adopt/scripts/checks/validate_adoption.py:57 | shipwright_run_config.json | literal(collection) | <module> | -
plugins/shipwright-adopt/scripts/checks/validate_adoption.py:58 | shipwright_project_config.json | literal(collection) | <module> | -
plugins/shipwright-adopt/scripts/checks/validate_adoption.py:59 | shipwright_plan_config.json | literal(collection) | <module> | -
plugins/shipwright-adopt/scripts/checks/validate_adoption.py:60 | shipwright_build_config.json | literal(collection) | <module> | -
plugins/shipwright-adopt/scripts/checks/validate_adoption.py:61 | shipwright_compliance_config.json | literal(collection) | <module> | -
plugins/shipwright-adopt/scripts/checks/validate_adoption.py:154 | shipwright_known_failures.json | literal(collection) | <module> | -
plugins/shipwright-adopt/scripts/lib/config_writer.py:65 | shipwright_project_config.json | literal(path-join) | write_project_config | -
plugins/shipwright-adopt/scripts/lib/config_writer.py:82 | shipwright_plan_config.json | literal(path-join) | write_plan_config | -
plugins/shipwright-adopt/scripts/lib/config_writer.py:110 | shipwright_build_config.json | literal(path-join) | write_build_config | -
plugins/shipwright-adopt/scripts/lib/config_writer.py:139 | shipwright_iterate_config.json | literal(path-join) | write_iterate_config | -
plugins/shipwright-adopt/scripts/lib/config_writer.py:151 | shipwright_compliance_config.json | literal(path-join) | write_compliance_config | -
plugins/shipwright-adopt/scripts/lib/config_writer.py:163 | shipwright_sync_config.json | literal(path-join) | write_sync_config | -
plugins/shipwright-adopt/scripts/lib/config_writer.py:222 | shipwright_run_config.json | literal(path-join) | write_run_config | -
plugins/shipwright-adopt/scripts/lib/dry_run_reporter.py:81 | shipwright_known_failures.json | literal | plan_standard_writes | -
plugins/shipwright-adopt/scripts/lib/dry_run_reporter.py:87 | shipwright_project_config.json | literal | plan_standard_writes | -
plugins/shipwright-adopt/scripts/lib/dry_run_reporter.py:88 | shipwright_plan_config.json | literal | plan_standard_writes | -
plugins/shipwright-adopt/scripts/lib/dry_run_reporter.py:89 | shipwright_build_config.json | literal | plan_standard_writes | -
plugins/shipwright-adopt/scripts/lib/dry_run_reporter.py:90 | shipwright_iterate_config.json | literal | plan_standard_writes | -
plugins/shipwright-adopt/scripts/lib/dry_run_reporter.py:91 | shipwright_compliance_config.json | literal | plan_standard_writes | -
plugins/shipwright-adopt/scripts/lib/dry_run_reporter.py:92 | shipwright_run_config.json | literal | plan_standard_writes | -
plugins/shipwright-adopt/scripts/lib/dry_run_reporter.py:100 | shipwright_sync_config.json | literal | plan_standard_writes | -
plugins/shipwright-adopt/scripts/lib/event_seeder.py:63 | shipwright_sync_config.json | literal(path-join) | _drops_layout | R
plugins/shipwright-adopt/scripts/lib/inherited_baseline.py:49 | shipwright_known_failures.json | const-def | <module> | -
plugins/shipwright-adopt/scripts/lib/nested_project_detector.py:59 | shipwright_run_config.json | literal(path-join) | _scan | R
plugins/shipwright-adopt/scripts/lib/nested_project_detector.py:60 | shipwright_run_config.json | literal | _scan | R
plugins/shipwright-adopt/scripts/lib/spec_table.py:57 | f'_shipwright_adopt_{name}' | constructed(f-string) | _load_shared | R
plugins/shipwright-adopt/scripts/tools/backfill_phase_tasks.py:59 | shipwright_run_config.json | const-def | <module> | -
plugins/shipwright-build/scripts/checks/setup_implementation_session.py:109 | shipwright_run_config.json | literal(path-join) | main | R
plugins/shipwright-build/scripts/lib/config.py:11 | shipwright_build_config.json | const-def | <module> | -
plugins/shipwright-build/scripts/lib/sections.py:42 | shipwright_build_config.json | literal(path-join) | load_section_states | R
plugins/shipwright-build/scripts/tools/update_section_state.py:129 | shipwright_build_config.json | literal(path-join) | main | RW
plugins/shipwright-compliance/scripts/audit/audit_adapters.py:292 | f'_shipwright_compliance_audit_{module_name}' | constructed(f-string) | load_shared_lib | R
plugins/shipwright-compliance/scripts/audit/group_a.py:340 | f'shipwright_{config_name}.json' | constructed(f-string) | _resolve_a4_targets | R
plugins/shipwright-compliance/scripts/audit/group_a.py:340 | shipwright_ | constructed(f-string) | _resolve_a4_targets | R
plugins/shipwright-compliance/scripts/audit/group_b.py:86 | shipwright_project_config.json | literal(path-join) | _check_b1 | R
plugins/shipwright-compliance/scripts/audit/group_b.py:89 | shipwright_plan_config.json | literal(path-join) | _check_b1 | R
plugins/shipwright-compliance/scripts/audit/group_b.py:145 | shipwright_plan_config.json | literal(path-join) | _check_b2 | R
plugins/shipwright-compliance/scripts/audit/group_b.py:259 | shipwright_project_config.json | literal(path-join) | _check_b4 | R
plugins/shipwright-compliance/scripts/audit/group_b.py:297 | shipwright_run_config.json | literal(path-join) | _check_b5 | R
plugins/shipwright-compliance/scripts/audit/group_g.py:140 | shipwright_project_config.json | literal(path-join) | _project_split_names | R
plugins/shipwright-compliance/scripts/lib/audit_disclosure.py:55 | shipwright_compliance_config.json | const-def | <module> | -
plugins/shipwright-compliance/scripts/lib/collectors/_common.py:17 | shipwright_run_config.json | literal(collection) | <module> | -
plugins/shipwright-compliance/scripts/lib/collectors/_common.py:18 | shipwright_project_config.json | literal(collection) | <module> | -
plugins/shipwright-compliance/scripts/lib/collectors/_common.py:19 | shipwright_plan_config.json | literal(collection) | <module> | -
plugins/shipwright-compliance/scripts/lib/collectors/_common.py:20 | shipwright_build_config.json | literal(collection) | <module> | -
plugins/shipwright-compliance/scripts/lib/collectors/_test_links_io.py:160 | shipwright_compliance_config.json | literal(path-join) | _read_traceability_config | RW
plugins/shipwright-compliance/scripts/lib/collectors/test_evidence.py:105 | shipwright_test_results.json | literal(path-join) | collect_test_results | R
plugins/shipwright-compliance/scripts/lib/rtm_gate_support.py:72 | shipwright_compliance_config.json | literal | read_threshold | R
plugins/shipwright-compliance/scripts/lib/security_gate.py:36 | shipwright_compliance_config.json | const-def | <module> | -
plugins/shipwright-compliance/scripts/lib/test_evidence.py:273 | shipwright_project_config.json | literal(path-join) | _collect_split_e2e_results | R
plugins/shipwright-compliance/scripts/lib/test_evidence.py:286 | shipwright_test_results.json | literal(path-join) | _collect_split_e2e_results | R
plugins/shipwright-compliance/scripts/lib/thresholds.py:33 | shipwright_compliance_config.json | literal(path-join) | load_thresholds | R
plugins/shipwright-compliance/scripts/tools/update_compliance.py:279 | shipwright_compliance_config.json | literal(path-join) | main | RW
plugins/shipwright-deploy/scripts/checks/validate-deploy.py:72 | shipwright_run_config.json | literal(path-join) | _deploy_target | R
plugins/shipwright-deploy/scripts/lib/test_gate.py:44 | shipwright_test_results.json | literal(path-join) | evaluate_test_gate | R
plugins/shipwright-design/scripts/checks/check-design-gates.py:53 | f'_shipwright_design_own_lib_{name}' | constructed(f-string) | _load_own_lib_module | R
plugins/shipwright-design/scripts/checks/check-design-gates.py:100 | shipwright_run_config.json | literal(collection) | <module> | -
plugins/shipwright-design/scripts/checks/check-design-gates.py:101 | shipwright_project_config.json | literal(collection) | <module> | -
plugins/shipwright-design/scripts/checks/setup-design-session.py:41 | shipwright_project_config.json | const-def | <module> | -
plugins/shipwright-iterate/scripts/hooks/iterate_worktree_gate.py:224 | shipwright_run_config.json | literal(path-join) | _iterate_eligible | R
plugins/shipwright-plan/scripts/checks/check-plan-gates.py:78 | shipwright_run_config.json | literal(collection) | <module> | -
plugins/shipwright-plan/scripts/checks/check-plan-gates.py:79 | shipwright_project_config.json | literal(collection) | <module> | -
plugins/shipwright-plan/scripts/checks/check-plan-gates.py:80 | shipwright_plan_config.json | literal(collection) | <module> | -
plugins/shipwright-plan/scripts/checks/setup-planning-session.py:46 | shipwright_plan_session.json | const-def | <module> | -
plugins/shipwright-plan/scripts/checks/setup-planning-session.py:47 | shipwright_plan_interview.md | const-def | <module> | -
plugins/shipwright-plan/scripts/checks/write-plan-config.py:39 | shipwright_plan_config.json | literal(path-join) | main | W
plugins/shipwright-plan/scripts/lib/config.py:17 | shipwright_plan_config.json | const-def | <module> | -
plugins/shipwright-project/scripts/checks/write-project-config.py:144 | shipwright_project_config.json | literal(path-join) | main | RW
plugins/shipwright-project/scripts/lib/config.py:38 | shipwright_project_session.json | const-def | <module> | -
plugins/shipwright-project/scripts/lib/config.py:39 | shipwright_project_interview.md | const-def | <module> | -
plugins/shipwright-project/scripts/write_run_config.py:92 | shipwright_run_config.json | literal(path-join) | write_run_config | RW
plugins/shipwright-run/scripts/hooks/master_stop_check.py:36 | shipwright_run_config.json | const-def | <module> | -
plugins/shipwright-run/scripts/lib/orchestrator_pkg/brief_resume_guard.py:21 | shipwright_run_config.json | const-def | <module> | -
plugins/shipwright-run/scripts/lib/orchestrator_pkg/constants.py:29 | shipwright_run_config.json | const-def | <module> | -
plugins/shipwright-run/scripts/lib/orchestrator_pkg/events.py:62 | shipwright_run_config.json | literal(path-join) | _run_id_of | R
plugins/shipwright-run/scripts/lib/orchestrator_pkg/gate_run_id.py:34 | shipwright_run_config.json | const-def | <module> | -
plugins/shipwright-run/scripts/lib/phase_task_core.py:38 | shipwright_run_config.json | const-def | <module> | -
plugins/shipwright-run/scripts/lib/phase_task_planning.py:71 | shipwright_design_config.json | literal(path-join) | _resolve_splits_with_fallback | R
plugins/shipwright-run/scripts/lib/phase_task_planning.py:72 | shipwright_project_config.json | literal(path-join) | _resolve_splits_with_fallback | R
plugins/shipwright-run/scripts/lib/phase_validators_late.py:70 | shipwright_test_results.json | literal(path-join) | _validate_test | R
plugins/shipwright-run/scripts/lib/phase_validators_split.py:65 | shipwright_run_config.json | literal(path-join) | _design_not_applicable | R
plugins/shipwright-run/scripts/lib/run_config_store.py:61 | shipwright_run_config.json | const-def | <module> | -
plugins/shipwright-run/scripts/lib/single_session/orchestrator_context.py:26 | shipwright_run_config.json | const-def | <module> | -
plugins/shipwright-security/scripts/lib/pr_review_generated.py:62 | shipwright_test_results.json | literal(collection) | <module> | -
plugins/shipwright-security/scripts/lib/pr_review_skip_safety.py:32 | shipwright_test_results.json | literal(collection) | <module> | -
plugins/shipwright-security/scripts/tools/finalize_security_compliance.py:56 | shipwright_project_config.json | const-def | <module> | -
plugins/shipwright-security/scripts/tools/generate_security_report.py:546 | shipwright_security_config.json | literal(path-join) | main | RW (hint only: it reads; the writer is skills/security/SKILL.md:316 prose)
plugins/shipwright-test/scripts/lib/performance_check.py:693 | shipwright_test_config.json | literal(path-join) | main | RW
plugins/shipwright-test/scripts/lib/screenshot_check.py:118 | shipwright_run_config.json | literal(path-join) | _screen_map | R
plugins/shipwright-test/scripts/lib/warning_followups.py:49 | shipwright_test_results.json | const-def | <module> | -
plugins/shipwright-test/scripts/tools/merge_boundary_coverage.py:67 | shipwright_test_results.json | literal | main | -
shared/scripts/accepted_risks.py:63 | shipwright_accepted_risks.yaml | const-def | <module> | -
shared/scripts/artifact_sync.py:173 | shipwright_sync_config.json | literal(path-join) | detect_drift | RW
shared/scripts/dev_server/profile_config.py:40 | shipwright_dev_server.json | const-def | <module> | -
shared/scripts/dev_server/profile_config.py:239 | shipwright_build_config.json | literal(path-join) | _services_from_profile_data | R
shared/scripts/dev_server/profile_config.py:280 | shipwright_build_config.json | literal(path-join) | _get_config | R
shared/scripts/github_triage/state.py:35 | shipwright_run_config.json | literal(path-join) | _run_config | R
shared/scripts/hooks/check_file_size.py:75 | shipwright_build_config.json | literal(path-join) | _limit_for | R
shared/scripts/hooks/check_required_checks_hook.py:151 | shipwright_build_config.json | literal | _is_shipwright_project | R
shared/scripts/hooks/check_required_checks_hook.py:151 | shipwright_run_config.json | literal | _is_shipwright_project | R
shared/scripts/hooks/generate_handoff_on_stop.py:66 | shipwright_run_config.json | const-def | <module> | -
shared/scripts/hooks/generate_handoff_on_stop.py:138 | shipwright_build_config.json | literal(path-join) | _detect_phase_complete | R
shared/scripts/hooks/generate_handoff_on_stop.py:149 | shipwright_plan_config.json | literal(path-join) | _detect_phase_complete | R
shared/scripts/hooks/generate_handoff_on_stop.py:157 | shipwright_project_config.json | literal(path-join) | _detect_phase_complete | R
shared/scripts/hooks/generate_handoff_on_stop.py:165 | shipwright_test_results.json | literal(path-join) | _detect_phase_complete | R
shared/scripts/hooks/required_checks_state.py:77 | shipwright_run_config.json | literal(path-join) | throttle_hours | R
shared/scripts/hooks/session_start_using_shipwright.py:32 | shipwright_run_config.json | const-def | <module> | -
shared/scripts/hooks/suggest_iterate.py:173 | shipwright_sync_config.json | literal(path-join) | classify_for_iterate | R
shared/scripts/hooks/suggest_iterate.py:212 | shipwright_run_config.json | literal(path-join) | main | R
shared/scripts/hooks/track_tool_calls.py:57 | shipwright_build_config.json | literal | _is_shipwright_project | R
shared/scripts/hooks/track_tool_calls.py:57 | shipwright_run_config.json | literal | _is_shipwright_project | R
shared/scripts/inline_suppression_baseline.py:29 | shipwright_inline_suppressions.json | const-def | <module> | -
shared/scripts/known_failures.py:40 | shipwright_known_failures.json | const-def | <module> | -
shared/scripts/lib/ac_mode.py:25 | shipwright_iterate_config.json | const-def | <module> | -
shared/scripts/lib/ac_suggest.py:88 | shipwright_iterate_config.json | literal(path-join) | _opted_out | R
shared/scripts/lib/ac_surface.py:35 | shipwright_bloat_baseline.json | literal(collection) | <module> | -
shared/scripts/lib/ac_surface.py:35 | shipwright_test_results.json | literal(collection) | <module> | -
shared/scripts/lib/adr_collision_baseline.py:30 | shipwright_adr_collision_baseline.json | const-def | <module> | -
shared/scripts/lib/artifact_migrations.py:157 | shipwright_test_results.json | literal(collection) | <module> | -
shared/scripts/lib/artifact_migrations.py:257 | shipwright_test_results.json | literal(collection) | <module> | -
shared/scripts/lib/artifact_migrations.py:336 | shipwright_test_results.json | literal(collection) | <module> | -
shared/scripts/lib/artifact_migrations.py:364 | shipwright_project_config.json | literal(collection) | <module> | -
shared/scripts/lib/artifact_migrations.py:461 | shipwright_test_results.json | literal(collection) | <module> | -
shared/scripts/lib/artifact_migrations.py:621 | shipwright_bloat_baseline.json | literal(collection) | <module> | -
shared/scripts/lib/autonomous_rules.py:142 | shipwright_run_config.json | literal(path-join) | verified_package_mockups | -
shared/scripts/lib/autonomous_rules.py:187 | shipwright_run_config.json | literal(path-join) | _brief_dir | -
shared/scripts/lib/bloat_baseline.py:46 | shipwright_bloat_baseline.json | const-def | <module> | -
shared/scripts/lib/brief_dir_intake.py:37 | shipwright_run_config.json | const-def | <module> | -
shared/scripts/lib/brief_intake.py:231 | _shipwright_ | constructed(concat) | _sibling | -
shared/scripts/lib/change_type_paths.py:62 | shipwright_test_results.json | literal(collection) | <module> | -
shared/scripts/lib/change_type_paths.py:80 | shipwright_*.json | glob(collection) | <module> | -
shared/scripts/lib/change_type_paths.py:80 | shipwright_*.yaml | glob(collection) | <module> | -
shared/scripts/lib/change_type_paths.py:90 | shipwright_*.json | glob(collection) | <module> | -
shared/scripts/lib/change_type_paths.py:90 | shipwright_*.yaml | glob(collection) | <module> | -
shared/scripts/lib/change_type_paths.py:96 | shipwright_*.json | glob(collection) | <module> | -
shared/scripts/lib/change_type_paths.py:96 | shipwright_*.yaml | glob(collection) | <module> | -
shared/scripts/lib/churn_merge.py:41 | shipwright_test_results.json | const-def | <module> | -
shared/scripts/lib/codex_review_model_resolution.py:140 | shipwright_model_config.json's  | constructed(f-string) | resolve_codex_review_model | R
shared/scripts/lib/config.py:24 | shipwright_run_config.json | literal(collection) | <module> | -
shared/scripts/lib/config.py:25 | shipwright_project_config.json | literal(collection) | <module> | -
shared/scripts/lib/config.py:26 | shipwright_plan_config.json | literal(collection) | <module> | -
shared/scripts/lib/config.py:27 | shipwright_build_config.json | literal(collection) | <module> | -
shared/scripts/lib/config.py:28 | shipwright_security_config.json | literal(collection) | <module> | -
shared/scripts/lib/config.py:29 | shipwright_compliance_config.json | literal(collection) | <module> | -
shared/scripts/lib/drift_anchor.py:40 | shipwright_run_config.json | literal(path-join) | is_shipwright_project | R
shared/scripts/lib/event_context_query.py:93 | shipwright_iterate_config.json | literal(path-join) | resolve_mode | R
shared/scripts/lib/event_context_query.py:98 | shipwright_iterate_config.json | literal | resolve_mode | R
shared/scripts/lib/events_fold.py:41 | shipwright_sync_config.json | const-def | <module> | -
shared/scripts/lib/events_layout.py:57 | shipwright_sync_config.json | const-def | <module> | -
shared/scripts/lib/events_read.py:49 | f'_shipwright_events_read_{name}_' | constructed(f-string) | _sibling | R
shared/scripts/lib/events_sentinel.py:27 | shipwright_sync_config.json | const-def | <module> | -
shared/scripts/lib/external_review_config.py:72 | shipwright_iterate_config.json | const-def | <module> | -
shared/scripts/lib/gate_policy.py:58 | shipwright_run_config.json | const-def | <module> | -
shared/scripts/lib/iterate_entry.py:44 | shipwright_run_config.json | const-def | <module> | -
shared/scripts/lib/iterate_test_results.py:17 | shipwright_test_results.json | const-def | <module> | -
shared/scripts/lib/iterate_tests_block.py:43 | shipwright_test_results.json | const-def | <module> | -
shared/scripts/lib/manifest_sync_paths.py:20 | shipwright_changelog_config.json | const-def | <module> | -
shared/scripts/lib/model_tier_config.py:82 | shipwright_model_config.json | const-def | <module> | -
shared/scripts/lib/phase_history.py:227 | shipwright_run_config.json | literal(path-join) | _read_run_config | R
shared/scripts/lib/phase_invocation_mode.py:47 | shipwright_run_config.json | const-def | <module> | -
shared/scripts/lib/phase_quality/_engagement.py:138 | shipwright_run_config.json | literal(path-join) | load_engagement_inputs | R
shared/scripts/lib/phase_quality/_resolution.py:166 | shipwright_run_config.json | literal(path-join) | resolve_source | R
shared/scripts/lib/phase_quality/_run_id_resolve.py:88 | shipwright_run_config.json | literal(path-join) | resolve_run_id | R
shared/scripts/lib/plan_design_check.py:86 | shipwright_run_config.json | literal(path-join) | is_autonomous_design_run | R
shared/scripts/lib/project_root.py:26 | shipwright_run_config.json | literal(collection) | <module> | -
shared/scripts/lib/project_root.py:27 | shipwright_project_config.json | literal(collection) | <module> | -
shared/scripts/lib/project_root.py:28 | shipwright_plan_config.json | literal(collection) | <module> | -
shared/scripts/lib/project_root.py:29 | shipwright_build_config.json | literal(collection) | <module> | -
shared/scripts/lib/required_checks_drift.py:40 | shipwright_run_config.json | const-def | <module> | -
shared/scripts/lib/review_diff_threshold.py:58 | shipwright_test_results.json | literal(collection) | <module> | -
shared/scripts/lib/section_file_list.py:78 | shipwright_build_config.json | literal(collection) | <module> | -
shared/scripts/playwright_setup.py:105 | shipwright_build_config.json | literal(path-join) | setup | RW
shared/scripts/profile_consumer.py:35 | shipwright_run_config.json | const-def | <module> | -
shared/scripts/project_facts.py:20 | shipwright_run_config.json | const-def | <module> | -
shared/scripts/tools/append_phase_history.py:72 | shipwright_run_config.json | const-def | <module> | -
shared/scripts/tools/archive_split.py:78 | shipwright_test_results.json | literal(path-join) | archive_split | RW
shared/scripts/tools/brief_project_mode.py:201 | shipwright_project_interview.md | literal(path-join) | apply | RW
shared/scripts/tools/check_ac_coverage_ratchet.py:56 | shipwright_ac_coverage_baseline.json | const-def | <module> | -
shared/scripts/tools/check_ac_ratchet_f0.py:56 | shipwright_ac_coverage_baseline.json | const-def | <module> | -
shared/scripts/tools/compliance_input_state.py:50 | shipwright_compliance_config.json | literal(collection) | <module> | -
shared/scripts/tools/convert_configs_to_events.py:104 | shipwright_run_config.json | literal(path-join) | convert | R
shared/scripts/tools/convert_configs_to_events.py:105 | shipwright_build_config.json | literal(path-join) | convert | R
shared/scripts/tools/convert_configs_to_events.py:106 | shipwright_project_config.json | literal(path-join) | convert | R
shared/scripts/tools/convert_configs_to_events.py:224 | shipwright_build_config.json | literal(path-join) | main | RW
shared/scripts/tools/fold_events.py:47 | shipwright_sync_config.json | literal | _stage_paths | -
shared/scripts/tools/fold_events.py:52 | shipwright_sync_config.json | literal | _stage_paths | -
shared/scripts/tools/fr_split.py:40 | shipwright_ac_coverage_baseline.json | const-def | <module> | -
shared/scripts/tools/fr_split.py:42 | shipwright_ac_registry.json | const-def | <module> | -
shared/scripts/tools/get_phase_context.py:90 | shipwright_design_config.json | literal(collection) | <module> | -
shared/scripts/tools/get_phase_context.py:91 | shipwright_plan_config.json | literal(collection) | <module> | -
shared/scripts/tools/get_phase_context.py:92 | shipwright_build_config.json | literal(collection) | <module> | -
shared/scripts/tools/get_phase_context.py:93 | shipwright_test_results.json | literal(collection) | <module> | -
shared/scripts/tools/get_phase_context.py:96 | shipwright_deploy_config.json | literal(collection) | <module> | -
shared/scripts/tools/get_phase_context.py:101 | shipwright_project_config.json | literal(collection) | <module> | -
shared/scripts/tools/get_phase_context.py:102 | shipwright_design_config.json | literal(collection) | <module> | -
shared/scripts/tools/get_phase_context.py:104 | shipwright_plan_config.json | literal(collection) | <module> | -
shared/scripts/tools/get_phase_context.py:105 | shipwright_build_config.json | literal(collection) | <module> | -
shared/scripts/tools/get_phase_context.py:106 | shipwright_test_results.json | literal(collection) | <module> | -
shared/scripts/tools/get_phase_context.py:107 | shipwright_test_results.json | literal(collection) | <module> | -
shared/scripts/tools/grill_trace_entry_channel.py:22 | shipwright_project_interview.md | const-def | <module> | -
shared/scripts/tools/grill_trace_entry_channel.py:35 | shipwright_project_config.json | literal(path-join) | interview_expected | R
shared/scripts/tools/grill_trace_entry_channel.py:43 | shipwright_project_config.json | literal(path-join) | is_extension_scope | R
shared/scripts/tools/grill_trace_entry_channel.py:101 | shipwright_run_config.json | literal(path-join) | _has_brief_dir | R
shared/scripts/tools/record_autonomous_decision.py:156 | shipwright_run_config.json | literal(path-join) | _profile | R
shared/scripts/tools/record_coverage_total.py:46 | shipwright_test_results.json | const-def | <module> | -
shared/scripts/tools/stamp_test_results.py:67 | shipwright_test_results.json | const-def | <module> | -
shared/scripts/tools/stamp_test_results.py:68 | shipwright_run_config.json | const-def | <module> | -
shared/scripts/tools/suite_units.py:40 | shipwright_test_config.json | const-def | <module> | -
shared/scripts/tools/suite_worktree_diff.py:24 | shipwright_test_config.json | literal(collection) | <module> | -
shared/scripts/tools/update_build_dashboard.py:218 | shipwright_test_results.json | literal(path-join) | _generate_test_results | R
shared/scripts/tools/update_build_dashboard.py:354 | shipwright_test_results.json | literal(path-join) | _read_iterate_test_results | R
shared/scripts/tools/verifiers/_iterate_latest.py:50 | shipwright_test_results.json | const-def | <module> | -
shared/scripts/tools/verifiers/_migration_check.py:32 | shipwright_run_config.json | literal(path-join) | check_migration_quarantine_empty | R
shared/scripts/tools/verifiers/_project_gate_manifest.py:88 | shipwright_run_config.json | literal(path-join) | _declared_split_names | R
shared/scripts/tools/verifiers/_project_gate_manifest.py:89 | shipwright_project_config.json | literal(path-join) | _declared_split_names | R
shared/scripts/tools/verifiers/_project_gate_manifest.py:98 | shipwright_project_config.json | literal | _declared_split_names | R
shared/scripts/tools/verifiers/_project_gate_manifest.py:113 | shipwright_run_config.json | literal | _declared_split_names | R
shared/scripts/tools/verifiers/_project_gate_rollout_snapshot.py:171 | shipwright_project_config.json | literal | _rollout_declared_split_names | R
shared/scripts/tools/verifiers/_project_gate_rollout_snapshot.py:175 | shipwright_run_config.json | literal | _rollout_declared_split_names | R
shared/scripts/tools/verifiers/_project_gate_wiring.py:68 | shipwright_project_config.json | literal(path-join) | _read_project_scope | R
shared/scripts/tools/verifiers/_test_gate_extras.py:117 | shipwright_test_results.json | literal | check_e2e_counts_reconciled | R
shared/scripts/tools/verifiers/_test_gate_fidelity.py:101 | shipwright_test_results.json | literal | check_design_fidelity_triage_matches_recomputation | R
shared/scripts/tools/verifiers/adopt_compliance.py:49 | shipwright_run_config.json | literal(collection) | <module> | -
shared/scripts/tools/verifiers/adopt_compliance.py:50 | shipwright_project_config.json | literal(collection) | <module> | -
shared/scripts/tools/verifiers/adopt_compliance.py:51 | shipwright_plan_config.json | literal(collection) | <module> | -
shared/scripts/tools/verifiers/adopt_compliance.py:52 | shipwright_build_config.json | literal(collection) | <module> | -
shared/scripts/tools/verifiers/adopt_compliance.py:53 | shipwright_compliance_config.json | literal(collection) | <module> | -
shared/scripts/tools/verifiers/agents_md_completion_check.py:117 | shipwright_project_config.json | literal(path-join) | check_agents_md_completion | R
shared/scripts/tools/verifiers/brief_design_checks.py:34 | shipwright_run_config.json | literal(path-join) | _mentions_brief | R
shared/scripts/tools/verifiers/build_checks.py:57 | shipwright_build_config.json | literal(path-join) | _read_build_config | R
shared/scripts/tools/verifiers/changelog_checks.py:212 | shipwright_changelog_config.json:  | constructed(f-string) | check_manifest_version_matches_tag | R
shared/scripts/tools/verifiers/ci_supplychain_ack_store.py:50 | shipwright_test_results.json | const-def | <module> | -
shared/scripts/tools/verifiers/common.py:129 | shipwright_run_config.json | literal(path-join) | read_run_config | R
shared/scripts/tools/verifiers/compliance_compliance.py:94 | shipwright_compliance_config.json | literal(path-join) | _load_rtm_threshold_pct | R
shared/scripts/tools/verifiers/deploy_checks.py:145 | shipwright_test_results.json | literal(path-join) | check_test_gate_passed | R
shared/scripts/tools/verifiers/deploy_compliance.py:42 | shipwright_deploy_config.json | literal(path-join) | _smoke_from_deploy_config | R
shared/scripts/tools/verifiers/deploy_compliance.py:54 | shipwright_test_results.json | literal(path-join) | _smoke_from_test_results | R
shared/scripts/tools/verifiers/deploy_compliance.py:90 | shipwright_deploy_config.json | literal | check_w7_smoke_status | -
shared/scripts/tools/verifiers/deploy_compliance.py:91 | shipwright_test_results.json | literal | check_w7_smoke_status | -
shared/scripts/tools/verifiers/design_checks.py:93 | shipwright_run_config.json | literal(path-join) | _is_no_ui_scope | R
shared/scripts/tools/verifiers/design_checks.py:124 | shipwright_run_config.json | literal(path-join) | _design_phase_ran | R
shared/scripts/tools/verifiers/iterate_checks.py:459 | shipwright_run_config.json | literal(path-join) | _freshness_mtime_reference | R
shared/scripts/tools/verifiers/plan_checks.py:100 | shipwright_plan_config.json | literal(path-join) | check_plan_config_status_complete | R
shared/scripts/tools/verifiers/project_checks.py:77 | shipwright_project_config.json | literal(path-join) | check_project_config_status_complete | R
shared/scripts/tools/verifiers/project_checks.py:102 | shipwright_project_config.json | literal(path-join) | check_manifest_splits_match_dirs | R
shared/scripts/tools/verifiers/quality_checks.py:147 | shipwright_plan_snapshot.json | literal(path-join) | _read_plan_section_names | R
shared/scripts/tools/verifiers/quality_checks.py:179 | shipwright_build_config.json | literal(path-join) | _read_build_section_status | R
shared/scripts/tools/verifiers/silent_revert_declarations.py:58 | shipwright_test_results.json | literal(path-join) | _unattributed_declared_removals | R
shared/scripts/tools/verifiers/test_checks.py:83 | shipwright_test_results.json | literal(path-join) | check_test_results_file_fresh | R
shared/scripts/tools/verifiers/test_compliance.py:36 | shipwright_test_config.json | literal(path-join) | _load_threshold | R
shared/scripts/tools/verifiers/test_compliance.py:53 | shipwright_test_results.json | literal(path-join) | _load_coverage | R
shared/scripts/tools/verifiers/test_results_backfill_check.py:104 | shipwright_test_results.json | literal | _is_modified_snapshot_status | -
shared/scripts/tools/verifiers/test_results_backfill_check.py:119 | shipwright_test_results.json | literal | _validate_source | R
shared/scripts/tools/verifiers/test_results_backfill_check.py:133 | shipwright_test_results.json | literal | _validate_source | R
shared/scripts/tools/verifiers/test_results_backfill_check.py:151 | shipwright_test_results.json | literal | _validate_source | R
shared/scripts/validate_env.py:298 | shipwright_run_config.json | literal(path-join) | init_env_file | RW
shared/scripts/validate_env.py:474 | shipwright_run_config.json | literal(path-join) | validate | R
```

## B. Constants bound to a basename (file, name -> basename) and the modules that use them

Following imports and same-file aliases only; a constant re-exported through a second module is not followed.

```
plugins/shipwright-adopt/scripts/lib/inherited_baseline.py :: REGISTER_REL = shipwright_known_failures.json
plugins/shipwright-adopt/scripts/tools/backfill_phase_tasks.py :: RUN_CONFIG_NAME = shipwright_run_config.json
plugins/shipwright-build/scripts/lib/config.py :: CONFIG_NAME = shipwright_build_config.json
plugins/shipwright-compliance/scripts/lib/audit_disclosure.py :: CONFIG_FILE = shipwright_compliance_config.json
plugins/shipwright-compliance/scripts/lib/security_gate.py :: CONFIG_FILENAME = shipwright_compliance_config.json
plugins/shipwright-design/scripts/checks/setup-design-session.py :: PROJECT_CONFIG = shipwright_project_config.json
plugins/shipwright-plan/scripts/checks/setup-planning-session.py :: INTERVIEW_FILE = shipwright_plan_interview.md
plugins/shipwright-plan/scripts/checks/setup-planning-session.py :: SESSION_STATE_FILE = shipwright_plan_session.json
plugins/shipwright-plan/scripts/lib/config.py :: SESSION_CONFIG_NAME = shipwright_plan_config.json
plugins/shipwright-run/scripts/hooks/master_stop_check.py :: CONFIG_NAME = shipwright_run_config.json
plugins/shipwright-run/scripts/lib/orchestrator_pkg/brief_resume_guard.py :: _CONFIG = shipwright_run_config.json
plugins/shipwright-run/scripts/lib/orchestrator_pkg/constants.py :: CONFIG_NAME = shipwright_run_config.json
plugins/shipwright-run/scripts/lib/orchestrator_pkg/gate_run_id.py :: _RUN_CONFIG = shipwright_run_config.json
plugins/shipwright-run/scripts/lib/phase_task_core.py :: CONFIG_NAME = shipwright_run_config.json
plugins/shipwright-run/scripts/lib/run_config_store.py :: RUN_CONFIG_NAME = shipwright_run_config.json
plugins/shipwright-run/scripts/lib/single_session/orchestrator_context.py :: RUN_CONFIG_REL_PATH = shipwright_run_config.json
plugins/shipwright-security/scripts/tools/finalize_security_compliance.py :: PIPELINE_MARKER = shipwright_project_config.json
plugins/shipwright-test/scripts/lib/warning_followups.py :: RESULTS_NAME = shipwright_test_results.json
shared/scripts/accepted_risks.py :: REGISTER_NAME = shipwright_accepted_risks.yaml
shared/scripts/dev_server/profile_config.py :: STATE_FILE = shipwright_dev_server.json
shared/scripts/hooks/generate_handoff_on_stop.py :: _RUN_CONFIG_NAME = shipwright_run_config.json
shared/scripts/hooks/session_start_using_shipwright.py :: CONFIG_NAME = shipwright_run_config.json
shared/scripts/inline_suppression_baseline.py :: BASELINE_NAME = shipwright_inline_suppressions.json
shared/scripts/known_failures.py :: KNOWN_FAILURES_NAME = shipwright_known_failures.json
shared/scripts/lib/ac_mode.py :: CONFIG_FILE = shipwright_iterate_config.json
shared/scripts/lib/adr_collision_baseline.py :: BASELINE_RELPATH = shipwright_adr_collision_baseline.json
shared/scripts/lib/bloat_baseline.py :: BASELINE_FILENAME = shipwright_bloat_baseline.json
shared/scripts/lib/brief_dir_intake.py :: CONFIG_NAME = shipwright_run_config.json
shared/scripts/lib/churn_merge.py :: TEST_RESULTS = shipwright_test_results.json
shared/scripts/lib/events_fold.py :: SYNC_CONFIG = shipwright_sync_config.json
shared/scripts/lib/events_layout.py :: SYNC_CONFIG = shipwright_sync_config.json
shared/scripts/lib/events_sentinel.py :: SYNC_CONFIG = shipwright_sync_config.json
shared/scripts/lib/external_review_config.py :: _PROJECT_ITERATE_CONFIG_NAME = shipwright_iterate_config.json
shared/scripts/lib/gate_policy.py :: _CONFIG_NAME = shipwright_run_config.json
shared/scripts/lib/iterate_entry.py :: RUN_CONFIG_NAME = shipwright_run_config.json
shared/scripts/lib/iterate_test_results.py :: RESULTS_FILENAME = shipwright_test_results.json
shared/scripts/lib/iterate_tests_block.py :: RESULTS_FILENAME = shipwright_test_results.json
shared/scripts/lib/manifest_sync_paths.py :: CONFIG_NAME = shipwright_changelog_config.json
shared/scripts/lib/model_tier_config.py :: _CONFIG_FILENAME = shipwright_model_config.json
shared/scripts/lib/phase_invocation_mode.py :: CONFIG_NAME = shipwright_run_config.json
shared/scripts/lib/required_checks_drift.py :: ADVISORY_CONFIG_FILE = shipwright_run_config.json
shared/scripts/profile_consumer.py :: RUN_CONFIG = shipwright_run_config.json
shared/scripts/project_facts.py :: RUN_CONFIG_NAME = shipwright_run_config.json
shared/scripts/tools/append_phase_history.py :: RUN_CONFIG_NAME = shipwright_run_config.json
shared/scripts/tools/check_ac_coverage_ratchet.py :: BASELINE_RELPATH = shipwright_ac_coverage_baseline.json
shared/scripts/tools/check_ac_ratchet_f0.py :: _BASELINE = shipwright_ac_coverage_baseline.json
shared/scripts/tools/fr_split.py :: BASELINE = shipwright_ac_coverage_baseline.json
shared/scripts/tools/fr_split.py :: REGISTRY = shipwright_ac_registry.json
shared/scripts/tools/grill_trace_entry_channel.py :: TRANSCRIPT_NAME = shipwright_project_interview.md
shared/scripts/tools/record_coverage_total.py :: RESULTS_REL = shipwright_test_results.json
shared/scripts/tools/stamp_test_results.py :: RESULTS_REL = shipwright_test_results.json
shared/scripts/tools/stamp_test_results.py :: RUN_CONFIG_REL = shipwright_run_config.json
shared/scripts/tools/suite_units.py :: CONFIG_NAME = shipwright_test_config.json
shared/scripts/tools/verifiers/_iterate_latest.py :: RESULTS_NAME = shipwright_test_results.json
shared/scripts/tools/verifiers/ci_supplychain_ack_store.py :: _RESULTS = shipwright_test_results.json
```

Users per basename (file -> function-level hints; `def` = only the definition or a module-level use):

```
shipwright_ac_coverage_baseline.json
    shared/scripts/tools/check_ac_coverage_ratchet.py [-]
    shared/scripts/tools/check_ac_ratchet_f0.py [R]
    shared/scripts/tools/fr_split.py [R]
shipwright_ac_registry.json
    shared/scripts/tools/fr_split.py [R]
shipwright_accepted_risks.yaml
    shared/scripts/accepted_risks.py [-,R]
shipwright_adr_collision_baseline.json
    shared/scripts/lib/adr_collision_baseline.py [R]
    shared/scripts/tools/rebuild_adr_collision_baseline.py [W]
shipwright_bloat_baseline.json
    shared/scripts/lib/bloat_baseline.py [-]
shipwright_build_config.json
    plugins/shipwright-build/scripts/lib/config.py [R,W]
shipwright_changelog_config.json
    shared/scripts/lib/manifest_sync_paths.py [R]
shipwright_compliance_config.json
    plugins/shipwright-compliance/scripts/lib/audit_disclosure.py [R,RW]
    plugins/shipwright-compliance/scripts/lib/security_gate.py [R]
shipwright_dev_server.json
    shared/scripts/dev_server/state.py [R,W]
shipwright_inline_suppressions.json
    shared/scripts/inline_suppression_baseline.py [-,R]
    shared/scripts/inline_suppressions.py [-]
shipwright_iterate_config.json
    shared/scripts/lib/ac_mode.py [-,R]
    shared/scripts/lib/external_review_config.py [RW]
shipwright_known_failures.json
    plugins/shipwright-adopt/scripts/lib/inherited_baseline.py [-,W]
    shared/scripts/known_failures.py [R]
    shared/scripts/tools/verifiers/test_checks.py [R]
shipwright_model_config.json
    shared/scripts/lib/model_tier_config.py [-,R]
shipwright_plan_config.json
    plugins/shipwright-plan/scripts/lib/config.py [R]
shipwright_plan_interview.md
    plugins/shipwright-plan/scripts/checks/setup-planning-session.py [R]
shipwright_plan_session.json
    plugins/shipwright-plan/scripts/checks/setup-planning-session.py [RW]
shipwright_project_config.json
    plugins/shipwright-design/scripts/checks/setup-design-session.py [R,RW]
    plugins/shipwright-security/scripts/tools/finalize_security_compliance.py [R]
shipwright_project_interview.md
    shared/scripts/tools/grill_trace_entry_channel.py [R]
shipwright_run_config.json
    plugins/shipwright-adopt/scripts/tools/backfill_phase_tasks.py [RW]
    plugins/shipwright-run/scripts/hooks/master_stop_check.py [RW]
    plugins/shipwright-run/scripts/lib/orchestrator_pkg/brief_resume_guard.py [R]
    plugins/shipwright-run/scripts/lib/orchestrator_pkg/config_factory.py [RW]
    plugins/shipwright-run/scripts/lib/orchestrator_pkg/config_io.py [R,RW,W]
    plugins/shipwright-run/scripts/lib/orchestrator_pkg/gate_run_id.py [R]
    plugins/shipwright-run/scripts/lib/phase_task_core.py [R,W]
    plugins/shipwright-run/scripts/lib/run_config_store.py [def]
    plugins/shipwright-run/scripts/lib/single_session/orchestrator_context.py [-]
    shared/scripts/hooks/generate_handoff_on_stop.py [RW,def]
    shared/scripts/hooks/session_start_using_shipwright.py [R]
    shared/scripts/lib/brief_dir_intake.py [R,RW]
    shared/scripts/lib/gate_policy.py [R]
    shared/scripts/lib/iterate_entry.py [R]
    shared/scripts/lib/phase_invocation_mode.py [R]
    shared/scripts/lib/required_checks_drift.py [R]
    shared/scripts/profile_consumer.py [-,R]
    shared/scripts/project_facts.py [R]
    shared/scripts/tools/append_iterate_entry.py [R,W]
    shared/scripts/tools/append_phase_history.py [R,RW]
    shared/scripts/tools/stamp_test_results.py [-,R,W]
    shared/scripts/tools/verifiers/_iterate_run_id.py [R]
shipwright_sync_config.json
    shared/scripts/lib/events_fold.py [R,RW]
    shared/scripts/lib/events_layout.py [R]
    shared/scripts/lib/events_layout_ci.py [-,R]
    shared/scripts/lib/events_sentinel.py [R,RW]
shipwright_test_config.json
    shared/scripts/tools/suite_units.py [-,R]
shipwright_test_results.json
    plugins/shipwright-test/scripts/lib/warning_followups.py [-,R]
    shared/scripts/lib/churn_merge.py [def]
    shared/scripts/lib/compliance_refresh.py [def]
    shared/scripts/lib/derived_snapshots.py [def]
    shared/scripts/lib/iterate_test_results.py [R]
    shared/scripts/lib/iterate_tests_block.py [R]
    shared/scripts/tools/record_coverage_total.py [-,RW]
    shared/scripts/tools/resolve_churn_conflicts.py [-]
    shared/scripts/tools/stamp_test_results.py [-,RW]
    shared/scripts/tools/verifiers/_iterate_latest.py [-,R]
    shared/scripts/tools/verifiers/ci_supplychain_ack_store.py [R]
```

## C. Derived lock names built from a constant

```
plugins/shipwright-run/scripts/lib/run_config_store.py :: LOCK_NAME = shipwright_run_config.json.lock
shared/scripts/hooks/generate_handoff_on_stop.py :: _RUN_CONFIG_LOCK_NAME = shipwright_run_config.json.lock
```

## D. Functions that read the run config (static guard facts; basis for the BRIEF 11.5 counts)

Columns: `exists` an existence test, `isdict` an `isinstance(..., dict)` guard, `get` uses `.get`, `raise` an explicit raise, `exc` the exception types caught.

```
plugins/shipwright-adopt/scripts/tools/backfill_phase_tasks.py:75 run | exists=1 isdict=1 get=1 raise=1 exc=LockTimeout as exc,json.JSONDecodeError as exc
plugins/shipwright-adopt/scripts/tools/generate_adoption_artifacts.py:204 generate | exists=1 isdict=0 get=1 raise=1 exc=EnrichmentValidationError as e,ValueError,ValueError, Import
plugins/shipwright-build/scripts/checks/setup_implementation_session.py:78 main | exists=1 isdict=0 get=1 raise=0 exc=json.JSONDecodeError, OSError
plugins/shipwright-compliance/scripts/audit/group_b.py:296 _check_b5 | exists=0 isdict=1 get=1 raise=0 exc=
plugins/shipwright-deploy/scripts/checks/validate-deploy.py:68 _deploy_target | exists=0 isdict=0 get=1 raise=0 exc=OSError, json.JSONDecodeError, AttributeError
plugins/shipwright-iterate/scripts/hooks/iterate_worktree_gate.py:216 _iterate_eligible | exists=0 isdict=1 get=1 raise=0 exc=OSError, ValueError
plugins/shipwright-run/scripts/hooks/master_stop_check.py:121 run | exists=1 isdict=0 get=1 raise=0 exc=json.JSONDecodeError
plugins/shipwright-run/scripts/lib/orchestrator_pkg/brief_resume_guard.py:36 _records_package | exists=0 isdict=1 get=0 raise=0 exc=OSError, ValueError
plugins/shipwright-run/scripts/lib/orchestrator_pkg/config_io.py:119 load_run_config | exists=0 isdict=0 get=0 raise=1 exc=RunConfigUnreadable as exc
plugins/shipwright-run/scripts/lib/orchestrator_pkg/events.py:53 _run_id_of | exists=0 isdict=1 get=1 raise=1 exc=OSError, json.JSONDecodeError
plugins/shipwright-run/scripts/lib/orchestrator_pkg/gate_run_id.py:49 canon_run_id | exists=0 isdict=1 get=1 raise=0 exc=OSError, ValueError
plugins/shipwright-run/scripts/lib/phase_task_core.py:123 _read_config | exists=1 isdict=0 get=0 raise=1 exc=
plugins/shipwright-run/scripts/lib/phase_validators_split.py:55 _design_not_applicable | exists=0 isdict=0 get=1 raise=0 exc=
plugins/shipwright-test/scripts/lib/screenshot_check.py:117 _screen_map | exists=0 isdict=1 get=1 raise=0 exc=
shared/scripts/github_triage/state.py:32 _run_config | exists=0 isdict=1 get=0 raise=0 exc=OSError, json.JSONDecodeError
shared/scripts/hooks/generate_handoff_on_stop.py:212 _seed_legacy_phase_task_history | exists=1 isdict=1 get=1 raise=0 exc=LockTimeout, OSError, json.JSONDecodeError
shared/scripts/hooks/generate_handoff_on_stop.py:295 main | exists=1 isdict=0 get=1 raise=0 exc=Exception,Exception as e,ValueError
shared/scripts/hooks/required_checks_state.py:66 throttle_hours | exists=0 isdict=1 get=1 raise=0 exc=OSError, json.JSONDecodeError, AttributeError, TypeError,Val
shared/scripts/hooks/session_start_using_shipwright.py:102 run | exists=1 isdict=0 get=0 raise=0 exc=OSError
shared/scripts/hooks/suggest_iterate.py:199 main | exists=1 isdict=0 get=1 raise=0 exc=json.JSONDecodeError, EOFError,json.JSONDecodeError, FileNot
shared/scripts/hooks/track_context_cost.py:52 main | exists=1 isdict=1 get=1 raise=0 exc=Exception,Exception as exc
shared/scripts/lib/brief_dir_intake.py:197 load_config | exists=0 isdict=1 get=0 raise=1 exc=OSError,ValueError as exc
shared/scripts/lib/gate_policy.py:151 read_run_config_mode | exists=0 isdict=1 get=1 raise=0 exc=ValueError, OSError, RecursionError, TypeError
shared/scripts/lib/iterate_entry.py:265 _read_legacy_array | exists=1 isdict=1 get=1 raise=0 exc=json.JSONDecodeError, OSError, UnicodeDecodeError
shared/scripts/lib/phase_history.py:215 _read_run_config | exists=0 isdict=1 get=0 raise=0 exc=OSError, json.JSONDecodeError, ValueError
shared/scripts/lib/phase_invocation_mode.py:71 read_run_config | exists=1 isdict=1 get=1 raise=1 exc=json.JSONDecodeError, OSError, UnicodeDecodeError
shared/scripts/lib/phase_quality/_engagement.py:129 load_engagement_inputs | exists=1 isdict=1 get=0 raise=0 exc=OSError,json.JSONDecodeError, OSError
shared/scripts/lib/phase_quality/_resolution.py:152 resolve_source | exists=1 isdict=1 get=1 raise=0 exc=json.JSONDecodeError, OSError
shared/scripts/lib/phase_quality/_run_id_resolve.py:30 resolve_run_id | exists=1 isdict=1 get=1 raise=1 exc=OSError,ValueError, OSError, RecursionError
shared/scripts/lib/plan_design_check.py:79 is_autonomous_design_run | exists=0 isdict=1 get=1 raise=0 exc=OSError, ValueError
shared/scripts/lib/required_checks_drift.py:44 load_advisory_checks | exists=0 isdict=1 get=1 raise=0 exc=OSError, ValueError
shared/scripts/profile_consumer.py:97 config_profile | exists=0 isdict=1 get=1 raise=1 exc=FileNotFoundError,OSError, ValueError
shared/scripts/project_facts.py:23 read_run_config | exists=0 isdict=1 get=0 raise=1 exc=OSError, json.JSONDecodeError, ValueError
shared/scripts/tools/append_iterate_entry.py:91 _load_config | exists=1 isdict=1 get=0 raise=1 exc=json.JSONDecodeError as exc
shared/scripts/tools/append_phase_history.py:137 main | exists=0 isdict=1 get=0 raise=0 exc=FileNotFoundError, ValueError,LockTimeout as exc,json.JSONDe
shared/scripts/tools/append_phase_history.py:75 append_history | exists=1 isdict=1 get=1 raise=1 exc=json.JSONDecodeError as exc
shared/scripts/tools/convert_configs_to_events.py:100 convert | exists=0 isdict=0 get=1 raise=0 exc=
shared/scripts/tools/grill_trace_entry_channel.py:99 _has_brief_dir | exists=0 isdict=1 get=1 raise=0 exc=OSError, ValueError
shared/scripts/tools/record_autonomous_decision.py:152 _profile | exists=0 isdict=0 get=1 raise=0 exc=OSError, ValueError, AttributeError
shared/scripts/tools/stamp_test_results.py:71 _run_id_from_config | exists=1 isdict=1 get=1 raise=0 exc=OSError, json.JSONDecodeError
shared/scripts/tools/verifiers/_iterate_run_id.py:118 own_entry_file_is_corrupt | exists=1 isdict=1 get=1 raise=0 exc=Exception,json.JSONDecodeError, OSError, UnicodeDecodeError
shared/scripts/tools/verifiers/_migration_check.py:25 check_migration_quarantine_empty | exists=1 isdict=0 get=1 raise=0 exc=json.JSONDecodeError, OSError
shared/scripts/tools/verifiers/_project_gate_manifest.py:62 _declared_split_names | exists=1 isdict=1 get=1 raise=0 exc=json.JSONDecodeError, OSError
shared/scripts/tools/verifiers/brief_design_checks.py:32 _mentions_brief | exists=0 isdict=0 get=0 raise=0 exc=OSError
shared/scripts/tools/verifiers/common.py:122 read_run_config | exists=1 isdict=0 get=0 raise=0 exc=json.JSONDecodeError
shared/scripts/tools/verifiers/deploy_checks.py:262 check_failed_liveness_recorded_as_failed | exists=1 isdict=1 get=1 raise=1 exc=
shared/scripts/tools/verifiers/design_checks.py:101 _design_phase_ran | exists=0 isdict=1 get=0 raise=0 exc=OSError, UnicodeDecodeError, json.JSONDecodeError
shared/scripts/tools/verifiers/design_checks.py:83 _is_no_ui_scope | exists=0 isdict=1 get=1 raise=0 exc=OSError, UnicodeDecodeError, json.JSONDecodeError
shared/scripts/validate_env.py:253 init_env_file | exists=1 isdict=0 get=1 raise=0 exc=OSError as exc,ValueError as exc
```

## E. Non-Python carriers (token scan, one line per file)

Basenames are shortened (`run_cfg` = `shipwright_run_config.json`, `events` = `shipwright_events.jsonl`); classes: ci/template, data-in-profile, prompt (a `.md` carrier), glob/constructed, literal. `.shipwright/`, tests and docs excluded.

```
.gitattributes :: events=literal
.github/workflows/bloat-check.yml :: bloat_baseline=ci/template,ci/template/R
.github/workflows/ci.yml :: ac_coverage_baseline=ci/template
.github/workflows/windows-tests.yml :: test_cfg=ci/template
.gitignore :: *_cfg=glob/constructed; events=literal
.trivyignore.yaml :: accepted_risks.yaml=ci/template
plugins/shipwright-adopt/.gitignore :: run_cfg=literal; *_cfg=glob/constructed
scripts/hooks/pre-commit :: bloat_baseline=literal
shared/config/external_review.json :: iterate_cfg=literal
shared/config/gate_catalog.json :: run_cfg=literal
shared/profiles/deploy/compose-vps.json :: test_results=data-in-profile
shared/profiles/deploy/jelastic.json :: test_results=data-in-profile
shared/profiles/deploy/vercel.json :: test_results=data-in-profile
shared/profiles/supabase-nextjs.json :: test_cfg=data-in-profile
shared/profiles/vite-hono.json :: test_cfg=data-in-profile; compliance_cfg=data-in-profile
shared/schemas/model_config.schema.json :: model_cfg=literal
shared/schemas/run_config.v2.schema.json :: run_cfg=literal
shared/schemas/stack_profile.schema.json :: compliance_cfg=literal
shared/schemas/triage_item.schema.json :: events=literal
shared/templates/agent-docs/session-handoff.md.template :: run_cfg=ci/template; project_cfg=ci/template; plan_cfg=ci/template; build_cfg=ci/template
shared/templates/gitattributes-union.template :: events=ci/template
shared/templates/shipwright-gitignore.template :: events=ci/template
shipwright_accepted_risks.yaml :: inline_suppressions=ci/template
shipwright_events.jsonl :: test_results=literal; events=literal; iterate_cfg=literal; plan_cfg=literal; run_cfg=literal; bloat_baseline=literal; compliance_cfg=literal; accepted_risks.yaml=literal; sync_cfg=literal; test_cfg=literal; model_cfg=literal; changelog_cfg=literal; ac_coverage_baseline=literal
shipwright_inline_suppressions.json :: accepted_risks.yaml=literal
shipwright_test_config.json :: test_results=literal
AGENTS.md :: model_cfg=prompt; test_results=prompt; *_cfg=prompt; bloat_baseline=prompt
CLAUDE.md :: *_cfg=prompt; bloat_baseline=prompt
plugins/shipwright-adopt/skills/adopt/SKILL.md :: *_cfg=prompt; run_cfg=prompt; bloat_baseline=prompt; known_failures=prompt; iterate_cfg=prompt
plugins/shipwright-adopt/skills/adopt/references/backfill-iterate-config.md :: iterate_cfg=prompt
plugins/shipwright-adopt/skills/adopt/references/backfill-phase-tasks.md :: run_cfg=prompt
plugins/shipwright-adopt/skills/adopt/references/codebase-analysis.md :: run_cfg=prompt
plugins/shipwright-adopt/skills/adopt/references/nested-project-policy.md :: run_cfg=prompt; *_cfg=prompt
plugins/shipwright-adopt/skills/adopt/references/step-a-preflight.md :: bloat_baseline=prompt
plugins/shipwright-adopt/skills/adopt/references/step-e-artifact-generation.md :: run_cfg=prompt; events=prompt; *_cfg=prompt
plugins/shipwright-adopt/skills/adopt/references/step-e18-inherited-baseline.md :: known_failures=prompt
plugins/shipwright-adopt/skills/adopt/references/step-h-validate-commit-handoff.md :: known_failures=prompt; events=prompt; *=prompt
plugins/shipwright-build/agents/code-reviewer.md :: bloat_baseline=prompt
plugins/shipwright-build/agents/section-builder.md :: build_cfg=prompt
plugins/shipwright-build/agents/spec-reviewer.md :: run_cfg=prompt
plugins/shipwright-build/skills/build/SKILL.md :: build_cfg=prompt
plugins/shipwright-build/skills/build/references/autonomous-loop.md :: build_cfg=prompt
plugins/shipwright-build/skills/build/references/browser-verify.md :: build_cfg=prompt
plugins/shipwright-build/skills/build/references/code-review.md :: run_cfg=prompt; build_cfg=prompt
plugins/shipwright-build/skills/build/references/first-actions.md :: run_cfg=prompt; build_cfg=prompt; model_cfg=prompt
plugins/shipwright-build/skills/build/references/migrations-apply.md :: run_cfg=prompt
plugins/shipwright-build/skills/build/references/section-doc-update.md :: build_cfg=prompt
plugins/shipwright-build/skills/build/references/section-state.md :: build_cfg=prompt
plugins/shipwright-changelog/skills/changelog/SKILL.md :: run_cfg=prompt; events=prompt
plugins/shipwright-changelog/skills/changelog/references/compliance-evidence.md :: events=prompt
plugins/shipwright-changelog/skills/changelog/references/manifest-sync.md :: changelog_cfg=prompt
plugins/shipwright-compliance/skills/compliance/SKILL.md :: bloat_baseline=prompt; compliance_cfg=prompt; *_cfg=prompt
plugins/shipwright-deploy/skills/deploy/SKILL.md :: test_results=prompt; run_cfg=prompt
plugins/shipwright-deploy/skills/deploy/references/rollback-discipline.md :: events=prompt
plugins/shipwright-design/skills/design/SKILL.md :: run_cfg=prompt; project_cfg=prompt
plugins/shipwright-design/skills/design/references/brief-compose.md :: run_cfg=prompt
plugins/shipwright-design/skills/design/references/invocation-mode.md :: run_cfg=prompt; project_cfg=prompt
plugins/shipwright-design/skills/design/references/review-loop.md :: run_cfg=prompt; project_cfg=prompt
plugins/shipwright-design/skills/design/references/review-viewer-template.md :: project_cfg=prompt
plugins/shipwright-design/skills/design/references/step-2-5-brand-extraction.md :: project_cfg=prompt
plugins/shipwright-design/skills/design/references/step-6a-review-viewer.md :: project_cfg=prompt
plugins/shipwright-design/skills/design/references/step-9-finalization.md :: run_cfg=prompt
plugins/shipwright-design/skills/design/references/upload-mode.md :: run_cfg=prompt
plugins/shipwright-grade/skills/grade/SKILL.md :: events=prompt
plugins/shipwright-iterate/agents/sub-iterate-runner.md :: run_cfg=prompt; build_cfg=prompt; test_results=prompt; events=prompt; bloat_baseline=prompt
plugins/shipwright-iterate/skills/iterate/SKILL.md :: run_cfg=prompt; events=prompt; sync_cfg=prompt; test_results=prompt
plugins/shipwright-iterate/skills/iterate/references/F-finalize-bundle.md :: test_results=prompt
plugins/shipwright-iterate/skills/iterate/references/F0.5.md :: test_results=prompt
plugins/shipwright-iterate/skills/iterate/references/F0.md :: test_cfg=prompt; ac_coverage_baseline=prompt; build_cfg=prompt
plugins/shipwright-iterate/skills/iterate/references/F11.md :: events=prompt; sync_cfg=prompt
plugins/shipwright-iterate/skills/iterate/references/F5.md :: test_results=prompt
plugins/shipwright-iterate/skills/iterate/references/F5b.md :: events=prompt; test_results=prompt
plugins/shipwright-iterate/skills/iterate/references/F5c.md :: run_cfg=prompt; test_results=prompt; events=prompt
plugins/shipwright-iterate/skills/iterate/references/F6.5.md :: events=prompt
plugins/shipwright-iterate/skills/iterate/references/F6.md :: run_cfg=prompt; events=prompt; test_results=prompt; sync_cfg=prompt
plugins/shipwright-iterate/skills/iterate/references/F7b.md :: events=prompt
plugins/shipwright-iterate/skills/iterate/references/artifact-ownership.md :: events=prompt
plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md :: events=prompt; model_cfg=prompt
plugins/shipwright-iterate/skills/iterate/references/context-loading.md :: run_cfg=prompt; sync_cfg=prompt; test_results=prompt; events=prompt; iterate_cfg=prompt
plugins/shipwright-iterate/skills/iterate/references/degraded-mode.md :: test_results=prompt
plugins/shipwright-iterate/skills/iterate/references/design-and-testing.md :: test_results=prompt
plugins/shipwright-iterate/skills/iterate/references/iterate-timings.md :: events=prompt
plugins/shipwright-iterate/skills/iterate/references/iteration-planning.md :: sync_cfg=prompt; model_cfg=prompt; test_results=prompt
plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md :: events=prompt; test_results=prompt; iterate_cfg=prompt
plugins/shipwright-iterate/skills/iterate/references/mid-flight-escalation.md :: events=prompt; test_results=prompt
plugins/shipwright-iterate/skills/iterate/references/path-a-feature.md :: sync_cfg=prompt; iterate_cfg=prompt
plugins/shipwright-iterate/skills/iterate/references/path-b-change.md :: sync_cfg=prompt
plugins/shipwright-iterate/skills/iterate/references/round-trip-tests.md :: run_cfg=prompt
plugins/shipwright-plan/agents/section-writer.md :: run_cfg=prompt
plugins/shipwright-plan/skills/plan/SKILL.md :: plan_cfg=prompt; plan_interview.md=prompt
plugins/shipwright-plan/skills/plan/references/e2e-test-plan.md :: test_results=prompt
plugins/shipwright-plan/skills/plan/references/first-actions.md :: run_cfg=prompt; plan_cfg=prompt
plugins/shipwright-plan/skills/plan/references/interview-protocol.md :: plan_interview.md=prompt
plugins/shipwright-plan/skills/plan/references/step-5-external-review.md :: model_cfg=prompt
plugins/shipwright-plan/skills/plan/references/step-9-completion.md :: run_cfg=prompt; project_cfg=prompt; plan_cfg=prompt
plugins/shipwright-preview/skills/preview/SKILL.md :: build_cfg=prompt; run_cfg=prompt
plugins/shipwright-project/skills/project/SKILL.md :: run_cfg=prompt; project_interview.md=prompt
plugins/shipwright-project/skills/project/references/brief-mode.md :: run_cfg=prompt; project_interview.md=prompt
plugins/shipwright-project/skills/project/references/first-actions.md :: run_cfg=prompt
plugins/shipwright-project/skills/project/references/interview-protocol.md :: project_interview.md=prompt
plugins/shipwright-project/skills/project/references/project-manifest.md :: project_interview.md=prompt
plugins/shipwright-project/skills/project/references/project-scaffolding.md :: project_cfg=prompt
plugins/shipwright-project/skills/project/references/spec-generation.md :: project_interview.md=prompt
plugins/shipwright-project/skills/project/references/split-heuristics.md :: project_interview.md=prompt
plugins/shipwright-project/skills/project/references/step-1-interview.md :: run_cfg=prompt; sync_cfg=prompt; project_interview.md=prompt
plugins/shipwright-project/skills/project/references/step-4-confirmation.md :: project_interview.md=prompt
plugins/shipwright-project/skills/project/references/step-6-spec-gen.md :: project_interview.md=prompt
plugins/shipwright-project/skills/project/references/step-7-scaffolding.md :: build_cfg=prompt
plugins/shipwright-project/skills/project/references/step-8-completion.md :: project_interview.md=prompt; run_cfg=prompt
plugins/shipwright-run/agents/phase-runner.md :: run_cfg=prompt
plugins/shipwright-run/skills/run/SKILL.md :: run_cfg=prompt; *_cfg=prompt
plugins/shipwright-run/skills/run/references/autonomy-levels.md :: run_cfg=prompt
plugins/shipwright-run/skills/run/references/single-session-loop.md :: run_cfg=prompt; events=prompt
plugins/shipwright-security/skills/security/SKILL.md :: project_cfg=prompt; inline_suppressions=prompt; security_cfg=prompt; run_cfg=prompt
plugins/shipwright-security/skills/security/references/remediation-loop.md :: security_cfg=prompt
plugins/shipwright-security/skills/security/references/suppression-syntax.md :: inline_suppressions=prompt
plugins/shipwright-test/agents/test-runner.md :: build_cfg=prompt; test_results=prompt/R
plugins/shipwright-test/skills/test/SKILL.md :: project_cfg=prompt; test_results=prompt; build_cfg=prompt; test_cfg=prompt; events=prompt; known_failures=prompt
plugins/shipwright-test/skills/test/references/completion-gate.md :: known_failures=prompt
plugins/shipwright-test/skills/test/references/first-actions.md :: project_cfg=prompt; run_cfg=prompt; test_results=prompt
plugins/shipwright-test/skills/test/references/prerequisite-self-healing.md :: build_cfg=prompt
plugins/shipwright-test/skills/test/references/results-enforcement.md :: known_failures=prompt
plugins/shipwright-test/skills/test/references/step-1-unit-tests.md :: run_cfg=prompt
plugins/shipwright-test/skills/test/references/step-2-smoke-test.md :: build_cfg=prompt
plugins/shipwright-test/skills/test/references/step-3.5-e2e-verification.md :: test_results=prompt
plugins/shipwright-test/skills/test/references/step-3.6-ui-consistency.md :: test_results=prompt
plugins/shipwright-test/skills/test/references/step-3.7-design-fidelity.md :: test_results=prompt
plugins/shipwright-test/skills/test/references/step-3.7b-screenshot-check.md :: test_results=prompt
plugins/shipwright-test/skills/test/references/step-3.8-performance-budget.md :: test_cfg=prompt; test_results=prompt
plugins/shipwright-test/skills/test/references/step-3.95-boundary-coverage.md :: test_cfg=prompt; events=prompt; test_results=prompt
plugins/shipwright-test/skills/test/references/step-5-report-results.md :: test_results=prompt; known_failures=prompt; build_cfg=prompt
shared/config/gate_catalog.md :: run_cfg=prompt
shared/fr-authoring.md :: events=prompt
shared/glossary.md :: bloat_baseline=prompt; inline_suppressions=prompt; dev_server=prompt; run_cfg=prompt; events=prompt
shared/grill-trace-format.md :: project_interview.md=prompt
shared/profiles/deploy-profile-schema.md :: test_results=prompt
shared/prompts/codex_review_dispatch.md :: model_cfg=prompt
shared/prompts/single-session-gate-discipline.md :: run_cfg=prompt
shared/prompts/using-shipwright.md :: run_cfg=prompt
shared/templates/claude-md-template.md :: run_cfg=prompt; project_cfg=prompt; plan_cfg=prompt; build_cfg=prompt; security_cfg=prompt; compliance_cfg=prompt
shared/templates/codex-agents-md-appendix.md :: test_results=prompt
```
