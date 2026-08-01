# Iterate Spec: f0-diff-coverage-gate

- **Run ID:** iterate-2026-08-01-f0-diff-coverage-gate
- **Type:** feature
- **Complexity:** medium
- **Status:** draft

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

- [ ] **AC-1** After `run_test_suite.py` completes on this repo, `<root>/coverage.xml`
      exists and contains repo-relative `filename` entries for **both** tiers:
      at least one matching `plugins/<name>/scripts/` and at least one matching
      `shared/`.
- [ ] **AC-2** For every discovered unit with a measurable source root,
      `build_command(unit, None)` contains `--cov=<source>`,
      `--cov-config=<absolute root pyproject.toml>` and `--cov-report=`, and the
      unit carries a distinct absolute `cov_file` under `<root>/.cov-data/`;
      a plugin with no `scripts/` directory carries none of them.
- [ ] **AC-3** The local gate argv equals the CI composite action's command shape:
      `uvx diff-cover@<V> coverage.xml --compare-branch=origin/main --fail-under=80`,
      where `<V>` equals the `diff-cover-version` default and `80` equals the
      `fail-under` default declared in `.github/actions/diff-coverage-gate/action.yml`
      — **plus exactly one deliberate divergence, `--include-untracked`**, asserted
      positionally so it cannot become accidental.
- [ ] **AC-3b** The gate measures files the iterate has **added but not yet
      committed**. F0 runs before F6, so every new file is untracked and diff-cover
      cannot see it by default. Without this the most likely under-covered case — a
      brand-new module — passes locally and reddens CI, and a diff of only new files
      measures nothing while reporting 100%. The divergence is what makes the two
      **line sets** equal, which is what parity is actually about; CI needs no such
      flag because it runs on a committed PR head.
- [ ] **AC-4** With a green suite, `run_test_suite.py` exits `4` when diff coverage
      is below the threshold, and `0` when at/above it.
