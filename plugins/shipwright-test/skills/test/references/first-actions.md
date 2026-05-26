# First Actions (CRITICAL)

**Governing rules:** Read and follow `shared/constitution.md` (ALWAYS / ASK FIRST / NEVER boundaries).

## A. Print Intro Banner

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
  4.  Security scan -> out-of-band; see /shipwright-security (not auto-invoked)
================================================================================
```

## B. Detect Profile

Read `shipwright_project_config.json` from project root:
```json
{
  "profile": "supabase-nextjs",
  ...
}
```

Load profile from `{plugin_root}/../../shared/profiles/{profile}.json`.

If no config: detect from package.json / pyproject.toml.

## B2. Detect Invocation Mode

Determine if running within the pipeline or standalone:

1. Read `shipwright_run_config.json` (if exists)
2. **Pipeline mode**: `status == "in_progress"` AND `current_step == "test"`
   - Full pipeline integration (update orchestrator state, enforce gates)
3. **Standalone mode**: file missing OR `status == "complete"` OR `current_step != "test"`
   - Skip pipeline state updates (no `orchestrator.py update-step` calls)
   - Skip upstream completion checks
   - Still produce all artifacts (`shipwright_test_results.json`, event log)
   - **Mark artifacts**: When writing `shipwright_test_results.json`, add `"mode": "standalone"` at the top level. This tells the pipeline validator to ignore standalone results and require a fresh pipeline test run.
   - Print: `"Running in standalone mode — pipeline state will not be updated."`
4. If `status == "in_progress"` AND `current_step != "test"`:
   - Warn: `"Pipeline is in progress at step {current_step}. Running /shipwright-test out of sequence may cause issues."`
   - Ask user before continuing.

Store the detected mode in a variable `invocation_mode` = `"pipeline"` | `"standalone"` for use in later steps.

## B3. Load Project Context

Read these files for app context before running tests:

1. `.shipwright/agent_docs/architecture.md` — app structure (understand what to test)
2. `shipwright_test_results.json` — previous test state (if exists, for comparison)

If a file does not exist, skip it silently.

## B4. Prerequisite Self-Healing

See [prerequisite-self-healing.md](prerequisite-self-healing.md) for the full
auto-generation flow (missing dev_url, visual-guidelines.md, screen-routes.json,
E2E plan, playwright.config.ts).

## C. Determine Test Strategy

Based on profile:

| Profile | Unit Runner | E2E | Smoke URL Pattern |
|---------|------------|-----|-------------------|
| `supabase-nextjs` | `npx vitest run` | Playwright | `http://localhost:3000` |
| (future) | configurable | configurable | configurable |
