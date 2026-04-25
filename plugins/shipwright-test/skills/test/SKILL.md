---
name: shipwright-test
description: "Profile-aware test runner. Runs unit tests, smoke tests, Playwright E2E, and optional security scans.\nTRIGGER when: user wants to run tests, execute test suite, check if tests pass, run unit tests, run E2E tests, run integration tests, verify test results, check design fidelity, visual comparison, compare UI with mockup, verify against design, run visual tests, or fix failing tests.\nDO NOT TRIGGER when: user asks to write new code or implement a section (/shipwright-build), fix a bug by changing code (/shipwright-iterate), deploy (/shipwright-deploy), create requirements (/shipwright-project), plan implementation (/shipwright-plan), or design UI (/shipwright-design)."
license: MIT
compatibility: Requires uv (Python 3.11+). Optional: Playwright.
---

# Shipwright Test Skill

Profile-aware test execution across all test layers.

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
   or: Invoked by /shipwright-run (orchestrator)

Test layers:
  1.  Unit tests (Vitest / pytest)
  1.5 Integration tests (if profile has testing.integration)
  1.6 pgTAP database tests (if supabase/tests/database/ exists)
  2.  Smoke test (HTTP 200 on DEV URL)
  3.  Playwright E2E (if UI project + DEV URL available)
  3.6 Cross-page consistency (if designs/visual-guidelines.md exists)
  4.  Design fidelity (if designs/screen-routes.json exists)
  5.  Security scan → see /shipwright-security
================================================================================
```

### B. Detect Profile

Read `shipwright_project_config.json` from project root:
```json
{
  "profile": "supabase-nextjs",
  ...
}
```

Load profile from `{plugin_root}/../../shared/profiles/{profile}.json`.

If no config: detect from package.json / pyproject.toml.

### B2. Detect Invocation Mode

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

**Hook auto-install**: If `shipwright_run_config.json` exists but `.claude/settings.json` does not contain the `UserPromptSubmit` hook for `suggest_iterate.py`, install it now (one-time, idempotent).

Store the detected mode in a variable `invocation_mode` = `"pipeline"` | `"standalone"` for use in later steps.

### B3. Load Project Context

Read these files for app context before running tests:

1. `agent_docs/architecture.md` — app structure (understand what to test)
2. `shipwright_test_results.json` — previous test state (if exists, for comparison)

If a file does not exist, skip it silently.

### B4. Prerequisite Self-Healing

Before determining test strategy, check for missing artifacts and auto-generate where possible.
This follows the constitution rule: **never silently skip a test layer due to missing prerequisites.**

**1. `dev_url` missing from `shipwright_build_config.json`?**
   - Search `CLAUDE.md` for `PORT=` references or port numbers
   - Search `package.json` scripts for `--port` flags
   - If found: add `"dev_url": "http://localhost:{port}"` to `shipwright_build_config.json`
   - If not found: **ASK** user "What port does your dev server run on?"

**2. `designs/visual-guidelines.md` missing but `designs/screens/` has HTML files?**
   - Read CSS `:root` variables from the first mockup HTML file
   - Extract color, typography, spacing, radius, and shadow tokens
   - Generate `designs/visual-guidelines.md` using the template format
   - Commit: `chore(test): auto-generate visual-guidelines.md from mockup CSS`

**3. `designs/screen-routes.json` missing but mockups + router exist?**
   - List mockup HTML files in `designs/screens/`
   - Read router config (`src/router.tsx`, `src/App.tsx`, or framework equivalent)
   - Generate `designs/screen-routes.json` mapping each mockup to its route
   - Commit: `chore(test): auto-generate screen-routes.json from mockups + router`

**4. `planning/claude-plan-e2e.md` missing but `designs/screen-routes.json` exists?**
   - Generate a minimal E2E test plan with one flow per major screen/route
   - Include page object model suggestions and test data structure
   - Commit: `chore(test): auto-generate E2E test plan from screen routes`

**5. `playwright.config.ts` missing?**
   - Run `playwright_setup.py` (creates config, installs browser)
   - If `dev_url` was resolved in step 1: substitute the correct port in the config

**Print diagnostic summary:**
```
PREREQUISITE CHECK:
  dev_url:             ✓ http://localhost:3847 (from CLAUDE.md)
  visual-guidelines:   ✓ auto-generated from mockup CSS
  screen-routes.json:  ✓ auto-generated (11 screens → 5 routes)
  E2E test plan:       ✓ auto-generated (6 flows)
  playwright.config:   ✓ created with port 3847
