# Mini-plan: U4 - 100-line cascade trigger (iterate-2026-10-08-u4-cascade-trigger-100)

Problem: the phase matrix says a `small` iterate runs the code-review cascade when a risk flag is set OR the diff has
more than 100 changed lines. Nothing enforces it: `code_review_floor` starts at medium and the review record only
requires an answer, so a free-text `not_run` passes. The 100-line count is also defined three ways
(`git diff HEAD~1 | wc -l` in the runner doc = patch lines incl. headers/context of the last commit only; numstat
added+deleted vs fork point in Step 3.4; nothing at F11).

1. `shared/scripts/lib/review_diff_threshold.py` (stdlib only): `DIFF_LOC_THRESHOLD = 100` (+ alias
   `PLAN_REVIEW_DIFF_LOC_THRESHOLD`), `exceeds_diff_threshold` (strict `>`), `is_counted_path` (excludes `.shipwright/`,
   `CHANGELOG-unreleased.d/`, `shipwright_events.jsonl`, `shipwright_test_results.json` - finalization records written
   after the trigger is decided), `numstat_changed_lines` (added+removed, binary 0, rename record raises).
2. Plugin side: `review_threshold_bridge.py` loads the shared file by path under a private module name, registered
   before exec (ADR-044/045), no local fallback. `diff_risk_recheck.py` re-exports the constant and uses
   `exceeds_diff_threshold`; `diff_change_set.py` applies `is_counted_path` to both numstat and untracked counts.
3. F11 gate `verifiers/cascade_trigger.py::check_cascade_trigger` registered in `CLAIM_CHECKS` (U0 extension point;
   `iterate_checks.py` untouched). Inputs in `verifiers/_cascade_trigger_inputs.py`: risk flags = union of the
   session plan (`<run_id>.plan.json`), Step 3.4 `risk_recheck.json`, and `cross_component`/CI paths recomputed from
   the diff; diff = numstat `merge-base..commit` via `_branch_base_commit`. At small + trigger: `code` must be
   `completed` with evidence (`carries_evidence`) or `not_run`/`not_applicable` with a `review_not_run` reason_code
   that does not deny the trigger (`diff-below-threshold`, `complexity-below-threshold`, `trivial-auto` refused).
   Other complexities SKIP; missing entry/record SKIP (check_review_record already fails them). Unmeasurable diff
   with no flag fails closed.
4. Docs: `sub-iterate-runner.md` Step 3.7 trigger lines (size-neutral, 510), `iteration-reviews.md` counting rule +
   `--reason-code delegated-to-orchestrator` on the campaign `code` row, `docs/hooks-and-pipeline.md` claim-check row.
5. Tests (all tagged FR-01.11): real-git gate tests incl. 100/101 boundary, removed lines, finalization exclusion,
   cross_component recompute, closed/contradicting codes, evidence; shared lib unit tests; plugin bridge tests.

Alternative considered: put the gate in `review_record_floor.py` (extend the floor to small) - rejected because that
file holds the medium+ substance predicates and iterate_checks/review_record_check have no headroom; the U0 registry is
the designated extension point.
