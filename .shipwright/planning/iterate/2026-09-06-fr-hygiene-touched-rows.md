# Iterate Spec: fr-hygiene-touched-rows

- **Run ID:** iterate-2026-09-06-fr-hygiene-touched-rows
- **Type:** feature
- **Complexity:** medium
- **Status:** draft

## Goal
An adopted repo's FR catalogue can carry ~50 iterates of implementation-prose
descriptions and test-status-report "acceptance criteria" while every
compliance gate reports clean, because Group I's substantive checks (I1/I2/I6)
are deliberately advisory-only and nothing checks a criterion's *shape*. This
iterate adds a non-dodgeable, diff-scoped finalization gate that holds any FR
row a run itself adds or edits to `shared/fr-authoring.md`'s rules for real,
adds the missing criterion-shape rule and check (I7), and adds a visibility
signal for a `/shipwright-adopt` TBD placeholder that has gone stale — without
reddening any existing adopted repo's dashboard for legacy content nobody
touched.

## Acceptance Criteria
- [ ] Given a run's diff adds a new FR row whose name or description carries
  implementation detail (file path / ADR number / HTTP verb / code symbol),
  when F11 finalization runs, then `check_fr_hygiene_on_touched_rows` STOPs
  the run naming the row and the violation kind.
- [ ] Given a run's diff edits an existing FR row's description to add
  implementation detail, when F11 runs, then the same gate STOPs.
- [ ] Given a run folds a new criterion into an existing FR (description
  unchanged, a bullet appended under `## Acceptance Criteria`) and that
  criterion is a prose status report rather than `(E) Given/when/then` shaped,
  when F11 runs, then the gate STOPs on the criterion shape.
- [ ] Given a run touches a spec.md but every touched row is clean, when F11
  runs, then the gate passes.
- [ ] Given a legacy spec.md carries a pre-existing I1/I2/I7 violation on a row
  this run does not touch, when F11 runs, then the gate does not fire on it —
  only Group I's existing advisory reporting sees it.
- [ ] Given the compliance audit runs on any spec, when Group I evaluates I7,
  then a criterion that exists but is not `Given/when/then` shaped is reported
  advisory (never fails the audit), and a row with zero criteria at all is I6's
  finding, not I7's.
- [ ] Given a `/shipwright-adopt` TBD placeholder has been committed for at
  least 90 days, when the compliance audit runs, then I8 reports it as an
  advisory MEDIUM finding (never blocking); a TBD younger than 90 days is not
  reported.

