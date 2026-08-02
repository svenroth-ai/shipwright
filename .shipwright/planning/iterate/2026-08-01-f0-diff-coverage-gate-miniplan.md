# Mini-Plan: f0-diff-coverage-gate

- **Run ID:** iterate-2026-08-01-f0-diff-coverage-gate
- **Spec:** `.shipwright/planning/iterate/2026-08-01-f0-diff-coverage-gate.md`

## 1. Files to create / modify

| File | Change | Why |
|---|---|---|
| `shared/scripts/tools/suite_coverage.py` | **new** | The gate: OS-backed run lock, data-dir reset, targeted CI-base fetch, invocation-owned combine XML, gate argv, pure verdict, and an injectable `runner`. |
| `shared/scripts/tools/suite_worktree_diff.py` | **new** | Builds one coherent merge-base → final-working-tree patch through a private temporary Git index; never mutates HEAD or the real index. |
| `shared/scripts/tools/tests/test_suite_coverage.py` | **new** | In-process unit tests for every function above. |
| `shared/scripts/tools/tests/test_f0_diff_coverage_e2e.py` | **new** | Drives the real pinned `diff-cover` over a synthetic git repo — proves the gate *bites*. Doubles as the F0.5 surface command. |
| `shared/scripts/tools/tests/test_f0_cli_diff_coverage_e2e.py` | **new** | Invokes the real `run_test_suite.py` surface over a synthetic repo and proves discovery → instrumentation → combine → gate returns `4`, then `0`. |
| `shared/scripts/tools/suite_units.py` | edit | Gains `Unit.cov_args` / `Unit.cov_file` and `instrument_for_coverage`; `build_command` deliberately stays with execution in `run_test_suite.py`. |
| `shared/scripts/tools/run_test_suite.py` | edit | Keeps `build_command`, appends `cov_args` after markers, sets `COVERAGE_FILE` per unit, and wires reset + instrument + the gate and its exit code. |
| `shared/scripts/tools/tests/test_suite_units.py` | edit | Coverage-arg construction, label sanitising, the no-`scripts/` case. |
| `shared/scripts/tools/tests/test_run_test_suite.py` | edit | `COVERAGE_FILE` wiring, exit-code arithmetic, red-suite skip. |
| `shared/scripts/tools/tests/test_f0_ci_parity.py` | edit | AC-3: the local gate argv is pinned against `action.yml`'s declared defaults, and ci.yml still runs the gate as backstop. |
| `plugins/shipwright-iterate/skills/iterate/references/F0.md` | edit | Document the gate + the new exit code `4`. |
| `docs/hooks-and-pipeline.md` | edit *(if it describes F0's contract)* | Repo rule: an F0 contract change is documented in the same diff. |
| `.gitignore` | edit | Gives disposable source experiments an explicit `/.scratch/` home; every other untracked source file intentionally participates in F0. |

**Not touched:** anything under `.github/`.

## 2. Work breakdown (sequential)

1. **`suite_coverage.py` + its tests (TDD).** Pure first: `gate_argv`,
   `combine_argv`, `verdict`. Then `reset_coverage` (real tmp dirs) and
   `run_gate(project_root, *, suite_green, runner=subprocess.run)`.
   *Test expectation:* every branch of `verdict` and both argv builders covered
   in-process; `run_gate` driven with a fake `runner` — no subprocess.
2. **`suite_units.py`.** Add the two `Unit` fields and
   `instrument_for_coverage(units, project_root, data_dir)`; keep
   `build_command` in `run_test_suite.py` (review finding G4).
   *Test expectation:* plugin-with-`scripts/` gets `--cov=scripts`; plugin
   without gets nothing; shared/integration get `--cov=shared`; three distinct
   data-file labels; marker expression still intact (AC-7).
3. **`run_test_suite.py`.** Append `unit.cov_args` at the existing command
   construction point; `_exec` sets `COVERAGE_FILE` from `unit.cov_file`;
   `run_suite` instruments the discovered units; `main` runs the gate and folds
   its verdict into the exit code.
   *Test expectation:* existing suite stays green (the fakes take `_exec`'s
   unchanged 5-arg signature); new tests for exit `4`, the red-suite skip, and
   the `n/a` path.
4. **Parity test** (AC-3) + **two E2E layers** (AC-8):
   `test_f0_diff_coverage_e2e.py` drives the real pinned gate and combined XML;
   `test_f0_cli_diff_coverage_e2e.py` invokes `run_test_suite.py` and proves the
   complete CLI wiring returns `4`, then `0`.
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
| G1/O5 | `origin/main` may not exist / may be the wrong base | high/med | **Superseded by O11.** The E2E builds a real `origin/main`; absence fails closed. The second review established that the existing CI action's declared `origin/main` is authoritative for this no-CI-change iterate, so local default-branch discovery would itself be drift. |
| O3 | two combine implementations would drift | med | **Accepted.** `suite_coverage` never re-implements combining: `combine_argv()` builds the exact `combine_coverage.py` invocation ci.yml uses, and that stays the single implementation. Shelled out rather than imported — `combine_coverage.py` binds a top-level `tools`/`lib` package, and importing it from a module loaded as `scripts.tools.*` would create two module objects for one file (ADR-045). Process isolation avoids that; the argv builder is pure and unit-tested, so nothing load-bearing hides in the subprocess. |
| O4 | assert the real XML, not just the flags | med | **Accepted** → AC-1 and AC-8 assert `filename` entries in the combined XML for a plugin tier *and* the shared tier. |
| O6 | two unit ids could sanitise to one label | med | **Accepted** → AC-9. Uniqueness is validated at instrumentation time and fails closed before any process starts. |
| O7 | `uvx` absent / resolution failure must not raise | low | **Accepted** → AC-4c. The runner wrapper catches `OSError`/`SubprocessError` and maps to 4 with a phase-specific message; argv lists, `shell=False`. |
| G2 | `pytest-cov` missing from the F0.5 runner command | med | **Accepted** for the command line. The *units* were never at risk — instrumentation appends `pytest-cov` to `unit.extra_deps`, which `build_command` already turns into `--with`. **Rejected**: adding it to dev-dependencies — `uv run --with` is how this runner provisions pytest and pytest-mock too. |
| G3 | `coverage combine` would look in the CWD, not `.cov-data/` | med | **Rejected — already correct.** `combine_coverage.py` discovers `.coverage.<label>` under an explicit `--data-dir` and passes each **resolved absolute path** to `coverage combine --append`. Verified in source. |
| G4 | moving `build_command` is churn without architectural value | low | **Accepted.** It stays in `run_test_suite.py`; only the line that appends `unit.markers` changes, to append `unit.cov_args` after them. The move was motivated by a 300-line budget, which is not a reason to enlarge a diff. Consequence recorded honestly in the ADR: `run_test_suite.py` ends slightly over the 300-line guideline — a *new* crossing (advisory), not a baseline ratchet. |
| O8 | a dangling `origin/HEAD` should not hide a valid `origin/main` | med | **Accepted, then strengthened by O11.** `origin/HEAD` no longer participates in selection at all; a differing or dangling symref cannot change CI's authoritative `origin/main` line set. |
| O9 | the file table still instructed moving `build_command` | low | **Accepted.** The file table and step 2 now agree with G4: execution stays in `run_test_suite.py`; `suite_units.py` owns only coverage metadata and instrumentation. |
| O10 | the 6.7-minute F0 cost lacked a maintainer decision and warm evidence | med | **Accepted.** The maintainer explicitly accepted the conservative cost on 2026-08-02 after a time-boxed warm benchmark. Coverage uses the C tracer; on the same 432 tests, n=8 was faster than n=4 (32.9 s vs 37.0 s; plain n=8 16.8 s), so no safe parallelism change was available. The canonical warm full-suite measurement remains an F11 delivery check. |
| G5 | local snapshot inclusion can catch unrelated unignored scratch Python files | med | **Accepted.** The private-index producer uses `git add -A`, so every unignored source file participates just as it would after F6. F0.md and the pipeline reference direct disposable work to the explicitly ignored `/.scratch/` directory. |
| O11 | preferring `origin/HEAD` can disagree with CI's fixed `origin/main` | med | **Accepted.** `compare_branch()` now verifies only the action's declared `origin/main`; tests prove a differing or dangling `origin/HEAD` cannot alter the local merge-base line set. Changing CI is explicitly outside this iterate. |
| O12 | the CLI-level E2E module was absent from the file table | med | **Accepted.** The file table and step 4 now name both E2E layers and distinguish direct real-tool coverage from full `run_test_suite.py` wiring. |
| O13 | exit code `4` needs a caller audit | low | **Accepted; no code change required.** The lifecycle's sole authoritative caller is the direct command in F0.md, where every non-zero STOPs. No wrapper translates only `1`; `final_exit_code` owns precedence and its focused tests cover `4` against suite and race failures. |
| O14 | untracked-file failures should identify their source | low | **Satisfied.** `run_gate` always prepends diff-cover's complete report before its own verdict, on pass and failure; that report names affected files/lines. The private-index E2E proves uncommitted source participates, while F0.md and hooks-and-pipeline warn why unrelated unignored source is included. |
| O15 | a resolving but stale local `origin/main` can select a different merge base than CI | med | **Accepted.** `compare_branch()` now mirrors the action's targeted `git fetch --no-tags origin main` before verifying the ref. Failure is closed; a real remote regression proves a deliberately stale tracking ref is refreshed. The parity test also pins the local constant to the action default. |
| O16 | root `coverage.xml` freshness cannot prove this combine produced it | med | **Accepted.** Combine writes a UUID-named candidate under `.cov-data/`; diff-cover gates that exact path, and only afterward is it atomically promoted to root `coverage.xml`. A freshly written foreign root report with a no-output combine now fails. |
| O17 | two simultaneous F0 invocations can reset/overwrite shared coverage state | med | **Accepted.** An OS-backed non-blocking lock spans reset → suite → combine → gate. The open handle owns the lock, so crashes release it without a stale sentinel; a focused test proves exclusion and reacquisition. |
| O18 | the documented scratch directory should be a real ignored path | low | **Accepted.** `/.scratch/` is now explicitly ignored and pinned by `test_the_documented_scratch_directory_is_actually_ignored`; F0.md and the pipeline reference name that concrete directory. |
| D1 | diff-cover's committed/staged/unstaged union can mix line coordinates after a dirty insertion above a committed hunk | high | **Accepted.** F0 builds one merge-base → final-working-tree patch with a private `GIT_INDEX_FILE` (`read-tree` + `git add -A`) and passes it via pinned `--diff-file`; real index and HEAD are untouched. A real-tool E2E inserts ten dirty lines above a committed uncovered function and still fails on final coordinates. |
| D2 | a failed first attempt's coverage can inflate an accepted retry | high | **Accepted.** Before retry, `_clear_failed_attempt_coverage` removes the exact base file and only its dot-suffixed pytest-cov/xdist family. Failure to remove closes the suite; a regression proves only the accepted retry remains. |
| D3 | a red suite can still hang fetching the compare branch because call arguments evaluate eagerly | high | **Accepted.** `_run_locked` branches before compare resolution: red suites and higher-priority race-record failures perform no fetch or diff build. Green fetches set `GIT_TERMINAL_PROMPT=0` and a 120 s timeout; focused tests prove both contracts. |
| O19 | mandatory fetch prevents an offline green even with a cached `origin/main` | high | **Rejected by contract.** The local gate promises the same refreshed `origin/main` line set as CI. Falling back to a stale ref can certify lines CI will reject—the exact delayed-red class this iterate removes. The fetch is bounded, non-interactive, and runs only after a green suite; inability to refresh is intentionally exit `4`. |
| O20 | reset might unlink a held lock path and let a second F0 lock a new inode | high | **Already safe; regression added.** The stable `.coverage.f0.lock` rendezvous is at repo root. Reset removes `.cov-data/`, root `coverage.xml`, and exact root `.coverage`, never `.coverage*`. `test_coverage_reset_preserves_the_held_lock_rendezvous` runs reset while held and proves a second acquisition still fails. |
| O21 | `uvx` launcher failure can also return `1` and be misreported as below threshold | med | **Accepted.** Exit `1` now becomes a threshold verdict only when output also contains diff-cover 10.3.0's pinned `Failure. Coverage is below 80%.` signature. A launcher-style rc=1 regression proves infrastructure advice wins otherwise; the real-tool E2E proves actual under-coverage still receives test advice. |
| O22 | shallow/truncated history can have `origin/main` but no merge base | med | **Accepted.** The private-index builder already validates `git merge-base` before `read-tree`; its failure now names `git fetch --deepen=100 origin main` as remediation, with a focused regression. It remains fail-closed. |
| O23 | Windows lock and combiner dependency may be implicit | low | **Already satisfied.** Locking selects `msvcrt.locking` on Windows and `fcntl.flock` elsewhere; this run's focused tests execute on Windows. `combine_argv` explicitly provisions `coverage` via `uv run --with coverage`, and its command shape/failure paths are tested. |
| O24 | the private-index environment could leak globally | low | **Already safe.** The implementation copies `os.environ`, sets `GIT_INDEX_FILE` only in the subprocess `env`, and never mutates process-global environment. The strengthened shared helper now also removes inherited Git repository redirection. |
| O25 | fork workflows may use `upstream` as canonical while CI parity requires `origin/main` | med | **Contract retained; message improved.** Auto-selecting another remote can diverge from the existing CI action, which is fixed to `origin/main`. Exit `4` now tells the operator to ensure `origin` is the canonical remote CI uses before fetching. |
| O26 | sources can change during the 6.7-minute suite, making coverage and final patch describe different snapshots | med | **Accepted** → AC-6d. A controlled `git ls-files -co --exclude-standard -z` inventory fingerprints all tracked and untracked, non-ignored Python files before and after measurement. Any change exits `4` before network, combine, or gate; focused tests prove file detection and orchestration precedence. |
| O27 | inherited `GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR`, or `GIT_INDEX_FILE` can redirect Git operations | med | **Accepted.** Every gate Git call now uses `git -C <absolute-root>` and a copied environment with those four context variables removed; only private-index calls receive the invocation-owned index path. Hostile-environment regressions cover fetch and private-index merge-base paths. |
| O28 | combine and diff-cover need bounded timeout failures | med | **Already satisfied; regression added.** Their shared runner has an explicit 600 s timeout and catches `subprocess.SubprocessError`, which includes `TimeoutExpired`; `test_diff_cover_timeout_is_a_phase_specific_closed_gate` proves exit `4` names the timed-out phase. |
| O29 | `git add -A` can execute repository-configured filters | low | **Documented trust boundary.** F0 already executes the checkout's tests and hooks, so it is only appropriate in a trusted repository. Filters remain enabled because disabling them would make the staged patch differ from the commit/CI snapshot. |
| O30 | a path-only source inventory would miss edits to existing files | high | **Already content-safe; clarified and strengthened.** `source_fingerprint` SHA-256 hashes normalized path plus file bytes (or symlink target), not the `ls-files` output alone. The focused regression now modifies an existing tracked `.py` file and root `pyproject.toml` and proves both alter the fingerprint. |
| O31 | sources can change after the post-suite check, during fetch, patch creation, or diff-cover | high | **Accepted** → strengthened AC-6d. The same baseline is rechecked after suite, after fetch immediately before patch creation, after patch creation, and after diff-cover. Any mismatch replaces even a passing gate with exit `4`; a parameterized in-process regression covers all three late windows. |
| O32 | private-index Git commands may hang and need cleanup | med | **Already satisfied.** Every Git call in `suite_worktree_diff` uses the same 120 s wrapper and catches `SubprocessError`/`OSError`; the private index and lock are removed in `finally` on every return/exception path. The plan now states this explicitly. Coverage/pytest-cov provisioning deliberately mirrors CI's existing unpinned commands; diff-cover alone is pinned because its CLI/exit contract is interpreted by the gate. |
| O33 | source fingerprinting is hostile over-engineering for a local runner | med | **Rejected for this permanent CI-parity gate.** F0's result is used as a pre-push certification, not an advisory watch-mode result. Certifying coverage from one source snapshot against another recreates the false-green/false-red class this iterate removes. Fingerprinting is local SHA-256/Git inventory work and negligible beside the accepted 6.7-minute suite. |
| O34 | exact fetch may succeed without updating `origin/main` | high | **Already proven with real Git.** `test_compare_branch_refreshes_a_stale_origin_main_before_using_it` advances the bare remote, deliberately rewinds `refs/remotes/origin/main`, executes `compare_branch()` (the exact fetch), and asserts the remote-tracking SHA equals the remote HEAD before use. |
| O35 | `.py` plus root pyproject omits other measurement inputs | med | **Accepted, bounded.** The content hash now includes `.py`, `.pyi`, and every tracked/untracked non-ignored `.coveragerc`, `.python-version`, `pyproject.toml`, `pytest.ini`, `setup.cfg`, `shipwright_test_config.json`, `tox.ini`, and `uv.lock`. Arbitrary data files are intentionally excluded because tests may generate them; the protected set is source plus runner/coverage/dependency configuration. |
| O36 | threshold text is a load-bearing compatibility dependency | low | **Accepted.** `DIFF_COVER_THRESHOLD_MESSAGE` now sits beside `DIFF_COVER_VERSION`/`FAIL_UNDER` with an explicit version-bump contract. Raw diff-cover output remains prepended on every verdict, so an unexpected signature is diagnosable and fails as infrastructure. |
| O37 | F0's Git filters need an explicit trust warning | low | **Already documented.** Both F0.md and `docs/hooks-and-pipeline.md` state that F0 executes project tests and normal configured Git filters and must run only in a trusted checkout. |
