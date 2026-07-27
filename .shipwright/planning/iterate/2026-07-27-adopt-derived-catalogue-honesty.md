# Iterate Spec: adopt-derived-catalogue-honesty

- **Run ID:** iterate-2026-07-27-adopt-derived-catalogue-honesty
- **Type:** feature
- **Complexity:** medium
- **Status:** draft
- **Triage:** `trg-1aa5a8ab` (REQ-3 Phase 2 walk, FR-01.13, P1/high)
- **Mode:** `--autonomous` — the operator handed a complete, self-contained
  brief and asked for an unattended run. Interview (§G) and the medium
  User-Approval gate are therefore **skipped by explicit instruction**, recorded
  in `degraded[]`. Everything else runs at full medium rigor.

## Goal

Make `/shipwright-adopt` describe an onboarded repository **honestly**: say out
loud that its requirements catalogue was derived by reading code and confirmed
by nobody, leave a tracked follow-up to question that catalogue with a person,
and record inherited test failures and untested capabilities as *inherited*
rather than as the project's own.

## Scope boundary (OWNS)

The onboarding plugin's artifact writers and its handover step —
`plugins/shipwright-adopt/**` only. The **consumer** half of the inherited
baseline (the test phase reading it, journey-coverage routing, retry reporting)
belongs to `trg-12b4cf3f`, and the grill module's *wiring into* adopt/project
belongs to `trg-e9fa7c49`. Neither is touched here.

## Acceptance Criteria

