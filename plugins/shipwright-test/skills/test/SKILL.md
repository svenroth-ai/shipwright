---
name: shipwright-test
description: "Profile-aware test runner. Runs unit tests, smoke tests, Playwright E2E, and optional security scans.\nTRIGGER when: user wants to run tests, execute test suite, check if tests pass, run unit tests, run E2E tests, run integration tests, verify test results, check design fidelity, visual comparison, compare UI with mockup, verify against design, run visual tests, or fix failing tests.\nDO NOT TRIGGER when: user asks to write new code or implement a section (/shipwright-build), fix a bug by changing code (/shipwright-iterate), deploy (/shipwright-deploy), create requirements (/shipwright-project), plan implementation (/shipwright-plan), or design UI (/shipwright-design)."
license: MIT
compatibility: Requires uv (Python 3.11+). Optional: Playwright.
---

# Shipwright Test Skill

Profile-aware test execution across all test layers.

> **How invoked:** directly via `/shipwright-test [--fix|--e2e-only|--design-fidelity|--report-boundary-coverage]`, or by `/shipwright-run` (orchestrator).

## Step Index — Where the prose lives

| Section | Reference |
|---|---|
| First Actions (A. Banner / B. Detect Profile / B2. Mode / B3. Context / B4. Prereqs / C. Strategy) | [first-actions](references/first-actions.md) · [prerequisite-self-healing](references/prerequisite-self-healing.md) |
| Step 0: Phase Session Context Recovery | [step-0-phase-session](references/step-0-phase-session.md) |
| Step 1: Run Unit Tests | [step-1-unit-tests](references/step-1-unit-tests.md) |
| Step 1.5: Run Integration Tests | [step-1.5-integration-tests](references/step-1.5-integration-tests.md) |
| Step 1.6: Run pgTAP Database Tests | [step-1.6-pgtap-tests](references/step-1.6-pgtap-tests.md) |
| Step 2: Run Smoke Test | [step-2-smoke-test](references/step-2-smoke-test.md) |
| Step 2.5: Generate E2E Specs from Plan | [step-2.5-e2e-spec-generation](references/step-2.5-e2e-spec-generation.md) |
| Step 3: Run Playwright E2E | [step-3-playwright-e2e](references/step-3-playwright-e2e.md) |
| Step 3.5: E2E Results Verification | [step-3.5-e2e-verification](references/step-3.5-e2e-verification.md) |
| Step 3.6: Cross-Page UI Consistency Check | [step-3.6-ui-consistency](references/step-3.6-ui-consistency.md) |
| Step 3.7: Design Fidelity Verification | [step-3.7-design-fidelity](references/step-3.7-design-fidelity.md) |
| Step 3.8: Performance Budget Check | [step-3.8-performance-budget](references/step-3.8-performance-budget.md) |
| Step 3.9: Stop Dev Server (always — finally-block) | [step-3.9-stop-dev-server](references/step-3.9-stop-dev-server.md) |
| Step 3.95: Boundary Coverage Report | [step-3.95-boundary-coverage](references/step-3.95-boundary-coverage.md) |
| Step 4: Security Scan -> /shipwright-security | [step-4-security](references/step-4-security.md) |
| Step 5: Report Results | [step-5-report-results](references/step-5-report-results.md) · [results-enforcement](references/results-enforcement.md) · [completion-gate](references/completion-gate.md) |
| Anti-Rationalization | [anti-rationalization](references/anti-rationalization.md) |
| Test layers strategy (legacy) | [test-layers](references/test-layers.md) |
| Reflection | [reflection](references/reflection.md) |

---

## CRITICAL: First Actions

**Governing rules:** Read and follow `shared/constitution.md` (ALWAYS / ASK FIRST / NEVER boundaries).

### A. Print Intro Banner

```
================================================================================
SHIPWRIGHT-TEST: Test Runner
================================================================================
Runs tests across all layers based on stack profile.

Usage: /shipwright-test
   or: /shipwright-test --fix        (auto-fix failures, max 3 retries)
   or: /shipwright-test --e2e-only   (only Playwright E2E)
   or: /shipwright-test --design-fidelity  (only design fidelity check)
   or: /shipwright-test --report-boundary-coverage  (audit Affected Boundaries declarations across iterate-specs, ADR-027)
   or: Invoked by /shipwright-run (orchestrator)

Test layers:
  1.  Unit tests (Vitest / pytest)
  1.5 Integration tests (if profile has testing.integration)
  1.6 pgTAP database tests (if supabase/tests/database/ exists)
  2.  Smoke test (HTTP 200 on DEV URL)
  3.  Playwright E2E (if UI project + DEV URL available)
  3.6 Cross-page consistency (if .shipwright/designs/visual-guidelines.md exists)
  3.7 Design fidelity (if .shipwright/designs/screen-routes.json exists)
  3.8 Performance budget (if profile has testing.performance.enabled)
  3.9 Stop dev server (always, finally-block — runs even if 3.7 / 3.8 failed)
  4.  Security scan → out-of-band; see /shipwright-security (not auto-invoked)
================================================================================
```

