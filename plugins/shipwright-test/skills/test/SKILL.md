---
name: shipwright-test
description: Profile-aware test runner. Runs unit tests, smoke tests, Playwright E2E, and optional security scans. Use after /shipwright-build or /shipwright-deploy.
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
   or: /shipwright-test --visual     (only visual comparison)
   or: Invoked by /shipwright-run (orchestrator)

Test layers:
  1.  Unit tests (Vitest / pytest)
  1.5 Integration tests (if profile has testing.integration)
  1.6 pgTAP database tests (if supabase/tests/database/ exists)
  2.  Smoke test (HTTP 200 on DEV URL)
  3.  Playwright E2E (if UI project + DEV URL available)
  3.6 Cross-page consistency (if designs/visual-guidelines.md exists)
  4.  Visual comparison (if designs/screen-routes.json exists)
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

### B2. Load Project Context

Read these files for app context before running tests:

1. `agent_docs/architecture.md` — app structure (understand what to test)
2. `shipwright_test_results.json` — previous test state (if exists, for comparison)

If a file does not exist, skip it silently.

### C. Determine Test Strategy

Based on profile:

| Profile | Unit Runner | E2E | Smoke URL Pattern |
|---------|------------|-----|-------------------|
| `supabase-nextjs` | `npx vitest run` | Playwright | `http://localhost:3000` |
| (future) | configurable | configurable | configurable |

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

6. Dev server remains running for Visual Comparison (Step 3.7). Stopped there.

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

Print outlier summary grouped by root cause (same taxonomy as visual comparison):

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

## Step 3.7: Visual Comparison — Regressions-Only (if applicable)

**Condition:** Runs if `designs/screen-routes.json` exists in the project root. Also runs standalone via `--visual` flag.

**Purpose:** Detect and fix visual regressions introduced by later build sections (cross-section side effects). Build handles the bulk of visual fixes per-section; Test is the safety net. Non-blocking (WARNING level) — visual differences don't fail the pipeline.

**1. Ensure dev server is running** (should be up from E2E step):
```bash
uv run {plugin_root}/../../shared/scripts/dev_server.py status --cwd {project_root}
```
If not running, start it:
```bash
uv run {plugin_root}/../../shared/scripts/dev_server.py start --profile {profile} --cwd {project_root}
```

**2. Read build visual results:**
Read `visual-build-report.json` from the project root. Build a screen-status map: `{screen: status}`.
- If file is missing or fails to parse → **fallback**: treat all screens as unchecked (full fix behavior, backward-compatible).
- If `build_complete: false` → log WARNING ("Build may still be in progress"), proceed with triage anyway.

**3. Run visual comparison (all screens):**
```bash
uv run {plugin_root}/scripts/lib/visual_compare.py \
  --cwd "{project_root}" \
  --base-url "http://localhost:{port}"
```

Parse the JSON output:
- `skipped: true` → no screen-routes.json, skip to step 7
- `passed == total` → all screens match, PASS, skip to step 6
- `passed < total` → mismatches found, proceed to triage

**4. Triage against build results:**

For each screen with visual mismatches, determine its category using `visual-build-report.json` screen status (NOT the script's `match` field — that only indicates screenshot capture success):

| Category | Condition | Priority | Action |
|----------|-----------|----------|--------|
| **Resolved** | Screen was `partial` in Build, now passes | Log only | Log as positive outcome, no fix needed |
| **Regression** | Screen was `full` in Build, now fails | Prio 1 | Cross-section side effect — fix loop |
| **Persistent Failure** | Screen was `partial` in Build, still fails | Prio 2 | Build gave up — one more try |
| **Unchecked** | Screen not in build report | Prio 3 | Never verified — full fix loop |

If a screen appears in multiple groups in the build report: status = worst-case (partial if in ANY parked group).

**5. Fix loop (Regressions + Persistent Failures + Unchecked only):**

Group failures by root cause (identical taxonomy to Build):

| Root Cause | Example | Fix Scope |
|------------|---------|-----------|
| **Layout structure** | Sidebar vs header, missing nav sections | Layout components, shell |
| **Colors/typography** | Wrong primary color, font-family | globals.css, CSS variables |
| **Missing components** | No logo, no stats section, no CTA | Individual pages/components |
| **Spacing/shadows/radius** | Wrong padding, no card shadow | Tailwind classes, globals.css |

Fix loop per group (max 3 retries per group):

a. Read both mockup screenshot + live screenshot for a representative screen in the group
b. Identify specific CSS/layout/component divergences
c. Fix source files (components, globals.css, layout.tsx, page.tsx)
d. Rebuild app: `npm run build` (production) or wait for dev server HMR
e. Re-run `visual_compare.py` for this group's screens
f. If fix works: **commit the fix** with message `fix(test-visual): {description}`, move to next group
g. If same issue persists after 3 attempts on this group: **park it** with diagnosis, move to next group

**After all groups attempted:**
- Report summary: which groups fixed, which parked, with diagnosis per parked group
- **ASK user** for direction on parked groups (one consolidated dialog, not per group)
- **Commit between fix rounds** — each successful group fix gets its own commit

**6. Record results** in `shipwright_test_results.json`:
```json
{
  "visual": {
    "passed": N,
    "total": N,
    "skipped": false,
    "comparisons": [
      {"mockup": "01-login.html", "route": "/login", "match": true},
      {"mockup": "08-dashboard.html", "route": "/dashboard", "match": false}
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

**7. Stop dev server** (always — whether visual ran or was skipped):
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
Visual tests:  {passed}/{total} matched | SKIP
Security:      {via /shipwright-security | not run}

Overall:       {PASS | FAIL}
{Failed tests: list if any}
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
| **Visual tests** | **Warning only** (non-blocking) | Visual divergence ≠ broken functionality |

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
| Visual tests | `pass`, `fail`, or `skipped: {reason}` |

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
- `skipped: no screen-routes.json` (Visual)

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

**Phase complete — update pipeline state** (only if Completion Gate passes):
```bash
# Mark test phase complete (triggers compliance update automatically)
uv run {plugin_root}/../../plugins/shipwright-run/scripts/lib/orchestrator.py \
  update-step --project-root "$(pwd)" --step test --status complete

# Update delivery dashboard
uv run {shared_root}/scripts/tools/update_build_dashboard.py \
  --project-root "$(pwd)" --phase test --detail "{passed}/{total} passing" \
  --session-id "{SHIPWRIGHT_SESSION_ID}"
```
Where `{shared_root}` = `{plugin_root}/../../shared`.

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