```

Only **ASK** the user if auto-generation is not possible (no source data to derive from).
Each auto-generated artifact gets its own commit.

### C. Determine Test Strategy

Based on profile:

| Profile | Unit Runner | E2E | Smoke URL Pattern |
|---------|------------|-----|-------------------|
| `supabase-nextjs` | `npx vitest run` | Playwright | `http://localhost:3000` |
| (future) | configurable | configurable | configurable |

---

## Step 0: Phase Session Context Recovery

If your context contains a `=== SHIPWRIGHT-PIPELINE-CONTEXT ===` block (injected
by the SessionStart hook), you are part of an active `/shipwright-run` pipeline.
Parse `phaseTaskId` from that block and run as your very first action:

```bash
uv run ${SHIPWRIGHT_PLUGIN_ROOT}/../../shared/scripts/tools/get_phase_context.py \
  --phase-task-id <phaseTaskId-from-context>
```

The tool prints structured JSON with `runId`, `phase`, `splitId`, `prerequisites`,
`runConditions`, and a `skill_artifacts_to_read` list. Read those artifacts
before proceeding so this phase session has full context for what came before.

If NO `PIPELINE-CONTEXT` block is present, this is a standalone invocation —
continue with Step 1 below as normal.

---

## Step 1: Run Unit Tests

```bash
uv run {plugin_root}/scripts/lib/test_runner.py \
  --profile "{profile}" \
  --layer unit
```

**Expected output:** Test results with pass/fail counts.

**Autonomous mode** (check `autonomy` in `shipwright_run_config.json`):
If tests fail, automatically apply --fix behavior (structured debugging,
up to 3 retries) without requiring the explicit --fix flag.

**Guided mode:** Only attempt fixes if `--fix` flag was explicitly passed.

**Fix behavior** (max 3 retries, structured debugging):
1. **Root cause:** Read error output, identify what's failing and why
2. **Pattern check:** Same root cause as previous attempt? → Change approach, don't retry same fix
3. **Hypothesis:** State what you'll change and why before editing
4. Attempt targeted fix based on hypothesis
5. Re-run tests
6. After 3 retries (or 2 with same root cause): report remaining failures with diagnosis

---

## Step 1.5: Run Integration Tests

**Skip if:** Profile has no `testing.integration` config, OR `tests/integration/` directory does not exist.

**Check prerequisites:**
1. Read profile `testing.integration` block
2. Verify env vars from `.env.test`: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
3. Verify URL is localhost/127.0.0.1 (safety check)
4. **In CI:** Missing env vars = FAIL (not skip). **Locally:** Missing env vars = skip with warning.

**Run integration tests:**
```bash
npx vitest run --config vitest.integration.config.ts
```

Or via runner script:
```bash
uv run {plugin_root}/scripts/lib/test_runner.py \
  --profile "{profile}" \
  --layer integration \
  --cwd {project_root} \
  --skip-if-missing
```

**Autofix behavior:** Same structured debugging as unit tests (root cause → hypothesis → fix → re-run), max 3 retries.

**Fast-fail rules:**
- If error matches `ECONNREFUSED`, `ETIMEDOUT`, `connect ENOENT` → skip autofix, fail immediately with infrastructure diagnosis
- If >50% of integration tests fail simultaneously → skip autofix, fail with diagnosis (likely global issue, not individual test bugs)