### B. Detect Profile

Read `shipwright_project_config.json` from project root and load profile from
`{plugin_root}/../../shared/profiles/{profile}.json`. If no config, detect from
`package.json` / `pyproject.toml`. Full detection rules: see
[first-actions](references/first-actions.md).

### B2. Detect Invocation Mode

Pipeline mode (`shipwright_run_config.json.status == "in_progress"` AND
`current_step == "test"`) vs standalone. Standalone runs add
`"mode": "standalone"` to `shipwright_test_results.json` and skip pipeline
state updates. Out-of-sequence pipeline state requires ASK before continuing.
Full rules: see [first-actions](references/first-actions.md).

### B3. Load Project Context

Read `.shipwright/agent_docs/architecture.md` and previous
`shipwright_test_results.json`. Missing files: skip silently.

### B4. Prerequisite Self-Healing

Auto-generate missing `dev_url`, `.shipwright/designs/visual-guidelines.md`,
`.shipwright/designs/screen-routes.json`, `.shipwright/planning/claude-plan-e2e.md`,
and `playwright.config.ts` where source data exists. Full rules and per-artifact
commit hints: see [prerequisite-self-healing](references/prerequisite-self-healing.md).

### C. Determine Test Strategy

Based on profile:

| Profile | Unit Runner | E2E | Smoke URL Pattern |
|---------|------------|-----|-------------------|
| `supabase-nextjs` | `npx vitest run` | Playwright | `http://localhost:3000` |
| (future) | configurable | configurable | configurable |

---

## Step 0: Phase Session Context Recovery

If your context contains `=== SHIPWRIGHT-PIPELINE-CONTEXT ===`, parse
`phaseTaskId` and run `get_phase_context.py` as the first action.
Full body: see [step-0-phase-session](references/step-0-phase-session.md).

## Step 1: Run Unit Tests

```bash
uv run "{plugin_root}/scripts/lib/test_runner.py" --profile "{profile}" --layer unit
```

Autonomous mode auto-applies `--fix` behavior. Max 3 retries, structured
debugging (root cause -> pattern check -> hypothesis -> fix -> re-run).
Full body: see [step-1-unit-tests](references/step-1-unit-tests.md).

## Step 1.5: Run Integration Tests

Skip if no `testing.integration` profile config OR `tests/integration/` missing.
CI: missing env vars = FAIL; locally: skip with warning. Fast-fail on
`ECONNREFUSED`/`ETIMEDOUT` and on >50% simultaneous failure. Never auto-fix by
weakening RLS, swapping to service-role, or disabling URL safety.
Full body: see [step-1.5-integration-tests](references/step-1.5-integration-tests.md).

## Step 1.6: Run pgTAP Database Tests

Skip if `supabase/tests/database/` missing. Run via `supabase test db` or the
shared `test_runner.py --layer pgtap`. Autofix as for integration.
Full body: see [step-1.6-pgtap-tests](references/step-1.6-pgtap-tests.md).

## Step 2: Run Smoke Test (if DEV URL available)

```bash
uv run "{shared_root}/scripts/smoke_test.py" --url "{dev_url}" --timeout 10 --health-path "/api/health"
```

DEV URL sources (in order): `shipwright_build_config.json.dev_url` ->
`SHIPWRIGHT_DEV_URL` env -> `http://localhost:3000` default.
The smoke-test script is shared (`{shared_root}/scripts/smoke_test.py`), not a
project file. On failure: diagnose, autonomous fix, retry, then ASK after 2.
Full body: see [step-2-smoke-test](references/step-2-smoke-test.md).

## Step 2.5: Generate E2E Specs from Plan (if missing)

Skip if `e2e/` already has `.spec.ts` files, or profile has no UI. Otherwise
scan `.shipwright/planning/` for `claude-plan-e2e.md` and generate
`e2e/flows/*.spec.ts`, `e2e/pages/*.page.ts`, `e2e/fixtures/*`, and
`e2e/fixtures/auth.setup.ts`. Full body and structure: see
[step-2.5-e2e-spec-generation](references/step-2.5-e2e-spec-generation.md).

## Step 3: Run Playwright E2E (if applicable)

