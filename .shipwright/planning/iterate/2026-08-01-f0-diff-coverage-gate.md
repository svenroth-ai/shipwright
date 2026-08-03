# Iterate Spec: f0-diff-coverage-gate

- **Run ID:** iterate-2026-08-01-f0-diff-coverage-gate
- **Type:** feature
- **Complexity:** medium
- **Status:** implemented

## Goal

Make F0 answer the diff-coverage question that today only CI can answer. The F0
suite runner measures coverage per unit, combines it into one repo-relative
`coverage.xml`, and runs the *same* pinned `diff-cover` gate the CI composite
action runs — so an under-tested diff STOPs the run before the push instead of
reddening a PR the iterate has already reported done.

`.github/**` is deliberately untouched: the CI step stays as the backstop, which
is also why this change raises no `touches_ci_supplychain` flag and cannot
collide with IT-9.

## Acceptance Criteria

- [x] **AC-1** After `run_test_suite.py` completes on this repo, `<root>/coverage.xml`
      exists and contains repo-relative `filename` entries for **both** tiers:
      at least one matching `plugins/<name>/scripts/` and at least one matching
      `shared/`.
- [x] **AC-2** For every discovered unit with a measurable source root,
      `build_command(unit, None)` contains `--cov=<source>`,
      `--cov-config=<absolute root pyproject.toml>` and `--cov-report=`, and the
      unit carries a distinct absolute `cov_file` under `<root>/.cov-data/`;
      a plugin with no `scripts/` directory carries none of them.
- [x] **AC-3** The local gate argv equals the CI composite action's command shape:
      `uvx diff-cover@<V> coverage.xml --compare-branch=origin/main --fail-under=80`,
      where `<V>` equals the `diff-cover-version` default and `80` equals the
      `fail-under` default declared in `.github/actions/diff-coverage-gate/action.yml`
      — **plus exactly one deliberate divergence, `--diff-file=<run-owned patch>`**,
      asserted positionally so it cannot become accidental.
- [x] **AC-3b** The gate measures files the iterate has **added but not yet
      committed**. F0 runs before F6, so the final tree spans committed, staged,
      unstaged, and untracked state. A private temporary index starts at the merge
      base and `git add -A`s that final working tree, including untracked and excluding
      ignored files, into one coherent patch. This avoids both the invisible-new-file
      false green and diff-cover's default union of hunks numbered against different
      file revisions. CI needs no patch because its final snapshot is one commit.
- [x] **AC-4** With a green suite, `run_test_suite.py` exits `4` when diff coverage
      is below the threshold, and `0` when at/above it.
- [x] **AC-4b** "Nothing was measurable" and "measurement failed" are different
      verdicts: with **zero** instrumented units the run exits `0` and prints an
      `n/a` line; with **one or more** instrumented units but no combined
      `coverage.xml`, or a non-zero combine, it exits `4` naming the phase that
      failed. Combine and diff-cover use a unique invocation-owned XML until the
      verdict is known, so a fresh root `coverage.xml` from another producer is
      never accepted as this run's evidence. *(Deliberately stricter than ci.yml's
      `if: hashFiles('coverage.xml') != ''` guard, which cannot tell those two apart.)*
- [x] **AC-4c** Every failure mode of the two subprocesses — non-zero exit, a
      raised `OSError`/`SubprocessError` (`uvx` absent, resolution failure) — maps
      to exit `4` with a phase-specific message, never to a traceback and never
      to a pass. Exit `1` is described as "below threshold" only when the output
      also contains diff-cover 10.3.0's pinned threshold-failure signature;
      launcher/package failures that also return `1` remain infrastructure errors.
