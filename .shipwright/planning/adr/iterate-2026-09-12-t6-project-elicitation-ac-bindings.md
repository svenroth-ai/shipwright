# t6 — FR-01.02 / FR-01.16 AC-binding disposition table

Campaign `req3-05-test-backfill-mono`, sub-iterate t6. Run-ID
`iterate-2026-09-12-t6-project-elicitation`. Full per-AC mapping requested by
external plan review (GLM, medium) and external code review (openai, low).

Ledger-`#N` -> current `ACnn` correspondence verified bullet-by-bullet against
`.shipwright/planning/01-adopted/spec.md` FR-01.02 (lines 105-168) against
`.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`'s
FR-01.02 table (lines 259-276): `AC01`=`C`, `AC02`=`14`, `AC03`=`1`, `AC04`=`2`,
`AC05`=`3`, `AC06`=`4`/`15` (merged), `AC07`=`4b`, `AC08`=`5`, `AC09`=`6`,
`AC10`=`7`, `AC11`=`8`, `AC12`=`9`, `AC13`=`10`, `AC14`=`11`, `AC15`=`12`.

## FR-01.02 — /shipwright-project

| AC | Disposition | Test(s) tagged | What it actually proves |
|---|---|---|---|
| AC01 | tested | `plugins/shipwright-run/tests/test_phase_validators_project.py::test_full_canon_project_passes` (happy path); `::test_legacy_pre_12_1_gate_still_fires` (the gating half — an empty catalogue actually FAILS) | Ledger row `C`: "a catalogue of individually deliverable requirements + starting guidance exists". The only seam that checks a NON-EMPTY catalogue (`_validate_project`, `plugins/shipwright-run/scripts/lib/phase_validators.py`) lives in a 3rd ADR-044 root beyond this unit's two originally-declared roots; campaign owner approved the extra root 2026-09-12 (`trg-704cdb22`, dismissed) — see the seam survey's t6 addendum. Corrected 2026-09-12 after Tier-3 PR-review correctly flagged that `test_full_canon_project_passes` alone only proves a valid catalogue passes, not that an absent one fails — added the `covers` tag to the pre-existing negative-case test in the same file, which already asserted exactly that. |
| AC02 | tested | `shared/tests/test_requirement_granularity_and_basis.py::test_fr_authoring_carries_the_granularity_section`, `::test_granularity_section_keeps_the_judgement_human` | `fr-authoring.md` §3a's granularity rule ("too broad -> divided", "judgement stays human, I6 advisory") — prompt-only per `requirement-elicitation.md` §6, drift-tested. |
| AC03 | **unbound — no seam** | none | "every capability the person described is present" — no doc anywhere instructs an interview-to-catalogue completeness cross-check; ledger row `1`, unchanged since 2026-07-24 walk. |
| AC04 | **unbound — no seam** | none | "nothing invented that was not asked for" — same as AC03, ledger row `2`. |
| AC05 | tested | `shared/tests/test_requirement_elicitation_rigor.py::test_spec_generation_requires_criteria_before_a_requirement_finishes` | `spec-generation.md`'s "Every FR with Priority \"Must\" MUST have acceptance criteria" instruction — prompt-only (no gate checks a row has >=1 criterion; `criteria_free_of_implementation_detail` vacuously passes zero criteria). |
| AC06 | tested | `shared/tests/test_project_gate_extras.py::test_basis_forbids_assumed_fails_on_a_bare_assumed_cell`, `::test_basis_forbids_assumed_passes_on_a_bare_assumed_cell_with_a_criterion`; `shared/tests/test_verifiers_project.py::test_run_project_checks_includes_all_four_new_gates` (wiring) | `basis_forbids_assumed` — a bare `assumed` cell is a hit only without a paired criterion; wired into `run_project_checks`. |
| AC07 | tested | `shared/tests/test_verifiers_project.py::test_run_project_checks_detects_grill_trace_blank_dimension` (wiring); `shared/tests/test_verify_grill_trace_completeness.py::test_blank_dimension_fails_on_a_missing_key` (pure function) | The grill-trace `blank_dimension` STOP — every one of the six context dimensions must be answered/assumed/n-a, both at the pure-function level and wired into the project phase's own Step 8 gate. |
| AC08 | tested | `shared/tests/test_project_gate_extras.py::test_criteria_free_of_implementation_detail_passes_on_clean_criteria`, `::test_criteria_free_of_implementation_detail_fails_on_a_code_symbol`; wiring via the same `test_run_project_checks_includes_all_four_new_gates` | `criteria_free_of_implementation_detail` — no file path/ADR/code-symbol/verb in a criterion. |
| AC09 | tested | `shared/tests/test_fr_authoring_refs.py::test_project_positively_states_the_plain_language_rule` | `spec-generation.md`'s plain-business-language + product-owner + "never drop a guarantee" rule — prompt-only (I2 advisory, no gate). |
| AC10 | tested | `shared/tests/test_verify_grill_trace_completeness.py::test_undefined_term_fails_when_a_declared_term_is_in_neither_source`, `::test_glossary_delta_declared_fails_when_a_delta_term_is_missing_from_terms_used` | The grill-trace `undefined_term`/`glossary_delta_declared` STOPs — a used term must be known or captured; wiring proven generically by the AC07 wiring tests over the same `check_grill_trace_completeness` dispatch. |
| AC11 | tested | `shared/tests/test_requirement_elicitation_rigor.py::test_module_requires_hard_to_reverse_rationale_linked_from_the_requirement` (link-back rule, prompt-only); `shared/tests/test_verifiers_project.py::test_run_project_checks_detects_missing_c4_adr` (floor: an ADR exists at all, enforced) | Conjunctive AC: floor enforced by C4, link-back half prompt-only per ledger row `8b`'s own D7 abort condition. |
| AC12 | tested | `plugins/shipwright-project/tests/test_assumptions_first_block.py::test_assumptions_listed_before_clarifying_questions`, `::test_kern_step_1_surfaces_assumptions_first` | Pre-existing OS2 assumptions-first drift test (ledger row `9`, "the one guarantee here that is genuinely built"). |
| AC13 | tested | `shared/tests/test_project_gate_extras.py::test_no_empty_split_passes_when_every_spec_has_a_row`, `::test_no_empty_split_fails_when_one_split_has_no_active_fr_row` (floor, pure function); `::test_split_heuristics_still_demands_cohesive_purpose` (judgement half, drift-tested); wiring via `test_run_project_checks_includes_all_four_new_gates` | `no_empty_split` (zero-row floor, enforced) + `split-heuristics.md`'s cohesive-purpose prose (judgement half). |
| AC14 | tested | `shared/tests/test_project_gate_extras.py::test_starting_guidance_present_passes_when_all_four_are_non_empty`, `::test_starting_guidance_present_fails_when_a_file_is_missing` | `starting_guidance_present` — CLAUDE.md + the three agent_docs files exist and are non-empty. |
| AC15 | tested | `shared/tests/test_fr_authoring_refs.py::test_iterate_paths_forbid_silently_deleting_a_retired_fr` (moved to a retired section, not deleted — prompt-only, no code seam exists for this clause per Stage-1 spec-review); `shared/tests/test_drift_parsers.py::test_parse_fr_table_excludes_removed_requirements_section` (excluded from live coverage counting); `plugins/shipwright-compliance/tests/test_audit_group_i.py::test_retired_fr_number_must_not_be_reused` (number stays permanently taken) | AC15 is conjunctive (3 clauses); together these three tests, in three different roots, cover all three. Corrected 2026-09-12 after Stage-1 spec-review (spec-reviewer) correctly rejected an earlier version of this row that claimed two tests already covered all three clauses — neither actually exercised the "not deleted" clause, and no code anywhere enforces it (`_layer_coverage_removal.py`'s removal gate and I4's number-reuse check both tolerate outright deletion). The rule turned out to be prompt-only, stated verbatim in `path-a-feature.md`/`path-b-change.md`'s REMOVE-classification instruction ("never silently delete"); a new drift test pins it. The "number stays taken" clause's only seam is the Group I audit, in a 3rd/4th ADR-044 root beyond this unit's two originally-declared roots; campaign owner approved the extra root (2026-09-12, `trg-704cdb22`, dismissed) alongside AC01. |

