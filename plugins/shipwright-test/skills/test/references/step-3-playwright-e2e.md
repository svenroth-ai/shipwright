# Step 3: Run Playwright E2E (if applicable)

**Prerequisites:**
- Profile has UI (e.g., `supabase-nextjs`)
- DEV URL is accessible (smoke test passed)

**Flow:**

1. **Ensure Playwright is set up:**
```bash
uv run "{plugin_root}/../../shared/scripts/playwright_setup.py" --cwd {project_root}
```

2. **Ensure dev server is running:**
```bash
uv run "{plugin_root}/../../shared/scripts/dev_server.py" start --profile {profile} --cwd {project_root}
```

3. **Run E2E tests:**
```bash
uv run "{plugin_root}/scripts/lib/playwright_runner.py" --cwd {project_root}
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
   c. Apply a single fix addressing the group (e.g., fix loginAs helper -> fixes all auth tests)
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
   - Auth/login failures -> run auth setup to seed test users (`npx playwright test --project=setup`)
   - Missing page elements -> verify pages render, check selectors against actual DOM
   - Connection issues -> verify dev server is running, check base URL config
   - Timeout -> increase test timeout, check for slow-loading pages
   - Missing test data -> check fixtures, seed required data
3. **Re-run failed tests only:** `npx playwright test --grep "{test_title}"`
4. After 2 failed fix attempts with same root cause: **ASK user** for direction