- [ ] **AC-4b** "Nothing was measurable" and "measurement failed" are different
      verdicts: with **zero** instrumented units the run exits `0` and prints an
      `n/a` line; with **one or more** instrumented units but no combined
      `coverage.xml`, or a non-zero combine, it exits `4` naming the phase that
      failed. *(Deliberately stricter than ci.yml's `if: hashFiles('coverage.xml')
      != ''` guard, which cannot tell those two apart.)*
- [ ] **AC-4c** Every failure mode of the two subprocesses — non-zero exit, a
      raised `OSError`/`SubprocessError` (`uvx` absent, resolution failure) — maps
      to exit `4` with a phase-specific message, never to a traceback and never
      to a pass.
- [ ] **AC-4d** The compare branch is resolved from `origin/HEAD`, falling back to
      `origin/main`. When neither resolves the gate exits `4` with an actionable
      message rather than crashing — a base that cannot be found must not silently
      green a gate whose whole job is to compare against it.
- [ ] **AC-5** With a red suite, the gate does not run at all: the process exits
      `1` and prints a line stating the gate was skipped because the suite is red.
- [ ] **AC-6** Each of the three `shared/` units writes its **own**
      `.cov-data/.coverage.<label>` file (no shared `--cov-append` target),
      because F0 runs them concurrently; the combine step unions them.
- [ ] **AC-7** Adding coverage args does not displace the shared units' marker
      expression: `build_command` for a `shared/…` unit still contains
      `-m` immediately followed by `not slow and not cross_plugin`.
- [ ] **AC-8 (agent, E2E)** Driven live through the CLI surface at F0.5, against a
      synthetic repo that has a real `origin/main` remote-tracking ref (bare
      remote → push → fetch): with one changed, **uncovered** source line the
      real pinned `diff-cover` makes the gate exit `4`; after a test covering
      that line is added, the same command exits `0`.
- [ ] **AC-9** Two units can never share a coverage data file: if two discovered
      unit ids sanitise to the same label, instrumentation raises
      `SuiteConfigError` **before** any process starts, rather than letting two
      concurrent writers silently merge.
- [ ] **AC-10** An uninstrumented unit does not inherit an ambient `COVERAGE_FILE`
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
  | P2 | `diff-cover --help` → `--include-untracked` | Exists in the pinned 10.3.0. This is what made the Stage-3 objection fixable rather than a documented limitation. |
  | P3 | `inspect.getsource(diff_cover_tool.main)` | `return 1` is emitted **only** for below-threshold. Every other non-zero is the tool's own failure — so conflating them (as the first cut did) tells an operator to write tests for a network or git problem. |
  | P4 | Real `run_test_suite.py` CLI over a synthetic repo, change left **uncommitted** | Exit **4** while `b()`/`c()` are uncovered, exit **0** once a test covers them. Proves the whole chain through the actual F0 entry point, including that untracked files are measured. 18 s. |
  | P5 | The combined `coverage.xml` from that run | Contains `plugins/p1/scripts/m.py` (**remapped** from the plugin's CWD-relative `scripts/m.py`) **and** `shared/s.py` (**not** remapped). Both halves of the combiner's rule, and proof the tiers were unioned rather than one overwriting the other. |
  | P6 | **The real F0 on this repo, with this change live** | 18/18 units GREEN in 6.7 min. The gate then reported: `Diff: origin/main...HEAD, staged, unstaged and untracked changes` — 166 changed lines across the four changed Python files, 4 missing, **97 %** → PASS. |
  | P7 | Same run, missing-data check | Every instrumented unit wrote its data file: no `missing_data` refusal fired, so the new fail-closed check does **not** false-STOP a healthy run. |

  **P6 is the load-bearing one**: it is the only probe that shows the gate measuring
  a real diff on the real repo rather than a fixture, and its output string is the
  direct evidence for AC-3b — `and untracked changes` is diff-cover confirming it
  looked at files F6 had not committed yet.

  **A cost the brief under-estimated, stated rather than smoothed over:** the brief
  budgeted ~1–2 min; the measured F0 was **6.7 min against a ~1.9 min baseline**.
  Part of that is a first run provisioning `pytest-cov` into 18 unit environments,
  and part is coverage instrumentation slowing the xdist tiers (`shared/tests` alone
  was 364 s). I have **not** measured a warm second run, so I am not claiming it
  drops — the honest number today is 6.7 min, and whether that stays acceptable is
  the operator's call, not mine to assume.

- **Test Completeness Ledger** — 14 ACs, 33 behaviours, **0 untested-testable**:

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
  | 19 | `gate_argv` measures files not yet committed | tested | `test_gate_argv_measures_files_the_iterate_has_not_committed_yet` PASSED; confirmed live by P6 |
  | 20 | Version + threshold equal the action's declared defaults | tested | `test_local_gate_pins_the_same_diff_cover_as_ci`, `test_local_gate_uses_the_same_threshold_as_ci` PASSED |
  | 21 | ci.yml keeps the gate as the backstop | tested | `test_ci_keeps_the_diff_coverage_gate_as_the_backstop` PASSED |
  | 22 | `combine_argv` delegates to the ONE combiner | tested | `test_combine_argv_delegates_to_the_one_combiner` PASSED |
  | 23 | `eligible == 0` ⇒ n/a PASS | tested | `test_nothing_eligible_is_n_a_and_passes` PASSED |
  | 24 | The no-config cause is named distinctly from no-source-root | tested | `test_the_no_config_case_names_the_config_not_the_source_roots` PASSED |
  | 25 | Instrumented but no XML ⇒ fail closed | tested | `test_eligible_units_but_no_xml_fails_closed` PASSED |
  | 26 | A failed combine ⇒ fail closed | tested | `test_a_failed_combine_fails_closed` PASSED |
  | 27 | Below threshold ⇒ fail, and names locally-skipping tests as a cause | tested | `test_below_threshold_fails_and_says_what_to_do` PASSED |
  | 28 | A broken diff-cover is NOT reported as a threshold verdict | tested | `test_a_broken_diff_cover_is_not_reported_as_a_threshold_verdict` PASSED |
  | 29 | No compare branch ⇒ fail closed naming `git fetch` | tested | `test_an_unresolvable_compare_branch_fails_closed_with_a_fix` PASSED |
  | 30 | A unit that wrote no data is named, and gating stops before combining | tested | `test_a_unit_that_wrote_no_data_is_named_not_ignored`, `test_the_gate_refuses_before_measuring_when_a_unit_wrote_nothing` PASSED; xdist suffix tolerated by `test_an_xdist_suffixed_data_file_counts_as_present` |
  | 31 | A red suite skips the gate entirely | tested | `test_a_red_suite_skips_the_gate_entirely` PASSED (asserts zero subprocesses) |
  | 32 | Every subprocess failure mode ⇒ closed gate, never a traceback | tested | `test_a_missing_binary_is_a_closed_gate_not_a_traceback[uvx\|combine_coverage]`, `test_git_being_unavailable_is_no_base_rather_than_a_crash`, `test_a_report_that_vanishes_mid_check_is_untrusted_not_a_traceback` PASSED |
  | 33 | Stale state: cleared, retried when held, refused when it survives, left alone when nothing will be measured, and an XML this run did not write is untrusted | tested | `test_prepare_clears_stale_state_and_returns_the_data_dir`, `test_a_momentarily_held_file_is_retried_not_refused`, `test_stale_state_that_survives_the_reset_is_refused`, `test_prepare_leaves_a_project_it_will_never_measure_alone`, `test_a_coverage_xml_this_run_did_not_write_is_not_trusted` PASSED |
  | 34 | Compare-branch resolution: prefers `origin/HEAD`, falls back, rejects an unresolvable symref target | tested | `test_compare_branch_prefers_origin_HEAD`, `test_compare_branch_falls_back_to_origin_main`, `test_compare_branch_is_None_when_no_base_exists`, `test_an_origin_HEAD_pointing_at_a_ref_that_does_not_resolve_is_rejected` PASSED |
  | 35 | End to end, real tools: uncovered fails / covered passes, both tiers land repo-relative in the combined XML, and the CLI surface itself returns 4 then 0 | tested | `test_an_uncovered_changed_line_fails_the_gate`, `test_covering_the_changed_line_passes_the_gate`, `test_the_combined_xml_is_repo_relative_so_diff_cover_can_match_it`, `test_the_f0_cli_stops_on_an_under_covered_diff_then_passes_once_covered` PASSED |

- **Confidence-pattern check:**
  - **Asymptote (depth).** Yes — and twice, which is the point. Stage 2 declared the
    gate fail-closed; Stage 3 then produced a scenario in which it reports PASS
    having measured nothing (F0 runs before F6, so added files are untracked and
    invisible to diff-cover). A second "confident" answer after the Stage-2 fixes
    would have been the pattern this check exists to catch, so I ran P4 and P6 —
    live runs whose output could have refuted the fix — rather than re-reading the
    code. P6's `and untracked changes` line is the refutation-resistant evidence.
  - **Coverage (breadth).** 35 ledger rows, every one `tested`, zero
    untested-testable, zero `untestable`. Independently corroborated by the gate
    measuring its own diff at 97 % (166 changed lines, 4 missed) — a number produced
    by the tool, not by me.
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
