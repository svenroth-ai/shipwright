# iterate-2026-08-01-campaign-diff-driven-risk-recheck

- **Run ID:** `iterate-2026-08-01-campaign-diff-driven-risk-recheck`
- **Intent:** CHANGE (Path B)
- **Complexity:** medium (Stage 1 `medium`; risk floor `cross_component` → medium; Stage 2 Thorough Scout confirms)
- **Risk flags:** `cross_component` (enforces `full_test_suite` + `integration_coverage`)
- **Spec Impact:** NONE — this changes framework process machinery, not a product
  requirement. No `spec.md` gains or loses a behavior. (`spec_impact_justification`
  required at F11; see F5b classification.)

## Problem

In campaign mode the `sub-iterate-runner` classifies complexity **exactly once**, at
Step 2, from the sub-iterate spec *text*, before any code exists:

```
uv run classify_complexity.py --project-root … --message "$(cat {sub_iterate_spec})"
```

`classify()` takes `(message, sync_config_path, project_root)`. Its risk detection is
`detect_risk_flags(message)` — a regex sweep over the message. The four **diff-driven**
detectors are imported into `classify_complexity` at line 30 and **never called** by
`classify()`. `risk_detectors.py:16-23` states this outright:

> **These detectors have no in-repo production caller.** … the functions here are
> contract surface … and for the Repo Scout, which runs them over the changed-file
> list at Stage 2.

The runner never reaches Stage 2 (Repo Scout). So in campaign mode
`cross_component`, `touches_ci_supplychain`, and the file-pattern halves of
`touches_io_boundary` / `touches_build` are **structurally unable to fire**.

### Two distinct consequences — they are not the same failure

1. **`touches_ci_supplychain` → hard failure.** `check_ci_supplychain_ack`
   (`verifiers/ci_supplychain.py:168`) *"Applies at EVERY complexity on purpose."*
   It RECOMPUTES the flag from the commit diff. A unit that edits
   `.github/workflows/**` never learns the flag, never writes the ack, and then
   **fails its own F6-verify** — the self-verifier the runner is contractually
   required to run against its own commit. The campaign unit dies at finalization
   with an error naming an artifact nobody told it to produce.

2. **`cross_component` → silent stand-down.** `check_integration_coverage`
   (`verifiers/integration_coverage.py:70`) returns a green **SKIP** when the
   recorded complexity is not `medium`/`large`. Combined with the #506 fall-through
   cap (`small`), a fleet unit touching hooks or the churn resolver records
   `small`, and the gate reports green without ever evaluating. The gate reads
   complexity from the **F5c entry** (`find_entry_by_run_id`), so the recorded
   value is what decides.

Downstream, Step 3.5 (External Plan Review, `medium+ OR risk flag`) is a guaranteed
skip for a no-keyword fleet unit, while Step 3.7 survives on its `OR diff > 100 LOC`
arm. That asymmetry is unintentional.

## Acceptance Criteria

- **AC1** — A single-purpose CLI runs the four diff-driven detectors over a
  changed-file list and reports: risk flags, the implied complexity floor, diff LOC,
  and whether the run must escalate. Usable both from a git range and from an
  explicit file list (the latter is what makes it testable).
- **AC2** — The runner contract gains **Step 3.4 — Diff-Driven Risk Re-Check**,
  placed after Build (Step 3) and before Step 3.5, so a diff exists when it runs.
  It raises the effective complexity to `max(stage-1 estimate, detector floor)`.
- **AC3** — The upgraded complexity is what F5c records, so
  `check_integration_coverage` stops green-SKIPping.
- **AC4** — `touches_ci_supplychain` makes the unit **stop and hand back**:
  `status: "escalated"` with a CI-specific reason code and the offending paths.
  The runner never writes its own CI acknowledgement. (Operator decision,
  2026-08-01: a machine writing its own permission slip defeats the gate.)
- **AC5** — Step 3.5's trigger mirrors Step 3.7's: `medium+ OR risk flag OR
  diff > 100 LOC`.
- **AC6** — The result-JSON schema accepts the new record and the new escalation
  shape. Both `success` and `escalated` set `additionalProperties: false`, so an
  unregistered field is a validation failure, not a no-op.
- **AC7** — `risk_detectors.py`'s "no in-repo production caller" paragraph is
  corrected in the same diff; it becomes false the moment the CLI lands.
- **AC8** — `sub-iterate-runner.md` ends at **≤497 lines** (baseline `current: 497`,
  `state: exception`, ADR-119). Anti-Ratchet forbids raising it.

## Affected Boundaries

