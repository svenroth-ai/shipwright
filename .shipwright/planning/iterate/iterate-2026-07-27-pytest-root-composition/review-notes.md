# Review record — iterate-2026-07-27-pytest-root-composition

Five passes ran. Every finding below was either fixed in the same diff or
explicitly answered. Two reviewer claims were **empirically disproven** and
are recorded as such rather than silently dropped.

## Stage 1 — spec-reviewer (subagent, opus) → REJECT, then resolved

| # | Finding | Resolution |
|---|---|---|
| 1 | Relative args joined to repo root → false refusal from a subdirectory | **Fixed** — resolve against `config.invocation_params.dir`. Found independently before the review landed; test `test_dot_inside_a_root_is_not_refused` |
| 2 | Same bug, other direction: a real spanning session from a subdir was NOT refused | **Fixed** by the same change; test `test_multi_root_is_refused_from_a_subdirectory` |
| 3 | Ledger row for `::` stripping passed with the split deleted | **Fixed** — replaced with a root-level selector, the case that resolves to nothing unsplit |
| 4 | "Single-root unaffected" evidence was `--collect-only` only | **Fixed** — added `test_single_root_session_still_executes_green` |
| 5 | "Zero testable-but-untested" was false (relative-arg rule, `_SKIP_DIRS`) | **Fixed** — added rows 11-13 plus tests against a synthetic tree |
| 6 | AC4's cited test passed with the capture check deleted | **Fixed** — the probe now reports the exception TYPE, so a `ModuleNotFoundError` regression fails |
| 7 | Dead `_SKIP_DIRS` entries + a comment justifying one | **Fixed** — list trimmed to names the walk can reach |
| 9 | Discovery rglobs into `.venv` on every session start | **Fixed** — pruning walk |

## Stage 2 — code-reviewer (subagent, opus) → FAIL, then resolved

Findings 1, 2, 5, 6 duplicate the above and were already fixed. New:

| # | Finding | Resolution |
|---|---|---|
| 3 | `shared/tests` + `shared/scripts/tests` die at conftest import (`ImportPathMismatchError`) **before** the guard, yet CLAUDE.md claimed the guard covers it | **Confirmed by running it.** Docs corrected; limit stated in the conftest docstring; `test_conftest_colliding_pair_still_fails_loudly` pins that it stays loud |
| 4 | Root conftest allegedly loads in plugin sessions and prepends `<repo>` to `sys.path`, masking ADR-044 | **DISPROVEN empirically.** Probe inside `cd plugins/shipwright-adopt && pytest tests/`: repo root absent from `sys.path`, root conftest not loaded (rootdir = plugin dir, each plugin owns `[tool.pytest.ini_options]`) |
| 7 | `_COMPLIANCE_PLUGIN_ROOT` compared unresolved against a resolved path → false `ImportError` under a symlink/junction | **Fixed** — resolved at definition |
| 8 | Module-level loop leaked `_name`/`_captured`/`_file` into the contract namespace | **Fixed** — wrapped in `_refuse_if_captured()` |

## Stage 3 — doubt-reviewer (subagent, opus) → 0 blocking, 3 serious, 4 minor

| # | Objection | Response |
|---|---|---|
| 1 | Candidate A rejected for the wrong reason; only ~7 `scripts.*` statements create the pin, and `<repo>/shared` on `sys.path` is harmless alone | **Accepted as a correction.** Spec now carries "Candidate A'" with the accurate mechanism. Not pursued: the decisive statements are deliberate `@pytest.mark.cross_plugin` probes into *another plugin's* lib, the trap returns with the next such import, and other pairs still cannot compose. Recorded as un-executed reasoning |
| 2 | The invariant was proven on its weakest instance | **Accepted.** Spec now cites the two stronger causes: production modules bind `scripts.tools` for `shared/scripts/tools/tests`, and the `tests` package-name collision |
| 3 | The reporter's single-junit need is foreclosed by decree next to `combine_coverage.py` | **Accepted.** Wording softened in both the refusal message and CLAUDE.md: one process cannot span roots, merging afterwards is the path, no merger exists yet, left out of scope rather than declared impossible |
| 4 | The guard refuses `shared/tests` + `shared/scripts/tools/tests`, which may compose | **Accepted as deliberate over-strictness.** A uniform rule matching CI beats a hand-maintained exception list |
| 5 | AC1 holds only for repo-root sessions | **Accepted** — stated in the conftest docstring and CLAUDE.md |
| 6 | `scripts.audit` missing from the capture check | **Fixed** — added |
| 7 | Subprocess tests carry no `slow` marker | **Answered** — marking them would delete the guard's only CI coverage, since CI runs `-m "not slow"`. Kept fast and unmarked; rationale in the module docstring |

Verified-and-unbroken by the doubt pass: the regular-vs-namespace mechanism,
the 29 lazy call-time imports behind `run_report`/`PHASE_REPORTS`,
`--import-mode=importlib` as a non-fix, sentinel path-loading as a non-fix,
and that the guard does not block CI.

## Stage 4 — external code review (GPT-5 via OpenRouter) → revise, resolved

1. No-positional-args session unhandled → **fixed**, `test_no_argument_session_is_not_refused`.
2. A cached foreign `scripts` PARENT bypasses the check → **fixed**, `scripts` added to the tuple.
3. Custom arg parsing is fragile → **addressed** by adding the
   `pytest_collection_modifyitems` backstop, which judges what pytest
   itself resolved.

## Stage 5 — external plan review (GPT-5 via OpenRouter) → revise, resolved

Gemini returned `degraded` (reply truncated by the provider) on both external
passes, so only one external reviewer answered. Its "move the guard to
`pytest_collection_modifyitems`" suggestion was **partially rejected**:
collection is exactly where some cross-root collisions detonate, so the
session-start hook must stay. It was adopted as a *second* layer instead.

## Self-review (Step 7)

- **Affected boundaries:** pytest session startup (`config.args`,
  `invocation_params.dir`, collected items), CPython import machinery
  (regular-vs-namespace packages, `sys.modules` caching),
  `shared.contracts.compliance` import-time bootstrap.
- **Scope:** no production behaviour changes. The contract diagnostic only
  relabels an already-fatal path.
- **Residual risk:** the guard is deliberately stricter than the minimum
  constraint (objection 4), and does not reach plugin-rooted sessions
  (objection 5). Both are documented where a reader will meet them.