**Never auto-fix by:**
- Weakening RLS policies
- Switching test assertions to use service-role client
- Disabling URL safety checks

**Common auto-fixable patterns:**

| Error Pattern | Diagnosis | Auto-fix |
|---|---|---|
| `relation "x" does not exist` | Migration not applied | Run `supabase db push --linked` |
| `permission denied for table` | RLS policy issue | Check auth context setup in test |
| `null value in column "x"` | Test data setup incomplete | Fix `beforeAll` / seed data |
| `duplicate key value` | Previous cleanup failed | Fix `afterAll` cleanup |
| Auth sign-in failure | Test user not provisioned | Create test user or check credentials |

**Record results:**
- `integration_passed`: number of passing tests
- `integration_total`: total tests
- `integration_duration_s`: duration in seconds
- If skipped: `integration_skipped: true`, `integration_skip_reason: "..."`

---

## Step 1.6: Run pgTAP Database Tests

**Skip if:** `supabase/tests/database/` directory does not exist.

**Run pgTAP tests:**
```bash
supabase test db
```

Or via runner script:
```bash
uv run {plugin_root}/scripts/lib/test_runner.py \
  --profile "{profile}" \
  --layer pgtap \
  --cwd {project_root} \
  --skip-if-missing
```

**Autofix:** Same as integration tests (structured debugging, max 3 retries).

**Record results:**
- `pgtap_passed` / `pgtap_total` / `pgtap_duration_s`
- If skipped: `pgtap_skipped: true`, `pgtap_skip_reason: "no supabase/tests/database/ directory"`

---

## Step 2: Run Smoke Test (if DEV URL available)

```bash
uv run {shared_root}/scripts/smoke_test.py \
  --url "{dev_url}" \
  --timeout 10 \
  --health-path "/api/health"
```

**DEV URL sources (in order):**
1. `shipwright_build_config.json` → `dev_url`
2. Environment variable `SHIPWRIGHT_DEV_URL`
3. Default: `http://localhost:3000`

If no DEV URL and app not running: skip with note.

**Note:** The smoke test script is a **shared plugin script** (`{shared_root}/scripts/smoke_test.py`),
not a project file. Do NOT search for smoke test files in the project directory.

**If smoke test fails (any reason) — diagnose before skipping:**
1. **Diagnose:** Read error output, identify root cause
2. **Attempt autonomous fix** based on diagnosis. Examples:
   - Connection refused → check if dev server is running, start/restart it
   - HTTP error (non-200) → check app logs, report to user (real app bug)
   - Timeout → increase timeout, retry
   - Process hung → kill stale process, restart
3. **Retry** smoke test after fix
4. After 2 failed fix attempts: **ASK user** how to proceed

---

## Step 2.5: Generate E2E Specs from Plan (if missing)

**Goal:** Implement Playwright E2E test specs from the E2E test plans generated by `/shipwright-plan`.

**Skip this step if:**
- `e2e/` directory already contains `.spec.ts` files (specs exist from previous run or manual creation)
- Profile has no UI (backend-only, CLI tool, library)

**Flow:**

1. **Check for existing specs:**
```bash
find e2e/ -name "*.spec.ts" -type f 2>/dev/null | head -1
```
If any `.spec.ts` file found → skip with note: "E2E specs already exist."

2. **Find E2E test plans:**
```bash
find planning/ -name "claude-plan-e2e.md" -type f 2>/dev/null
```
If no plans found → skip with note: "No E2E test plans found in planning/."

3. **Generate specs from plans:**
For each `claude-plan-e2e.md` found:
   - Read the plan file (contains user flows, page objects, test data)
   - Generate Playwright test specs following the plan's scenarios
   - Place specs in `e2e/flows/NN-flow-name.spec.ts`
   - Generate Page Object Models in `e2e/pages/*.page.ts`
   - Generate test fixtures/seed data in `e2e/fixtures/test-data.ts`
   - Create `e2e/fixtures/auth.setup.ts` for authenticated test state (if auth flows in plan)

