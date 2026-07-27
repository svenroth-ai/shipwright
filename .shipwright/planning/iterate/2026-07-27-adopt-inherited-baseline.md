# Iterate Spec: adopt-inherited-baseline

- **Run ID:** iterate-2026-07-27-adopt-inherited-baseline
- **Type:** feature
- **Complexity:** medium
- **Status:** draft
- **Triage:** `trg-1aa5a8ab` (FR-01.13) — **part 2 of 2**, after #454
- **Mode:** `--autonomous`; interview and approval gate skipped by instruction.

## Goal

An onboarded project is not required to arrive perfect, only to arrive
**honestly described**. Record what the codebase arrived with — already-failing
tests, requirements no test covers, tests switched off — as **inherited**, not as
this project's own failures. And leave the tracked follow-up that takes the
derived catalogue to a person.

## What #454 left for this PR, and why

Two things could not ship in part 1:

- **the confirmation follow-up card** needs a step that runs *after* Step E.16
  scaffolds the Triage Inbox. Part 1 therefore claimed no card at all — its
  commit body pointed at the method instead, because naming an unfiled card
  would have been exactly the dishonesty the change removes;
- **the validator entry for the register** must ship with the step that writes
  the file. A validator demanding a file no step produces would have broken every
  adopt run between the two merges.

## Changed since the card was written: #453

`shared/scripts/known_failures.py` landed mid-flight as the **one reader** for
`shipwright_known_failures.json` — both the audit and the test phase go through
it. That is the consumer half of `trg-12b4cf3f`, delivered independently.

Consequences taken here:

- the boundary probe runs against `load_accepted_baseline`, not the compliance
  collector. Testing against a plugin-local copy would prove agreement with the
  wrong thing;
- that module's docstring called the file *"a hand-maintained declaration"*.
  Adopt now seeds it, so the line is corrected in the same diff rather than left
  contradicting observable behaviour;
- `baseline_observed` and the reader's `present` are **kept apart**: `present`
  answers *"is there a declaration?"*, `baseline_observed` answers *"did anyone
  run the suite?"*. A register can be present, well-formed, and still describe a
  run that never happened.

## Acceptance Criteria

- [ ] **AC1 — inherited failures are recorded as inherited.** Step E.18 writes
  `shipwright_known_failures.json` in the shape the shared reader parses.
- [ ] **AC2 — a coverage gap never launders a failure.** `inherited_coverage_gaps`
  sits beside `known_failures[]` and never contributes to
  `baseline_failure_count`, which is what excuses a red run.
- [ ] **AC3 — unobserved is not clean.** No baseline run ⇒
  `baseline_observed: false`, `baseline_source: "not_run"` — never a confident
  zero, and distinct from the reader's `present`.
- [ ] **AC4 — an untrustworthy baseline fails closed.** `source` and `command`
  must be real, non-empty strings; a declared count must be a non-boolean
  non-negative integer matching the entries; malformed input exits non-zero
  rather than writing an empty register.
- [ ] **AC5 — nothing sensitive reaches the committed register.** Only the five
  fields the reader reads are copied from each failure, and the `command` is
  required as evidence then **dropped** — `baseline_source` carries the short
  `source` label, length-bounded.
- [ ] **AC6 — onboarding leaves the questioning follow-up**, idempotent, naming
  its count as of onboarding.
- [ ] **AC7 — gaps route to onboarding, not to a blocked run.** One idempotent
  card per non-empty gap class.
- [ ] **AC8 — the register is written before the cards that point at it**, so a
  failed write cannot leave durable cards citing a file that does not exist.
- [ ] **AC9 — the run cannot silently skip it.** `validate_adoption.py` hard-errors
  on the missing register, naming Step E.18.

## Spec Impact