- [x] **AC-4d** The compare branch is CI's declared `origin/main`, refreshed with
      the action's `git fetch --no-tags origin main` shape and then verified before
      the gate runs. A stale local ref or a differing/dangling `origin/HEAD` cannot
      change the local line set. When fetch/verification fails the gate exits `4`
      with an actionable message rather than crashing — a base that cannot be
      refreshed must not silently green a gate whose whole job is to compare it.
      A shallow checkout with no merge base also exits `4` and names history
      deepening as the remediation. All Git subprocesses use `git -C` with an
      absolute root and remove inherited repository/index redirection variables;
      a fork workflow must configure `origin` as the canonical remote CI uses.
- [x] **AC-5** With a red suite, the gate does not run at all: the process exits
      `1` and prints a line stating the gate was skipped because the suite is red.
- [x] **AC-6** Each of the three `shared/` units writes its **own**
      `.cov-data/.coverage.<label>` file (no shared `--cov-append` target),
      because F0 runs them concurrently; the combine step unions them.
- [x] **AC-6b** Two simultaneous F0 CLI invocations in one checkout cannot reset,
      combine, or gate each other's repository-global coverage state. An OS-backed
      lock spans reset → suite → combine → gate; a second invocation exits `2`
      with an actionable message, and a crashed process releases the lock. The
      stable root lock path is outside resettable coverage state and survives a
      reset while held.
- [x] **AC-6c** Coverage from a failed first attempt never contributes to an
      accepted retry. Before the retry, the unit's base `COVERAGE_FILE` and exact
      pytest-cov/xdist suffix family are removed; a survivor fails closed rather
      than inflating the authoritative retry's coverage.
- [x] **AC-6d** The coverage data and gated patch describe the same Python-source
      snapshot. F0 hashes path plus file bytes/symlink target for tracked plus
      untracked, non-ignored `.py`/`.pyi` files and the repository's test, coverage,
      interpreter and dependency config inputs before the suite, after the
      suite/fetch/patch, and after diff-cover; any change exits `4` and asks for a
      rerun. Ignored generated coverage artefacts do not participate.
- [x] **AC-7** Adding coverage args does not displace the shared units' marker
      expression: `build_command` for a `shared/…` unit still contains
      `-m` immediately followed by `not slow and not cross_plugin`.
- [x] **AC-8 (agent, E2E)** Driven live through the CLI surface at F0.5, against a
      synthetic repo that has a real `origin/main` remote-tracking ref (bare
      remote → push → fetch): with one changed, **uncovered** source line the
      real pinned `diff-cover` makes the gate exit `4`; after a test covering
      that line is added, the same command exits `0`.
- [x] **AC-9** Two units can never share a coverage data file: if two discovered
      unit ids sanitise to the same label, instrumentation raises
      `SuiteConfigError` **before** any process starts, rather than letting two
      concurrent writers silently merge.
- [x] **AC-10** An uninstrumented unit does not inherit an ambient `COVERAGE_FILE`
      from the operator's shell — its subprocess environment has the variable
      removed, not merely left unset.

## Spec Impact

- **Classification:** none
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** This changes a framework-internal quality gate (the F0
  verification step of the iterate lifecycle). It adds no user- or
  system-observable product capability, and `file_to_fr_map` maps none of the
  touched files to an FR. `change_type: tooling`, matching the precedent set by
  `iterate-2026-08-01-pin-python-311` on this same runner.

## Out of Scope

- **Any edit under `.github/`.** The CI step remains the backstop (brief §3:
  the mirrored gates cost 5 s of 461 s — there is no fat to cut). This also keeps
  the change clear of `touches_ci_supplychain` and of IT-9.
- Changing the `80` threshold, or making it configurable.
- An opt-out env var or config key. The brief specifies a *permanent* addition;
  a switch would be the first thing reached for on a red gate.
- Parallelising CI, or otherwise weakening `test_ci_stays_SERIAL`.
- Changing which units F0 discovers.

## Design Notes

n/a — no UI surface.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| pytest-cov (per unit, via `COVERAGE_FILE`) | `combine_coverage.combine_to_xml` | coverage.py data file |
| `combine_coverage.combine_to_xml` | `diff-cover` | cobertura XML |

