# Iterate Spec: windows-ci-tests

- **Run ID:** iterate-2026-08-05-windows-ci-tests
- **Type:** change
- **Complexity:** medium
- **Status:** draft

## Goal

No CI job in this repository runs on Windows — all seven workflows
(`ci.yml`, `security.yml`, `codeql.yml`, `bloat-check.yml`,
`grade-empirical.yml`, `pr-review.yml`, `pr-review-run.yml`) pin
`runs-on: ubuntu-latest`. Four tests across `shared/` are gated with
`skipif(sys.platform != "win32")` / `skipif(os.name != "nt")` — they exist
specifically to pin native-Windows behavior, and CI never executes a single
one of them. A Windows-only defect (97392eea, shipwright-changelog:
`subprocess` `stderr` decoded with the locale codec, every reader decoded
strict UTF-8) already reached `main` green and was found only because a
human happened to test locally on Windows. Add the missing CI coverage so
platform-gated regressions are caught mechanically instead of by luck. This
is IT-9 Unit 5 of 6 (split from anchor `trg-bd66b9b0` → `trg-210fde7b`,
re-filed 2026-08-05); IT-9 owns every file under `.github/workflows/`
exclusively, so no other card may touch a workflow file.

## Acceptance Criteria

- [ ] (AC1) A new workflow runs `shared/tests`, `shared/scripts/tests`, and
  `shared/scripts/tools/tests` on `windows-latest`, on the same triggers as
  `ci.yml` (`pull_request` → `main`, `push` → `main`, `workflow_dispatch`).
- [ ] (AC2) All four currently Windows-gated tests
  (`test_audit_phase_quality.py::…case_insensitive…`,
  `test_atomic_write_windows_retry.py`, the four native-lock cases in
  `test_host_resource_locking.py`, `test_playwright_setup_multiservice.py`)
  actually execute (not skip) under this job.
