# Mini-Plan: f0-diff-coverage-gate

- **Run ID:** iterate-2026-08-01-f0-diff-coverage-gate
- **Spec:** `.shipwright/planning/iterate/2026-08-01-f0-diff-coverage-gate.md`

## 1. Files to create / modify

| File | Change | Why |
|---|---|---|
| `shared/scripts/tools/suite_coverage.py` | **new** | The gate: data-dir reset, combine argv, gate argv, the pure verdict function, and a thin orchestrator with an injectable `runner`. |
| `shared/scripts/tools/tests/test_suite_coverage.py` | **new** | In-process unit tests for every function above. |
| `shared/scripts/tools/tests/test_f0_diff_coverage_e2e.py` | **new** | Drives the real pinned `diff-cover` over a synthetic git repo — proves the gate *bites*. Doubles as the F0.5 surface command. |
| `shared/scripts/tools/suite_units.py` | edit | Receives `build_command` (moved), gains `Unit.cov_args` / `Unit.cov_file` and `instrument_for_coverage`. |
| `shared/scripts/tools/run_test_suite.py` | edit | Re-exports `build_command`; sets `COVERAGE_FILE` per unit; wires reset + instrument + the gate and its exit code. |
| `shared/scripts/tools/tests/test_suite_units.py` | edit | Coverage-arg construction, label sanitising, the no-`scripts/` case. |
| `shared/scripts/tools/tests/test_run_test_suite.py` | edit | `COVERAGE_FILE` wiring, exit-code arithmetic, red-suite skip. |
| `shared/scripts/tools/tests/test_f0_ci_parity.py` | edit | AC-3: the local gate argv is pinned against `action.yml`'s declared defaults, and ci.yml still runs the gate as backstop. |
| `plugins/shipwright-iterate/skills/iterate/references/F0.md` | edit | Document the gate + the new exit code `4`. |
| `docs/hooks-and-pipeline.md` | edit *(if it describes F0's contract)* | Repo rule: an F0 contract change is documented in the same diff. |

**Not touched:** anything under `.github/`.

## 2. Work breakdown (sequential)

1. **`suite_coverage.py` + its tests (TDD).** Pure first: `gate_argv`,
   `combine_argv`, `verdict`. Then `reset_coverage` (real tmp dirs) and
   `run_gate(project_root, *, suite_green, runner=subprocess.run)`.
   *Test expectation:* every branch of `verdict` and both argv builders covered
   in-process; `run_gate` driven with a fake `runner` — no subprocess.
2. **`suite_units.py`.** Move `build_command` in; add the two `Unit` fields and
   `instrument_for_coverage(units, project_root, data_dir)`.
   *Test expectation:* plugin-with-`scripts/` gets `--cov=scripts`; plugin
   without gets nothing; shared/integration get `--cov=shared`; three distinct
   data-file labels; marker expression still intact (AC-7).
3. **`run_test_suite.py`.** Re-export `build_command`; `_exec` sets
   `COVERAGE_FILE` from `unit.cov_file`; `run_suite` instruments the discovered
   units; `main` runs the gate and folds its verdict into the exit code.
   *Test expectation:* existing suite stays green (the fakes take `_exec`'s
   unchanged 5-arg signature); new tests for exit `4`, the red-suite skip, and
   the `n/a` path.
4. **Parity test** (AC-3) + **E2E test** (AC-8).
5. **Docs.**

## 3. Component hierarchy

n/a — no UI.

## 4. Data model changes

None. All artefacts are already gitignored: `.cov-data/`, `.coverage*`,
`coverage.xml`, `diff-cover.json`, `diff-cover.md`.

## 5. Test strategy

- **Unit, in-process** — the bulk. Every decision function (`verdict`,
  `gate_argv`, `combine_argv`, `instrument_for_coverage`) is pure or
  runner-injected, so it is measurable by the very gate this change adds.
  This is landmine (1) handled by construction: nothing load-bearing is reachable
  only through a subprocess.
- **Injection over monkeypatching.** `run_gate` takes `runner=` as a parameter.
  Where monkeypatching is unavoidable the existing suite's convention holds —
  patch the **module object** (`monkeypatch.setattr(mod, "_exec", …)`), never the
  dotted string (ADR-045).
- **One root per invocation** — landmine (2). Every new test lives under
  `shared/scripts/tools/tests/`, an existing root. No test spans roots, and the
  runner keeps emitting one `--cov`/`--junit-xml` per unit, mirroring ci.yml's
  three separate steps rather than collapsing them.
- **Markers** — landmine (3). Coverage args are *appended after* `unit.markers`;
  AC-7 pins that the composed `-m "not slow and not cross_plugin"` expression
  survives, since the line that appends markers is the one being edited.
- **E2E** — the real pinned `diff-cover` over a synthetic repo (same pattern as
  the existing `test_measure_diff_coverage_gate.py`), asserting the gate both
  fails and passes. Not marked `slow`, so it actually runs at F0.

## 6. Alternative approach considered — and why rejected

**Reuse `measure_diff_coverage.py --fail-under 80` as the local gate** instead of
invoking `uvx diff-cover@10.3.0` directly. It already exists, already owns a
hardened fail-closed decision (`decide_gate`), and would additionally refresh the
gitignored dashboard transient `.shipwright/coverage/diff_coverage.json`.

**Rejected**, for two reasons:

1. **It resolves `diff-cover` unpinned** — it tries the binary on `PATH`, then
   `python -m diff_cover.diff_cover_tool`. CI pins `10.3.0`. The brief's own
   requirement is that an unpinned local run would disagree with CI, and a gate
   whose verdict depends on whatever version happens to be importable is not a
   mirror. Fixing that means editing `measure_diff_coverage`'s resolution order,
   which changes behaviour for its *existing* callers — scope creep on a tool
   three other things consume.
2. **CI does not run it either.** ci.yml's gate is the composite action, which
   shells `uvx diff-cover@<pin>`. Mirroring the action's command shape is the
   thing that makes local and CI agree; going through a second wrapper adds a
   layer where they could silently diverge, and AC-3 could no longer be a
   byte-level pin against `action.yml`.

The dashboard transient is unaffected — it is still produced by
`measure_diff_coverage.py` during compliance regen, exactly as before.

## 7. External plan review — what changed as a result

Both providers returned `SHIPWRIGHT_VERDICT: revise`. Accepted, with the AC each
became:

| # | Finding | Sev | Disposition |
|---|---|---|---|
| O1 | "nothing to measure" and "measurement failed" are not distinguished | high | **Accepted** → AC-4b. An `eligible` counter drives it: 0 instrumented units ⇒ `n/a`/exit 0; ≥1 but no combined XML ⇒ exit 4. Deliberately stricter than ci.yml's `hashFiles` guard, which cannot tell them apart. |
| O2 | concurrent `COVERAGE_FILE` could race via `os.environ` | high | **Half already correct** — `_exec` builds `env = os.environ.copy()` and passes it per subprocess, so nothing global is mutated. The other half stands: an *inherited* `COVERAGE_FILE` must be removed for uninstrumented units → AC-10. |
| G1/O5 | `origin/main` may not exist / may be the wrong base | high/med | **Accepted** → AC-4d + the E2E now builds a real `origin/main`. Resolution is `origin/HEAD` → `origin/main`; unresolvable ⇒ exit 4, not a crash. **Rejected**: probing `upstream/*`. This repo pushes to `origin`, and `setup_iterate_worktree.py` branches off a freshly fetched `origin/<default>`, so the ref is guaranteed in the iterate flow; speculative remote-name discovery is scope the evidence does not support. |
| O3 | two combine implementations would drift | med | **Accepted.** `suite_coverage` never re-implements combining: `combine_argv()` builds the exact `combine_coverage.py` invocation ci.yml uses, and that stays the single implementation. Shelled out rather than imported — `combine_coverage.py` binds a top-level `tools`/`lib` package, and importing it from a module loaded as `scripts.tools.*` would create two module objects for one file (ADR-045). Process isolation avoids that; the argv builder is pure and unit-tested, so nothing load-bearing hides in the subprocess. |
| O4 | assert the real XML, not just the flags | med | **Accepted** → AC-1 and AC-8 assert `filename` entries in the combined XML for a plugin tier *and* the shared tier. |
| O6 | two unit ids could sanitise to one label | med | **Accepted** → AC-9. Uniqueness is validated at instrumentation time and fails closed before any process starts. |
| O7 | `uvx` absent / resolution failure must not raise | low | **Accepted** → AC-4c. The runner wrapper catches `OSError`/`SubprocessError` and maps to 4 with a phase-specific message; argv lists, `shell=False`. |
| G2 | `pytest-cov` missing from the F0.5 runner command | med | **Accepted** for the command line. The *units* were never at risk — instrumentation appends `pytest-cov` to `unit.extra_deps`, which `build_command` already turns into `--with`. **Rejected**: adding it to dev-dependencies — `uv run --with` is how this runner provisions pytest and pytest-mock too. |
| G3 | `coverage combine` would look in the CWD, not `.cov-data/` | med | **Rejected — already correct.** `combine_coverage.py` discovers `.coverage.<label>` under an explicit `--data-dir` and passes each **resolved absolute path** to `coverage combine --append`. Verified in source. |
| G4 | moving `build_command` is churn without architectural value | low | **Accepted.** It stays in `run_test_suite.py`; only the line that appends `unit.markers` changes, to append `unit.cov_args` after them. The move was motivated by a 300-line budget, which is not a reason to enlarge a diff. Consequence recorded honestly in the ADR: `run_test_suite.py` ends slightly over the 300-line guideline — a *new* crossing (advisory), not a baseline ratchet. |
