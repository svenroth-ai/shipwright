# Iterate Spec: f0-cross-invocation-resume

- **Run ID:** iterate-2026-10-02-f0-cross-invocation-resume
- **Type:** change
- **Complexity:** medium
- **Status:** draft

## Goal

After an F0 unit goes red and the agent fixes it, the NEXT F0 invocation re-runs only the
previously red tests of each red unit and consolidates them with the prior invocation's
results into one report - instead of re-running the whole unit (`shared/tests`: ~15-22 min
per fix round). Units that were green are not re-run.

## Decision: operator option A (binding - not reopened in review)

Operator decision 2026-10-02: a resume is allowed **even when the fix changed NON-test
source files**. This deliberately replaces condition (i) of the deferral recorded in
`2026-10-02-f0-failed-only-retry.md` ("any changed non-test file => full run"), which would
make the resume useless because a fix almost always touches source. The safety net is CI,
which runs the full suite on every PR: a regression hiding in a reused result surfaces as a
red CI run, never on `main`. Reviews may flag the residual risk; the disposition is
**accepted by operator**, not a scope cut. The other four deferral conditions are all kept:
(ii) hash of ALL tracked + untracked files, (iii) resumed evidence marked as such and never
a full green run, (iv) coverage that cannot satisfy the gate => full run + recorded reason,
(v) atomic, hash-keyed state.

## Acceptance Criteria

- [ ] **AC-1 (state is a resume token)** A run with at least one red unit leaves state under
      `<main root>/.shipwright/runs/f0-evidence/resume/<hash of the checkout path>/`: a
      `CURRENT` pointer naming a directory with `manifest.json`, `tree.json`, per-unit
      `reports/` and `cov/`. A fully green run deletes it. The manifest lists the SHA-256 of
      every stored file; an edited or truncated file, an unreadable manifest, a foreign
      schema, a pointer escaping the store, or a state older than 24 h is refused (full run).
      A failed publication leaves the previous state intact and no stray pointer file.
- [ ] **AC-2 (red unit => red tests only)** A previously red unit whose saved red ids are
      trustworthy (`lastfailed` count == failing testcases of the saved report, 1..10, no
      `<error>`) is run as `--lf --lfnf=none --cov-append` without xdist against a restored
      `lastfailed`; only those tests execute. pytest must re-run EXACTLY the red tests (not
      fewer, not more, and the SAME testcase identities as the saved red ones - an equal count
      of different tests is refused), else the unit runs in full. The report left for the unit is the saved
      report with the red testcases replaced, so the unit's testcase total stays whole.
- [ ] **AC-3 (green unit => not re-run)** A previously green unit is not executed; its saved
      report and coverage stand in and are retained as this run's evidence.
- [ ] **AC-4 (source edits are allowed)** A changed non-test source file between the two
      invocations is NOT a refusal (operator decision); the number of changed files across
      the whole tree is reported.
- [ ] **AC-5 (every doubt => full unit run)** A unit runs in full, with the reason printed, on:
      no state or torn state; merge base with `origin/main` moved (whole run); unit
      definition changed; test files added/removed/renamed/EDITED, or a `conftest.py` above them edited (incl. a
      deleted tracked file);
      saved result already reused 3 times; prior outcome infra/no report; red ids
      untrustworthy or > 10; no saved coverage for an instrumented unit; coverage that cannot
      be restored; rc 5, a short or long re-run, an unmergeable report; any unexpected fault
      in planning (fails closed). `SHIPWRIGHT_F0_RESUME=0` forces full runs.
- [ ] **AC-6 (hash over ALL files)** The tree fingerprint covers every tracked and untracked,
      non-ignored file of any type (SKILL.md, JSON, fixtures, not only `.py`); a deleted
      tracked file is marked, not fatal; state is keyed per checkout so another worktree's
      state is never read.