## Spec Impact
This iterate changes `/shipwright-iterate` and `/shipwright-compliance`
framework behavior (a new finalization gate, a new Group I check, a
documentation rule) — it does not add or change a capability of this
monorepo's OWN adopted product spec (`.shipwright/planning/01-adopted/spec.md`).
- **Classification:** none
- **NONE justification:** the change is to the SDLC framework's own
  compliance/finalization tooling (shared/scripts, the compliance plugin, the
  iterate skill's own reference docs), not to a capability this repo's adopted
  spec declares. `shared/fr-authoring.md` and `docs/hooks-and-pipeline.md` are
  hand-written framework documentation, not FR-table rows.

## Out of Scope
- Promoting I1/I2/I3/I6/I7 to blocking globally (rejected direction — see
  Architecture Review below).
- A per-producer (adopt vs. project) split of Group I's advisory status —
  unimplementable at the audit layer, which reads a spec file, not its
  producer.
- Blocking on a stale TBD — deliberately advisory-only (targets legacy content
  a run did not touch).

## Design Notes
No UI surface; framework/tooling change only.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `/shipwright-adopt`'s `spec_document.py` (TBD marker text) | `group_i_tbd_age.py` (I8, via `git blame`) | Markdown literal string match |
| A run's `spec.md` diff (any author) | `fr_hygiene.py`'s `check_fr_hygiene_on_touched_rows` (F11) | Markdown FR table + criteria sections, read via `fr_table_reader`/`fr_criteria` |

No serialized config/JSON format changed — `touches_io_boundary` does not fire.

## Confidence Calibration
- **Boundaries touched:** the two producer/consumer pairs above — both
  read-only consumption of existing Markdown shapes, no new serialization
  format introduced.
- **Empirical probes run:**
  - Real git-repo round-trip test proving the diff-scoped gate distinguishes a
    touched dirty row from an untouched legacy dirty row in the SAME spec file
    (`test_ignores_a_legacy_violation_in_a_row_this_run_never_touched`) — PASS.
  - Real git-repo round-trip test proving the FOLD pattern (criterion appended,
    description unchanged) is still caught, not just a row-text edit
    (`test_fails_on_malformed_criterion_added_by_a_fold_edit`) — PASS.
  - Real git-repo (`git blame` on actual commits with controlled
    `GIT_AUTHOR_DATE`) round-trip proving I8's age computation fires past 90
    days and not before (`test_old_tbd_is_flagged_stale`,
    `test_fresh_tbd_is_not_flagged`) — PASS.
  - Full existing Group I plugin suite (97 pre-existing + 15 new tests) re-run
    after the `group_i_detectors`/`group_i_criteria` refactor — all pass,
    confirming the shared-lib extraction changed no observable behavior.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | Gate STOPs on a new row with a name/description violation | tested | `test_fails_on_name_and_description_violations_in_a_new_row` PASSED |
  | 2 | Gate STOPs on an edited row's description violation | tested | `test_fails_on_edited_description_of_an_existing_row` PASSED |
  | 3 | Gate STOPs on a folded criterion that is malformed | tested | `test_fails_on_malformed_criterion_added_by_a_fold_edit` PASSED |
  | 4 | Gate passes when a touched row is clean | tested | `test_passes_when_touched_row_is_clean` PASSED |
  | 5 | Gate ignores an untouched legacy violation | tested | `test_ignores_a_legacy_violation_in_a_row_this_run_never_touched` PASSED |
  | 6 | Gate passes (fast) when no spec.md touched | tested | `test_passes_when_no_spec_touched` PASSED |
  | 7 | Gate skips outside a git work tree | tested | `test_skips_outside_a_git_work_tree` PASSED |
  | 8 | I7 detects a malformed criterion at the whole-catalogue advisory level | tested | `test_i7_reports_the_requirement_with_a_malformed_criterion` PASSED |
  | 9 | I7 never fails the audit | tested | `test_i7_never_fails` PASSED |
  | 10 | I7 does not flag a row with zero criteria (that's I6's finding) | tested | `test_i7_does_not_flag_a_row_with_no_criteria_at_all` PASSED |
  | 11 | I8 flags a TBD older than 90 days | tested | `test_old_tbd_is_flagged_stale` PASSED |
  | 12 | I8 does not flag a fresh TBD | tested | `test_fresh_tbd_is_not_flagged` PASSED |
  | 13 | I8 never fires on a row carrying NO TBD marker line at all (a row with only real criteria and no leftover placeholder) | tested | `test_row_with_real_criteria_never_flagged` PASSED — narrower than "any row with real criteria" (external review, openai leg): a TBD line left behind ALONGSIDE real criteria elsewhere in the same row is dead placeholder litter and I8 correctly still reports it |
  | 14 | `is_well_formed_criterion` recognizes/rejects the shape correctly (incl. keyword-order and whole-word cases) | tested | `test_fr_criterion_shape.py` (6 cases) PASSED |
  | 15 | The detector-vocabulary move (`group_i_detectors` → shared lib) preserves all existing I1/I2/I3 behavior | tested | `covered-by-existing-test` — full pre-existing Group I suite (97 tests) re-run green |
  | 16 | Gate judges the DELTA, not the whole row: a legacy-dirty Name is not re-flagged by a description-only edit | tested | `test_ignores_a_legacy_dirty_name_when_only_description_is_edited` PASSED — internal Opus plan-review finding (HIGH), fixed and pinned |
  | 17 | Gate judges the DELTA: a fold that adds one clean criterion does not inherit a block from a different, pre-existing malformed criterion on the same row | tested | `test_ignores_legacy_dirty_criteria_when_a_clean_criterion_is_folded_in` PASSED — same finding, criteria half |
  | 18 | A row reinstated from `## Removed Requirements` (criteria section present at base all along) does not inherit a block on its unchanged legacy criteria | tested | `test_reinstated_row_does_not_inherit_a_legacy_malformed_criterion` PASSED — Stage-2 code-reviewer finding (MEDIUM), fixed and pinned; genuinely reddens under the pre-fix code (traced by the reviewer) |
  | 19 | An already-merged commit (base_sha == commit) reports an honest skip, not a false "clean" | tested | `test_reports_skip_when_commit_is_already_contained_in_the_trunk` PASSED — Stage-2 code-reviewer finding (MEDIUM), fixed and pinned |
  | 20 | Gate fails closed when `git_context` cannot answer whether this is a work tree | tested | `test_fails_closed_when_git_context_is_unresolvable` PASSED |
  | 21 | Gate fails closed when the merge-base cannot be resolved | tested | `test_fails_closed_when_merge_base_is_unresolvable` PASSED |
  | 22 | Gate fails closed when the base spec text cannot be read | tested | `test_fails_closed_when_base_spec_text_is_unreadable` PASSED |
  | 23 | A brand-new spec.md (absent at merge-base) is judged against an empty base, not treated as an infra failure | tested | `test_passes_when_a_brand_new_spec_file_is_added` PASSED — glm external-review finding |
  | 24 | A violating row in a brand-new spec FILE (not just a new row in an existing file) is still caught — refutes an "untracked file bypass" hypothesis | tested | `test_fails_on_a_dirty_row_in_a_brand_new_spec_file` PASSED — openai external-review claim (HIGH), empirically disproven and pinned |
  | 25 | `spec_text_at` returns `""` (not `None`) for a path absent at a valid, resolvable base commit | tested | empirical probe against a real two-commit repo (not a pytest case — recorded in the ADR's External-Code-Review-Findings table) confirms `""`, refuting the openai `None`-false-block claim |
  | 26 | `git blame` porcelain `committer-time` for an uncommitted line is current wall-clock time, not `0` | tested | empirical probe against a real repo with an uncommitted edit (recorded in the ADR) confirms non-zero, refuting the glm stale-uncommitted-TBD claim |
  | 27 | `FrTableRow.text` is the Description-preferred cell only, never the whole physical row | tested | code inspection of `_fr_table_columns.title_cell` (recorded in the ADR) confirms, refuting the glm Priority/Basis-edit-triggers-block claim |
  | 28 | A dirty row added TWO commits back on the branch, with an unrelated commit as HEAD, is still caught (the merge-base range is used, not a single-commit fallback) | tested | `test_a_dirty_row_added_in_an_earlier_commit_is_still_caught_at_a_later_head` PASSED — doubt-review finding (HIGH), fixed and pinned |
  | 29 | A non-canonical FR id (e.g. `FR-1.02`) this run adds, carrying a dirty name/description, is still flagged instead of silently invisible | tested | `test_a_non_canonical_id_this_run_added_is_still_flagged` PASSED — doubt-review finding (MEDIUM), fixed and pinned |
  | 30 | A criterion anchored OUTSIDE the recognised `## Acceptance Criteria` region (same id already found inside it) still marks the row touched | tested | `test_a_criterion_anchored_outside_the_recognised_ac_region_is_still_touched` PASSED — doubt-review finding (MEDIUM), fixed and pinned |
  | 31 | A wholly-TBD `/shipwright-adopt` spec (no feature has any AC) still renders each FR's `TBD_MARKER` under its own `### FR-xx.yy` heading, not undifferentiated prose | tested | `test_an_all_tbd_adoption_still_renders_the_marker_under_an_fr_heading` (integration-tests) PASSED — doubt-review finding (MEDIUM), fixed and pinned; renders through the real `_render_spec_md`, not a hand-typed fixture |
  | 32 | Merge-base fail-closed check fires unconditionally, before any "was spec.md touched" question — no path is supplied at all | tested | `test_fails_closed_when_merge_base_is_unresolvable` (rewritten) PASSED — doubt-review finding (HIGH), structural fix removed the vulnerable fallback path entirely |
  | 33 | Group I's empty-corpus SKIP-on-all-checks set includes I7 and I8, not just I1-I6 | tested | `test_fv2_group_i_skips_every_check_on_empty` (integration-tests, updated) PASSED — stale expected-set from before I7/I8 existed, caught by the full integration-tests root run this doubt-review pass triggered |
  | 34 | A legacy dirty row relocated (byte-identical) to a different split's spec.md is not re-flagged; the same move WITH a violation added during it is still caught | tested | `test_a_row_moved_between_spec_files_is_not_reflagged_when_unchanged` PASSED, `test_a_row_moved_between_spec_files_is_flagged_for_a_violation_added_during_the_move` PASSED — round-2 doubt-review finding (HIGH), fixed and pinned |
  | 35 | A criterion anchored under a non-canonical heading id (e.g. missing zero-pad) that this run adds is flagged instead of silently invisible to every FR-catalogue check | tested | `test_orphan_criterion_anchor_with_non_canonical_id_is_flagged` PASSED — round-2 doubt-review finding (MEDIUM), fixed and pinned |
  | 36 | A duplicate FR id newly introduced at HEAD (a dirty row shadowed behind a clean same-id legacy row) is flagged rather than silently dropped by a dict-based lookup | tested | `test_a_new_duplicate_id_at_head_is_flagged` PASSED — round-2 doubt-review finding (HIGH), fixed and pinned |
  | 37 | A second row sharing an already-malformed legacy id/reason pair is still flagged as a new reject, not masked by set-based dedup | tested | `test_a_second_row_with_the_same_malformed_id_and_reason_is_flagged` PASSED — round-2 doubt-review finding (LOW), fixed and pinned |
  | 38 | `_blame_epoch` never trusts a non-positive committer-time as a real commit date (a git-version-dependent zero for the "Not Committed Yet" pseudo-commit would otherwise manufacture a ~20,000-day-stale I8 finding out of an uncommitted TBD line) | tested | `test_blame_epoch_treats_non_positive_committer_time_as_unavailable` PASSED — Tier-3 PR-review finding (PR #679, `openai/gpt-5.6-luna`), fixed and pinned |
  | 39 | `is_well_formed_criterion` rejects a vacuous `Given when then` (keywords in order, no actual clause) | tested | `test_vacuous_given_when_then_is_not_well_formed` PASSED — Tier-3 PR-review finding (PR #679), fixed and pinned |
  | 40 | `is_well_formed_criterion` rejects `Given x when then` (content after `given`, none between `when`/`then`) | tested | `test_vacuous_missing_when_clause_is_not_well_formed` PASSED — same finding, second named case |
  | 41 | `is_well_formed_criterion` rejects `Given x when y then` (content through `when`, none after `then`) | tested | `test_vacuous_missing_then_clause_is_not_well_formed` PASSED — same finding, third named case |
  | 42 | A duplicate id already present at base is still flagged when this run edits the CONTENT of one occurrence, even though `_row_map`'s last-wins collapse means the edited occurrence may not be the one `_touched_ids` would otherwise compare | tested | `test_editing_one_occurrence_of_a_pre_existing_duplicate_id_is_flagged` PASSED — Tier-3 PR-review finding (PR #679, first of two in that pass), fixed and pinned |
  | 43 | An already-rejected row's CONTENT edit (same id, same rejection reason) is still flagged as new, not silently absorbed because `(id, reason)` alone matched an existing base-side reject | tested | `test_editing_an_already_rejected_rows_content_is_flagged` PASSED — Tier-3 PR-review finding (PR #679, second of two in that pass), fixed and pinned |
  | 44 | A new row reusing an FR id that already exists in an UNTOUCHED catalogue spec.md (this run's diff never touches that file at all) is still flagged as a duplicate | tested | `test_a_new_duplicate_id_against_an_untouched_catalog_file_is_flagged` PASSED — Tier-3 PR-review finding (PR #679, round 4), fixed and pinned |
  | 45 | An already-rejected row's content edit landing entirely AFTER the reader's 200-character `raw` truncation boundary is still flagged, not silently absorbed because `raw[:200]` alone stayed identical | tested | `test_editing_an_already_rejected_row_past_the_raw_truncation_boundary_is_flagged` PASSED — Tier-3 PR-review finding (PR #679, round 4), fixed (`raw_digest`) and pinned; the truncation-boundary premise (`raw[:200]` identical between the two rows) was verified by direct computation before trusting the test |
  | 46 | `fr_table_reader.py`'s sibling-loader split (bloat-gate response) preserves identical behavior under all three production import styles, plus the adversarial foreign-`lib`-bound case | tested | `covered-by-existing-test` — `test_fr_table_reader_load_styles.py` (13 cases) re-run green after the split; two attribute-path assertions updated to the new `reader._loader_mod._SIBLINGS`/`_ALLOWED_SIBLINGS` location, no behavior change. Full fr_table_reader consumer surface (101 tests) also re-run green |
  | 47 | A new criterion anchored under an id carrying a canonical PREFIX but extra trailing characters (`FR-01.02.03`) is still flagged as non-canonical | tested | `test_a_new_anchor_with_a_canonical_prefix_but_extra_suffix_is_flagged` PASSED — Tier-3 PR-review finding (PR #679, round 5); the underlying claim (`.match` vs `.fullmatch`) was checked empirically and NOT reproduced against `CANONICAL_FR_RE`'s own `$`-anchored pattern, but `.fullmatch` was adopted anyway as a zero-cost hardening, and this test pins the gate-level behavior either way |
  | 48 | A criterion edited (or supplemented) under an ALREADY-EXISTING non-canonical anchor id — not just a brand-new one — is still flagged, instead of silently invisible because the old id-set exclusion dropped any `fr_id` present anywhere at base regardless of content change | tested | `test_an_existing_non_canonical_anchors_edited_criterion_is_flagged` PASSED — Tier-3 PR-review finding (PR #679, round 6), confirmed genuine by direct code inspection (unlike round 5), fixed (content comparison via `_whole_doc_criteria_texts` replacing the id-set exclusion) and pinned |

- **Confidence-pattern check:** asymptote (depth) — this run's first "are you
  confident?" probe (the internal Opus plan-review) DID surface a
  contradiction (whole-row vs delta judgment), and the Stage-2 code-reviewer
  re-review surfaced two more in the fix for it — both fixed and each pinned
  by a new test before the second probe was trusted. Two further external
  rounds each produced claims that did NOT survive empirical verification
  (rows 25-27) — verified via a real probe repo or direct code inspection
  rather than accepted on the reviewer's inference, per this session's own
  standing practice of never trusting an AI-review claim's specifics without
  checking. A fourth, Stage-3 doubt-review pass (fresh context, biased to
  disprove) surfaced two more genuine defects the prior three rounds all
  missed (rows 28, 29-30) plus a documentation-shape gap in a DIFFERENT
  plugin (`spec_document.py`, row 31) — each fixed and pinned; two of its
  seven findings were rejected with recorded reasoning (an inherited resolver
  behavior shared by three other F11 gates, and a pre-existing detector
  allowlist gap with a narrow, self-correcting blast radius). Running the
  full `integration-tests` root as part of verifying the doubt-review fixes
  also caught an unrelated, pre-existing gap: this iterate's own I7/I8
  additions had never been reflected in the Group I empty-corpus contract
  test (row 33) — a reminder that the fast per-plugin suites this run relied
  on during earlier fix-and-test cycles do not cover cross-plugin contract
  tests, which only the slower `integration-tests` root exercises. Coverage
  (breadth) — every ledger row is `tested`; 0 untested-testable. No
  `cross_component` machinery (hooks, merge/churn resolver, phase validators,
  campaign drain) is touched, so the Integration Coverage gate is
  inapplicable here — this change adds a new, independent F11 verifier
  function rather than modifying the finalization *pipeline mechanism*
  itself.

## Verification (medium+)
- **Surface:** none
- **Runner command:** n/a
- **Evidence path:** n/a
- **Justification (only if surface=none):** framework/tooling change with no
  startable web/dev-server/CLI surface of its own — this repo's own unit +
  real-git integration tests (shared/tests, shared/scripts/tests,
  plugins/shipwright-compliance/tests) are the verification, matching how
  every other F11-verifier-adding iterate in this repo's own history
  (`check_integration_coverage`, `check_ci_supplychain_ack`) was verified.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** Genuinely well-argued design with strong fail-closed posture, real-git tests and unusually good rationale docs — but the two teeth-bearing decisions had gaps: a touched row was judged in FULL (so the recommended fold pattern could block a run at F11 on legacy criteria it never wrote), and the base-commit resolver diverged from the hardened one path-selection already uses (a false-green risk in the exact property the gate advertises as non-dodgeable).
- **Findings:**
  - architecture/high: whole-row judgment instead of delta judgment → **accepted-and-fixed** — `_row_findings` now takes `base_row`/`base_text` and only checks a cell/criterion that actually changed vs base; 2 new regression tests (`test_ignores_a_legacy_dirty_name_when_only_description_is_edited`, `test_ignores_legacy_dirty_criteria_when_a_clean_criterion_is_folded_in`) pin it.
  - architecture/high: heuristic prose detectors (I1/I2 vocabulary) promoted to hard-blocking with no allowlist/ack path → **rejected-with-reason** — the detector vocabulary is unchanged, already-shipped, advisory-tested code; this iterate only changes what happens on a hit for a run's OWN touched rows (the same "reword the row" remedy already applies at the advisory level). An escape-hatch/allowlist mechanism is a real, contained follow-up but is new scope beyond the 3 user-approved decisions for this iterate; filed as a follow-up rather than built here.
  - architecture/medium: two different merge-base resolvers used in one decision (a false-green risk) → **accepted-and-fixed** — swapped `_layer_coverage_regen._merge_base` for `git_helpers._branch_base_commit` (the same hardened, corroborated resolver `_iterate_changed_paths` already uses for path selection).
  - architecture/medium: unclearable fail-closed block when base==commit (on-the-trunk case) → **accepted-and-fixed** — a side effect of the resolver swap: `_branch_base_commit` does not reject `base==commit` the way the old resolver did, so the on-trunk case now correctly yields an empty touched set (base_text==head_text) rather than an ERROR.
  - completeness/medium: a brand-new FR row with zero criteria bypasses I1/I2/I7 → **rejected-with-reason** — out of scope per this iterate's own AC6, which explicitly leaves "zero criteria" to I6; requiring >=1 criterion on a new row is a real, contained follow-up but is new blocking behavior beyond what was approved.
  - architecture/medium: I8's `TBD_MARKER` literal duplicated across the adopt/compliance plugin boundary with no parity test → **accepted-and-fixed** — hoisted to a named constant in `spec_document.py`, added `integration-tests/test_tbd_marker_parity.py`.
  - performance/medium: I8 spawns one `git blame` subprocess per TBD-bearing FR → **rejected-with-reason** (deferred) — advisory/dashboard-only, not correctness; filed as a follow-up (batch to one `--porcelain` blame per file).
  - performance/low: repeated whole-document criteria reparsing → **rejected-with-reason** (deferred) — perf nit, not correctness; filed as a follow-up.
  - completeness/low: doc gaps (I8 missing from §7 table; delta-scope undocumented; `_SPEC_PATH_RE`/`scan_specs` parity comment overclaimed) → **accepted-and-fixed** — §7 table gained the I8 row and a delta-scope paragraph; the `_SPEC_PATH_RE` comment now states the actual (still-correct-in-practice) relationship instead of an unqualified "same shape" claim.
  - completeness/low: fail-closed branches untested (git_error, unresolvable merge-base, unreadable base spec text) → **accepted-and-fixed** — 3 new monkeypatched tests pin all three.
  - security/low: no issue found (lossy `errors="ignore"` decode noted, negligible) → **acknowledged, no action**.

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-09-06-fr-hygiene-touched-rows/architecture_brief.md`
- **Verdicts:** glm=approve · openai=revise (not a contradiction requiring
  resolution — one step apart; no `reject` from either, so this is integrated
  like any other finding, not a stop-and-ask).
- **Smallest thing that would do (per reviewers):** glm confirms Option A
  (the diff-scoped F11 gate) as proposed, "the smallest mechanism that fixes
  the problem," with I7/I8 as advisory Group I rows and no new persisted
  state. openai's `revise` recommends going smaller still: ship the F11 gate,
  keep I7 advisory, but drop I8 (the TBD-age signal) entirely as a standing
  mechanism not worth its upkeep.
- **Findings:**
  - proportionality/medium (openai): I8's `git blame`-based age computation
    and 90-day threshold is "policy machinery for a recoverable,
    already-visible documentation debt" that changes no outcome for legacy
    content → **rejected-with-reason** — I8's threshold and its inclusion in
    this run were an explicit, binding operator decision made before this
    spec was written (the interview-equivalent scoping answers: "TBD-aging
    threshold is 90 calendar days"), not incidental scope this pass
    discovered. Silently dropping it now, post-hoc, on a reviewer's
    proportionality judgment would reverse an operator decision without
    asking — the same silent-reversal failure mode the operator's own
    original problem statement (compliance gates staying green while
    authoring rules are violated) exists to close. It is also the cheaper of
    the two mechanisms under review: advisory-only, no gate, no persisted
    state, reads git history rather than storing it — glm's independent
    `approve` explicitly credits this same property ("the difference between
    a mechanism and a liability").
  - proportionality/medium (glm): blocking on heuristic prose detectors
    (I1/I2 vocabulary, `_PASCAL_RE`) with no allowlist makes a false positive
    on a touched row an unclearable F11 stop; "the first false-positive hard
    block is when it stops being optional" → **acknowledged, already
    tracked** — the identical gap was raised independently by the Stage-3
    doubt review (finding #6) and rejected-with-reason there for the same
    scope boundary (pre-existing, already-shipped advisory detector logic;
    narrow, immediately-diagnosable blast radius); the allowlist/ack
    follow-up glm asks to treat as a real obligation is the same follow-up
    already filed in both the Internal Plan Review and doubt-review
    disposition tables above, not a new item.
- **Reconciliation:** an ad-hoc pre-build validation pass (an independent
  Opus-model review of the proposal shape, run before this spec was written)
  already rejected the operator's own initial suggestion of blanket-promoting
  I1/I2/I6 to blocking, on two grounds: (1) `fr-authoring.md` §7's advisory
  rationale for legacy content is explicit, tested, load-bearing design, not
  an oversight — reversing it would instantly redden every adopted brownfield
  repo's dashboard for content nobody in the current run touched; (2) Group I
  audits a spec FILE, not its PRODUCER, so a project-vs-adopt narrowing is not
  implementable at that layer. The diff-scoped touched-row gate was adopted
  instead, following the precedent already established by
  `check_integration_coverage`/`check_ci_supplychain_ack` (RECOMPUTE from the
  diff, non-dodgeable, no complexity floor). That same pass also corrected the
  original TBD-aging design (a second stamped line would have broken existing
  criteria detection for a row with both a TBD marker and real bullets) —
  fixed by reading git history instead of storing new state. The
  architecture-mode pass (this section) re-litigated I8's existence itself
  and both reviewers converged on Option A being the right shape (`approve`/
  `revise`, no `reject`); the one substantive disagreement (drop I8) is
  reconciled above by naming it as bound scope, not a discovery.