These implement three (E) criteria already standing in FR-01.13 (added by
REQ-3 Phase 2, #436, as `unimplemented`).

- [ ] **AC1 — the catalogue announces itself.** The generated
  `.shipwright/planning/<split>/spec.md` carries a provenance block, above the
  FR table, stating in plain words that the requirements were derived from the
  codebase, how many there are, and that none has been confirmed by a person.
  The block is prose (never a Markdown table row), so no FR-table reader,
  layers resolver, or audit parser changes meaning.
- [ ] **AC2 — the count is machine-readable.** Adopt writes
  `.shipwright/adopt/derived-catalogue.json` — schema-versioned, one entry per
  derived requirement (`fr_id`, `name`, `basis`, `confirmed`), plus totals and
  a per-basis tally — so traceability, coverage and drift consumers can read
  "unconfirmed" without parsing prose.
- [ ] **AC3 — the count is reported at handover.** The Step H adoption commit
  message and the Step H handoff banner both state how many requirements are
  derived and unconfirmed, and name the follow-up that resolves them.
- [ ] **AC4 — onboarding leaves the questioning follow-up.** Adopt files one
  tracked, idempotent triage item asking that the derived requirements be taken
  through `shared/requirement-elicitation.md` with a person. It names the count
  and the spec path, and dedupes so a re-adopt never doubles it.
- [ ] **AC5 — inherited failures are recorded as inherited.** Adopt writes
  `shipwright_known_failures.json` in the exact shape the audit phase already
  reads (`known_failures[]` + `baseline_failure_count`), so a red test that
  predates onboarding is attributable to the inherited codebase. The register
  states whether a baseline run was actually observed — an unobserved baseline
  reads as `baseline_observed: false`, never as "clean".
- [ ] **AC6 — untested capabilities are recorded as inherited gaps, and never
  launder a failure.** The same register carries `inherited_coverage_gaps`
  (requirements with no `@FR`-tagged test + pre-existing disabled tests) in a
  **separate** block that does not contribute to `baseline_failure_count` — a
  missing test is not a failure and must never excuse one.
- [ ] **AC7 — the gaps route to onboarding, not to a blocked run.** Each
  non-empty gap class leaves a tracked triage follow-up (idempotent), which is
  the destination the test phase's journey-coverage routing needs.
- [ ] **AC8 — the run cannot silently skip it.** `validate_adoption.py` hard-
  errors when either artifact is missing, so Step H stops rather than handing
  over a catalogue that looks confirmed.

## Spec Impact

- **Classification:** `none`
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** the three acceptance criteria this iterate implements
  were written into **FR-01.13** by REQ-3 Phase 2 (#436) and carded as
  `unimplemented` → `trg-1aa5a8ab`. This iterate builds the mechanism that makes
  them true; it changes no requirement text. `affected_frs: ["FR-01.13"]`.

## Out of Scope

- The **test phase** reading `shipwright_known_failures.json`, per-journey
  coverage checks, warning-only-layer follow-ups, retry-pass reporting —
  `trg-12b4cf3f`, owns the test plugin.
- Wiring the grill module *into* adopt's Step C interview and building the
  elicitation evidence trail — `trg-e9fa7c49` (Phase 4, interactive).
- Adding a `Confirmation` column to the FR table. `shared/scripts/lib/
  fr_table_shape.FR_TABLE_COLUMNS` is a frozen two-sided contract shared with
  the greenfield producer and the compliance reader; changing it would touch
  three other plugins and break this iterate's OWNS boundary.
- Putting `(unconfirmed)` in the `Basis` cell. `fr_basis.classify` treats a
  known value carrying a qualifier as **malformed and blocking** (audit check
  `I5`) — verified by reading `shared/scripts/lib/fr_basis.py:108-120`.
- Running the adopted repo's test suite unattended. The register accepts an
  observed baseline; discovering one is the operator's call, and an unobserved
  baseline is recorded as unobserved rather than guessed.

## Design Notes

No UI. Two new pure-ish modules under `plugins/shipwright-adopt/scripts/lib/`
(`derived_catalogue.py`, `inherited_baseline.py`), one new tool
(`scripts/tools/record_inherited_baseline.py`), one new Kern step **E.18** with
its reference doc.

**Kern LOC landmine:** `skills/adopt/SKILL.md` is at exactly 300 lines and
`tests/test_skill_references_link.py::test_kern_skill_md_under_300_loc` caps it
there. Step E.18 is added only after trimming the Step E prose that the linked
`step-e-artifact-generation.md` already carries verbatim.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `derived_catalogue.write_summary` | `record_inherited_baseline` (fr ids), WebUI/future consumers | JSON `.shipwright/adopt/derived-catalogue.json` |
| `inherited_baseline.build_register` | `shipwright-compliance` `collectors/test_evidence.collect_known_failures` | JSON `shipwright_known_failures.json` |
| `derived_catalogue.render_provenance_banner` (in `spec.md`) | `fr_table_reader`, `traceability_layers`, compliance Group I | Markdown |
| `seed_traceability_baseline` (backfill report + skip inventory) | `record_inherited_baseline` | JSON |

`touches_io_boundary` fires (new `*_config`-adjacent JSON producers + `json.dump`).
Boundary Probe + round-trip tests are therefore **mandatory**, not advisory.

## Confidence Calibration

- **Boundaries touched:** the four rows above.

- **Empirical probes run** (each one changed something):
  1. *Does a prose block above the FR table change what a reader sees?* Rendered
     the section with and without the banner, parsed both with the real
     `fr_table_reader` → **identical `cells` tuples**. Repeated with a
     pipe-bearing description and a pipe-bearing split name.
  2. *Can `(unconfirmed)` ride on the `Basis` cell?* Read
     `shared/scripts/lib/fr_basis.py:108-120` → a known value carrying a
     qualifier classifies as **malformed → blocking** (audit `I5`). **Design
     changed:** the marking moved from the row to the catalogue.
  3. *Does anything write `shipwright_known_failures.json` today?* Repo-wide
     grep → **no producer**, one consumer (`collect_known_failures`). Confirms
     the file was a consumer contract with no writer.
  4. *Is there a strict schema that additive keys would break?* (external review
     G1) `shared/schemas/` holds exactly three schemas, none for known-failures
     → **finding declined on evidence.**
  5. *Does the compliance collector actually read what adopt writes?* Ran the
     REAL collector in a subprocess against a written register →
     `baseline == 2`, failures round-tripped. Also for the unobserved case →
     `([], 0)`, byte-identical to the no-file behaviour.
  6. *Does `_load_shared` survive a module containing dataclasses?* It did
     **not** — `fr_basis` raised `AttributeError` in `@dataclass` because the
     module was registered in `sys.modules` only after `exec_module`. **Fixed
     the loader** (register-before-exec + unwind on failure).
  7. *Would the diff ratchet a grandfathered file?* Measured all ten baseline
     entries → three would have (**+24 / +16 / +17**). **Restructured**:
     `spec_document.py` extracted, `artifact_writer.py` 690 → **590** and its
     baseline tightened. Re-measured: **zero ratchets.**
  8. *Does the new strict reader reject a real-world mistake?* It immediately
     rejected a fixture **in this iterate** that sliced `requirements` to one row
     while leaving `total: 3`. The guard's first catch was its own author's.
  9. **F0.5 surface run** (`cli`, real executables, cwd = project_root):
     `exit_code 0`, `tests_run 25` — the E.18 CLI, the spec/summary contract, and
     the full adopt-pipeline subprocess.
  10. *Is `confirmed` safe once it must be a real boolean?* **No** — a
      count-consistent document setting every row to `{"basis": "code",
      "confirmed": true}` still passed and suppressed the follow-up. Found by the
      round-3 fresh review that the CI gate's fail-closed forced. **Fixed:**
      `confirmed` must equal `basis in CONFIRMED_BASES`, checked in both
      directions.
  11. *Is the provenance block true for every catalogue?* **No** — it said
      "nobody has confirmed them yet" unconditionally, which is false the moment
      the elicitation follow-up lands its first answer. **Fixed:** three variants
      rendered from the counts; all three re-checked for table-shaped lines.
  12. *Did the `write_spec` return-type change break an unshown caller?* Repo-wide
      grep → only `generate_adoption_artifacts` and two test modules, all updated
      → **finding declined on evidence.**
  13. *Does the lazy `spec_table` import survive another plugin's session?*
      **No** — after merging `origin/main` the cross-plugin F0 went RED on
      `shipwright-compliance::test_adopt_emission_round_trips`, which imports
      adopt's `_render_spec_md` after binding its own `lib`. A name-based import
      resolves whatever the *process* bound, so the whole chain vanished.
      **Fixed** by path-loading `spec_table` under a sentinel with both
      `scripts/` and `scripts/lib` on `sys.path`, and pinned by a hostile-binding
      regression test. Adopt's own suite could never have caught this.

- **Test Completeness Ledger** — 0 untested-testable.

  | # | Testable behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | spec.md carries a derived-and-unconfirmed provenance block naming the count | tested | `test_spec_document::test_the_spec_says_the_catalogue_is_derived_and_unconfirmed` PASSED |
  | 2 | the block changes no FR-table reader's view of the rows | tested | `test_derived_catalogue::test_the_reader_sees_the_same_rows_with_and_without_the_banner`, `::test_banner_contains_no_table_row`, `test_spec_document::test_the_banner_does_not_disturb_the_table` PASSED |
  | 3 | the block interpolates no free text, so a `\|` cannot reach it | tested | `test_derived_catalogue::test_banner_interpolates_no_free_text`, `test_spec_document::test_pipes_in_detected_text_survive_the_round_trip` PASSED |
  | 4 | `derived-catalogue.json` is schema-versioned and lists every derived row | tested | `test_derived_catalogue_doc::test_document_is_schema_versioned_and_carries_every_row` PASSED |
  | 5 | the JSON describes the table actually rendered (anti-drift) | tested | `test_derived_catalogue::test_json_summary_matches_the_table_the_reader_actually_parses`, `test_spec_document::test_the_summary_describes_the_table_that_was_actually_rendered` PASSED |
  | 6 | a zero-detection repo's placeholder row is counted, not reported as 0 | tested | `test_derived_catalogue::test_a_zero_detection_repo_summarizes_the_placeholder_row`, `test_spec_document::test_a_zero_detection_repo_still_agrees` PASSED |
  | 7 | nothing adopt derives today counts as confirmed; `interview` does | tested | `test_derived_catalogue::test_nothing_adopt_derives_today_counts_as_confirmed`, `::test_an_interview_backed_row_is_confirmed` PASSED |
  | 8 | an explicitly declared vocabulary `Basis` survives re-rendering | tested | `test_spec_table::test_an_explicitly_declared_basis_survives_re_rendering` PASSED |
  | 9 | a declared `Basis` outside the vocabulary is ignored, never emitted | tested | `test_spec_table::test_a_declared_basis_outside_the_vocabulary_is_ignored_not_passed_through` (5 cases) PASSED |
  | 10 | every emitted `Basis` passes the audit vocabulary | tested | `test_derived_catalogue::test_every_emitted_basis_passes_the_audit_vocabulary` PASSED |
  | 11 | the commit body reports the unconfirmed count and names the follow-up | tested | `test_adopt_commit_template::test_the_body_reports_how_many_requirements_are_unconfirmed` PASSED |
  | 12 | the count cannot be silently omitted from the handover | tested | `test_adopt_commit_template::test_the_count_cannot_be_omitted` PASSED |
  | 13 | onboarding files exactly one confirmation follow-up | tested | `test_record_inherited_baseline::test_onboarding_leaves_exactly_one_confirmation_follow_up` PASSED |
  | 14 | a re-adopt duplicates no card | tested | `test_record_inherited_baseline::test_a_re_adopt_duplicates_nothing` PASSED |
  | 15 | the card's dedup key does not vary with the count; figures are as-of | tested | `test_derived_catalogue_doc::test_confirmation_card_dedup_key_does_not_vary_with_the_count`, `::test_the_card_states_its_count_as_of_onboarding` PASSED |
  | 16 | no card when every requirement was confirmed | tested | `test_derived_catalogue_doc::test_no_card_when_every_requirement_was_confirmed_by_a_person` PASSED |
  | 17 | the register carries the two keys the audit phase reads | tested | `test_inherited_baseline::test_register_carries_the_two_keys_the_audit_phase_reads` PASSED |
  | 18 | the real compliance collector reads back what adopt wrote | tested | `test_inherited_baseline_input::test_the_compliance_collector_reads_back_what_adopt_wrote` PASSED (subprocess, real consumer) |
  | 19 | an unobserved baseline says so and never reads as forgiveness | tested | `test_inherited_baseline::test_an_unobserved_baseline_says_so_rather_than_claiming_clean`, `test_inherited_baseline_input::test_an_unobserved_register_reads_as_zero_baseline_not_as_forgiveness` PASSED |
  | 20 | coverage gaps never feed `baseline_failure_count` | tested | `test_inherited_baseline::test_gaps_never_feed_the_number_that_excuses_failures` PASSED |
  | 21 | requirements with no tagged test are inherited gaps; both tag origins count | tested | `test_inherited_baseline::test_a_requirement_with_no_tagged_test_is_an_inherited_gap`, `::test_both_tag_origins_count_as_coverage` PASSED |
  | 22 | a tag naming an unknown FR is not coverage | tested | `test_inherited_baseline::test_a_tag_pointing_at_an_unknown_requirement_is_not_coverage` PASSED |
  | 23 | an observed red baseline lands as inherited failures | tested | `test_inherited_baseline::test_an_observed_red_baseline_is_recorded_as_inherited`, `test_record_inherited_baseline::test_an_observed_red_baseline_lands_as_inherited_failures` PASSED |
  | 24 | an observed green baseline is distinguishable from no run | tested | `test_inherited_baseline::test_an_observed_green_baseline_is_observed_and_empty` PASSED |
  | 25 | a failure list without provenance / malformed / self-inconsistent is rejected | tested | `test_inherited_baseline_input::test_a_failure_list_without_provenance_is_rejected`, `::test_a_malformed_payload_is_rejected_rather_than_read_as_empty` (5 cases), `::test_a_declared_count_that_disagrees_with_the_list_is_rejected` PASSED |
  | 26 | only the five fields the collector reads are copied (no secret carry-over) | tested | `test_inherited_baseline_input::test_only_the_fields_the_audit_phase_reads_are_copied` PASSED |
  | 27 | each non-empty gap class leaves a follow-up; empty leaves none | tested | `test_inherited_baseline::test_each_non_empty_gap_class_leaves_a_follow_up`, `::test_an_empty_gap_class_leaves_nothing_behind` PASSED |
  | 28 | gap cards read as inherited absence, not as breakage | tested | `test_inherited_baseline::test_gap_cards_describe_the_gap_without_pointing_at_a_failure` PASSED |
  | 29 | a clean repo records a register and crashes on nothing | tested | `test_inherited_baseline::test_a_clean_repo_has_empty_gaps_not_a_crash`, `test_record_inherited_baseline::test_a_clean_repo_records_a_register_and_no_gap_cards` PASSED |
  | 30 | a missing catalogue stops the step and names the step that writes it | tested | `test_record_inherited_baseline::test_a_missing_catalogue_stops_the_step_and_names_the_step_that_writes_it` PASSED |
  | 31 | a corrupt upstream artifact stops rather than inventing gaps | tested | `test_record_inherited_baseline::test_a_corrupt_upstream_artifact_stops_rather_than_inventing_gaps` PASSED |
  | 32 | a catalogue that lies about confirmation cannot suppress the follow-up | tested | `test_derived_catalogue_doc::test_a_truthy_string_is_not_confirmation`, `::test_a_malformed_catalogue_is_rejected` (7 cases), `::test_a_document_that_contradicts_its_own_entries_is_rejected`, `test_record_inherited_baseline::test_a_catalogue_that_lies_about_confirmation_stops_the_step` PASSED |
  | 33 | `--dry-run` touches nothing | tested | `test_record_inherited_baseline::test_dry_run_touches_nothing` PASSED |
  | 34 | a missing honesty artifact hard-blocks the handover, naming its step | tested | `test_validate_adoption_soft_checks::test_a_missing_honesty_artifact_blocks_the_handover` (2 cases), `::test_the_error_names_the_step_that_writes_the_missing_file` PASSED |
  | 35 | Step H's reference doc names the artifact, the kwarg and the follow-up | tested | `test_skill_references_link::test_step_h_reference_tells_the_agent_where_the_count_comes_from` PASSED |
  | 36 | the wired-up generator writes both artifacts and they agree | tested | `test_adopt_pipeline_subprocess` (real CLI) + `test_spec_document` PASSED; F0.5 `tests_run 24, exit 0` |
  | 37 | `effective_features` is the one answer to "which rows exist", and does not alias its input | tested | `test_spec_table::test_effective_features_*` (3 cases) PASSED |
  | 38 | confirmation cannot be claimed without an interview basis (either direction) | tested | `test_derived_catalogue_doc::test_confirmation_cannot_be_claimed_without_an_interview_basis`, `::test_an_interview_row_claiming_to_be_unconfirmed_is_also_rejected`, e2e `test_record_inherited_baseline::test_a_catalogue_claiming_confirmation_without_an_interview_stops_the_step` PASSED |
  | 39 | a row without a basis is rejected; an interview-backed document still round-trips | tested | `test_derived_catalogue_doc::test_a_row_without_a_basis_is_rejected`, `::test_an_interview_backed_document_round_trips` PASSED |
  | 40 | the provenance block states what is true of THIS catalogue (all-derived / partly confirmed / fully confirmed) | tested | `test_derived_catalogue::test_a_partly_confirmed_catalogue_does_not_claim_nobody_confirmed_it`, `::test_a_fully_confirmed_catalogue_says_so_and_asks_for_nothing`, `::test_an_all_derived_catalogue_still_says_nobody` PASSED |
  | 41 | no banner variant emits a table row | tested | `test_derived_catalogue::test_no_banner_variant_emits_a_table_row` PASSED (3 variants) |
  | 42 | `summarize` still resolves `spec_table` when `lib` belongs to ANOTHER plugin (ADR-045) | tested | `test_derived_catalogue::test_summarize_works_when_lib_belongs_to_another_plugin` PASSED (subprocess, hostile binding); the defect it pins was caught by the cross-plugin F0 via `shipwright-compliance::test_adopt_emission_round_trips`, now green |
  | 43 | the Step H handoff *banner* renders these counts | untestable | `covered-by-existing-test` — the banner is prompt-rendered text, not code; what IS mechanical (the required kwarg, the doc naming the source) is rows 12 and 35. Stated as a limitation, not hidden. |

- **Confidence-pattern check.**
  *Asymptote (depth):* yes — **four times**, and the last one is the instructive
  one. The run looked complete before probe 6 (the dataclass loader), before
  probe 7 (the bloat ratchet), and before the round-2 review found the
  `bool("false")` hole. It then looked complete again — and the CI review gate
  failing **closed** on diff truncation forced a fresh full-context review, which
  found that fixing `bool("false")` had not actually closed the hole: a
  count-consistent `{"basis": "code", "confirmed": true}` still passed. The
  pattern to take seriously is that each "surely now" was wrong, including after
  a clean two-model review.
  *Coverage (breadth):* 43 behaviors enumerated, 42 `tested`, 1 `untestable`
  with a closed-vocabulary reason, **0 untested-testable**. 8 acceptance
  criteria, all covered.
  *Integration composition:* `cross_component` does **not** fire — the diff
  touches no merge/churn resolver, no `hooks.json`, no phase validator, no
  campaign driver. The genuine composition risk here is producer↔consumer, and
  it is covered by running the real compliance collector in its own interpreter
  (row 18) rather than by asserting on a shape.

## Verification (medium+)

- **Surface:** `cli`
- **Runner command:** `uv run --directory plugins/shipwright-adopt --extra dev pytest tests/test_record_inherited_baseline.py tests/test_spec_document.py tests/test_adopt_pipeline_subprocess.py -q`
- **Result:** `exit_code 0`, `tests_run 25`
- **Evidence path:** `.shipwright/runs/iterate-2026-07-27-adopt-derived-catalogue-honesty/surface_verification.json`
- **Justification (if surface=none):** n/a — real executables drive the new E.18
  CLI and the full adopt artifact pipeline as subprocesses against temp repos.
