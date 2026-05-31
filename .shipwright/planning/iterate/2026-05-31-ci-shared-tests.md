# Iterate Spec — Run shared/ test suites in CI (close the rot gap)

- **Run ID:** `iterate-2026-05-31-ci-shared-tests`
- **Type:** change (CI coverage) + bug (stale/born-red shared tests)
- **Complexity:** medium (systemic CI gap; touches CI infra + test hygiene; multi-file root-cause across two failure modes)
- **Status:** draft

## Goal

`.github/workflows/ci.yml` only iterates `plugins/*/tests/` + `integration-tests/`.
`shared/scripts/**/tests/` and `shared/tests/` **never run in CI** — which is
why the 7 `record_event` tests fixed in
`iterate-2026-05-30-record-event-test-failures` rotted unseen. Wire the three
shared test dirs into CI so future regressions break the build, and clear the
pre-existing reds that would otherwise make the new step **born red**.

Wiring is non-trivial in two ways:
- **(a) Collection collision.** `pytest shared/tests shared/scripts/tests
  shared/scripts/tools/tests` in ONE process raises 11 `ModuleNotFoundError`:
  `shared/tests/` and `shared/scripts/tests/` both define a top-level `tests`
  package (each has `__init__.py`), so the second import shadows the first.
- **(b) Pre-existing reds.** The named candidate failures must be root-caused
  (stale vs real) and resolved first.

## Root-Cause Findings (the "stale vs real?" verdicts)

Empirically established by (i) tracing `validate()` + the runtime loader
`load_shipwright_env`, and (ii) a **clean-clone CI simulation** (`git clone`
of `origin/main` at `78a281f`, scrubbed env) — see Confidence Calibration.

| Named candidate | Verdict | Evidence |
|---|---|---|
| `test_validate_env.py::TestValidateBuild::test_all_vars_present` | **STALE — non-hermetic test** | Red locally, **green in clean CI**. The dev session loaded the repo's own scaffold `.env.local` (`NEXT_PUBLIC_SUPABASE_URL=...`) into `os.environ`. `validate()` lets `os.environ` override `.env.local` — **correct**, it mirrors `load_shipwright_env` ("vars already in os.environ are never overwritten"). `...` is a `_PLACEHOLDER_PATTERNS` value → false "missing". The test simply failed to isolate ambient env (its sibling `test_vars_from_os_environ` already monkeypatches). |
| `test_validate_env.py::TestValidateBuild::test_partial_vars` | **STALE — non-hermetic test** | Same root cause. |
| `test_architecture_md_reflects_arch_impact.py::test_every_arch_impact_drop_has_architecture_md_entry` | **Already GREEN — task info stale** | Passes locally; **skips** in clean CI (`pytest.skip("no architecture-impact decision-drops to verify")`) because decision-drops are gitignored. No fix needed for this function. |
| `test_artifact_path_canon.py::test_no_legacy_artifact_paths[compliance-migrated]` | **Already GREEN — fixed by prior merges** | Passes in main tree, worktree, and clean clone. The compliance canon was repaired by PR #122 (`658198f`, "fix(canon): resolve compliance + planning artifact-path-canon failures on main") and earlier allowlist refreshes (`9d9b1e5`, `9e26a9c`, `5c06748`). No fix needed. |

**The actual born-red blocker (not in the named list, found by the CI sim):**
`test_architecture_md_reflects_arch_impact.py::test_arch_impact_drops_found_at_all`
asserts decision-drops exist. They're gitignored → **absent in a clean CI
checkout** → the new CI step would be born red. This is the real defect the
AC's "else the new CI step is born red" warns about; fixing it is in scope.

## Acceptance Criteria

- [ ] (AC1) `test_validate_env.py::TestValidateBuild` is hermetic — the
  file-based assertions no longer depend on ambient `os.environ`; red→green
  locally, stays green in CI.
- [ ] (AC2) The misleading `# Always check os.environ as fallback` comment in
  `validate_env.validate()` is corrected to state that `os.environ` takes
  precedence (mirrors `load_shipwright_env`). No behavior change.
- [ ] (AC3) `test_arch_impact_drops_found_at_all` SKIPs (does not FAIL) when
  the `decision-drops/` directory is absent (clean checkout), while still
  asserting when the directory exists (resolution-misfire guard preserved).
- [ ] (AC4) The three shared dirs each **collect + pass** as separate per-dir
  pytest invocations, in BOTH the dev tree and a clean-clone CI simulation.
- [ ] (AC5) `ci.yml` runs the three shared dirs as a `set -e` blocking step,
  one separate `pytest` invocation per dir (collision-safe), mirroring the
  per-plugin loop.

## Spec Impact

