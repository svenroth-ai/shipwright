# Iterate Spec: requirement-writeback-loop

- **Run ID:** iterate-2026-07-27-requirement-writeback-loop
- **Type:** change
- **Complexity:** medium
- **Status:** complete
- **Triage anchor:** trg-e9e5188e (supersedes trg-35785118 design, trg-ed419fd7 build)

## Goal

Close the requirement write-back loop at its two open call sites. What design
rounds and build sections learn about the product must reach the requirements
instead of staying in the mockup or being resolved silently. One mechanism —
the requirement-impact declaration the change workflow already runs — given to
the design feedback round and the build section, so all three decided rules
become checkable at one cost.

## Acceptance Criteria

- [x] **AC-1** A shared module validates a requirement-impact declaration:
      `impact ∈ {add, modify, remove, none}`; `none` requires a valid one-line
      reason; `add|modify|remove` requires at least one FR id AND at least one
      touched `.shipwright/planning/**/spec.md` path. Malformed vocabulary is
      an error, not a silent pass.
- [x] **AC-2** A CLI records a declaration as one tracked JSON file per
      `(run_id, phase, scope)` under `.shipwright/planning/requirement-impact/`,
      validating first and **writing nothing on failure** (exit 1, fail-closed).
      The touch evidence is git-derived only — the caller cannot hand in a path
      list. Git-unavailable degrades the *touch* check to a recorded warning
      (fail-open on unavailable, never on unknown); the vocabulary/reason/FR
      checks still apply, and a bad ref is an error, not a skip.
- [x] **AC-3** The design feedback round (Option B) declares a requirement
      impact per round, and its Spec Backflow table carries a
      `.shipwright/planning/*/spec.md` row for **substance** — not only the
      pointer rows that exist today.
- [x] **AC-4** Design finalization (Option A) refuses to declare the phase
      complete while any processed round has no recorded declaration.
- [x] **AC-5** The build phase carries an explicit STOP rule for the
      mockup-vs-section contradiction, naming the expected resolution
      (correct the requirement to match the mockup) and requiring the decision
      to be put to a person and recorded.
- [x] **AC-6** The build phase's "nothing outside the section" criterion carries
      the shared-touch carve-out at every place it is stated
      (`self-review-checklist.md`, `spec-reviewer.md`, `section-builder.md`),
      so a section that must touch something shared is no longer unbuildable
      by the letter of the rule.
- [x] **AC-7** A checker verifies that every file a section changed is either
      declared by the section's `## Files to Create/Modify` block or recorded
      as an attributed extra on that section's declaration.
- [x] **AC-8** Drift-protection tests pin each prompt-side rule so a future edit
      cannot silently delete it.

## Spec Impact

