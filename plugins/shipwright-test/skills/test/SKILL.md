---
name: shipwright-test
description: Profile-aware test runner. Runs unit tests, smoke tests, Playwright E2E, and optional security scans. Use after /shipwright-build or /shipwright-deploy.
license: MIT
compatibility: Requires uv (Python 3.11+). Optional: Playwright, Aikido account.
---

# Shipwright Test Skill

Profile-aware test execution across all test layers.

---

## CRITICAL: First Actions

### A. Print Intro Banner

```
================================================================================
SHIPWRIGHT-TEST: Test Runner
================================================================================
Runs tests across all layers based on stack profile.

Usage: /shipwright-test
   or: /shipwright-test --fix        (auto-fix failures, max 3 retries)
   or: /shipwright-test --security   (include security scan)
   or: /shipwright-test --e2e-only   (only Playwright E2E)
   or: Invoked by /shipwright-run (orchestrator)

Test layers:
  1. Unit tests (Vitest / pytest)
  2. Smoke test (HTTP 200 on DEV URL)
  3. Playwright E2E (if UI project + DEV URL available)
  4. Security scan (if --security flag, placeholder)
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

If `--fix` flag and tests fail:
1. Analyze failure output
2. Attempt auto-fix (edit code to fix the issue)
3. Re-run tests
4. Max 3 retries, then report remaining failures

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

5. **Auto-fix mode** (only with `--fix` flag, max 3 retries):
   a. For each failed test, check if a screenshot exists
   b. Spawn `browser-fixer` subagent with:
      - Screenshot image (if available)
      - Error message from test failure
      - DOM snippet (if available via trace)
      - Relevant source files
   c. Apply the recommended fix
   d. Re-run failed tests only: `npx playwright test --grep "{test_title}"`
   e. If still failing after 3 retries, report failures to user

6. **Stop dev server** (after all E2E tests complete):
```bash
uv run {plugin_root}/../../shared/scripts/dev_server.py stop --cwd {project_root}
```

If no Playwright config exists and setup fails: skip with note.

---

## Step 4: Security Scan (Optional — Placeholder)

**Only runs with `--security` flag.**

This is a placeholder for future integration with security scanning tools
(e.g., Aikido, Snyk, or similar). Currently outputs:

```
Security scan: Not configured.
To enable, set AIKIDO_API_KEY or configure a security provider in
shipwright_test_config.json.
```

---

## Step 5: Report Results

**Print Summary:**
```
================================================================================
SHIPWRIGHT-TEST RESULTS
================================================================================
Unit tests:    {passed}/{total} passed ({duration}s)
Smoke test:    {PASS | FAIL | SKIP} ({url}, {response_time}ms)
E2E tests:     {passed}/{total} passed | SKIP
Security:      {clean | N findings | not configured}

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

---

## Reference Documents

- [test-layers.md](references/test-layers.md) — Test layer overview and strategy