Both formats are produced and consumed by third-party tools already wired
together in `ci.yml`; this change introduces **no new serialized format** of our
own. `is_io_boundary_change` over the planned file list returns `False`, so no
Boundary Probe is enforced — the round-trip that matters (data file → combined
XML → diff-cover) is exercised end-to-end by AC-8 instead.

## Confidence Calibration

- **Boundaries touched:** the two producer/consumer pairs above; no
  Shipwright-owned format.

- **Empirical probes run** (each one a command whose output could have refuted the
  design, not a re-reading of the diff):

  | # | Probe | Finding |
  |---|---|---|
  | P1 | `diff-cover --help` → `--diff-range-notation` | Defaults to `...`, so `--compare-branch origin/main` is **already** a merge-base diff. The brief's requirement is met by mirroring CI's flags; no extra work, and a moved `main` cannot inflate the changed-line set. |
  | P2 | pinned diff-cover 10.3.0 `--diff-file` source/help | `GitDiffFileTool` replaces the committed diff and returns empty staged/unstaged/untracked additions, so one private-index patch is the complete line set rather than a fourth union member. |
  | P3 | `inspect.getsource(diff_cover_tool.main)` | `return 1` is emitted **only** for below-threshold. Every other non-zero is the tool's own failure — so conflating them (as the first cut did) tells an operator to write tests for a network or git problem. |
  | P4 | Real `run_test_suite.py` CLI over a synthetic repo, change left **uncommitted** | Exit **4** while `b()`/`c()` are uncovered, exit **0** once a test covers them. Proves the whole chain through the actual F0 entry point, including that untracked files are measured. 18 s. |
  | P5 | The combined `coverage.xml` from that run | Contains `plugins/p1/scripts/m.py` (**remapped** from the plugin's CWD-relative `scripts/m.py`) **and** `shared/s.py` (**not** remapped). Both halves of the combiner's rule, and proof the tiers were unioned rather than one overwriting the other. |
  | P6 | **Pre-hardening real F0 on this repo** | 18/18 units GREEN in 6.7 min and 97% over 166 changed lines. This established the cost and coverage baseline; the final F11 run supersedes its old multi-diff line-set evidence with the private-index path. |
  | P7 | Same run, missing-data check | Every instrumented unit wrote its data file: no `missing_data` refusal fired, so the new fail-closed check does **not** false-STOP a healthy run. |
  | P8 | Post-integration race E2E + full integration root | The pre-existing race-followup E2E now creates the real `origin/main`, committed Python-3.11 lockfile, and ignored runtime state that permanent F0 requires. The focused proof passed 1/1 and the complete integration root passed 444/444 (2 deselected) in 106.94 s. Production fingerprinting remained fail-closed. |
  | P9 | **Final canonical F0 after origin/main integration** | 18/18 units GREEN in 4.0 min. Pinned diff-cover 10.3.0 measured 335 changed lines at 93% (22 missing) against refreshed `origin/main`, above the 80% gate. |

  **The two E2E layers are load-bearing for AC-3b**: the CLI fixture leaves its new
  implementation uncommitted, while the direct real-tool E2E adds a ten-line dirty
  shift above a committed hunk and still fails on the final uncovered coordinates.
  Together they prove new files are included and mixed states are one snapshot.

  **A cost the brief under-estimated, stated rather than smoothed over:** the brief
  budgeted ~1–2 min; the measured F0 was **6.7 min against a ~1.9 min baseline**.
  `shared/tests` alone was 364 s. A time-boxed warm diagnosis on 432 deterministic
  tests confirmed that coverage uses coverage.py's C tracer and that the existing
  8-worker setting is already the faster safe setting: plain n=8 was 16.8 s,
  coverage n=8 was 32.9 s, and coverage n=4 was 37.0 s. There is therefore no small,
  semantics-preserving parallelism fix to take; narrowing the measured source or
  diverging from CI would weaken the gate. On 2026-08-02 the maintainer explicitly
  accepted this conservative cost after that diagnosis, given the observed 29%
  CI-failure rate and 1.18 additional CI cycles per branch. The final F11 warm
  full-suite measurement completed in 4.0 min with all 18 units green and 93%
  diff coverage over 335 changed lines.

- **Test Completeness Ledger** — 17 ACs, 39 behaviours, **0 untested-testable**:

  | # | Testable behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | A plugin with `scripts/` is measured from its own CWD | tested | `test_a_plugin_with_scripts_is_measured_from_its_own_cwd` PASSED |
  | 2 | A plugin without `scripts/` is not instrumented at all | tested | `test_a_plugin_without_scripts_is_not_instrumented` PASSED |
  | 3 | shared + integration tiers measure `shared/` | tested | `test_shared_and_integration_tiers_measure_shared` PASSED |
  | 4 | `--cov-config` is the ABSOLUTE root pyproject | tested | `test_the_cov_config_is_the_absolute_root_pyproject` PASSED |
  | 5 | Each shared unit writes its OWN data file; no `--cov-append` | tested | `test_each_shared_unit_writes_its_OWN_data_file` PASSED |
  | 6 | Colliding labels fail closed before any process starts | tested | `test_colliding_labels_fail_before_any_process_starts` PASSED |
  | 7 | No root `pyproject.toml` ⇒ nothing instrumented | tested | `test_no_root_pyproject_means_no_instrumentation` PASSED |
  | 8 | `instrument_for_coverage` resolves a relative root/data dir | tested | `test_the_cov_config_is_the_absolute_root_pyproject` PASSED (asserts `is_absolute()`) |
  | 9 | Coverage args never split the `-m` marker expression | tested | `test_coverage_args_never_split_the_marker_expression` PASSED |
  | 10 | An instrumented unit gets its own `COVERAGE_FILE` | tested | `test_an_instrumented_unit_gets_its_own_coverage_file` PASSED |
  | 11 | An uninstrumented unit does not inherit an ambient `COVERAGE_FILE` | tested | `test_an_uninstrumented_unit_does_not_inherit_an_ambient_coverage_file` PASSED |
  | 12 | `run_suite` reports the data files it told units to write | tested | `test_run_suite_reports_the_files_it_told_units_to_write` PASSED (real `run_suite`, expectation derived from `discover_units`) |
  | 13 | A project that cannot be measured reports nothing, not breakage | tested | `test_a_project_without_a_root_pyproject_measures_nothing` PASSED |
  | 14 | `main` hands the gate the FILES, not a count | tested | `test_the_gate_is_handed_the_files_not_just_a_count` PASSED |
  | 15 | `main` exits 4 and surfaces diff-cover's report | tested | `test_an_under_covered_diff_stops_the_run` PASSED |
  | 16 | Exit precedence: suite rc > unrecorded race > gate | tested | `test_exit_code_precedence` PASSED (6 combinations) |
  | 17 | `warm_up` provisions the package instrumentation adds | tested | `test_warm_up_provisions_the_package_instrumentation_adds` PASSED |
  | 18 | `gate_argv` mirrors the action's command shape, positionally | tested | `test_the_local_gate_command_matches_the_action_command` PASSED |
  | 19 | Gate argv consumes one coherent final-worktree patch that includes untracked and excludes ignored files | tested | `test_gate_argv_uses_one_coherent_final_worktree_diff`, `test_the_documented_scratch_directory_is_actually_ignored`, `test_line_shifting_uncommitted_edits_use_one_coherent_final_snapshot` PASSED |
  | 20 | Version, threshold, and compare ref equal the action's declared defaults | tested | `test_local_gate_pins_the_same_diff_cover_as_ci`, `test_local_gate_uses_the_same_threshold_as_ci`, `test_local_gate_uses_the_same_compare_branch_as_ci` PASSED |
  | 21 | ci.yml keeps the gate as the backstop | tested | `test_ci_keeps_the_diff_coverage_gate_as_the_backstop` PASSED |
  | 22 | `combine_argv` delegates to the ONE combiner | tested | `test_combine_argv_delegates_to_the_one_combiner` PASSED |
  | 23 | `eligible == 0` ⇒ n/a PASS | tested | `test_nothing_eligible_is_n_a_and_passes` PASSED |
  | 24 | The no-config cause is named distinctly from no-source-root | tested | `test_the_no_config_case_names_the_config_not_the_source_roots` PASSED |
  | 25 | Instrumented but no XML ⇒ fail closed | tested | `test_eligible_units_but_no_xml_fails_closed` PASSED |
  | 26 | A failed combine ⇒ fail closed | tested | `test_a_failed_combine_fails_closed` PASSED |
  | 27 | Below threshold ⇒ fail, and names locally-skipping tests as a cause | tested | `test_below_threshold_fails_and_says_what_to_do` PASSED |
  | 28 | A broken diff-cover or uvx rc=1 without diff-cover's pinned threshold message is NOT reported as a threshold verdict | tested | `test_a_broken_diff_cover_is_not_reported_as_a_threshold_verdict`, `test_uvx_exit_one_without_diff_cover_verdict_is_infrastructure_failure` PASSED |
  | 29 | No compare branch ⇒ fail closed naming `git fetch` | tested | `test_an_unresolvable_compare_branch_fails_closed_with_a_fix` PASSED |
  | 30 | A unit that wrote no data is named, and gating stops before combining | tested | `test_a_unit_that_wrote_no_data_is_named_not_ignored`, `test_the_gate_refuses_before_measuring_when_a_unit_wrote_nothing` PASSED; xdist suffix tolerated by `test_an_xdist_suffixed_data_file_counts_as_present` |
  | 31 | A red suite skips the gate, fetch, and diff builder entirely | tested | `test_a_red_suite_skips_the_gate_entirely`, `test_a_red_suite_never_fetches_or_builds_a_diff` PASSED |
  | 32 | Every subprocess failure mode ⇒ closed gate, never a traceback | tested | `test_a_missing_binary_is_a_closed_gate_not_a_traceback[uvx\|combine_coverage]`, `test_git_being_unavailable_is_no_base_rather_than_a_crash`, `test_a_report_that_vanishes_mid_check_is_untrusted_not_a_traceback` PASSED |
  | 33 | Stale/foreign state: reset retries/refusal stay fail-closed, and even a freshly written root XML is not trusted unless this invocation's unique combine candidate produced it | tested | `test_prepare_clears_stale_state_and_returns_the_data_dir`, `test_a_momentarily_held_file_is_retried_not_refused`, `test_stale_state_that_survives_the_reset_is_refused`, `test_prepare_leaves_a_project_it_will_never_measure_alone`, `test_a_coverage_xml_this_run_did_not_write_is_not_trusted` PASSED |
  | 34 | Compare-branch parity: targeted non-interactive bounded fetch refreshes CI's `origin/main`, a differing/dangling `origin/HEAD` is ignored, and missing/shallow history fails closed with a specific deepening fix | tested | `test_compare_branch_uses_ci_origin_main_even_when_origin_HEAD_differs`, `test_compare_branch_returns_origin_main_when_it_resolves`, `test_compare_branch_refreshes_a_stale_origin_main_before_using_it`, `test_compare_fetch_cannot_prompt_or_wait_without_a_bound`, `test_compare_branch_is_None_when_no_base_exists`, `test_a_dangling_origin_HEAD_falls_back_to_a_valid_origin_main`, `test_missing_merge_base_names_the_shallow_history_fix` PASSED |
  | 35 | End to end, real tools: uncovered fails / covered passes, mixed committed+dirty line shifts use final coordinates, both tiers land repo-relative, the CLI returns 4 then 0, and the existing race-followup path remains green under the permanent gate | tested | `test_an_uncovered_changed_line_fails_the_gate`, `test_covering_the_changed_line_passes_the_gate`, `test_line_shifting_uncommitted_edits_use_one_coherent_final_snapshot`, `test_the_combined_xml_is_repo_relative_so_diff_cover_can_match_it`, `test_the_f0_cli_stops_on_an_under_covered_diff_then_passes_once_covered`, `test_the_runner_records_a_real_race_and_never_auto_closes_it` PASSED |
  | 36 | A second F0 cannot enter the repository-global coverage critical section; reset preserves the stable lock rendezvous, while release makes it reusable | tested | `test_a_second_f0_cannot_enter_the_coverage_critical_section`, `test_coverage_reset_preserves_the_held_lock_rendezvous` PASSED |
  | 37 | An authoritative retry discards the failed attempt's base and xdist-suffixed coverage before it starts | tested | `test_an_authoritative_retry_discards_the_failed_attempts_coverage` PASSED |
  | 38 | Inherited Git repository/index variables cannot redirect fetch, fingerprint, merge-base, or the private index away from the absolute project root | tested | `test_compare_fetch_cannot_prompt_or_wait_without_a_bound`, `test_missing_merge_base_names_the_shallow_history_fix` PASSED |
  | 39 | A measured source/config change during suite, fetch, patch creation, or gate invalidates coverage | tested | `test_source_fingerprint_hashes_existing_source_and_root_config` (existing `.py`, root coverage config, suite config), `test_source_change_during_suite_invalidates_coverage`, `test_source_change_after_fetch_patch_or_gate_invalidates_measurement` PASSED |

- **Confidence-pattern check:**
  - **Asymptote (depth).** Yes — and twice, which is the point. Stage 2 declared the
    gate fail-closed; Stage 3 then produced a scenario in which it reports PASS
    having measured nothing (F0 runs before F6, so added files are untracked and
    invisible to diff-cover). A second "confident" answer after the Stage-2 fixes
    would have been the pattern this check exists to catch, so I ran P4 and P6 —
    live runs whose output could have refuted the fix — rather than re-reading the
    code. The CLI E2E and mixed-state real-tool E2E are the refutation-resistant evidence.
  - **Coverage (breadth).** 39 ledger rows, every one `tested`, zero
    untested-testable, zero `untestable`. Independently corroborated by the final
    gate measuring its own diff at 93% (335 changed lines, 22 missed) — a number
    produced by the pinned tool, not by me.
  - **Integration composition.** `cross_component` does **not** fire on this file
    list (verified with `is_cross_component_change` at Stage 2 of the Repo Scout, and
    the F11 verifier recomputes it from the diff independently). The composition that
    *does* matter here — runner → instrumentation → combiner → diff-cover — is
    nonetheless proven end to end by row 35 rather than assumed from unit tests.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run --python 3.11 --with pytest --with pytest-cov --with pytest-mock pytest shared/scripts/tools/tests/test_f0_cli_diff_coverage_e2e.py shared/scripts/tools/tests/test_f0_diff_coverage_e2e.py -q`
  — the two end-to-end modules. The first drives **`run_test_suite.py` itself** over
  a synthetic repo (real discovery, real per-unit `uv run pytest` with real
  pytest-cov, real combine, real pinned diff-cover) and asserts the F0 exit codes:
  **4** while the new function is uncovered, **0** once a test covers it. The second
  proves the same discrimination at the `run_gate` level plus the repo-relative
  combined XML for both tiers.
  Driving the CLI was added after external review pointed out that an E2E calling
  `run_gate` directly would still pass if the runner-level wiring were broken — a
  gate proven only below its own entry point is not proven.
  Real pytest modules rather than bespoke scripts, so the same evidence also runs
  inside the `shared/scripts/tools/tests` unit at F0 and in CI; deliberately **not**
  marked `slow`, since the shared units run `-m "not slow and not cross_plugin"` and
  a `slow` mark would silently remove the only end-to-end proof of the surface.
- **Evidence path:** `.shipwright/planning/iterate/iterate-2026-08-01-f0-diff-coverage-gate/f05_surface.txt`