- **Classification:** none
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** FR-01.04 and FR-01.05 already state all three
  guarantees as (E) acceptance criteria — they were written in REQ-3 Phase 2
  (#436). This iterate builds the enforcement for requirement text that already
  exists; no requirement wording changes. `affected_frs = [FR-01.04, FR-01.05]`.

## Out of Scope

- Judging **behaviour vs appearance** for a given feedback item, and detecting a
  **prose-vs-markup contradiction**. Both are human reads by decision; this
  iterate makes the *declaration* and the *touch check* mechanical and leaves
  the judgement where it belongs.
- Re-tagging or renumbering FRs; no FR row is added, changed or removed.
- The WebUI surface for the new log.
- Wiring the build-side file-attribution check into a blocking CI gate — it
  ships as a checker the phase runs, matching the honest ceiling the triage
  item names.

## Design Notes

n/a — no UI. The changed surfaces are runtime prompts (SKILL.md + references +
agent definitions) and Python under `shared/`.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `record_requirement_impact.py:main` | `requirement_impact_store.py:read_declarations` | JSON (one file per declaration) |
| `record_requirement_impact.py:main` | `check_section_file_attribution.py:main` | JSON (one file per declaration) |
| `requirement_impact_git.py:changed_paths` | `requirement_impact.py:touch_error` | `git diff --name-status -z` |

`touches_io_boundary` fires (new serialized producer/consumer pair) →
Boundary Probe + round-trip test required.

## Confidence Calibration

- **Boundaries touched:** the per-declaration JSON files under
  `.shipwright/planning/requirement-impact/` (one producer
  `record_requirement_impact.py`, two consumers — the design Option-A gate and
  `check_section_file_attribution.py`).

- **Empirical probes run:**
  1. *Is the new artifact actually git-tracked?* Wrote a probe file into
     `.shipwright/planning/requirement-impact/` and ran `git check-ignore -v`.
     **Finding:** trackable — the canon `!/.shipwright/planning/` re-include
     covers it, so no `.gitignore` change was needed (the assumption held).
  2. *Round-trip through the real boundary.* `record_requirement_impact.py`
     writes → `read_declarations` reads back with zero problems, twice per run
     and across two run_ids. **Finding:** clean; re-recording the same identity
     overwrites in place rather than accumulating.
  3. *Does the touch check bind against a REAL repo?* Ran the recorder in a
     genuine git repo with and without a `spec.md` edit. **Finding:** rejects
     with `requirement_impact_no_spec_touched` and writes nothing.
  4. *Do the three git outcomes stay apart?* Bad ref / no repo / good range.
     **Finding:** `error` rejects, `skipped` warns + records
     `touch_check.source="skipped"`, `git` records the verified spec files.
  5. *Does the messy-markdown parser hold?* 12 real bullet variants (checkboxes,
     bold, backticks, em/en/ascii dashes, Windows separators, prose).
     **Finding:** all normalize; "None — …" prose needed a placeholder guard,
     found by test and fixed.
  6. *Do parts (2) and (3) contradict each other?* The integration test caught
     that a section correcting the requirement (mandated by part 2) had its
     `spec.md` edit flagged as unattributed by part 3. **Finding: a real design
     defect, fixed** — a behaviour-affecting declaration's git-verified spec
     files are attributed by the declaration itself, while an `--impact none`
     section editing requirements is still reported.
  7. *Do the plugin gates hold?* `uvx ruff@0.15.15` clean; anti-ratchet clean
     (section-builder.md 485 ≤ 486 baseline after compressing the additions);
     SKILL.md kern back under 300 LOC after the reference split.
  8. *Does the checker survive a REAL multi-section build?* Internal code review
     traced the actual flow. **Finding: two defects.** `git add -A` at Step 8
     sweeps the previous section's post-commit bookkeeping into the next
     section's commit, and `--base-ref {branch_base}` put every earlier section
     inside the current section's range — so the checker would have false-failed
     every section after the first. Fixed: the range is now the section's own
     commit (`HEAD^..HEAD`) and framework-written artifacts are an explicit,
     documented category (`FRAMEWORK_BOOKKEEPING`). The "the declaration file
     cannot appear in the range" claim was **false** and has been removed.
  9. *Is `{run_id}` a defined placeholder in these plugins?* Grepped both.
     **Finding: no** — `{SHIPWRIGHT_SESSION_ID}` is the convention, so the
     run-scoped identity that justifies the whole storage design would not have
     bound. All call sites switched.
  10. *Can the caller still steer the evidence?* Yes, via the range. **Finding:**
      `--base-ref HEAD --head-ref HEAD` gave an empty diff that passed any
      declaration. Fixed: a degenerate range is rejected, and the resolved SHAs
      are recorded so the range is auditable afterwards.
  11. *Is AC-4's gate actually a gate?* External code review: **no** — it was
      `ls` plus a prose instruction, with no code consumer and nothing that could
      fail. Fixed by building `check_design_round_declarations.py`, which
      discovers the rounds, looks each up by this run id, and exits non-zero.
  12. *Does the design-side touch check bind in the REAL pipeline?* Adversarial
      doubt review traced the flow. **Finding: no — it was vacuous.** Nothing in
      the pipeline commits before the build phase, so every `spec.md` the project
      phase wrote is untracked, `git ls-files --others` listed it, and **any**
      `--impact modify` passed on a spec nobody had edited. Part (1) was
      decorative exactly where it needed to bite. Fixed by giving each round a
      **baseline** (`--snapshot-baseline`) — the boundary a commit gives a build
      section — and refusing a behaviour-affecting declaration without one.
  13. *Where does the design gate's round list come from?* From gitignored review
      scratch, and an empty glob resolved to PASS — so rounds exported via a
      browser download could finalize clean. Fixed: the tracked baselines are the
      round registry.
  14. *Can anything still escape the section check?* Three ways, all fixed: a
      deletion (`git rm` of an undeclared shared file) was reported and never
      failed; a section that skipped the recorder entirely still exited 0; and a
      bare prose token (`- src/lib helpers as needed`) minted a covering
      directory that pre-attributed everything beneath it.
  15. *Does the forgiving parser stay forgiving?* `- Modify: path` and
      `- Tests: path` declared the **label** and dropped the path. Fixed with an
      explicit confidence ordering; `_utils.py` and `__init__.py` survive, and a
      back-ticked word in the prose no longer hijacks the path.
  16. *Does it behave the same on both platforms?* Two real divergences fixed: a
      declaration re-saved as UTF-16 (Notepad / PowerShell 5.1) raised an
      unhandled `UnicodeDecodeError` whose exit code is the same as "rule
      violated"; and `git -C` resolves upward, so a project nested inside a
      larger repo compared repo-root-relative git paths against project-relative
      declared ones and matched nothing. Paths are now rebased onto the toplevel.
  17. *Do the error classes still hold?* `PermissionError` was mapped to
      "unavailable" — contradicting its own docstring — and git's
      `detected dubious ownership` (the default in bind-mounted containers) was
      reported as "not a git repository", turning the whole mechanism
      green-and-inert there. Both now fail closed.

- **Test Completeness Ledger:** 243 new tests, all executed and passing
  (204 shared + 26 build-drift + 13 design-drift). Full suites green: shared
  **5158 passed / 0 failed**, build 110, design 32, integration 418,
  `uvx ruff@0.15.15` clean, anti-ratchet clean.

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | Declaration vocabulary is closed (`add/modify/remove/none`, phase, scope, run_id) | tested | `test_requirement_impact.py::test_impact_outside_vocabulary_rejected` + `_invalid_phase/_scope/_run_id` PASSED |
  | 2 | `none` requires a valid one-line reason | tested | `test_none_without_reason_rejected`, `_blank_`, `_multiline_` PASSED |
  | 3 | Behaviour-affecting requires ≥1 **well-formed** FR id | tested | `test_behavior_affecting_without_fr_rejected` + `test_malformed_fr_id_rejected[8 cases]` PASSED |
  | 4 | A requirements file is `.shipwright/planning/<split>/spec.md` (not an iterate spec) | tested | `test_requirement_spec_recognized[5]` / `test_non_requirement_paths_rejected[8]` PASSED |
  | 5 | Behaviour-affecting without a spec touch is rejected | tested | `test_behavior_affecting_without_spec_touch_rejected`, `test_behaviour_change_without_spec_touch_is_rejected` PASSED |
  | 6 | Unobtainable evidence skips the touch check; empty evidence does not | tested | `test_touch_check_skipped_when_evidence_unavailable` PASSED |
  | 7 | Attributed extras are structured, reasoned, deduped, root-confined | tested | `test_extras_*` (6 cases) + `test_extra_escaping_project_root_is_rejected` PASSED |
  | 8 | Identity `(run_id, phase, scope)` is path-safe and run-scoped | tested | `test_requirement_impact_store.py` filename + `find_declaration` tests (9) PASSED |
  | 9 | Damage is named, never silently skipped (bad JSON, conflict markers, non-object) | tested | `test_read_declarations_*` (7) PASSED |
  | 10 | A rejected declaration writes **nothing** | tested | `test_*_rejected_and_writes_nothing`, `test_vocabulary_is_enforced_even_without_git` PASSED |
  | 11 | The three git outcome classes stay distinct | tested | `test_unknown_ref_is_an_error_not_a_skip`, `test_non_repository_skips_the_touch_check_but_still_records`, `test_worktree_and_range_together_are_rejected` PASSED |
  | 12 | Record round-trips; same identity overwrites; different runs coexist | tested | `test_record_round_trips_through_the_reader`, `_rerecording_`, `_same_scope_under_two_runs_` PASSED |
  | 13 | Section `## Files to Create/Modify` parses across messy LLM formatting | tested | `test_messy_bullet_forms_normalize_to_a_path[12]` + heading variants[5] PASSED |
  | 14 | Undeclared shared touch fails; recorded extra passes | tested | `test_undeclared_shared_touch_fails`, `test_recorded_attributed_extra_makes_the_same_touch_pass` PASSED |
  | 15 | A declared directory covers files beneath it | tested | `test_a_declared_directory_covers_files_beneath_it` PASSED |
  | 16 | Deletions and renames are reported, not failed | tested | `test_deletions_are_reported_not_failed`, `test_renames_are_reported_not_failed` PASSED |
  | 17 | A stale run's extra does not excuse this run's touch | tested | `test_declaration_from_another_run_does_not_excuse_the_touch` PASSED |
  | 18 | Part (2)'s mandated spec correction is not punished by part (3) | tested | `test_a_declaration_verified_spec_edit_is_attributed` + integration PASSED |
  | 19 | An `--impact none` section editing requirements is still flagged | tested | `test_none_impact_section_editing_requirements_is_flagged` PASSED |
  | 20 | The declaration file is never itself flagged (Step-10b ordering) | tested | `test_declaration_file_is_not_itself_flagged`, `test_declaration_is_recorded_after_the_section_commit` PASSED |
  | 21 | The whole loop composes: design round → spec correction → build contradiction → attribution | tested | `test_requirement_writeback_integration.py::test_the_loop_closes_from_design_round_through_build_section` PASSED |
  | 22 | Design Option B declares + writes back substance (prompt rule) | tested | `shipwright-design/tests/test_skill_writeback_rules.py` (6) PASSED |
  | 23 | Design Option A blocks on a missing/foreign-run declaration (prompt rule) | tested | `test_option_a_has_a_requirement_write_back_gate`, `_rejects_a_declaration_from_another_run` PASSED |
  | 24 | Build states the contradiction STOP + expected resolution (prompt rule) | tested | `shipwright-build/tests/test_skill_writeback_rules.py` contradiction tests (9) PASSED |
  | 25 | The carve-out exists at **every** scope-rule site | tested | `test_every_scope_rule_site_carries_the_shared_touch_carve_out[4 files]` PASSED |
  | 26 | The autonomous priority ladder no longer settles contradictions silently | tested | `test_autonomous_priority_ladder_does_not_silently_settle_contradictions` PASSED |
  | 27 | A degenerate range (base == head) cannot pass a declaration | tested | `test_requirement_impact_git.py::test_degenerate_range_is_rejected` PASSED |
  | 28 | Resolved base/head SHAs are recorded, so the range is auditable | tested | `test_resolved_shas_are_recorded_for_a_committed_range` PASSED |
  | 29 | A greenfield design phase works before the first commit (unborn HEAD) | tested | `test_design_round_works_before_the_first_commit` PASSED |
  | 30 | Bad vocabulary exits 1 with structured JSON, not argparse's exit 2 | tested | `test_bad_vocabulary_exits_1_with_structured_json[2]` PASSED |
  | 31 | Free-text fields stay one line | tested | `test_free_text_fields_must_stay_one_line[3]` PASSED |
  | 32 | A damaged declaration is surfaced, never read as "never declared" | tested | `test_find_declaration_surfaces_damage_...`, `test_a_damaged_declaration_is_reported_not_treated_as_absent` PASSED |
  | 33 | A rename destination is still the section's to declare | tested | `test_rename_source_is_reported_but_the_destination_must_be_accounted_for`, `test_a_declared_rename_destination_passes` PASSED |
  | 34 | Framework bookkeeping is excluded; ordinary files are not | tested | `test_framework_bookkeeping_is_not_section_work[5]`, `test_ordinary_files_are_not_bookkeeping[3]` PASSED |
  | 35 | Emphasis stripping does not mangle `_utils.py` / `__init__.py` | tested | `test_emphasis_stripping_does_not_eat_real_filenames[4]` PASSED |
  | 36 | A back-ticked word in the description does not hijack the path | tested | `test_backtick_in_the_description_does_not_hijack_the_path` PASSED |
  | 37 | Several paths on one bullet are all declared | tested | `test_multiple_paths_on_one_bullet_are_all_declared` PASSED |
  | 38 | Spec auto-attribution requires the declaration to cover THIS range | tested | `test_spec_attribution_requires_the_declaration_to_cover_this_range` PASSED |
  | 39 | An embedded `..` segment is refused, not only a leading one | tested | `test_extra_escaping_project_root_rejected` + CLI PASSED |
  | 40 | Design finalization REFUSES while a round is silent (AC-4 as mechanism) | tested | `test_design_round_declarations.py` (11) PASSED |
  | 41 | A design round is judged against ITS OWN baseline, not "everything uncommitted" | tested | `test_requirement_impact_baseline.py` (15) + `test_an_untouched_spec_no_longer_satisfies_a_worktree_modify` PASSED |
  | 42 | A behaviour declaration with no baseline is refused (fail-closed) | tested | `test_a_worktree_modify_without_a_baseline_is_refused` PASSED |
  | 43 | The round registry is the tracked baselines, not gitignored scratch | tested | `test_rounds_are_discovered_from_the_baselines_the_rounds_recorded`, `test_rounds_from_another_run_are_not_this_run_s` PASSED |
  | 44 | A deletion outside the section's scope fails; a declared one does not | tested | `test_deleting_an_undeclared_file_fails`, `test_deleting_a_declared_file_passes` PASSED |
  | 45 | A section with no declaration at all fails | tested | `test_a_section_with_no_declaration_fails` PASSED |
  | 46 | Only an explicit trailing slash makes a declared entry cover a directory | tested | `test_a_bare_prose_token_does_not_become_a_covering_directory`, `test_an_explicit_trailing_slash_does_cover_files_beneath` PASSED |
  | 47 | `Label: path` bullets still yield the path | tested | `test_label_prefixed_bullets_still_yield_the_path[3]` PASSED |
  | 48 | The `--name-status -z` parser handles A/M/D/R/C, spaces, quotes, truncation | tested | `test_git_name_status.py` (16) PASSED |
  | 49 | Repo-root paths rebase onto a nested project root | tested | `test_a_path_under_the_project_is_rebased`, `test_a_sibling_with_a_shared_prefix_is_not_rebased`, `test_parse_applies_the_prefix` PASSED |
  | 50 | A non-UTF-8 declaration is named damage, not a traceback | tested | `read_declarations` OSError/UnicodeDecodeError guard + `test_find_declaration_surfaces_damage_instead_of_reporting_absence` PASSED |
  | 51 | An agent correctly *judging* behaviour-vs-appearance on real feedback | untestable | `requires-manual-visual-judgment` — the judgement is a human read by decision; what is testable (the declaration, the touch) is rows 1–12 |
  | 52 | An agent correctly *detecting* a prose-vs-markup contradiction | untestable | `requires-manual-visual-judgment` — needs reading comprehension between prose and rendered markup; the honest ceiling is the instruction (row 24) plus the recorded decision (row 12) |

- **Confidence-pattern check:**
  - *Asymptote (depth):* **repeatedly yes, and each time it paid.** Probe 6
    found parts (2) and (3) contradicting each other *after* the unit tests were
    green. Probe 7 then found two more blocks. Probes 8–10 (internal code review)
    found that the checker would have false-failed every section after the first,
    that `{run_id}` was undefined in both plugins, and that the caller could
    still neuter the evidence by choosing a degenerate range. Probe 11 (external
    code review) found that AC-4's gate was prose, not a gate. Probes 12–17
    (adversarial doubt review) then found the most serious defect of all: the
    design-side touch check was **satisfiable for free in the standard
    pipeline**, so part (1) was decorative. Every one of those arrived after a
    point where the work looked finished — which is exactly why "are you
    confident?" is not evidence, and why each review pass was actually run
    rather than reasoned about.
  - *Coverage (breadth):* 52 rows, 50 `tested`, 2 `untestable` with a
    closed-vocabulary reason_code, **0 untested-testable**. The two untestable
    rows are precisely the two human reads the work unit itself names as
    staying human.
  - *Integration composition:* `cross_component` does not fire (no merge/churn
    resolver, hooks, phase validator, or campaign-drain file touched), but a
    real composition test was written anyway — row 21 drives design → build →
    attribution against a genuine git repo, and it is what caught the row-18
    defect.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run shared/scripts/tools/record_requirement_impact.py --help`
  plus the end-to-end round-trip driver (record → read back → attribution check)
- **Evidence path:** `.shipwright/planning/iterate/iterate-2026-07-27-requirement-writeback-loop/`
- **Justification (only if surface=none):** n/a
