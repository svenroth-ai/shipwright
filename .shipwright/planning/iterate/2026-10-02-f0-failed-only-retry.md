# Iterate Spec: f0-failed-only-retry

- **Run ID:** iterate-2026-10-02-failed-only-retry
- **Type:** change
- **Complexity:** medium
- **Status:** draft

## Goal

When an F0 unit is red in its parallel attempt, the serial retry re-runs **only the red
tests** instead of the whole unit. Measured 2026-10-02 over 146 red unit-attempts: 66 %
passed alone on the retry (a race, no code change), and each such retry re-ran the whole
unit (`shared/tests` alone: ~22 min). The cross-invocation resume ("fix, then re-run only
the red tests") that the operator also asked for was **designed, reviewed and deferred**:
see "Decision: resume deferred" - this iterate ships the safe part and the primitives a
later resume would reuse.

## Decision: resume deferred (review-driven scope cut)

Three independent reviews (internal architecture, internal plan, external GPT + GLM) found
the cross-invocation resume (option B in the architecture brief) unsafe or not worth its
state as specified:
- reusing a green unit after a changed NON-test source file can report green while a
  regression sits in a reused test (the 5-file bound does not detect it);
- non-Python inputs (SKILL.md, prompts, JSON, fixtures) are invisible to a .py-only hash;
- the staged compliance evidence would claim a full green run of a tree that never ran;
- purging stale coverage makes the diff gate fail often, forcing a full run anyway;
- plus resume-path gaps (rc 5, removed/renamed tests, torn state, run-id keyed paths).

Disposition: **fix by scope cut** (not decline). Follow-up, to be filed as a triage card:
build resume only with (i) any changed non-test file => full run for affected units,
(ii) hashing of ALL tracked + untracked files, (iii) resumed evidence marked as such and
never stageable as a full green run, (iv) a measured purged-coverage-gate failure rate on
real fix iterations first, (v) atomic, hash-keyed state. The primitives built here
(`lastfailed` cross-check, report merge, `--lf` argv) are its reusable part.

## Acceptance Criteria

- [ ] **AC-1 (failed-only retry)** A unit whose parallel attempt is a TEST failure is
      retried with `--lf --lfnf=none --cov-append` against the SAME per-unit pytest cache
      dir the first attempt wrote, without xdist, when the cross-check holds: the number of
      entries in the cache's `lastfailed` equals the number of testcases carrying a
      failure/error in the attempt's own JUnit report, and is `> 0`. A unit green on that
      retry is `race=True` with `retry_kind="failed-only"` and is still filed as a race in the
      Triage Inbox, exactly like a serial-retry race.
- [ ] **AC-2 (fallback)** When the cross-check does not hold (missing/unreadable cache,
      count mismatch, zero entries, unreadable JUnit), when the failed-only retry exits
      pytest rc 5 (nothing selected), or when the reports cannot be merged, the unit is
      re-run WHOLE, serially, exactly as today (including clearing the failed attempt's
      coverage). INFRA failures keep the identical-shape retry; they never take the
      failed-only path.
- [ ] **AC-3 (coverage appends)** On a failed-only retry the unit's coverage data file is
      NOT cleared and the retry appends; on a whole-unit retry it is cleared as today.
- [ ] **AC-4 (report merge)** The retained per-unit JUnit report after a failed-only retry
      is the first attempt's report with every failing testcase removed and every re-run
      testcase added (a re-run testcase replaces a same classname+name one; on key
      collision the retry wins), so the unit's test total stays the whole unit's and
      `stage_f0_evidence`'s "complete and green" rule holds. A report that cannot be
      merged is AC-2's fallback, never a best-effort guess.
- [ ] **AC-5 (still-red is honest)** A unit still red after the failed-only retry is
      reported red with the RETRY's output and evidence, and both its summary row and its
      output-block header say `failed-only`.
- [ ] **AC-6 (isolation unchanged)** The first attempt's pytest cache lives in the unit's
      own temp dir (`-o cache_dir=<unit tmp>/c`), never the repo's `.pytest_cache`;
      `build_command` without a cache dir is byte-identical to today (`-p no:cacheprovider`).
- [ ] **AC-7 (integration, real pytest)** A real-pytest integration test drives a tiny
      project through the runner's own `run_suite`: parallel (xdist) attempt with 2 red of 4
      tests -> failed-only retry executes exactly those 2 -> merged report has 4 testcases
      and 0 failures; a still-red test keeps the unit red; a call-failure-plus-teardown-error
      case and a collection-error case end green on EITHER path (narrow or whole-unit
      fallback) with a correct retained report and no stale error entry; a coverage file
      written by the first attempt is unioned, not erased. The fallback branches themselves
      (no cache, mismatch, rc 5, unmergeable, >10 failures) are pinned by the fake-exec tests.
- [ ] **AC-8** `run_test_suite.py` does not grow past its bloat baseline (`current` 529);
      the retry loop moves to a new `suite_retry.py`, the primitives live in
      `suite_failed_only.py` (each < 300 lines); every existing F0 test file passes unchanged.

## Spec Impact
- **Classification:** none
- **NONE justification:** developer-facing F0 gate mechanics; no product FR names the F0
  runner's retry strategy (precedent: iterate-2026-08-01-f0-diff-coverage-gate, none).

## Out of Scope
- Cross-invocation resume (deferred, see Decision above).
- Test selection from the diff ("run only affected tests") - rejected by the operator.
- Changing `ci.yml` (stays the full serial authoritative gate) or the `suite` config schema.
- Per-test coverage contexts (so a failed test's pre-failure lines are still in the union).

## Design Notes
- `lastfailed` is the id source (probed 2026-10-02 under xdist and serial): the JUnit
  classname -> nodeid mapping is lossy. `--lfnf=none` turns "nothing selected" into rc 5.
- `suite_retry.retry_red_units` receives the runner's seams (`_exec`, evidence retention,
  coverage clearing, event emitter) as an `ops` namespace built at call time, so every
  existing `monkeypatch.setattr(mod, "_exec", ...)` keeps working.
- Disclosed limit: the union coverage includes lines the red attempt ran before failing (a
  failing test can reach an error-path line a passing run never would). Narrow; CI re-gates.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| first attempt (pytest cache plugin) | `suite_failed_only.read_lastfailed` | `<cache_dir>/v/cache/lastfailed` JSON |
| `suite_failed_only.merge_junit` | `Retention.record` -> `stage_f0_evidence` | JUnit XML |

## Confidence Calibration
- **Boundaries touched:** the two above (producer and consumer both in this diff or pinned by it).
- **Empirical probes run:** to be filled at F5 (real-pytest integration test AC-7; `lastfailed` shape probed under xdist and serial on 2026-10-02).
- **Test Completeness Ledger:** filled at F5.
- **Confidence-pattern check:** filled at F5.

## Verification (medium+)
- **Surface:** none
- **Runner command:** `uv run pytest shared/scripts/tools/tests -k "failed_only or suite_retry"` and, separately, `uv run pytest shared/scripts/tools/tests/test_f0_failed_only_real_pytest.py` (one root per pytest process)
- **Evidence path:** `.shipwright/agent_docs/iterates/iterate-2026-10-02-failed-only-retry.test-results.json`
- **Justification (only if surface=none):** CLI/library mechanics of the test runner; no startable web/api surface. The real-pytest integration test is the empirical probe.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** high (all high findings concern the cross-invocation resume, now out of scope)
- **Summary:** In-run failed-only retry is mostly sound; the false greens are in the cross-run resume.
- **Findings:**
  - architecture/high - resume reuses green units after a non-test source change: **fixed by scope cut** (resume deferred).
  - completeness/high - .py-only hash misses SKILL.md/JSON/fixtures: **fixed by scope cut**.
  - architecture/high - stale coverage of edited/deleted tests: **fixed by scope cut**.
  - security/high - purge path-form mismatch silently misses: **fixed by scope cut**.
  - architecture/medium - narrow retry turns order-dependent failure into a "race": **fixed** - own `retry_kind=failed-only`, still filed in the Triage Inbox, `FAILED_ONLY_MAX_TESTS=10` cap, disclosed limit in F0.md.
  - architecture/medium - session-level red (rc 1 with fewer failing testcases): **fixed in part** - the cross-check requires a non-zero testcase count equal to the cache, so a purely session-level rc 1 (zero failing testcases) goes whole-unit (tested); N real failures PLUS a session-level condition (a coverage `fail_under`, a plugin sessionfinish hook) can still pass the narrow retry - **disclosed**, this repo configures no `fail_under` and CI re-gates.
  - completeness/medium - resume edge cases / torn state / composite evidence: **fixed by scope cut**.
  - completeness/medium - integration test mechanism: **fixed** - per-execution marker files, real `uv run`, CI hard-fail when uv is missing.
  - architecture/medium - bloat/seams: **fixed** - `RetryOps` resolved at call time, run_test_suite 529 -> 485 lines, all existing F0 tests unchanged and green.
  - completeness/low - reproduce command: **disclosed** - the printed command stays the whole-unit reproduce command.
- **Known limitations:** order-dependent failures can pass alone (see Design Notes); union coverage includes red-attempt pre-failure lines.
- **Status:** 5 fixed, 1 fixed in part (rest disclosed), 4 resolved by scope cut, 1 disclosed

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes
- **Severity:** high (against option B only)
- **Summary:** Build option A; defer cross-invocation resume until it can prove reused tests still hold against the new tree.
- **Findings:** smallest-option/high - take A, defer B: **fixed** (scope cut). completeness/high x2 (regression via reused units, non-Python inputs): **fixed** (scope cut). completeness/medium (evidence honesty), complexity-cost/medium: **fixed** (scope cut). completeness/low (A gaps: pre-failure coverage, teardown+call double element, race classification): **disclosed**; teardown case now covered by the real-pytest test. security/low: n/a for A.
- **Known limitations:** none beyond the disclosed A gaps.
- **Status:** 5 fixed by scope cut, 1 disclosed

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-10-02-failed-only-retry/architecture_brief.md`
- **Verdicts:** glm=approve · openai=approve (both approve option A as scoped; the brief's persisted resume state is outside that scope)
- **Smallest thing that would do (per reviewers):** option A - the existing serial retry selecting failed tests from the same temporary per-unit pytest cache, merged report, appended coverage, whole-unit fallback; retain nothing across invocations.
- **Findings:** proportionality/low (keep the fallback as the single safety net): accepted. ownership/low (comment where `stage_f0_evidence` consumes reports that may be merges): fixed in `suite_failed_only` module docstring + F0.md.
- **Reconciliation:** the plan had rejected "resume now"; the reviewers' independent conclusion matches - resume is deferred, with the five conditions recorded above.

## External Plan Review (GPT + GLM, verdict revise on the original two-part plan)
Both reviewers' high findings targeted the resume half (5-file bound unsafe, removed/renamed tests, resume rc-5, torn state, run-id key). Their A-relevant findings (rc-5 fallback, merge-mismatch => fallback, fresh cache per attempt, argv-pinning tests untouched) are all implemented and tested. After the scope cut the plan was re-judged by the external architecture call (approve, approve).