## FR-01.16 — Guided requirement elicitation

| AC | Disposition | Test(s) tagged | What it actually proves |
|---|---|---|---|
| AC01 | tested | `shared/tests/test_verify_grill_trace_completeness.py::test_blank_dimension_passes_when_all_seven_are_answered_or_assumed_or_na`, `::test_blank_dimension_fails_on_a_missing_key` | Every dimension is answered/assumed/n-a — the three-way classification AC01 names. |
| AC02 | tested | `shared/tests/test_requirement_elicitation_refs.py::test_module_retains_cited_sections` (parametrized over all 13 sections incl. §2/§3); `shared/tests/test_requirement_elicitation_discovery.py::test_elicitation_surface_cites_the_module` | The shared method's sections exist AND every elicitation surface (project/adopt/iterate) actually cites it. |
| AC03 | tested | `shared/tests/test_requirement_elicitation_refs.py::test_module_pins_the_execution_order_rule_by_sentence` | §0's "the order is load-bearing" rule, verbatim. |
| AC04 | tested | `shared/tests/test_requirement_elicitation_refs.py::test_module_pins_the_glossary_cross_check_trigger_by_sentence` | §4's glossary cross-check trigger, verbatim. |
| AC05 | tested | `shared/tests/test_requirement_elicitation_refs.py::test_module_pins_the_minimum_two_scenarios_rule_by_sentence` | §5's minimum-two-scenarios rule, verbatim. |
| AC06 | tested | `shared/tests/test_requirement_elicitation_rigor.py::test_module_requires_adr_capture_at_the_decision_moment` (new) | §7's "captured at the moment it is decided" + CONTEXT.md's "totally devoid of implementation detail" rules, verbatim (normalized whitespace). |
| AC07 | tested | `shared/tests/test_requirement_elicitation_rigor.py::test_assumed_is_only_for_unobtainable_answers`; `shared/tests/test_verify_grill_trace_completeness.py::test_blank_dimension_passes_when_all_seven_are_answered_or_assumed_or_na` (reused) | "guess only where genuinely unobtainable" (doc-level) + "every dimension answered or marked" (code-level). |
| AC08 | tested | `shared/tests/test_requirement_elicitation_rigor.py::test_module_requires_confirmation_before_writing_the_requirement` (new) | §9's confirm-before-writing rule, verbatim (normalized whitespace). |
| AC09 | tested | `shared/tests/test_requirement_elicitation_discovery.py::test_discovery_finds_at_least_the_known_citing_docs`, `::test_discovery_is_dynamic_a_new_reference_doc_is_picked_up`, `::test_elicitation_surface_cites_the_module` | Discovery-not-a-hand-maintained-list mechanism (AC09's own subject). |
| AC10 | tested | `shared/tests/test_requirement_elicitation_rigor.py::test_module_separates_enforced_from_prompt_only` | The disclaimer's establishable half: the method exists whole and the three-way verdict framework it depends on is real (§6). |

## Regeneration provenance (external plan review, glm, low)

`shipwright_ac_coverage_baseline.json` was regenerated by: (1) running
`plugins/shipwright-compliance/scripts/lib/collectors/test_links.py`'s
`generate_file()` against the worktree to produce a FRESH (uncommitted)
`.shipwright/compliance/test-traceability.json` reflecting every `@covers` tag
in the tree at this commit; (2) running
`shared/scripts/tools/check_ac_coverage_ratchet.py --write --project-root .`
against that fresh manifest; (3) reverting the manifest file itself
(`git checkout -- .shipwright/compliance/test-traceability.json`) since the
manifest is the compliance phase's (t7) own artifact, refreshed wholesale
there — committing a partial, ad-hoc regeneration here would misrepresent it
as current for FRs this unit never touched. Verified reproducible: re-running
steps (1)-(2) on the final branch state reports `status: clean`,
`unbound_count == baseline_count == 108`, `new_unbound: []`.