- [ ] **AC-7 (coverage)** A restored coverage file loses the rows of every file the fix edited
      and of every path it cannot map onto a hashed file (unknown = dropped, never trusted;
      a plugin-relative path is never matched against the repo-root `scripts/`). If the
      diff-coverage gate (exit 4) still refuses a resumed run, the whole suite is re-run once
      in full and the reason is printed and written as `resume_fallback` in the manifest;
      any other exit code is returned as is.
- [ ] **AC-8 (evidence honesty)** A resumed run prints `RESUMED F0 RUN - NOT a full run`
      naming both invocations, the units reused and the tests re-run; the retained manifest
      carries `resumed` (both invocation ids, per-unit mode, re-run tests, changed-file
      count); `stage_f0_evidence.py` stages it with `resumed_local` provenance and reports
      `"resumed": true`; the AC-ratchet mirror prints that its evidence is a resume. A full
      run carries none of these markers.
- [ ] **AC-9 (no regression, no bloat)** `run_test_suite.py` stays within its bloat baseline
      (`current` 529); every new module is < 300 lines; every pre-existing F0 test passes
      with no assertion changed (only the e2e test's synthetic-repo module list gained the new modules).
- [ ] **AC-10 (real fix round)** Against real pytest and a real git checkout: red unit + green
      unit -> fix the source -> second run: the green unit's tests do not execute again, only
      the red test executes once more, the consolidated report has the whole unit's total and
      zero failures, coverage of the untouched file survives while the edited file's is
      rebuilt, the manifest says `resumed`, and the state is spent after the green run.

## Spec Impact
- **Classification:** none
- **NONE justification:** developer-facing F0 gate mechanics; no product FR names the F0
  runner's retry/resume strategy (precedent: iterate-2026-10-02-failed-only-retry, none).

## Out of Scope
- Test selection from the diff ("run only affected tests") - rejected by the operator.
- Changing `ci.yml` (stays the full serial authoritative gate) or the `suite` config schema.
- Re-validating a reused green result against the edited source (operator decision A).

## Design Notes
- State is a **resume token, not a cache**: only kept while something is red, so a later F0
  on a later tree can never be answered from it. Reuse depth is capped at 3 and age at 24 h
  so an operator-accepted staleness cannot compound silently.
- The resumed first attempt stands in for the ordinary first attempt: it leaves a WHOLE
  `r.xml` + a pytest cache, so a still-red result flows through the existing in-run retry
  and retention unchanged.
- Coverage is edited with direct sqlite (the runner's interpreter has no coverage.py);
  tables `file` / `line_bits` / `arc` are the stable coverage 5+ schema the real-pytest
  tests already read.
- `suite_resume.py` takes the runner's `_exec` / coverage clearing / classify as injected
  `ResumeOps` (same seam style as `RetryOps`), so it never imports the runner.

## Review Sequencing (honest note)

The operator pre-decided the scope (option A), so the build ran first and the plan-level
reviews ran over the built diff, after the first F0 run. Their findings were still integrated
(two real gaps were fixed in code, see below) - they were not treated as a formality.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** high
- **Summary:** sound design (atomic hash-verified state, exact re-run trust, fail-closed
  planning, one-shot fallback); one real false-green gap: edited test files were compared by
  path only.
- **Findings:**
  - test files edited in place not detected (high) - **fixed**: `unit_test_files` now carries
    `path:digest` and every `conftest.py` above the target; any edit = full unit run.
  - env outside the target (root/plugin `conftest.py` fixed; `pyproject.toml`/`uv.lock` not)
    (medium) - **fixed** for conftest AND (after the PR-review preflight raised the same point) for
    `pyproject.toml` / `uv.lock` / `pytest.ini` / `setup.cfg` / `tox.ini` of the unit and of the repo
    root: they are part of the unit signature, a change = "definition changed" = full unit run.
  - coverage of UNedited files trusted though the edit may change reachability (medium) -
    **disclosed**, accepted by operator (same class as decision A).
  - fallback may fire on most real fix rounds, so a resume could cost more than a full run
    (medium) - **disclosed**: unmeasured until real fix rounds run; the full re-run is one-shot
    and `resume_fallback` is recorded in the manifest so the rate is observable.
  - `resumed_local` is written but no consumer enforces it (medium) - **disclosed**: AC-8 is
    read as "marked, advisory"; a hard F5/F11 consumer is a follow-up, not this scope.
  - manifest could name a report/cov path that was never hash-verified (low) - **fixed**:
    `load_state` refuses a unit path absent from `sha256`.
  - state of deleted worktrees never pruned (low) - **disclosed** (24 h refusal; small data).
  - `tree_snapshot` hashes every file on every F0 (low) - **disclosed**, unmeasured.
  - tree changed during the run still saved against the pre-run snapshot (low) -
    **disclosed**: the next run's per-file digests (incl. test files) see the drift.
  - suffixed pytest-cov sibling files not stashed (low) - **disclosed**: safe, falls back to a
    full unit run.
- **Known limitations:** the disclosed items above.
- **Status:** 3 fixed (+ env files after the preflight), 7 disclosed (residual-risk ones: accepted by operator), 0 declined

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** worth building under decision A; main doubt is that the gate-refusal fallback
  re-runs the WHOLE suite, so the feature may be often inert.
- **Findings:**
  - fallback cost may erase the gain (medium) - **disclosed**, see above (one-shot, recorded).
  - pin the coverage schema / pytest-cache format and refuse on mismatch (medium) -
    **disclosed**: any sqlite fault or unexpected table already means "cannot be restored" ->
    full unit run (tested with a non-sqlite file); an explicit version pin is a follow-up.
  - put the `resumed` marker inside the JUnit as well (low) - **declined**: the manifest and the
    staged provenance carry it, and the JUnit is kept byte-compatible with a full run.
- **Known limitations:** as above.
- **Status:** 0 fixed, 2 disclosed, 1 declined

## Architecture Review
- **Driver:** claude; models: glm (openrouter), openai (codex). Verdicts: plan review
  glm=approve, openai=revise; architecture review glm=revise, openai=approve.
- **openai plan review (revise):** (1) test edits not invalidated (high) - **fixed**; (2) "exactly
  the red tests" verified by count only (high) - **fixed**: `suite_failed_only.same_tests`
  compares testcase identities `(classname, name)` against the saved red ones, test added for an
  equal-count/different-identity run; (3) fallback needs a clean reset boundary (medium) -
  **already so**: the fallback run starts through `prepare_resume(enabled=False)` AFTER the
  coverage reset, so no plan, no restored coverage, no `resumed` marker; (4) tree edited during
  the run (medium) - **disclosed**.
- **glm plan review (approve):** per-unit residual risk (consolidated report shows reused
  results as green) - **disclosed** (the manifest lists the re-run tests; reused ones are the
  rest); rename between runs - covered by the test-file rule and the identity check; one-shot
  fallback - by construction (`_run_locked` loops once); sqlite faults - already a full run;
  fold `suite_resume_report.py` - **declined** (71 lines, but it keeps the 300-line cap on
  `suite_resume.py`).
- **glm architecture review (revise):** drop the `--lf` precision layer and the coverage sqlite
  surgery; re-run red units in full - **declined**: the operator's scope (item 2) is
  explicitly "run only the red tests", and decision A is not reopened in review. The cost it
  names (a second execution mode, coupling to coverage 5+) is real and accepted.
- **openai architecture review (approve):** no findings.

## External Code Review (glm approve, openai revise)
- openai: the manifest has no integrity check of its own (high) - **fixed**: `CURRENT` pins the
  manifest's SHA-256, a valid-JSON edit (red unit -> `pass`) is refused, test added.
- openai: pointer containment (medium) - **fixed**: `..`/`.`/escaping symlink refused after
  resolving against the store, tests added.
- openai: green run with an unavailable snapshot kept the token (medium) - **fixed**: the token is
  spent before the snapshot/retention guard, test added.
- openai: AC-10 coverage assertion could not tell rebuilt from kept (medium) - **fixed**: the
  original `lib_b` executes a line the fix removes; the probe asserts it is gone.
- glm: a gate-refused resume and its fallback publish two retained runs under one `run_id`
  (medium) - **verified harmless**: `find_published_run` picks the most recently published one,
  which is the full fallback run.
- glm: green-with-evidence-error spent the token (low) - **fixed** (same predicate as the exit
  code); cancelled narrow attempt left the red-only report (low) - **fixed**; future-dated
  manifest (low) - **fixed**; snapshot taken even when resume is off (low) - **declined**
  (`persist` needs it for the NEXT run); cross-thread `ctx` mutation (low) - **declined**
  (single writer per unit key, CPython-atomic dict ops).

## Doubt Review (doubt-reviewer)
- **Status:** 2 fixed, 1 disclosed (accepted by operator).
- Foreign token reused by another iterate in the same checkout - **fixed**: the state is refused
  when its `run_id` differs from the current run's (a fix round keeps its run id).
- Non-`.py` test inputs (fixtures, golden files) not hashed - **fixed**: every file under the unit's
  test target is part of the unit's file digest (plus `conftest.py` above it).
- `resumed_local` is read by no downstream consumer: F11's cross-layer evidence and the compliance
  test-evidence index credit reused green testcases as executed at head - **disclosed, accepted by
  operator**: the operator brief asks that F11/compliance "accept it as resumed-local evidence";
  AC-8 therefore means marked and visible, not gated. CI's full run is the net (decision A).
- Minor, disclosed: any gate exit 4 (incl. "source changed during the run") triggers the one-shot
  full re-run; a file error inside `try_resume` is not converted to a per-unit full run.

## Code Review (code-reviewer)
- **Status:** 4 fixed, 5 disclosed/declined. No blocking bug; slot accounting, retry hand-off,
  fallback loop, persist timing and merge identity were traced correct.
- superseded token survives a red run that cannot save (medium) - **fixed**, test added.
- non-`.py` test data not fingerprinted (low) - **fixed** (see Doubt Review).
- gate-refusal reason wording (low) - **fixed** (now "failed on a resumed run").
- `_run_dir` naming (low) - **fixed**.
- no run_suite-level test of the narrow-to-full slot fallback (medium) - **disclosed**: the
  accounting was traced correct by two reviewers; a Budget-spy test is a follow-up.
- duplicate race follow-up in the fallback pass (low), untouched-file coverage under `--cov-append`
  not proven in the real probe (low), test-hygiene nits (low) - **disclosed**.
- `resume`/`resume_fallback` double parameter (low) - **declined**: a 2-argument monkeypatch of
  `_run_host_leased_suite` in existing tests pins the current call shape.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `suite_resume_state.save_state` (end of a red run) | `suite_resume_state.load_state` (next run) | `manifest.json` + `tree.json` + stored reports / coverage / `CURRENT` pointer |
| `suite_resume_cov.restore_coverage` | pytest-cov `--cov-append`, `combine_coverage.py` | sqlite coverage data file (`file`, `line_bits`, `arc`) |
| first-attempt pytest cache (restored `lastfailed`) | `pytest --lf --lfnf=none` | `<cache_dir>/v/cache/lastfailed` JSON |
| `Retention.publish` (`extra`: `resumed`, `resume_fallback`) | `stage_f0_evidence.published_resumed` -> `evidence_drop` provenance (`resumed_local`) | manifest.json keys |

## Confidence Calibration
- **Boundaries touched:** the four above (producer and consumer both in this diff).
- **Empirical probes run:** to be filled at F5 (real-pytest + real-git fix round, AC-10).
- **Test Completeness Ledger:** filled at F5.
- **Confidence-pattern check:** filled at F5.

## Verification (medium+)
- **Surface:** none
- **Runner command:** `uv run pytest shared/scripts/tools/tests/test_f0_resume_real_pytest.py` (one root per pytest process), then the whole `shared/scripts/tools/tests` root
- **Evidence path:** `.shipwright/agent_docs/iterates/iterate-2026-10-02-f0-cross-invocation-resume.test-results.json`
- **Justification (only if surface=none):** CLI/library mechanics of the test runner; no startable web/api surface. The real-pytest + real-git integration test is the empirical probe.