Prereqs: UI profile + smoke test passed. Run `playwright_setup.py`,
`dev_server.py start`, then `playwright_runner.py --cwd {project_root}`.
Auto-fix groups failures by root cause (auth / selector / data / network /
other), fixes per group with commits, parks unresolvable groups after 3
attempts and ASKs the user.
Full body: see [step-3-playwright-e2e](references/step-3-playwright-e2e.md).

## Step 3.5: E2E Results Verification

Read `e2e-results.json` (Playwright authoritative). Filter to the `chromium`
project (exclude `setup`). Reconcile `shipwright_test_results.json.e2e` with
Playwright's `expected + unexpected + skipped`, write an
`e2e_verification_note` if divergent, and verify `playwright-report/index.html`.
Full body: see [step-3.5-e2e-verification](references/step-3.5-e2e-verification.md).

## Step 3.6: Cross-Page UI Consistency Check (if applicable)

Runs if `.shipwright/designs/visual-guidelines.md` exists AND profile has UI
(`component_library` set), or standalone via `--consistency`. Non-blocking
(WARNING). Outliers are grouped by Spacing / Components / Colors root cause and
fixed with per-group commits, max 3 retries per category.
Full body: see [step-3.6-ui-consistency](references/step-3.6-ui-consistency.md).

## Step 3.7: Design Fidelity Verification — Regressions-Only (if applicable)

Runs if `.shipwright/designs/screen-routes.json` exists, or standalone via
`--design-fidelity`. Non-blocking (WARNING). Triages `needs_review` screens
against `design-fidelity-report.json` into Resolved / Regression / Persistent
Failure / Unchecked. Deep-reviews flagged screens against 5 dimensions, max
3 retries each.
Full body: see [step-3.7-design-fidelity](references/step-3.7-design-fidelity.md).

## Step 3.8: Performance Budget Check (if applicable)

Runs if `profile.testing.performance.enabled: true` OR
`shipwright_test_config.json.performance.enabled: true`. Lighthouse via
Playwright Chromium; bundle measurement = gzip-compressed `*.js`/`*.css` in
`build_output_dir`. Gate `warn` (default) vs `block` (opt-in).
Override precedence: `--gate` -> `shipwright_test_config.json.performance` ->
profile -> defaults (LH 85, bundle 250 KB gz, LCP 2500 ms, gate warn).
Full body: see [step-3.8-performance-budget](references/step-3.8-performance-budget.md).

## Step 3.9: Stop Dev Server (always — finally-block semantics)

**Run unconditionally as a cleanup pass — even if Step 3.7 or Step 3.8
raised or failed.** A blocked test phase is recoverable; a zombie dev server
bound to the dev port is not.

```bash
uv run "{plugin_root}/../../shared/scripts/dev_server.py" stop --cwd {project_root}
```

Full body: see [step-3.9-stop-dev-server](references/step-3.9-stop-dev-server.md).

## Step 3.95: Boundary Coverage Report (if --report-boundary-coverage)

Runs only when invoked with `--report-boundary-coverage` OR
`shipwright_test_config.json.boundary_coverage.enabled: true`. Audit hook for
ADR-024. Scans `.shipwright/planning/iterate/**/*.md` for `## Affected
Boundaries`, correlates against `shipwright_events.jsonl`, writes coverage
summary + drift signals. Non-blocking (WARNINGs in test summary).
Full body: see [step-3.95-boundary-coverage](references/step-3.95-boundary-coverage.md).

## Step 4: Security Scan → /shipwright-security

Security scanning runs **out-of-band**; `/shipwright-run` does NOT auto-invoke
it (decoupled in iterate `sec-report-and-orchestrator-decouple`, 2026-04).
This step is a no-op in shipwright-test.
Full body: see [step-4-security](references/step-4-security.md).

## Step 5: Report Results

Print the SHIPWRIGHT-TEST RESULTS summary (unit / integration / pgTAP / smoke /
e2e / consistency / design fidelity / performance / security / overall) and the
preview banner when the profile has UI. Capture learnings into
`conventions.md#Learnings`. Record `test_run` + `phase_completed` events,
update build dashboard, write canon-marker handoff, append `phase_history`,
then mark the test step complete via the orchestrator.

Per-layer enforcement: see [results-enforcement](references/results-enforcement.md).
Completion gate (every layer must have an explicit result): see
[completion-gate](references/completion-gate.md).
Full body: see [step-5-report-results](references/step-5-report-results.md).

---

## Anti-Rationalization

See [anti-rationalization](references/anti-rationalization.md) — the table of
common rationalizations ("Tests pass = correct", "E2E flaky = ignore",
"We'll add more later", etc.) and the reality check for each.