| Boundary | Producer | Consumer |
|---|---|---|
| Re-check CLI stdout (JSON) | `diff_risk_recheck.py` | the runner (Bash, Step 3.4) |
| `result.json` | runner | campaign orchestrator + JSON schema |
| F5c entry `complexity` | runner Step 4 | `check_integration_coverage` |
| Detector pattern tuples | `risk_detectors.py` (SSoT) | drift-pinned verifier copies |

## Non-Goals

- Adding a `--changed-files` parameter to `classify()`. Rejected (see Alternative).
- Making the runner author CI acknowledgements autonomously (AC4 forbids it).
- Widening the detector pattern tuples themselves. The patterns are correct; nothing
  *calls* them. Widening a surface without a caller is the exact mistake
  `risk_detectors.py:20-23` warns about.

## Confidence Calibration

- **Boundaries touched:**
  1. `diff_risk_recheck.py` stdout JSON — producer; the runner (Bash) consumes it.
  2. `result.json` — runner produces, `autonomous_loop.cmd_record` + the JSON
     schema consume.
  3. F5c entry `complexity` — runner produces, `check_integration_coverage`
     consumes.
  4. `git` porcelain (`--numstat -z`, `ls-files --others -z`) — git produces,
     `diff_change_set` parses.
  5. Stage-1 `risk_flags` (a JSON array) → `--stage1-flags` (a comma list).

- **Empirical probes run:**
  1. **git rename behaviour (found a real bug).** Built a repo, committed
     `.github/workflows/security.yml`, `git mv`'d it to `security.yml.disabled`.
     With default rename detection git emits ONE record whose path is
     `.github/workflows/{security.yml => security.yml.disabled}` — which fails the
     `^\.github/workflows/.+\.ya?ml$` anchor, so **no CI flag fired and an
     autonomous unit could have disabled a security workflow**. With
     `--no-renames` the same move yields `0 1 .github/workflows/security.yml` +
     `1 0 …disabled`, and the flag fires. Fixed; pinned by
     `test_moving_a_workflow_out_of_the_trust_boundary_still_escalates`.
  2. **Uncommitted/untracked visibility.** Real repo, `hooks.json` staged-not-
     committed → `cross_component` fires; a never-`git add`ed hook script under
     `plugins/x/hooks/` → still fires (it appears in no `git diff`). Confirms the
     working-tree change set, the highest-severity plan-review finding.
  3. **Wire-format probe (found a real bug).** `classify_complexity` emits
     `risk_flags` as a JSON *array*; the naive split yielded
     `['["touches_auth"', '"touches_rls"]']` — enough to keep
     `plan_review_required` truthy while Step 3.8's NAMED lookup for
     `touches_io_boundary` missed. `_split_flags` now strips JSON punctuation;
     pinned by a parametrised case plus a by-name assertion.
  4. **Escalation termination probe (found a real design bug).** Traced the
     documented recovery — record ack → re-run unit → Build re-creates the CI edit
     → escalate again. Non-terminating. The CLI is now ack-aware (`--run-id`);
     pinned by `test_recorded_ack_clears_the_stop_but_keeps_the_finding` and a
     run-binding negative case.
  5. **Verifier-agreement probe.** Ran `drr.detect_diff_flags` and
     `integration_coverage._is_cross_component` over the same four paths — the two
     drift-pinned copies agree. Two further probes (mode-only chmod change,
     non-UTF-8 paths) found nothing; **asymptote reached** (two consecutive
     no-finding probes).

- **Test Completeness Ledger:** every behavior below is `tested`; **0
  testable-but-untested**.