- **Classification:** `none` — implements (E) criteria already in FR-01.13
  (#436), carded `unimplemented` → `trg-1aa5a8ab`. `affected_frs: ["FR-01.13"]`.

## Out of Scope

- The test phase *consuming* the register — `trg-12b4cf3f`, partly delivered by
  #453.
- Running an adopted repo's suite unattended to discover a baseline. The register
  accepts an observed run; discovering one is the operator's call.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `inherited_baseline.write_register` | `shared/scripts/known_failures.load_accepted_baseline` (audit + test phase) | JSON `shipwright_known_failures.json` |
| `record_inherited_baseline` | `shared/scripts/triage` (idempotent cards) | JSONL |
| Step E's `derived-catalogue.json` | `record_inherited_baseline` via `read_summary` | JSON |

## Confidence Calibration

- **Boundaries touched:** the three rows above.

- **Empirical probes run:**
  1. Does the producer's shape match the **new** shared reader? Ran
     `load_accepted_baseline` in a subprocess against a written register →
     `baseline`, entries and `present`/`malformed` all as intended.
  2. Does `present` mean what `baseline_observed` means? **No** — pinned as
     distinct facts in the same test.
  3. Does the whitelist actually close the privacy boundary? **No, it did not.**
     `baseline_source` persisted the raw `command`, so `TOKEN=… pytest` would
     have been committed. Found by review; the command is now evidence-only.
  4. Is requiring `source`/`command` non-empty enough? **No** — they were
     `str()`-coerced, so `{"token": "secret"}` passed and its repr was persisted.
     Now typed, stripped and length-bounded.
  5. Is the declared count validated? **No** — `True == 1` and `1.0 == 1` in
     Python. Now typed before comparison.
  6. Does a failed register write leave misleading state? **Yes** — cards were
     filed first. Order reversed; pinned by a test that makes the destination
     unwritable.
  7. Did part 1 actually ship its documentation? **No.** `docs/guide.md` never
     received it: the edit was a `str.replace` against text that did not exist in
     that branch's base, so it silently did nothing and only the other doc was
     asserted. Both halves are documented here.
  8. **F0.5** (`cli`, real executables): `exit_code 0`, `tests_run 62`.

- **Test Completeness Ledger** — 0 untested-testable.

  | # | Testable behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | the register carries the two keys the reader parses | tested | `test_inherited_baseline::test_register_carries_the_two_keys_the_audit_phase_reads` |
  | 2 | the REAL shared reader reads back what adopt wrote | tested | `test_inherited_baseline_input::test_the_shared_reader_reads_back_what_adopt_wrote` (subprocess) |
  | 3 | an unobserved register never reads as forgiveness, and `present` ≠ `baseline_observed` | tested | `test_inherited_baseline_input::test_an_unobserved_register_reads_as_zero_baseline_not_as_forgiveness` |
  | 4 | unobserved says so rather than claiming clean | tested | `test_inherited_baseline::test_an_unobserved_baseline_says_so_rather_than_claiming_clean` |
  | 5 | coverage gaps never feed `baseline_failure_count` | tested | `test_inherited_baseline::test_gaps_never_feed_the_number_that_excuses_failures` |
  | 6 | untested requirements are gaps; both tag origins count as coverage | tested | `test_inherited_baseline::test_a_requirement_with_no_tagged_test_is_an_inherited_gap`, `::test_both_tag_origins_count_as_coverage` |
  | 7 | a tag naming an unknown FR is not coverage | tested | `test_inherited_baseline::test_a_tag_pointing_at_an_unknown_requirement_is_not_coverage` |
  | 8 | an observed red baseline lands as inherited failures | tested | `test_inherited_baseline::test_an_observed_red_baseline_is_recorded_as_inherited`, e2e `test_record_inherited_baseline::test_an_observed_red_baseline_lands_as_inherited_failures` |
  | 9 | an observed green baseline is distinguishable from no run | tested | `test_inherited_baseline::test_an_observed_green_baseline_is_observed_and_empty` |
  | 10 | a list without provenance / malformed / self-inconsistent is rejected | tested | `test_inherited_baseline_input::test_a_failure_list_without_provenance_is_rejected`, `::test_a_malformed_payload_is_rejected_rather_than_read_as_empty` (5) |
  | 11 | `source`/`command` must be real strings, not coerced | tested | `test_inherited_baseline_input::test_source_and_command_must_be_real_strings` (4 cases) |
  | 12 | the `source` label has a ceiling | tested | `test_inherited_baseline_input::test_a_source_label_has_a_ceiling` |
  | 13 | a declared count of the wrong type is rejected | tested | `test_inherited_baseline::test_a_declared_count_of_the_wrong_type_is_rejected` (5 cases) |
  | 14 | only the five reader fields are copied from a failure | tested | `test_inherited_baseline_input::test_only_the_fields_the_audit_phase_reads_are_copied` |
  | 15 | the command never reaches the committed register | tested | `test_inherited_baseline::test_the_command_never_reaches_the_committed_register` |
  | 16 | each non-empty gap class leaves a card; empty leaves none | tested | `test_inherited_baseline::test_each_non_empty_gap_class_leaves_a_follow_up`, `::test_an_empty_gap_class_leaves_nothing_behind` |
  | 17 | gap cards read as inherited absence, not breakage | tested | `test_inherited_baseline::test_gap_cards_describe_the_gap_without_pointing_at_a_failure` |
  | 18 | dedup keys do not vary with the count | tested | `test_inherited_baseline::test_gap_card_dedup_keys_do_not_vary_with_the_count` |
  | 19 | onboarding files exactly one confirmation card; a re-adopt duplicates nothing | tested | `test_record_inherited_baseline::test_onboarding_leaves_exactly_one_confirmation_follow_up`, `::test_a_re_adopt_duplicates_nothing` |
  | 20 | no card when every requirement was confirmed | tested | `test_derived_catalogue_doc::test_no_card_when_every_requirement_was_confirmed_by_a_person` |
  | 21 | no card is filed when the register cannot be written | tested | `test_record_inherited_baseline::test_no_card_is_filed_when_the_register_cannot_be_written` |
  | 22 | a clean repo records a register and crashes on nothing | tested | `test_inherited_baseline::test_a_clean_repo_has_empty_gaps_not_a_crash`, `test_record_inherited_baseline::test_a_clean_repo_records_a_register_and_no_gap_cards` |
  | 23 | a missing or corrupt prerequisite stops the step, naming what to re-run | tested | `test_record_inherited_baseline::test_a_missing_catalogue_stops_the_step_and_names_the_step_that_writes_it`, `::test_a_corrupt_upstream_artifact_stops_rather_than_inventing_gaps` |
  | 24 | a forged catalogue cannot suppress the follow-up | tested | `test_record_inherited_baseline::test_a_catalogue_that_lies_about_confirmation_stops_the_step`, `::test_a_catalogue_claiming_confirmation_without_an_interview_stops_the_step` |
  | 25 | `--dry-run` touches nothing | tested | `test_record_inherited_baseline::test_dry_run_touches_nothing` |
  | 26 | a missing register hard-blocks the handover, naming Step E.18 | tested | `test_validate_adoption_soft_checks::test_a_missing_honesty_artifact_blocks_the_handover` (2 cases), `::test_the_error_names_the_step_that_writes_the_missing_file` |
  | 27 | the commit body names the card and the register | tested | `test_adopt_commit_template::test_the_body_reports_how_many_requirements_are_unconfirmed`, `::test_the_body_names_the_inherited_baseline_register` |
  | 28 | Step H's reference names the register, the card and `read_summary` | tested | `test_skill_references_link::test_step_h_reference_tells_the_agent_where_the_count_comes_from` |
  | 29 | the new step reference is registered and linked from the Kern | tested | `test_skill_references_link::test_every_expected_step_reference_exists_and_is_linked` |
  | 30 | the Step H handoff *banner* renders these counts | untestable | `covered-by-existing-test` — prompt-rendered text; the mechanical parts are rows 27-28. |

- **Confidence-pattern check.**
  *Asymptote:* five of the eight probes overturned something, and three of those
  (3, 4, 5) were the *same* boundary being closed one layer at a time — whitelist
  the entries, then stop persisting the command, then stop coercing the fields
  that name it. Worth recording: closing a boundary at one field is not closing
  the boundary.
  *Coverage:* 30 behaviors, 29 `tested`, 1 `untestable`, **0 untested-testable**;
  9 ACs, 9 covered.
  *Integration composition:* the real risk is producer↔consumer across the
  ADR-045 barrier, covered by row 2 (real shared reader, own interpreter).

## Verification (medium+)

- **Surface:** `cli`
- **Runner:** `uv run --directory plugins/shipwright-adopt --extra dev pytest tests/test_record_inherited_baseline.py tests/test_inherited_baseline.py tests/test_inherited_baseline_input.py tests/test_validate_adoption_soft_checks.py -q`
- **Result:** `exit_code 0`, `tests_run 62`
- **Evidence:** `.shipwright/runs/iterate-2026-07-27-adopt-inherited-baseline/surface_verification.json`
