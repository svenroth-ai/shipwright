# Iterate Spec: the test phase's record tells the truth about the run

- **Run ID:** iterate-2026-07-27-test-phase-record-honesty
- **Type:** change
- **Complexity:** medium
- **Status:** planning
- **Triage card:** `trg-12b4cf3f` (supersedes `trg-0516e85e` → `trg-506f164c` →
  `trg-737d0449` / `trg-30fc1fc6` / `trg-3a4466e5`)
- **Requirement:** FR-01.06 (`/shipwright-test`)
- **Evidence:** `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  (§ `.06` test — no new criteria, two decided gaps; and the
  "Removed from the catalog → carried as triage" table)

## Goal

Four independent defects, one mechanism: **the test phase's own record should
describe what actually happened.** Each is a place where the phase reports
something other than the truth of the run — a journey with no test that nobody
mentions, a warning that evaporates at session end, an inherited failure counted
as a fresh one, and a test that only passed the second time reported as if it
passed the first.

Card ownership is explicit: this iterate owns **the test plugin**, **the
test-phase validator branch** (`verifiers/test_checks.py`), and **the
browser-test result reader** (`playwright_runner.py`). It does **not** own
artifact stamping (binding the record to the code version it describes) — that
moved to `trg-4d5b6a56` so it is built once.

## Problem

### (1) Journey coverage is all-or-nothing

`step-2.5-e2e-spec-generation.md` skips generation entirely when
`find e2e/ -name "*.spec.ts" | head -1` returns anything. So the first journey
gets a test and every journey added to the plan afterwards gets nothing — and
nothing reports the gap. The campaign kept the *true half* ("a project with no
browser tests gets them written from the plan's journeys", criterion 6) and
carried the missing half as `trg-30fc1fc6`.

### (2) Three of four warning-only layers leave nothing behind

`results-enforcement.md` names four non-blocking layers: **E2E**,
**Consistency**, **Design fidelity**, **Performance**. Only performance calls
`_emit_failures_to_triage` (`performance_check.py:250`), so only performance
leaves a follow-up that outlives the session. The other three warn to stdout and
are gone. A suite failing for six weeks is indistinguishable from one that
started failing this morning.

### (3) The test phase does not know the accepted-baseline list exists

`shipwright_known_failures.json` is read by exactly one component:
`plugins/shipwright-compliance/scripts/lib/collectors/test_evidence.py`
(`collect_known_failures`). The audit phase therefore knows which failures
predate onboarding and does not count them as new
(`rtm_generator.py:478` → `COVERED (baseline)`; `test_evidence.py:422` →
`PASS (baseline)`). The test phase has **zero** mentions of the file. Result:
an onboarded project reports a permanently red test run while the audit reports
the same run as within baseline — two components holding different truths about
one run.

> Operator, recorded in the campaign: *"Ohne das lernt der Bedienende, Rot zu
> ignorieren"* — which is worse than any single failure.

### (4) A retry-pass is indistinguishable from a first-time pass

`playwright_runner.parse_playwright_json` walks `test["results"]` and counts
**every attempt** as a separate test. Playwright's own per-test verdict
(`test.status` ∈ `expected` / `unexpected` / `flaky` / `skipped`) is never read.
Two consequences:

- `flaky` is discarded — a test that needed a retry is recorded as a plain pass.
- Retries **inflate** `total` and simultaneously add to `failed`, so a
  successfully-retried test makes `success` false. The record is wrong in both
  directions at once.

`step-3.5-e2e-verification.md` names `stats.flaky` in its parse list but then
reconciles against `expected + unexpected + skipped` — flaky is dropped from the
total, so the documented reconciliation cannot balance on any run that had a
retry.

## Design decisions

**D1 — One reader for the accepted-baseline list, not two.** The defect is
*two components holding different truths*; adding a second parser to the test
plugin would reproduce it. `shipwright_known_failures.json` gets a single reader
at `shared/scripts/known_failures.py` (top-level, the `triage.py` precedent —
ADR-045 keeps shared helpers out of any plugin's `lib/` namespace), and
compliance's `collect_known_failures` delegates to it. Compliance's observable
behaviour is unchanged; it simply stops owning the parse.

**D2 — Baseline arithmetic is copied, not re-invented.** The validator mirrors
compliance rather than inventing a rule; a different rule here would re-open the
very divergence being closed. **Revised twice under review, and the final shape
is the audit's two-branch one:**

- *No `failed` / `skipped` breakdown* → charitable branch. `gap = total - passed`;
  `gap <= baseline_failure_count` → within baseline. Mirrors
  `rtm_generator.py:475-478` and `tests_block.progression_result`'s no-skip arm.
  **This is the card's motivating case** — an onboarded project reporting bare
  counts.
- *An explicit `failed` or `skipped`* → exact branch. The residual is exact, so
  the aggregate allowance does **not** apply, and acceptance is decided per
  failure by identity instead. Mirrors `tests_block.progression_result`'s
  explicit-skip arm, which compliance pins deliberately
  (`test_explicit_residual_ignores_baseline_charity`: waiving an exactly-counted
  failure on a count would make the rendered cell contradict the D4 detective).

The first revision came from the external *plan* review (skips must not consume
the allowance). The second came from the parity harness written for the external
*code* review, which failed on its first run: the validator was excusing exact
residuals that the audit calls FAIL. That is this card's own defect one layer
down, and it is now pinned by `test_known_failures_audit_parity.py` — including
the one place the two **deliberately** differ (a bare gap beyond the baseline:
the audit is describing merged history, the validator is gating a live run).

**D3 — `flaky` is a subset of `passed`, not a fourth bucket.** The operator's
instruction is "still a pass, still non-blocking, but counted separately". So
`passed + failed + skipped == total` continues to hold and `flaky <= passed`.
This keeps every existing consumer of the shape correct while adding the signal.

**D4 — Journey coverage blocks on greenfield, files a follow-up on brownfield.**
The card says so, and it matches the adopt contract: a brownfield repo's
pre-existing gaps are a backlog, not a build failure. The greenfield/brownfield
signal is `run_config["adoption"]` — the same signal compliance already uses
(`compliance_report._is_adopted`, chosen empirically over `scope` in Iterate B.1).
That helper moves to the shared module too, for the same reason as D1.

**D5 — Warning follow-ups are a new module, not an extension of
`performance_check.py`.** That file is 795 lines and carries a bloat baseline
entry; the emission pattern is what gets reused, not the file.

**D6 — Journey matching is reported as an indication, never as proof.** Matching
a journey title to a spec file is a name/slug heuristic, exactly like the
existing boundary-coverage report which labels itself "(heuristic)". The output
uses the same three-state honesty: `covered` · `uncovered` · `undetermined`
(no journeys parseable from the plan). Nothing here claims the test actually
exercises the journey.

## Acceptance Criteria

- [ ] **AC1** — Given a plan describing user journeys and an `e2e/` directory
  that already contains at least one spec file, when journey coverage is
  checked, then each journey is reported individually as covered or uncovered —
  the check is no longer skipped wholesale because some other journey has a test.
- [ ] **AC2** — Given uncovered journeys on a greenfield project, when the check
  runs, then it fails (blocking); given the same on a brownfield (onboarded)
  project, then it does not block and each uncovered journey leaves a triage
  follow-up routed to the onboarding phase.
- [ ] **AC3** — Given a warning-only layer (browser tests, cross-page
  consistency, screen-vs-mockup fidelity) reported a failure, when the session
  ends, then a triage follow-up exists for it — the same durability the
  performance budget check already provides, deduplicated so a persistent
  failure does not multiply.
- [ ] **AC4** — Given a project with `shipwright_known_failures.json`, when the
  test phase reports, then failures listed there are reported as
  known-and-accepted, separately from genuine failures, and the phase validator
  does not treat a gap within the declared baseline as a failing run.
- [ ] **AC5** — Given the same file, when both the test phase and the audit
  phase read it, then they read it through one shared reader — one parse, one
  set of semantics, so the two components cannot hold different truths about the
  same run.
- [ ] **AC6** — Given a browser test that failed and then passed on retry, when
  results are recorded, then it counts as a pass (non-blocking) **and** is
  counted separately as having needed a retry, with the retry count recorded.
- [ ] **AC7** — Given any browser-test run, when its numbers are recorded, then
  each test contributes exactly one outcome regardless of how many attempts it
  took (`passed + failed + skipped == total`, `flaky <= passed`) — retries no
  longer inflate the total nor mark a retried-and-passed test as failed.
- [ ] **AC8** — Given this ships, when the requirements catalog is read, then
  FR-01.06 states the guarantees added here (per the campaign's standing rule:
  *mint the acceptance criterion when it ships*), and the campaign's evidence
  ledger reflects the new state.

## Affected Boundaries

- **`shipwright_known_failures.json` (declared-list read boundary).** One
  producer (a human, by hand) and — after this change — two consumers reading
  through one parser. Round-trip probe: a fixture file written to disk, read by
  the shared reader, and asserted to give byte-identical results to compliance's
  pre-change `collect_known_failures` output shape.
- **`e2e-results.json` (Playwright JSON reporter → `playwright_runner`).**
  Foreign producer; we only read. The shape must tolerate the reporter's real
  output (`test.status` present) *and* the legacy shape our fixtures use
  (`test.status` absent, derive from `results[]`). Both are probed.
- **`.shipwright/triage.jsonl` (append boundary).** Three new producers. Dedup
  keys must be stable across runs or a persistent warning multiplies every run.
- **`shipwright_run_config.json` (`adoption` object)** — read-only, for the
  greenfield/brownfield routing decision.

## Confidence Calibration

- **Boundaries touched:** `shipwright_known_failures.json` (declared-list read),
  `e2e-results.json` (Playwright reporter → our reader),
  `.shipwright/triage.jsonl` (two new producers),
  `shipwright_run_config.json` `adoption` (read-only).

- **Empirical probes run:**
  - *Does the audit actually agree with the validator's arithmetic?* Wrote the
    parity harness before trusting the answer. **It did not.** With an explicit
    skip count and a declared baseline the audit renders `FAIL` while my
    validator returned ok — the exact two-truths defect this card exists to
    close, reintroduced one layer down. Read compliance's own pinning test
    (`test_explicit_residual_ignores_baseline_charity`) and found the audit's
    side is deliberate; the validator moved.
  - *Do the new triage producers work in a real plugin test session?* Ran the
    whole `shipwright-test` suite, not just the new files. **13 failures** —
    `ModuleNotFoundError: No module named 'lib.file_lock'`. The ADR-045
    collision: `triage.py`'s lazy import does not help once `sys.modules['lib']`
    is already the plugin's own package. Every pre-existing producer emits from
    a subprocess, which is why nothing had hit it. Fixed at the root.
  - *Is the `21 failed` in the combined `shared/tests + integration-tests` run
    mine?* Stashed the whole change and re-ran the identical command: **18
    failed on the clean tree, 18 on mine** (5003 passed vs 4960 — my 43 new
    tests). Pre-existing cross-session `sys.path` pollution; CI runs these as
    separate steps.
  - *Does the compliance delegation move any audit behaviour?* Full compliance
    suite: **1325 passed, 1 skipped**, unchanged.
  - *Do both new CLIs run end-to-end as the prose invokes them?* Subprocess
    integration test over a realistic project fixture: journey check exits 1 on
    greenfield gaps / 0 on brownfield, warning emitter files 4 items and 0 on
    re-run.

- **Test Completeness Ledger:**

| # | Behavior this diff introduces or changes | Disposition | Evidence |
|---|---|---|---|
| 1 | Journeys are parsed per journey from the plan's User Flows section | `tested` | `test_journey_plan.py` — 10 tests incl. plain headings, `Flow N:` prefix parity, page-object exclusion, duplicate titles |
| 2 | Each journey is reported covered / uncovered individually | `tested` | `test_journey_coverage.py::test_a_journey_with_no_spec_is_reported_even_though_other_specs_exist` |
| 3 | Greenfield gaps block; brownfield gaps do not | `tested` | `::test_greenfield_gaps_block`, `::test_brownfield_gaps_do_not_block_and_leave_a_follow_up` |
| 4 | Brownfield gaps route to onboarding via `launchPayload` | `tested` | `::test_the_brownfield_follow_up_routes_to_the_onboarding_phase` |
| 5 | Coverage is three-state; no plan / no journeys / no specs never read as covered | `tested` | 3 `undetermined` / `no_specs` tests |
| 6 | E2E, consistency and fidelity failures each leave a durable follow-up | `tested` | `test_warning_followups.py` — one test per layer + `::test_all_three_layers_emit_in_one_pass` |
| 7 | A persistent failure stays one item across commits | `tested` | `::test_the_same_failure_across_two_commits_stays_one_follow_up` |
| 8 | A skipped or green layer files nothing | `tested` | `::test_a_green_run_files_nothing`, `::test_a_skipped_layer_files_nothing` |
| 9 | Emission never raises into the phase | `tested` | `::test_a_broken_triage_writer_does_not_raise_into_the_phase` |
| 10 | `shipwright_known_failures.json` has exactly one reader | `tested` | `test_known_failures_delegation.py::test_the_audit_and_the_test_phase_read_one_parser` + 6 parity tests over present/absent/malformed/partial |
| 11 | Accepted failures are split from genuine **by identity** | `tested` | `test_known_failures.py::test_a_declared_failure_that_did_not_fire_does_not_excuse_a_different_one` and 5 siblings |
| 12 | The validator does not fail a run whose gap is within the declared baseline | `tested` | `test_test_checks_accepted_baseline.py::test_an_unbroken_gap_within_the_declared_baseline_does_not_fail_the_check` |
| 13 | An exactly-counted failure is **not** waived by the baseline (audit parity) | `tested` | `::test_an_exactly_counted_failure_is_not_waived_by_the_baseline` + `test_known_failures_audit_parity.py` (21 tests) |
| 14 | Skips do not consume accepted-failure allowance | `tested` | 4 tests incl. `::test_a_skip_only_gap_does_not_consume_accepted_failure_allowance` |
| 15 | An unreadable accepted list excuses nothing and says so | `tested` | `::test_an_unreadable_baseline_file_never_widens_what_is_excused`, `::test_the_summary_says_when_the_accepted_list_could_not_be_read` |
| 16 | Playwright per-test classification follows the decision table | `tested` | `test_playwright_runner_flaky.py::TestClassifyDecisionTable` — 11 parametrized rows + 5 edge cases |
| 17 | A retry-pass is a pass, counted separately, non-blocking | `tested` | `::test_a_retried_and_passed_test_is_a_pass_and_is_counted_as_flaky`, `::test_a_flaky_test_does_not_make_the_run_fail` |
| 18 | Retries no longer inflate the total | `tested` | `::test_retries_no_longer_inflate_the_total` |
| 19 | An empty or unrecognised result is never promoted to a pass | `tested` | `::test_no_results_at_all_is_a_failure_not_a_pass`, `::test_an_unrecognised_status_is_a_failure_not_a_pass` |
| 20 | The adoption signal has one definition | `tested` | `test_known_failures.py` 4 tests + full compliance suite unchanged |
| 21 | Control characters are stripped before record and dedup key | `tested` | `test_journey_plan.py::test_control_characters_in_a_title_are_stripped`, `test_warning_followups.py::test_long_titles_are_bounded` |
| 22 | Both CLIs are reachable as the phase invokes them | `tested` | `test_record_honesty_wiring.py` — 5 subprocess tests + 2 prose-drift meta-tests |
| 23 | `triage.py` can append in-process from a plugin test session | `tested` | `covered-by-existing-test` in effect — the 13 previously-failing tests in `test_warning_followups.py` / `test_journey_coverage.py` now pass; that suite IS the regression pin |
| 24 | A warning layer that reports a failure it cannot itemize still leaves a follow-up | `tested` | `test_warning_followups.py` — 6 tests, incl. the per-layer parametrized fallback and count-only cross-commit dedup |
| 25 | The aggregate follow-up does not claim any failure was matched against the accepted list | `tested` | `::test_the_aggregate_item_does_not_claim_anything_was_matched` |
| 26 | A legacy multi-attempt pass is a retry-pass, not a first-time pass | `tested` | `test_playwright_runner_flaky.py::test_a_legacy_multi_attempt_pass_is_not_silently_a_first_time_pass` |
| 27 | A fully-skipped count-bearing layer is not a failure and files nothing | `tested` | `test_warning_followups.py` — 3 parametrized layers + explicit-zero-`failed` |
| 28 | An integer skip COUNT is not read as the boolean layer-skipped flag | `tested` | `::test_a_truthy_skip_COUNT_does_not_read_as_a_skipped_layer` |
| 29 | The prose reports known-vs-genuine and flaky separately | `untestable` | `requires-manual-visual-judgment` — the summary banner is agent-rendered prose in `step-5-report-results.md`, not code. The *inputs* it must render are tested (row 11, 17); the wording is not mechanisable |

**0 testable-but-untested.** (Rows 24-26 were added by the fresh external code
review on the *delivered head* — the earlier review ran against the
pre-consolidation diff. It found that the identity-driven emitters saw nothing
when a record reported a layer failure through counts alone, so AC3 held only
for records carrying the optional detail; that the greenfield `no_specs` path
had no post-generation re-check, so an incomplete generation could finish with
journeys unverified; and that the legacy Playwright fallback contradicted this
spec's own decision table on a multi-attempt pass. All three fixed here.)

- **Confidence-pattern check:**
  - *Asymptote (depth):* the two hardest claims — "the two components cannot
    hold different truths" and "a retry-pass is honestly recorded" — are pinned
    by executable parity/decision tables, not by prose. The parity harness
    earned its place by failing on first run.
  - *Coverage (breadth):* all four card items have both a happy path and a
    degraded path (missing file, malformed file, unknown reporter shape, broken
    triage writer, un-parseable plan). Both branches of the greenfield /
    brownfield fork are exercised.
  - *Integration composition:* `cross_component` does **not** fire — the diff
    touches no merge/churn resolver, no `hooks.json`, no `hooks/*.py`, and not
    `verify_phase.py` / `get_phase_context.py` (only `verifiers/test_checks.py`,
    which the pattern list deliberately excludes). An integration-level test was
    written anyway (`test_record_honesty_wiring.py`), because the external plan
    review's strongest finding was that these modules could pass in isolation
    while nothing in production ran them.

## Out of scope

- **Artifact stamping / binding the record to the code version it describes.**
  Explicitly moved to `trg-4d5b6a56` by the card so it is built once across the
  campaign. Nothing here touches record freshness.
- **Making the journey→test match *proof* rather than indication.** Whether a
  spec file genuinely exercises the journey it is named for has no oracle; D6
  keeps the claim at the honest altitude.
- **Auto-generating the missing specs when a gap is found.** The card asks for
  the gap to be *reported*; generating is step-2.5's existing job on the
  no-specs-at-all path and stays there.
- **Changing which layers block.** `results-enforcement.md`'s blocking table is
  unchanged — item (2) is about durability of the record, not about escalating
  warnings into failures.
