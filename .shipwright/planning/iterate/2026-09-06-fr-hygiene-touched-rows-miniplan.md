# Mini-Plan: fr-hygiene-touched-rows

- **Run ID:** iterate-2026-09-06-fr-hygiene-touched-rows

## Files to create/modify

- `shared/scripts/lib/fr_hygiene_detectors.py` (new) — I1/I2/I3 detector
  vocabulary, moved from the compliance plugin so a second, non-plugin
  consumer can read it.
- `plugins/shipwright-compliance/scripts/audit/group_i_detectors.py` (edit) —
  thin delegator to the shared lib (same move `group_i_criteria.py` already
  made for `fr_criteria`).
- `shared/scripts/lib/fr_criterion_shape.py` (new) — pure `Given/when/then`
  shape check, its own module so it never touches `fr_criteria.py`'s
  criteria-FINDING logic.
- `plugins/shipwright-compliance/scripts/audit/group_i_criteria.py` (edit) —
  add `malformed_criteria_for`/`frs_with_malformed_criteria` (I7).
- `plugins/shipwright-compliance/scripts/audit/group_i_tbd_age.py` (new) — I8,
  `git blame`-based TBD age.
- `plugins/shipwright-compliance/scripts/audit/group_i.py` (edit) — register
  I7/I8.
- `shared/scripts/tools/verifiers/fr_hygiene.py` (new) — the F11 gate's git
  orchestration (merge-base resolution, reading either side, assembling the
  result).
- `shared/scripts/tools/verifiers/_fr_hygiene_touched.py` (new, split out
  during the Stage-3 doubt-review round once `fr_hygiene.py` crossed the
  300-line guideline) — the pure per-FR touched/clean comparison logic
  (`_row_map`, `_whole_doc_criteria_digests`, `_touched_ids`,
  `_new_reject_findings`, `_row_findings`).
- `shared/scripts/tools/verifiers/iterate_checks.py` (edit) — register the gate
  in `run_all_checks`.
- `shared/fr-authoring.md` (edit) — new §3b (criterion shape), §7 table + note.
- `docs/hooks-and-pipeline.md`, `docs/guide.md` (edit) — document the new gate
  and I7/I8 per CLAUDE.md's same-diff rule.
- Tests: `shared/tests/test_check_fr_hygiene.py`,
  `shared/tests/test_check_fr_hygiene_delta_scope.py` (split out once the
  first file crossed the 300-line guideline, during the review-fix rounds —
  the delta-scoping regression tests found by internal/external review, later
  extended with three more Stage-3 doubt-review regression tests),
  `shared/scripts/tests/test_fr_criterion_shape.py`,
  `plugins/shipwright-compliance/tests/test_audit_group_i_tbd_age.py`,
  `integration-tests/test_tbd_marker_parity.py` (added during review — pins
  `spec_document.TBD_MARKER` against `group_i_tbd_age.TBD_MARKER`, later
  extended with a behavioral render-through test during the doubt-review
  round), `integration-tests/test_requirements_corpus_false_verdicts.py`
  (edit, doubt-review round — its empty-corpus Group-I check-id set had never
  been updated for this iterate's own I7/I8 additions; caught by running the
  full `integration-tests` root while verifying the doubt-review fixes), plus
  edits to the three existing Group I test files that hardcode the check-id
  set.
- `plugins/shipwright-adopt/scripts/lib/spec_document.py` (edit, added during
  review) — hoisted the inline TBD-placeholder literal into a named
  `TBD_MARKER` constant so the parity test above has something to pin; edited
  again during the doubt-review round so the Acceptance Criteria block always
  renders a per-FR heading, even when no feature has any AC.

## Work breakdown

1. Move I1/I2/I3 detectors to a shared pure module; delegate from the plugin.
   Test: full existing Group I detector suite stays green.
2. Add the shape-check module (I7 primitive) + wire I7 into Group I. Test: new
   I7 unit tests + updated greenfield-clean fixture.
3. Build the diff-scoped F11 verifier reusing `_layer_coverage_ac`'s digest
   primitives + `fr_table_reader`. Test: real-git round-trip tests covering
   touched/untouched/fold/clean/no-spec/non-git cases.
4. Register the verifier in `run_all_checks`.
5. Add I8 (TBD aging via `git blame`, no new state). Test: real-git round-trip
   with controlled commit dates.
6. Amend `fr-authoring.md`, `hooks-and-pipeline.md`, `guide.md`.
7. Full test suite + ruff + `verify_local.py`.

## Test strategy

Real-git fixtures throughout (the existing `git_origin_repo`/`make_worktree`
pattern for the F11 verifier; a self-contained tmp_path repo with controlled
`GIT_AUTHOR_DATE` for I8) — no mocking of git, since the whole gate's integrity
depends on reading actual diffs and actual commit history. No E2E/UI layer:
this is a framework/tooling change with no dev-server surface.

## Alternative approach considered — and rejected

**Alternative: promote I1/I2/I6 out of `_ADVISORY_CHECKS` globally**, exactly
as the operator's own initial suggestion proposed. Rejected because
`fr-authoring.md` §7 and the `group_i.py` code comments state, as tested,
load-bearing design, that "an existing spec can carry historical violations
and clean up gradually without reddening CI" — flipping this would instantly
redden the compliance dashboard of every adopted brownfield repo (this
monorepo's own history included) for pre-existing content nobody in any given
run touched, not just the one motivating example (leadwright). It would also
conflate two different failure classes — "this spec has old prose" vs. "this
run just wrote bad prose" — under one signal, losing the ability to hold new
work to a higher bar than a repo can retroactively meet. The diff-scoped gate
gets the enforcement onto the one surface where it is fair (what a run itself
chooses to write or edit) without that blast radius, and follows an existing,
proven pattern in this same pipeline (`check_integration_coverage`,
`check_ci_supplychain_ack`) rather than inventing a new one.