- [ ] (AC3) `ci.yml` is not modified (explicit anchor constraint — all six
  IT-9 units are serial and this unit's fix is a standalone workflow file).
- [ ] (AC4) The new job fails closed (no `continue-on-error`, no `|| true`)
  so `shared/scripts/tools/check_ci_gate_coverage.py`'s loose-gate check
  stays green and a real Windows regression shows red, not silent green.

## Spec Impact

- **Classification:** none
- **NONE justification:** framework/CI-infrastructure change (adds a CI
  workflow); no target-app FR — this repo's own `spec.md` files describe
  Shipwright's product surface, not its own CI plumbing. Same precedent as
  `iterate-2026-05-31-ci-shared-tests`, which wired the same three
  directories into `ci.yml` under an identical NONE classification.

## Out of Scope

- Modifying `ci.yml` itself (anchor constraint: IT-9 owns workflow files
  exclusively and the six units are strictly serial; touching `ci.yml` here
  would be scope creep into a sibling unit's territory).
- Running the full plugin test suite (`plugins/*/tests`) or
  `integration-tests/` on Windows. `plugins/shipwright-security/tests`
  hard-fails in CI (ADR-044) when Semgrep/Trivy/Gitleaks binaries are
  absent, and none of those tools ship a drop-in Windows install identical
  to `ci.yml`'s Linux steps — replicating that is materially more work with
  no bearing on the four tests this unit exists to unskip, all of which live
  under `shared/`. Flagged as a possible future IT-9-adjacent follow-up, not
  taken on here.
- Making the new job a required (branch-protection) check. Reconciling the
  configured must-pass set against the checks that actually exist is IT-9
  Unit 3's (`trg-a089c9f7`) explicit remit — doing it here would pre-empt a
  serial sibling unit.
- Registering the new workflow in `shared/scripts/lib/main_health.py`'s
  `MONITORED_WORKFLOWS`. That registry drives the *post-merge* red-main
  repair path; this job runs on `pull_request` (visible in the PR's own
  Checks tab, pre-merge) so the repair path is not the detection mechanism
  here. Wiring it in would also touch a file `main_health.py`'s own pinned
  invariant test does not require touching for this fix to work.

## Design Notes

N/A — no UI surface.

## Affected Boundaries

n/a — no serialized producer/consumer format is introduced or changed; this
adds a CI workflow definition, not an I/O boundary.

## Confidence Calibration

- **Boundaries touched:** none.
- **Empirical probes run:**
  1. Grepped the full repo (excluding `.venv`/`.worktrees`) for
     `skipif(...win32...)` / `skipif(os.name...)` — confirmed the complete
     set of 4 Windows-gated tests, all under `shared/`.
  2. Confirmed via `grep -n "runs-on"` across `.github/workflows/*.yml` that
     all 7 workflows use `ubuntu-latest` — no existing Windows coverage.
  3. Read `shared/scripts/tools/check_ci_gate_coverage.py` — confirmed it
     parses *all* workflow files generically (not just `ci.yml`), so the new
     job is automatically covered by the loose-gate guard without needing a
     registry edit.
  4. Ran the exact three-directory pytest loop the new workflow will run,
     locally, **on this machine's native Windows host** — see Test
     Completeness Ledger row 1 for the result.
  5. Read `.shipwright/planning/iterate/2026-05-31-ci-shared-tests.md`
     (prior iterate that first wired these 3 dirs into `ci.yml`) — its
     "Flagged follow-ups" section explicitly names "A `windows-latest` CI
     job … so the `os.name`-fake Windows-simulation tests also run" as the
     out-of-scope item this iterate now closes.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | The 3-directory pytest loop (`shared/tests`, `shared/scripts/tests`, `shared/scripts/tools/tests`, `-m "not slow and not cross_plugin"`) collects and passes on native Windows | tested | local run on this Windows host: `shared/tests` 7932 passed/23 skipped/26 deselected (1 pre-fix failure, root-caused by Stage-2 code review, fixed, independently re-verified 14/14 passed), `shared/scripts/tests` 365 passed, `shared/scripts/tools/tests` 482 passed/15 skipped/2 deselected |
  | 2 | The 4 Windows-gated tests execute (not skip) under this invocation | tested | confirmed PASSED (not SKIPPED) in the logs: `test_atomic_write_windows_retry.py` (8 cases), `test_audit_phase_quality.py::test_strict_ancestor_windows_case_insensitive`, `test_playwright_setup_multiservice.py::test_setup_uses_resolved_executable_for_npm`, and all 4 `test_host_resource_locking.py::test_windows_*` cases |
  | 3 | `check_ci_gate_coverage.py` still passes with the new workflow present | tested | ran the guard locally against the worktree after adding the file — OK |
  | 4 | The monitored-workflow drift test does not regress when a new push-to-main workflow is added | tested | `test_no_push_to_main_workflow_is_silently_left_out_of_the_policy` — found failing by Stage-2 code review, fixed by registering `windows-tests.yml` in `DELIBERATELY_UNMONITORED`, re-verified 14/14 passed |
  | 5 | GitHub Actions actually runs `windows-latest` green on the real PR | untestable | requires-external-nondeterministic-service (verified post-push by observing the live CI run) |

- **Confidence-pattern check:** asymptote (depth) — traced to the actual
  `runs-on` lines and the actual `skipif` predicates, not "CI looks like it
  covers Windows"; coverage (breadth) — both failure modes named in the
  anchor (no Windows runner at all; existing Windows-gated tests
  permanently skipped) are independently probed and closed by the same
  fix.

## Verification (medium+)

- **Surface:** none (CI/workflow-infrastructure change; no web/UI/API/store/SSE
  surface touched).
- **Justification:** Backend-affects-Frontend rule N/A — no API routes,
  store mutations, SSE/WS, or message contracts changed. Verified via a
  native-Windows local run of the exact pytest invocation the new workflow
  runs, plus the live PR's own Windows Actions run (external,
  non-deterministic — see Ledger row 4).
- **Evidence path:** `.shipwright/runs/iterate-2026-08-05-windows-ci-tests/surface_verification.json`
  (surface=none + justification).
