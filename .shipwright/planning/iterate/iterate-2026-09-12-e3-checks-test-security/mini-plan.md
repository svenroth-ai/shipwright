# Mini-Plan — e3-checks-test-security

## Goal

Close the 7 `prompt-only (mechanisable)` lines the REQ-3 AC-evidence ledger
names under FR-01.06 (`/shipwright-test`, 5) and FR-01.07 (`/shipwright-security`,
2). Per campaign decision D7, no line may become an LLM-judgement gate —
each either gets a deterministic check + test, or is explicitly recorded as
`judgement` with a reason and a drift test. The 4 pre-existing FR-01.06
enforced-untested lines belong to REQ3.05 (already backfilled, PR #744) and
are untouched here.

## Approach

**FR-01.06 — 3 built, 2 explicitly deferred:**

- #5 "recorded browser-test numbers are the tool's own": new
  `check_e2e_counts_reconciled` (`_test_gate_extras.py`) reconciles
  `shipwright_test_results.json`'s `e2e` counts against Playwright's own raw
  `stats` block in `e2e-results.json`, per step-3.5's own documented formula.
  Deliberately reads the raw stats rather than importing this repo's
  `playwright_runner.parse_playwright_json` (plugin-local, ADR-045 boundary)
  or reproducing its per-test walk.
- #6 "a project with no browser tests gets them written from the plan's
  journeys": new `check_e2e_specs_exist_when_journeys_planned`. Coarse
  existence check (plan declares a flow -> at least one `*.spec.ts` exists) —
  per-journey name-matching stays criterion 14's (`journey_coverage.py`) job,
  already shipped; duplicating its heuristic here would be two
  independently-maintained fuzzy matchers.
- #7 (mechanisable half) "screens compared back to mockups; regression !=
  never-checked": new `check_design_fidelity_triage_matches_recomputation`
  (`_test_gate_fidelity.py`) recomputes step-3.7's Resolved/Regression/
  Persistent-Failure/Unchecked table as a pure function of two
  already-recorded values (`design-fidelity-report.json`'s build-time status,
  `shipwright_test_results.json`'s test-time status) and fails on disagreement
  with what was recorded — closing the "agent judgement" gap without
  inventing a new agent-facing gate.
- Two more `prompt-only (mechanisable)` mentions physically fall inside
  FR-01.06's ledger section (both about the SAME cross-cutting constitution
  rule, "test every AC at the layer that can falsify it") but explicitly say
  "five phases touch it, so no per-phase FR can own it" and are already
  routed to a named Phase-3 work unit. Recorded as accounted-for-and-deferred
  in the ledger rather than mis-scoped into a `.06`-only check.

All three new checks wired into `run_test_checks` (`test_checks.py`), the
same `_run_canon_checks("test", ...)` bridge every other phase-own check
uses.

**FR-01.07 — 2 downgraded to judgement, per the campaign's abort condition:**

- #6 "'fixed' means the tests passed after the fix" and #7 "a human-judgement
  finding carries the decision and the reason": building showed no
  deterministic oracle exists for either — `_remediation_status` (the only
  field that could carry #6's outcome) is read with a default of `"open"`
  but never written by any code path, and nothing records a per-finding
  Fix/Decline/Defer decision+reason for #7 either (confirmed by grep across
  `plugins/shipwright-security/scripts/` before downgrading, not assumed).
  Both downgraded to `prompt-only (judgement)`, each drift-tested
  (`plugins/shipwright-security/tests/test_remediation_judgement_drift.py`
  pins the relevant `remediation-loop.md` sentences verbatim). No gate built
  against a field nothing writes.

## Risk / boundaries

All three FR-01.06 checks are read-only over already-produced artifacts
(`e2e-results.json`, `shipwright_test_results.json`, `design-fidelity-report.json`,
`.shipwright/planning/**/claude-plan-e2e.md`, `e2e/**/*.spec.ts`); no runtime
or production code path is touched, and every check SKIPs (never fails) when
its inputs are absent, so an existing project with no browser tests / no UI
sees no new failures. `touches_io_boundary` fires because the checks read
project-tree files by path (JSON parsing of files whose shape a hostile or
malformed run could control) — hardened against malformed JSON, non-dict
values, non-int stats fields (bool coercion), directories masquerading as
the plan file, and non-string dict keys; each has a regression test.

## Out of scope (recorded on the ledger, not built)

- The 2 cross-cutting constitution-rule mentions inside FR-01.06's section
  (see above) — Phase-3's `req3-constitution-enforcement-register-DESIGN.md`
  owns them.
- FR-01.07 #6/#7's underlying missing recording mechanism (a real
  `_remediation_status` writer, or a durable Fix/Decline/Defer decision
  record) — building that is a product feature, not a check over an existing
  artifact, and is exactly what would need its own iterate spec + ledger
  status flip (`enforced, untested` at minimum) once someone builds it.