| # | Behavior | Category | Status | Evidence |
|---|---|---|---|---|
| 1 | Four diff-driven detectors fire from a path list | unit | tested | `test_cross_component_detected`, `test_ci_supplychain_detected`, `test_touches_build_detected`, `test_io_boundary_detected` |
| 2 | Flags sorted, de-duplicated, path-normalised (Windows + git-quoted) | unit | tested | `test_flags_are_sorted_and_deduped`, `test_windows_separators_normalized`, `test_quoted_non_ascii_path_still_fires` |
| 3 | Complexity floor uses canonical order, never lowers Stage 1 | unit | tested | `test_cross_component_floors_at_medium`, `test_floor_never_lowers_stage1`, `test_ordering_is_semantic_not_lexicographic` |
| 4 | Unknown Stage-1 complexity rejected at the boundary | unit | tested | `test_unknown_stage1_complexity_rejected` |
| 5 | Stage-1 flags UNIONED, not replaced (incl. JSON-array wire form) | unit | tested | `test_stage1_flags_are_unioned_not_replaced`, `test_split_flags_accepts_both_separators_and_json_arrays`, `test_json_array_flags_survive_by_name_not_just_by_count` |
| 6 | `plan_review_required` mirrors Step 3.7 (medium+ / flag / >100 LOC, strict) | unit | tested | `test_plan_review_required_on_*`, `test_diff_loc_boundary_is_strictly_greater_than_100` |
| 7 | CI change escalates with reason_code + only CI paths | unit | tested | `test_ci_supplychain_escalates`, `test_escalation_paths_list_only_ci_files`, `test_non_ci_flags_do_not_escalate` |
| 8 | A recorded ack for THIS run clears the stop; another run's does not | unit | tested | `test_recorded_ack_clears_the_stop_but_keeps_the_finding`, `test_main_exit_0_once_an_ack_exists`, `test_main_still_exits_3_when_the_ack_is_for_another_run` |
| 9 | numstat parsing: counts, binary `-`, TAB/newline in path, rename refused | unit | tested | `test_parse_numstat_*`, `test_parse_numstat_rejects_rename_shaped_records` |
| 10 | Change set = fork point → working tree, unioned with untracked | unit | tested | `test_collect_change_set_unions_tracked_and_untracked`, `test_collect_change_set_prefers_merge_base_over_ref_tip` |
| 11 | git failures RAISE (diff, ls-files, unresolvable ref) — never fail-open | unit | tested | `test_untracked_failure_raises_instead_of_silently_dropping`, `test_diff_failure_raises`, `test_unresolvable_base_ref_raises` |
| 12 | `main()` exit/stdout contract: 0, 3, 2-with-JSON; `--base-ref` defaults to HEAD | unit | tested | `test_main_exit_0_and_json_when_clean`, `test_main_exit_3_and_json_on_ci_escalation`, `test_main_exit_2_still_writes_json`, `test_main_defaults_base_ref_to_head` |
| 13 | **Uncommitted / unstaged / untracked work is seen end-to-end** | **integration** | tested | `test_uncommitted_cross_component_change_is_detected`, `test_unstaged_change_is_detected`, `test_untracked_new_hook_is_detected` |
| 14 | **A workflow moved out of the trust boundary still escalates** | **integration** | tested | `test_moving_a_workflow_out_of_the_trust_boundary_still_escalates` |
| 15 | **The returned floor is inside the verifier's own evaluate-set** | **integration** | tested | `test_floor_unskips_the_integration_coverage_gate` (threshold read out of `integration_coverage.py`, not copied) |
| 16 | **The escalation is expressible as a schema-valid result** | **integration** | tested | `test_escalation_result_matches_the_runner_contract_schema` |
| 17 | Detector and drift-pinned verifier copy agree on the same paths | integration | tested | `test_verifier_and_detector_agree_on_cross_component_paths` |
| 18 | Schema: `risk_recheck` optional; CI escalation requires non-empty `ci_paths`; legacy `large` still valid | unit | tested | `test_schema_*` in `test_sub_iterate_runner_step_3_4.py` |
| 19 | Contract drift: Step 3.4 anchors, ordering, ≤497 ceiling, campaign-mode prose | unit | tested | `test_sub_iterate_runner_step_3_4.py` (assertions scoped to the Step 3.4 slice) |
| 20 | Escalated unit keeps its `reason`; a complete unit never gains one | unit | tested | `test_ci_escalation_preserves_reason_and_strict_stops`, `test_complete_result_never_gains_a_failure_reason` |

- **Confidence-pattern check:**
  - **Asymptote (depth):** four probes found real bugs (rename blind spot, wire
    format, non-terminating escalation, plus the plan-review-narrowing regression
    caught in review); each was fixed and re-probed. The final two probes
    (mode-only change, non-UTF-8 paths) found nothing → exhausted.
  - **Coverage (breadth):** all five boundaries above have at least one test; the
    git boundary is covered both in-process (fakes encoding git's real record
    shapes) and against a real repository.
  - **Integration composition:** `cross_component` is set, so rows 13–17 carry
    `category: "integration"`. They prove the pieces *compose* — the original
    defect was that four individually-correct detectors were collectively inert
    because nothing called them.
  - **Known limit, stated rather than hidden:** AC3 (F5c records the upgraded
    complexity) is enforced by contract prose, not by a gate — see the ADR's
    "Accepted limitation". Every other runner-contract step (3.5–3.8) is
    enforced the same way, so this is consistent with the existing design rather
    than new debt, but it is real and is filed for follow-up.