4. **Structure:**
```
e2e/
  flows/
    01-auth.spec.ts           # Auth flows (login, signup, logout)
    02-courses.spec.ts        # Course browsing and enrollment
    03-downloads.spec.ts      # Download hub flows
    04-payments.spec.ts       # Purchase and billing flows
    ...
  pages/
    home.page.ts              # Page Object: Home page
    course-detail.page.ts     # Page Object: Course detail
    login.page.ts             # Page Object: Login page
    ...
  fixtures/
    test-data.ts              # Seed data for E2E tests
    auth.setup.ts             # Playwright auth state setup
  browser-verify.ts           # Existing browser verify (unchanged)
```

5. **Guidelines for spec generation:**
   - Each flow from the plan maps to one `.spec.ts` file
   - Use Playwright `test.describe()` to group related flows
   - Use Page Object Model pattern for element selectors
   - Use `test.beforeAll()` for auth setup where needed
   - Respect `playwright.config.ts` settings (base URL, browser, timeouts)
   - Tests must be runnable against the dev server (localhost)
   - Use `test.skip()` for flows that require external services (e.g., Stripe Checkout redirect)
   - If `designs/visual-guidelines.md` exists, generate basic visual assertion tests in `e2e/flows/00-visual.spec.ts`:
     - Check brand colors on key elements (header, CTA buttons, links)
     - Check font-family on body/headings
     - Check page background color

**Checkpoint:** `e2e/flows/` contains at least one `.spec.ts` file.

---

## Step 3: Run Playwright E2E (if applicable)

**Prerequisites:**
- Profile has UI (e.g., `supabase-nextjs`)
- DEV URL is accessible (smoke test passed)

**Flow:**

1. **Ensure Playwright is set up:**
```bash
uv run {plugin_root}/../../shared/scripts/playwright_setup.py --cwd {project_root}
```

2. **Ensure dev server is running:**
```bash
uv run {plugin_root}/../../shared/scripts/dev_server.py start --profile {profile} --cwd {project_root}
```

3. **Run E2E tests:**
```bash
uv run {plugin_root}/scripts/lib/playwright_runner.py --cwd {project_root}
```

4. **Evaluate results:**
   - Parse the JSON output for pass/fail/skip counts
   - If all passed: continue to Step 4
   - If failures and `--fix` flag active: invoke auto-fix

5. **Auto-fix mode** (autonomous mode or `--fix` flag):

   **Group failures by root cause** before fixing:
   - Auth/login failures (e.g., loginAs timeout, missing credentials)
   - Selector mismatches (e.g., getByRole not found, wrong label)
   - Missing data (e.g., no test courses, empty tables)
   - Connection/timeout issues
   - Other

   **For each root-cause group:**
   a. Diagnose the group's common root cause
   b. If screenshots exist for failed tests, read them for visual context
   c. Apply a single fix addressing the group (e.g., fix loginAs helper → fixes all auth tests)
   d. Re-run only the tests in this group: `npx playwright test --grep "{pattern}"`
   e. If fix works: **commit the fix**, move to next group
   f. If same root cause persists after 3 attempts on this group: **park it**, move to next group
   
   **After all groups attempted:**
   - Report summary: which groups fixed, which parked, with diagnosis per parked group
   - **ASK user** for direction on parked groups (one consolidated dialog, not per group)
   
   **Commit between fix rounds** — each successful group fix gets its own commit
   to prevent losing progress on session interruption.

6. Dev server remains running for Design Fidelity (Step 3.7). Stopped there.

If no Playwright config exists and setup fails: skip with note.