- **Classification:** NONE (framework/CI/test-hygiene change — no target-app FR;
  this repo's own `spec.md` files are unaffected).
- **NONE justification:** Adds a CI step and fixes test hygiene; introduces no
  user-visible application requirement.

## Out of Scope

- Changing `validate()`'s env-var precedence (it is correct — mirrors runtime).
- Renaming/namespacing the duplicate `tests` packages, or switching pytest to
  `--import-mode=importlib` (see alternative below — higher blast radius).
- Re-fixing the already-green canon / arch-md-entry tests.
- Making the arch-md drift test meaningful in CI (its data is gitignored by
  design; skipping in CI is the honest outcome — it remains a dev/Stop-hook
  guard).

## Mini-Plan + Alternative Considered

**Chosen:** per-dir loop of separate `uv run ... pytest <dir>` invocations.
Mirrors the existing per-plugin loop exactly; zero change to import semantics;
each process has only one top-level `tests` package → no collision.

**Alternative — `pytest --import-mode=importlib <all three dirs>`** (one
invocation): would also dodge the duplicate-package error, but importlib mode
changes sys.path/conftest resolution repo-wide and risks breaking the many
shared tests that rely on the current rootdir-relative imports
(`from lib.events_log import ...` via `shared/tests/conftest.py`). Rejected:
disproportionate blast radius for a CI-plumbing change. The per-dir loop is
the boring, established shape (Simplicity First).

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `init_env_file` scaffold + `load_shipwright_env` | `validate()` (`os.environ` ⊐ `.env.local`) | `.env.local` / `os.environ` |
| `write_decision_drop.py` (gitignored drops) | `test_arch_impact_drops_found_at_all` | JSON files under `.shipwright/agent_docs/decision-drops/` (absent in CI) |
| `.github/workflows/ci.yml` shared-test step | GitHub Actions | per-dir pytest invocations |

`validate_env.py` touches the `.env*` / `os.environ` IO boundary
(`parse_env`, `json.load`) → `touches_io_boundary`. This iterate's change there
is comment-only; the boundary behavior is verified unchanged by the existing
parser/round-trip tests plus the empirical probes below.

## Confidence Calibration

- **Boundaries touched:** `.env.local`/`os.environ` precedence (read-only
  verification — no logic change); the gitignored decision-drops directory
  (CI-presence-dependent); the CI workflow file.
- **Empirical probes run:** populated at F5 (see Ledger). Key probes already
  executed: (1) traced `validate()` returning `found=[]` with ambient
  `NEXT_PUBLIC_SUPABASE_URL=...`; (2) confirmed `load_shipwright_env` precedence
  matches `validate()`; (3) **clean-clone CI sim** of all 3 dirs (1 born-red
  identified, everything else green); (4) confirmed collision = 11
  ModuleNotFoundError; (5) confirmed `ci.yml` template-convention test governs
  shipped templates, not the monorepo's own CI.
- **Test Completeness Ledger:** see table below.
- **Confidence-pattern check:** asymptote (depth) — root cause traced to source
  precedence + tracking facts, not "looks fixed"; coverage (breadth) — both
  failure modes (env-leak, gitignored-data) probed under both dev-tree AND
  clean-CI conditions.

### Test Completeness Ledger (this iterate)

| # | Testable behavior | Disposition | Evidence / reason_code |
|---|---|---|---|
| 1 | `TestValidateBuild` file-based tests green regardless of ambient env | tested | F0 re-run with ambient `NEXT_PUBLIC_SUPABASE_*` set → green (was red) |
| 2 | validate_env dir collects + passes per-dir, clean env | tested | clean-clone sim: 175 passed |
| 3 | `test_arch_impact_drops_found_at_all` SKIPs when drops dir absent | tested | run edited test against clean clone → skipped (was failed) |
| 4 | `test_arch_impact_drops_found_at_all` still asserts when drops present | tested | dev-tree run → passes (assertion path still exercised) |
| 5 | `shared/tests` dir collects + passes/skips per-dir, clean CI | tested | clean-clone sim re-run with fix → 0 failed |
| 6 | `shared/scripts/tools/tests` collects + passes | tested | clean-clone sim: 51 passed |
| 7 | 3 dirs together still collide (negative control) | tested | reproduced 11 ModuleNotFoundError |
| 8 | comment-only edit to validate_env doesn't change behavior | tested | full `shared/scripts/tests` green after edit |
| — | GitHub Actions actually executing the new step green | untestable | `requires-external-nondeterministic-service` (verified post-push by observing the live CI run on the PR) |

## Verification (medium+)

- **Surface:** none (CI/test-infra; no web/UI/API/store/SSE surface touched).
- **Justification:** Backend-affects-Frontend rule N/A — no API routes, store
  mutations, SSE/WS, or message contracts changed. The deliverable is CI
  plumbing + test hygiene. Verified via the clean-clone CI simulation and the
  live PR CI run rather than a dev-stack surface.
- **Evidence path:** `.shipwright/runs/{run_id}/surface_verification.json`
  (surface=none + justification).
