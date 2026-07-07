# Iterate A — grade local-mode honesty fix (Part 1 + Part 2)

- **run_id:** `iterate-2026-07-07-grade-local-honesty`
- **Intent:** CHANGE · **Spec Impact:** MODIFY (change_traceability scoring semantics)
- **Complexity:** medium · **Risk:** cross-plugin shared engine (compliance engine ↔ grade consumer)
- **Source plan:** `Spec/grade-local-honesty-fix-plan.md` (user-approved 2026-07-07)

## Problem (reproduced end-to-end)
`/shipwright-grade <repo>` in the default **local-only** mode grades a well-run repo
**F "out of control"** solely because `change_traceability` scores 0 when commit
subjects lack `#N` PR-refs. Root cause: change_traceability is a network-dependent
control (like test-health/security) but was the only one emitting a git-log **style
proxy** locally instead of degrading to n/a — AND it is a hard F-collapse pillar
(`_grade_gate._COLLAPSE_PILLARS`). The git-log `#N` signal *anti-correlates* with
quality (a disciplined squash-merge repo leaves reference-free subjects).

## Acceptance Criteria
- **AC1:** default local-only grade of a well-run repo (CI+tests+small files, clean
  Conventional Commits w/o `#N`) is NOT F and NOT "out of control"; change_traceability
  shows n/a.
- **AC2:** `--allow-network` path unchanged — network fixtures still grade their bands;
  the dogfood monorepo stays **A** (authoritative).
- **AC3:** SKILL.md lists change_traceability under `--allow-network`, not local.
- **AC4:** new local-only calibration fixture/test asserts AC1; full grade suite +
  compliance grade-engine suite green.
- **AC5:** A-cap (`expected_dimensions` reconciliation), reputational guard, and scorer
  math untouched (existing tests green).

## Approach (+ alternative)
Add `GradeInputs.change_traceability_measurable` and gate dimension 3 on it (mirror
`reconciliation_measurable`/`security_measurable`). The cold projector sets it to
`cp.measurable` (True only when the network PR-association tier resolved); the
authoritative/compliance adapter sets it True (real provenance).

**Key decision — the flag defaults `True` (NOT False as the plan literally suggested).**
The empirical calibration replays *stored* `GradeInputs` dicts (`engine.GradeInputs(**gi)`);
a new field defaulting False would flip the 7 committed **network** fixtures to n/a on
replay → change their grades (violates the plan's "must NOT change network grades"
landmine) and force a full network re-record. Default True keeps every existing caller
(engine tests, dogfood A, network fixtures) byte-identical; only the cold LOCAL projector
opts out. Semantically honest: change_traceability is measurable from ANY real provenance
— only the cold git-log fallback is not.
**Alternative (rejected):** default False + update all engine tests + both adapters +
re-record 7 fixtures (needs network). Larger blast radius, higher regression risk.

**Calibration consequence (intended):** synthetic `no_tests` fixture drops local C→D (the
git-log provenance was the C-lifter; without it, 0% test coverage is honestly D).
`well_run` stays B; `messy` stays F. Ordering B>D>F holds.

## Files
- `_grade_types.py` (flag), `control_grade.py` (dim-3 gate), `_control_block.py` (explicit
  True), `grade_inputs_projector.py` (`cp.measurable`), `SKILL.md` + `report_copy.py` +
  `guide.md` + empirical `CALIBRATION.md` (docs), new fixture + tests.

## Confidence Calibration
- **Boundaries touched:** `GradeInputs` cross-plugin contract (compliance engine ↔ grade
  consumer ↔ empirical fixture JSON round-trip `GradeInputs(**gi)`). New bool field is
  JSON-serializable and defaulted → old fixtures round-trip (verified: test_projector_capture
  + calibration replay green).
- **Empirical probes run:**
  - RED repro: synthetic well-run-no-`#N` repo graded **F 49.0 "out of control"** before
    the fix (the exact shitstorm).
  - GREEN E2E via the real CLI: same repo → **B 89.0**, change_traceability **n/a**
    ("not measurable without --allow-network"); verdict capped by reconciliation.
  - Dogfood E2E via the real CLI: monorepo → **A 99.9 authoritative**, change_traceability
    **ok 276/276** (measurable preserved).
  - No other `compute_grade`/`GradeInputs` consumers outside the two plugins (grep of
    shared/, integration-tests/, scripts/).
- **Test Completeness Ledger:**
  | Behavior | Disposition | Evidence |
  |---|---|---|
  | Local-only well-run-no-refs repo is NOT F | tested | `test_well_run_without_pr_refs_is_not_f` |
  | change_traceability n/a in local mode | tested | `test_well_run_without_pr_refs_change_trace_is_na`, `test_change_traceability_na_in_local_mode` |
  | Engine gate: measurable=False → dim score None | tested | `test_control_grade_change_traceability.py::test_na_when_not_measurable` |
  | Engine gate: no F-collapse on 0-provenance + measurable=False | tested | `...::test_not_measurable_never_f_collapses_on_reference_free_repo` |
  | Network/authoritative path still scores it | tested | `test_network_mode_still_scores_change_traceability`, `...::test_scored_when_measurable`, dogfood CLI A |
  | Engine default is True (existing callers unchanged) | tested | `...::test_default_is_measurable`, `test_control_grade.py::test_real_shipwright_case_grades_B` |
  | measurable=True + 0 events → n/a "no change events" | tested | `...::test_measurable_but_no_events_is_na` |
  | git-log count retained but ungraded | tested | `test_git_log_count_kept_when_network_absent` |
  | no_tests calibration C→D | tested | `test_grades_d_maintainability_lit` |
  | HTML report n/a copy hint | tested | golden snapshot regenerated (copy-only diff) |
  | Drift-guard: adapter explicitly sets measurable=True | tested | `TestAuthoritativeAdapterKeepsItMeasurable::test_adapter_sets_change_traceability_measurable_true` (added per internal-review finding #1) |
  - 0 untested-testable behaviors.
- **Confidence-pattern check:** asymptote (depth) — engine gate unit-tested + real-CLI E2E
  both local and authoritative; coverage (breadth) — engine, projector, fixture, renderer,
  docs, and cross-plugin round-trip all exercised. No `cross_component` machinery touched
  (no integration-coverage flag).