**If E2E tests fail — diagnose before reporting:**
1. **Diagnose:** Read error output, identify root cause pattern across failures
2. **Attempt autonomous fix** based on diagnosis. Examples:
   - Auth/login failures → run auth setup to seed test users (`npx playwright test --project=setup`)
   - Missing page elements → verify pages render, check selectors against actual DOM
   - Connection issues → verify dev server is running, check base URL config
   - Timeout → increase test timeout, check for slow-loading pages
   - Missing test data → check fixtures, seed required data
3. **Re-run failed tests only:** `npx playwright test --grep "{test_title}"`
4. After 2 failed fix attempts with same root cause: **ASK user** for direction

---

## Step 3.5: E2E Results Verification

After E2E tests complete, verify consistency across all result sources. This catches
miscounts from setup projects, retries, or skipped tests.

1. Read `e2e-results.json` (Playwright's authoritative output):
   - Parse `stats.expected`, `stats.unexpected`, `stats.skipped`, `stats.flaky`
   - Filter: only count tests from the `chromium` project (exclude `setup` project tests)
2. Compare against `shipwright_test_results.json` e2e counts:
   - `e2e.total` should match Playwright's `expected + unexpected + skipped` (chromium only)
   - `e2e.passed` should match `expected`
3. **If numbers diverge:**
   - Analyze WHY: setup project counted? Retries inflating counts? Skipped tests miscounted?
   - Fix `shipwright_test_results.json` to match Playwright's authoritative numbers
   - Add `"e2e_verification_note"` field documenting the discrepancy and resolution
4. **If numbers match:** proceed silently
5. Verify `playwright-report/index.html` exists — note path for compliance linking

---

## Step 3.6: Cross-Page UI Consistency Check (if applicable)

**Condition:** Runs if `designs/visual-guidelines.md` exists AND profile has UI config (`component_library` set). Also runs standalone via `--consistency` flag or alongside `--visual`.

**Purpose:** Detect cross-page UI inconsistencies that per-page mockup comparison cannot catch (e.g., mixed heading sizes, inconsistent spacing, different table wrappers across pages). Non-blocking (WARNING level).

**1. Run consistency analysis:**
```bash
uv run {plugin_root}/scripts/lib/ui_consistency_check.py \
  --cwd "{project_root}" \
  --guidelines "designs/visual-guidelines.md"
```

Parse JSON output: `passed`, `total`, `skipped`, `categories`, `root_cause_groups`.

**2. If all categories CONSISTENT:** Log result, proceed to Step 3.7.

**3. If INCONSISTENT categories found:**

Print outlier summary grouped by root cause (same taxonomy as design fidelity):

| Root Cause | Categories | Fix Scope |
|------------|-----------|-----------|
| **Spacing** | heading_hierarchy, spacing_patterns | Tailwind classes on page headings/containers |
| **Components** | component_patterns, form_patterns, interactive_patterns | Component imports, wrapper replacements |
| **Colors** | token_usage | Replace hardcoded colors with semantic tokens |

**Fix loop per root-cause group** (max 3 retries per group):
a. Read outlier details (file, line, found vs. expected)
b. Apply targeted fix (e.g., change `text-3xl` → `text-2xl`)
c. Re-run consistency check for that category: `--category {name}`
d. If fix works: commit with `fix(ui-consistency): normalize {category} across pages`
e. If same issue persists after 3 attempts: park with diagnosis

**4. Record results** in `shipwright_test_results.json`:
```json
{
  "consistency": {
    "passed": 4,
    "total": 6,
    "skipped": false,
    "skip_reason": "",
    "categories": { ... },
    "root_cause_groups": { ... }
  }
}
```

**5. Non-blocking:** Consistency issues produce WARNINGs, never hard-fail the pipeline.

---

## Step 3.7: Design Fidelity Verification — Regressions-Only (if applicable)

**Condition:** Runs if `designs/screen-routes.json` exists in the project root. Also runs standalone via `--design-fidelity` flag.

**Purpose:** Detect and fix design fidelity regressions introduced by later build sections (cross-section side effects). Build handles the bulk of fidelity checks per-section; Test is the safety net. Non-blocking (WARNING level) — fidelity differences don't fail the pipeline.

**1. Run structural extraction:**
```bash
uv run {plugin_root}/scripts/lib/design_fidelity_check.py \
  --cwd "{project_root}"
```

Parse the JSON output:
- `skipped: true` → no screen-routes.json, skip to step 6
- All screens `status: "pass"` → PASS, skip to step 5
- Some screens `status: "needs_review"` → proceed to triage

**2. Read build fidelity results:**
Read `design-fidelity-report.json` from the project root. Build a screen-status map: `{screen: status}`.
- If file is missing or fails to parse → **fallback**: treat all screens as unchecked (full analysis, backward-compatible).
- If `build_complete: false` → log WARNING ("Build may still be in progress"), proceed with triage anyway.

**3. Triage against build results:**

For each screen with `status: "needs_review"`, determine its category using `design-fidelity-report.json`:

| Category | Condition | Priority | Action |
|----------|-----------|----------|--------|
| **Resolved** | Screen was `partial` in Build, now auto-passes | Log only | Log as positive outcome |
| **Regression** | Screen was `full` in Build, now has failures | Prio 1 | Cross-section side effect — agent deep review |
| **Persistent Failure** | Screen was `partial` in Build, still fails | Prio 2 | Build gave up — one more try |
| **Unchecked** | Screen not in build report | Prio 3 | Never verified — full agent review |

**4. Agent deep review (for flagged screens):**

For each flagged screen:
a. Read the mockup HTML source at `{mockup_path}`
b. Read the implementation TSX source at `{implementation_files[0]}`
c. Compare against 5 dimensions: Layout Structure, Component Order, Component Types, Card Patterns, shadcn Rules
d. If mismatches found: fix implementation, run unit tests, commit: `fix(test-fidelity): {description}`
e. Re-run `design_fidelity_check.py --screen {screen}` to verify fix
f. Max 3 retries per screen; if unresolvable: park with diagnosis

**After all screens attempted:**
- Report summary: which screens fixed, which parked, with diagnosis per parked screen
- **ASK user** for direction on parked screens (one consolidated dialog)
- **Commit between fix rounds** — each fix gets its own commit

**5. Record results** in `shipwright_test_results.json`:
```json
{
  "design_fidelity": {
    "passed": N,
    "total": N,
    "skipped": false,
    "screens": [
      {"mockup": "01-login.html", "route": "/login", "status": "pass"},
      {"mockup": "08-dashboard.html", "route": "/dashboard", "status": "needs_review"}
    ],
    "triage": {
      "regressions": 1,
      "persistent_failures": 0,
      "unchecked": 0,
      "resolved": 2
    }
  }
}
```

**6. Stop dev server** (always — whether design fidelity ran or was skipped):
```bash
uv run {plugin_root}/../../shared/scripts/dev_server.py stop --cwd {project_root}
```

---

## Step 4: Security Scan → /shipwright-security

Security scanning is handled by the dedicated `/shipwright-security` plugin (Aikido integration).

- Standalone: `/shipwright-security`
- Pipeline: Automatically called after test by `/shipwright-run` (if `AIKIDO_CLIENT_ID` is set)

This step is a no-op in shipwright-test.

---

## Step 5: Report Results

**Print Summary:**
```
================================================================================
SHIPWRIGHT-TEST RESULTS
================================================================================
Unit tests:    {passed}/{total} passed ({duration}s)
Integration:   {passed}/{total} passed ({duration}s) | SKIP: {reason}
pgTAP:         {passed}/{total} passed ({duration}s) | SKIP: {reason}
Smoke test:    {PASS | FAIL | SKIP} ({url}, {response_time}ms)
E2E tests:     {passed}/{total} passed | SKIP
Consistency:   {passed}/{total} categories consistent | SKIP
Design fidelity: {passed}/{total} checked | SKIP
Security:      {via /shipwright-security | not run}

Overall:       {PASS | FAIL}
{Failed tests: list if any}
================================================================================
```

**If profile has UI** (component_library set, or client-side framework detected):
```
================================================================================
  Verify visually:  /shipwright-preview
  Preview URL:      {dev_url from shipwright_build_config.json}
================================================================================
```

If `--fix` was used:
```
Auto-fix attempts: {N}
Fixed: {list of fixed tests}
Remaining failures: {list}
```

### Results Enforcement

Test results determine pipeline continuation:

| Layer | On FAIL | Rationale |
|-------|---------|-----------|
| **Unit tests** | **Pipeline stops** (blocking) | Unit tests are deterministic — failure = real bug |
| **Integration tests** | Autofix (3 retries, fast-fail for infra), then blocking | Deterministic against real DB |
| **pgTAP tests** | Autofix (3 retries), then blocking | Schema-level verification |
| **Smoke test** | **Pipeline stops** (blocking) | App not running = can't deploy |
| **E2E tests** | **Warning only** (non-blocking) | E2E can be flaky; log failures but continue |
| **Consistency** | **Warning only** (non-blocking) | Cross-page cosmetic issues don't gate deployment |
| **Design fidelity** | **Warning only** (non-blocking) | Fidelity divergence ≠ broken functionality |

If unit tests, integration tests, pgTAP tests, or smoke test FAIL: set phase status to `FAIL` and inform user. Do NOT proceed to deploy.

### Completion Gate

Before marking the test phase complete, ALL test layers must have an explicit result:

| Layer | Required Result |
|-------|----------------|
| Unit tests | `pass` or `fail` (always required) |
| Integration tests | `pass`, `fail`, or `skipped: {reason}` |
| pgTAP tests | `pass`, `fail`, or `skipped: {reason}` |
| Smoke test | `pass`, `fail`, or `skipped: {reason}` |
| E2E tests | `pass`, `fail`, or `skipped: {reason}` |
| Consistency | `pass`, `warning`, or `skipped: {reason}` |
| Design fidelity | `pass`, `fail`, or `skipped: {reason}` |

If any layer has NO result (was never executed and has no skip reason):
- **Do NOT mark test phase as complete**
- Print warning: "Test layer {layer} has no result. Run it or document skip reason."
- Set phase status to `incomplete`

Valid skip reasons:
- `skipped: no testing.integration config in profile` (Integration)
- `skipped: tests/integration/ directory does not exist` (Integration)
- `skipped: missing integration test env vars` (Integration, local only)
- `skipped: no supabase/tests/database/ directory` (pgTAP)
- `skipped: no DEV URL available` (Smoke + E2E)
- `skipped: no Playwright config` (E2E)
- `skipped: profile has no UI` (E2E)
- `skipped: smoke test failed` (E2E, because prerequisite not met)
- `skipped: no designs/visual-guidelines.md` (Consistency)
- `skipped: profile has no UI` (Consistency)
- `skipped: no screen-routes.json` (Design fidelity)

**Reflection — Capture Test Learnings** (before marking phase complete):

If test failures required investigation or fixes:
1. Flaky test patterns worth documenting?
2. Infrastructure quirks (timing, ports, browser drivers)?
3. Test strategy insights (missing coverage, better approaches)?

If learnings exist:
- **Observations** → append to `agent_docs/conventions.md` under `## Learnings`
  Format: `- ({YYYY-MM-DD}) test — {summary}`
- **Cross-project insights** → save Claude Code feedback/project Memory
If none: skip.

**Record test_run event** (always, even on failure — captures layer results):
```bash
uv run {shared_root}/scripts/tools/record_event.py \
  --project-root "$(pwd)" \
  --type test_run \
  --trigger "pipeline" \
  --unit-passed {unit_passed} \
  --unit-total {unit_total} \
  --e2e-passed {e2e_passed} \
  --e2e-total {e2e_total} \
  --smoke-status "{pass|fail|skip}"
```
Where `{shared_root}` = `{plugin_root}/../../shared`.

Omit `--e2e-passed`/`--e2e-total` if E2E was skipped. Omit `--smoke-status` if smoke was skipped.
Use `--trigger "iterate"` when invoked by `/shipwright-iterate`, `"manual"` when invoked standalone.

**Phase complete — update pipeline state** (only if Completion Gate passes):

Iterate 12.4 wires the test plugin into the Minimum Phase Completion
Canon at C1/C2/C3 only. **C4 is skipped by policy** — test runs are
events, not architectural decisions (both LLM reviewers flagged this
as CRITICAL). **C5 is also skipped** — test results live in
`shipwright_test_results.json`, not CHANGELOG.

```bash
# Derive a run id if the orchestrator didn't set one.
: "${SHIPWRIGHT_RUN_ID:=test-$(date +%Y%m%d-%H%M%S)}"
export SHIPWRIGHT_RUN_ID

# C1 — test_run event already recorded above.
# (The event-type is `test_run`, not `phase_completed`, but also emit
# a phase_completed event so the generic C1 verifier matches uniformly.)
uv run {shared_root}/scripts/tools/record_event.py \
  --project-root "$(pwd)" --type phase_completed --phase test \
  --detail "{unit_passed}/{unit_total} unit, {e2e_passed}/{e2e_total} e2e"

# C2 — delivery dashboard
uv run {shared_root}/scripts/tools/update_build_dashboard.py \
  --project-root "$(pwd)" --phase test --detail "{passed}/{total} passing" \
  --session-id "{SHIPWRIGHT_SESSION_ID}"

# C3 (NEW 12.4) — canon-marker handoff
uv run {shared_root}/scripts/tools/generate_session_handoff.py \
  --project-root "$(pwd)" --canon-marker --phase test \
  --reason "test complete: {unit_passed}/{unit_total} unit, {e2e_passed}/{e2e_total} e2e, smoke {smoke_status}"

# C4 — SKIPPED by policy (test is not a decision-taking phase).
# C5 — SKIPPED by policy (test results belong in shipwright_test_results.json,
#      not CHANGELOG).

# phase_history (NEW 12.4) — audit trail
uv run {shared_root}/scripts/tools/append_phase_history.py \
  --project-root "$(pwd)" --phase test --run-id "$SHIPWRIGHT_RUN_ID" \
  --entry-json '{"unit":"{unit_passed}/{unit_total}","e2e":"{e2e_passed}/{e2e_total}","smoke":"{smoke_status}","outcome":"passed"}'

# Mark test phase complete (triggers compliance update automatically).
# _validate_test() now runs the modular test_checks verifier (canon
# C1/C2/C3 + phase_history) in addition to the existing results-layer
# completion gate.
uv run {plugin_root}/../../plugins/shipwright-run/scripts/lib/orchestrator.py \
  update-step --project-root "$(pwd)" --step test --status complete
```

---

## Anti-Rationalization

Before accepting test results as sufficient, resist these justifications:

| Rationalization | Reality |
|---|---|
| "Tests pass, so the code is correct" | Tests are necessary but insufficient — they can't catch what they don't cover |
| "E2E tests are flaky, ignore failures" | Flaky tests hide real regressions. Fix the flakiness or investigate each failure |
| "We'll add more tests later" | Test debt compounds faster than code debt. Cover it now |
| "Manual testing is enough" | Manual testing doesn't run on every commit. Automated tests do |
| "100% coverage means no bugs" | Coverage measures execution, not correctness. A test that asserts nothing has coverage |

---

## Reference Documents

- [test-layers.md](references/test-layers.md) — Test layer overview and strategy
