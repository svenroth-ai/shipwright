# Iterate Spec: adopt-derived-catalogue

- **Run ID:** iterate-2026-07-27-adopt-derived-catalogue
- **Type:** feature
- **Complexity:** medium
- **Status:** draft
- **Triage:** `trg-1aa5a8ab` (REQ-3 Phase 2 walk, FR-01.13, P1/high) — **part 1 of 2**
- **Mode:** `--autonomous`. Interview and the medium approval gate are skipped by
  explicit instruction; recorded in `degraded[]`.

## Why this is half a card

`trg-1aa5a8ab` carries three items. Delivered whole (PR #440) they made a
5,079-line diff that the Tier-3 `PR Review` gate **failed closed** on: it could
not read the diff whole (~51.5k tokens, 18 generated files already excluded) and
correctly refused to bless it. The `skip-pr-review` override is ignored for a
diff touching `plugins/*/skills/` (FR-01.17 (E)7, #437) — a change to the checks
cannot exempt itself.

Splitting is not a workaround for that gate; it is what lets the gate **work**.
Measured: this half ≈33k tokens, the other ≈26k — both under budget, so both get
a real automated review instead of a human waving 50 files through.

The seam is one written artifact, not shared code:

| | |
|---|---|
| **This PR** | the derived catalogue announces itself and its count reaches the handover. **Writes** `.shipwright/adopt/derived-catalogue.json`. |
| **Next PR** | the inherited-baseline register + Step E.18 + the confirmation follow-up. **Reads** that artifact. |

## Goal

Make the requirements catalogue `/shipwright-adopt` produces say, in the handed-
over repository, that it was derived by reading code and confirmed by nobody —
and report how many at handover.

## Acceptance Criteria

Implements two of the three (E) criteria standing in FR-01.13 (added by REQ-3
Phase 2, #436, as `unimplemented`). The third — the tracked follow-up — needs a
step that runs after the Triage Inbox exists, and ships in the next PR.

- [ ] **AC1 — the catalogue announces itself.** The generated `spec.md` carries a
  provenance block above the FR table stating that the requirements were derived
  from the codebase, how many there are, and how many nobody has confirmed. Prose
  only, never a Markdown table row, so no FR-table reader changes meaning.
- [ ] **AC2 — the block tells the truth about THIS catalogue.** All-derived,
  partly confirmed and fully confirmed each render differently. A fixed "nobody
  has confirmed them" sentence would be false the moment a row is
  `Basis: interview`.
- [ ] **AC3 — the count is machine-readable.** `.shipwright/adopt/derived-catalogue.json`,
  schema-versioned, one entry per requirement (`fr_id`, `name`, `basis`,
  `confirmed`) plus totals and a per-basis tally.
- [ ] **AC4 — the JSON and the rendered table cannot disagree.** Both come from
  one `spec_table.effective_features` pass through one writer.
- [ ] **AC5 — reading it back fails closed.** `confirmed` must be a real boolean
  **and** must equal `basis in CONFIRMED_BASES`; a document contradicting its own
  totals is rejected. A catalogue cannot claim a confirmation nobody gave.
- [ ] **AC6 — the count is reported at handover.** The adoption commit message
  states how many requirements are derived-and-unconfirmed, via a **required**
  kwarg a caller cannot silently omit.
- [ ] **AC7 — the run cannot silently skip it.** `validate_adoption.py` hard-errors
  when the artifact is missing, naming the step that writes it.

## Spec Impact

- **Classification:** `none`
- **NONE justification:** the criteria implemented here were written into
  **FR-01.13** by REQ-3 Phase 2 (#436) and carded `unimplemented` →
  `trg-1aa5a8ab`. This builds the mechanism; it changes no requirement text.
  `affected_frs: ["FR-01.13"]`.

## Out of Scope

- **The confirmation follow-up card** and everything that files it (Step E.18).
  It must run after Step E.16 scaffolds the Triage Inbox. Deliberate consequence:
  nothing here claims a card was filed — the commit body and banner point at
  `shared/requirement-elicitation.md` instead. Claiming an unfiled card would be
  exactly the dishonesty this change removes.
- **The inherited-baseline register** (`shipwright_known_failures.json`) and its
  validator entry. A validator demanding a file no step writes would break every
  adopt run between the two merges, so the check arrives with its producer.
- The test phase reading that register — `trg-12b4cf3f`.
- A `Confirmed` column in the FR table (`FR_TABLE_COLUMNS` is a frozen two-sided
  contract) or `(unconfirmed)` on `Basis` (`fr_basis.classify` scores a qualified
  vocabulary value as malformed-and-blocking, audit `I5`).

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `spec_document.write_spec` → `derived_catalogue_doc.write_summary` | Step H handover; the next PR's Step E.18 | JSON `.shipwright/adopt/derived-catalogue.json` |
| `derived_catalogue.render_provenance_banner` (in `spec.md`) | `fr_table_reader`, `traceability_layers`, compliance Group I | Markdown |

`touches_io_boundary` fires. Boundary probes are mandatory.

## Confidence Calibration

- **Boundaries touched:** the two rows above.

- **Empirical probes run** (carried from the combined run; each changed something):
  1. Banner above the table → parsed with the real `fr_table_reader` with and
     without it: **identical `cells` tuples**, incl. pipe-bearing text.
  2. `(unconfirmed)` on `Basis` → `fr_basis.py:108-120` scores it **malformed →
     blocking**. Design moved from the row to the catalogue.
  3. `_load_shared` + a dataclass-bearing module → `AttributeError`; the loader
     registered in `sys.modules` **after** `exec_module`. Loader fixed.
  4. Bloat measurement → `artifact_writer` +24 would have ratcheted. Extracted
     `spec_document.py`: **690 → 590**, baseline tightened.
  5. `bool(confirmed)` → `"false"` reads as True. Made a real-boolean check.
  6. Real-boolean is still not enough → a count-consistent
     `{"basis": "code", "confirmed": true}` passed. Now `confirmed` must EQUAL
     `basis in CONFIRMED_BASES`, both directions.
  7. Banner wording → said "nobody has confirmed them" unconditionally, false
     once a row is `interview`. Three count-driven variants.
  8. Lazy `spec_table` import under a foreign `lib` → died inside compliance's
     session. Path-load under a sentinel with both `scripts/` and `scripts/lib`.
  9. **Split probe (new):** does PR1 claim anything it does not do? **Yes** — the
     commit body and Step H banner named a Triage card that only the next PR
     files. Reworded to point at the method instead.
  10. **F0.5** (`cli`, real executables): `exit_code 0`, `tests_run 52`.

- **Test Completeness Ledger** — 0 untested-testable.

  | # | Testable behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | spec.md carries the derived-and-unconfirmed block naming the count | tested | `test_spec_document::test_the_spec_says_the_catalogue_is_derived_and_unconfirmed` |
  | 2 | the block changes no FR-table reader's view of the rows | tested | `test_derived_catalogue::test_the_reader_sees_the_same_rows_with_and_without_the_banner`, `::test_banner_contains_no_table_row`, `test_spec_document::test_the_banner_does_not_disturb_the_table` |
  | 3 | the block interpolates no free text, so a `\|` cannot reach it | tested | `test_derived_catalogue::test_banner_interpolates_no_free_text`, `test_spec_document::test_pipes_in_detected_text_survive_the_round_trip` |
  | 4 | all-derived / partly confirmed / fully confirmed each render differently | tested | `test_derived_catalogue::test_a_partly_confirmed_catalogue_does_not_claim_nobody_confirmed_it`, `::test_a_fully_confirmed_catalogue_says_so_and_asks_for_nothing`, `::test_an_all_derived_catalogue_still_says_nobody` |
  | 5 | no banner variant emits a table row | tested | `test_derived_catalogue::test_no_banner_variant_emits_a_table_row` (3 variants) |
  | 6 | the JSON is schema-versioned and lists every derived row | tested | `test_derived_catalogue_doc::test_document_is_schema_versioned_and_carries_every_row` |
  | 7 | the JSON describes the table actually rendered | tested | `test_derived_catalogue::test_json_summary_matches_the_table_the_reader_actually_parses`, `test_spec_document::test_the_summary_describes_the_table_that_was_actually_rendered` |
  | 8 | a zero-detection repo's placeholder row is counted, not reported as 0 | tested | `test_derived_catalogue::test_a_zero_detection_repo_summarizes_the_placeholder_row`, `test_spec_document::test_a_zero_detection_repo_still_agrees` |
  | 9 | nothing adopt derives counts as confirmed; `interview` does | tested | `test_derived_catalogue::test_nothing_adopt_derives_today_counts_as_confirmed`, `::test_an_interview_backed_row_is_confirmed` |
  | 10 | an explicitly declared vocabulary `Basis` survives re-rendering | tested | `test_spec_table::test_an_explicitly_declared_basis_survives_re_rendering` |
  | 11 | a declared `Basis` outside the vocabulary is ignored, never emitted | tested | `test_spec_table::test_a_declared_basis_outside_the_vocabulary_is_ignored_not_passed_through` (5 cases) |
  | 12 | every emitted `Basis` passes the audit vocabulary | tested | `test_derived_catalogue::test_every_emitted_basis_passes_the_audit_vocabulary` |
  | 13 | a truthy string is not confirmation | tested | `test_derived_catalogue_doc::test_a_truthy_string_is_not_confirmation` |
  | 14 | confirmation cannot be claimed without an `interview` basis, either direction | tested | `test_derived_catalogue_doc::test_confirmation_cannot_be_claimed_without_an_interview_basis`, `::test_an_interview_row_claiming_to_be_unconfirmed_is_also_rejected` |
  | 15 | a malformed / self-contradicting document is rejected | tested | `test_derived_catalogue_doc::test_a_malformed_catalogue_is_rejected` (7 cases), `::test_a_document_that_contradicts_its_own_entries_is_rejected`, `::test_a_row_without_a_basis_is_rejected` |
  | 16 | an interview-backed document still round-trips | tested | `test_derived_catalogue_doc::test_an_interview_backed_document_round_trips` |
  | 17 | the commit body reports the unconfirmed count and points at the method | tested | `test_adopt_commit_template::test_the_body_reports_how_many_requirements_are_unconfirmed` |
  | 18 | the count cannot be silently omitted from the handover | tested | `test_adopt_commit_template::test_the_count_cannot_be_omitted` |
  | 19 | a missing artifact hard-blocks the handover, naming its step | tested | `test_validate_adoption_soft_checks::test_a_missing_honesty_artifact_blocks_the_handover`, `::test_the_error_names_the_step_that_writes_the_missing_file` |
  | 20 | Step H's reference doc names the artifact, the kwarg and the method | tested | `test_skill_references_link::test_step_h_reference_tells_the_agent_where_the_count_comes_from` |
  | 21 | `effective_features` is the one answer to "which rows exist", non-aliasing | tested | `test_spec_table::test_effective_features_*` (3 cases) |
  | 22 | both files are written together, spec first, idempotently | tested | `test_spec_document::test_both_files_are_written_spec_first`, `::test_a_re_run_overwrites_both_in_place` |
  | 23 | `summarize` survives `lib` bound to another plugin (ADR-045) | tested | `test_derived_catalogue::test_summarize_works_when_lib_belongs_to_another_plugin` (subprocess, hostile binding) |
  | 24 | the wired-up generator writes both artifacts and they agree | tested | `test_adopt_pipeline_subprocess::test_full_pipeline_e2e_via_subprocess`; F0.5 `tests_run 52` |
  | 25 | the Step H handoff *banner* renders these counts | untestable | `covered-by-existing-test` — prompt-rendered text, not code. What is mechanical is rows 18 and 20. |

- **Confidence-pattern check.**
  *Asymptote:* the combined run looked complete four separate times and was wrong
  each time (probes 3, 4, 6, 8). Probe 9 is this split's own: cutting the card in
  half exposed a claim PR1 would have made falsely.
  *Coverage:* 25 behaviors, 24 `tested`, 1 `untestable`, **0 untested-testable**;
  7 ACs, 7 covered.
  *Integration composition:* `cross_component` does not fire. The real risk is
  producer↔consumer and cross-plugin `lib` binding, covered by rows 23-24.

## Verification (medium+)

- **Surface:** `cli`
- **Runner:** `uv run --directory plugins/shipwright-adopt --extra dev pytest tests/test_spec_document.py tests/test_derived_catalogue.py tests/test_derived_catalogue_doc.py tests/test_adopt_pipeline_subprocess.py -q`
- **Result:** `exit_code 0`, `tests_run 52`
- **Evidence:** `.shipwright/runs/iterate-2026-07-27-adopt-derived-catalogue/surface_verification.json`
