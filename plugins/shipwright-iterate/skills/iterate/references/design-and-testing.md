# Design & Testing Reference

Consolidated protocol for: Design Check, Scoped Testing, Browser Verify, Design Fidelity, E2E Update, Smoke Test.

---

## Design Check (2-tier)

### Tier 1 — Small + UI (text description)
1. Read `designs/visual-guidelines.md` for design tokens
2. Describe the UI change in structured text:
   - Which screen/component is affected
   - What changes visually (layout, components, colors, spacing)
   - Reference specific design tokens (colors, font sizes, spacing values)
3. Fill in "Design Notes" section of iterate spec (if exists)

### Tier 2 — Medium+ + UI (markdown component sketch)
All of Tier 1, plus:
1. Read `designs/chrome-definition.md` for shared chrome
2. Read relevant existing mockup HTML from `designs/screens/`
3. Write a markdown component tree:
   ```
   PageShell
   ├── Sidebar (shared chrome)
   ├── MainContent
   │   ├── PageHeader: "Course Search"
   │   ├── SearchBar: input + filter dropdowns
   │   ├── ResultsGrid
   │   │   ├── CourseCard (repeat)
   │   │   │   ├── CardHeader: thumbnail + title
   │   │   │   ├── CardContent: description + tags
   │   │   │   └── CardFooter: price + CTA button
   │   └── Pagination
   └── Footer (shared chrome)
   ```
4. Note prop structures for key components
5. Proceeds automatically unless `--pause` flag set

### Skip When
- No UI change
- Trivial complexity

---

## Scoped Testing

### Framework-Native Approach
Use Vitest's built-in dependency analysis instead of custom filename matching:
```bash
npx vitest --related {changed_files} --run
```

### New-Code Coverage Rule
When `--related` returns zero tests for newly created files: write at minimum one **unit test**
(boundary mock) per AC. For CRUD/DB operations, ALSO write one **integration test** (real DB)
per AC with `afterAll` cascade cleanup. Do NOT proceed with zero test coverage on new code —
the `--related` shortcut only works when tests already exist.

### Safety Floor
Changes touching these paths ALWAYS trigger full suite, regardless of complexity:
- `src/lib/`
- `src/middleware*`
- `src/components/ui/`
- `supabase/migrations/`

### Full Suite Trigger
- Medium+ complexity
- `--related` flag unavailable or returns no tests
- Safety floor paths touched

### Test Commands
```bash
# Scoped (trivial/small)
npx vitest --related $(git diff --name-only HEAD) --run

# Full suite (medium+ or safety floor)
npx vitest run
npx tsc --noEmit
```

---

## Integration Testing (Real Database)

### When
Any change that creates, reads, updates, or deletes database records, modifies RLS policies, or changes API routes that write data. Not complexity-gated — always write integration tests for CRUD operations.

### What it tests
The full wiring from API route or service function through to the actual database — no mocks.
Catches: wrong column names, broken joins, missing RLS policies, incorrect query filters.

### Protocol
1. Check profile for `testing.integration` config. If absent: skip.
2. Verify env vars (from `.env.test`): `NEXT_PUBLIC_SUPABASE_URL` (must be localhost), `SUPABASE_SERVICE_ROLE_KEY`, test user credentials
3. If env vars missing: **In CI: fail.** Locally: skip with warning.
4. Run integration tests:
   ```bash
   npx vitest run --config vitest.integration.config.ts
   ```
5. **Autofix:** Structured debugging (root cause → hypothesis → fix → re-run), max 3 retries.
6. **Fast-fail:** If error matches `ECONNREFUSED`, `ETIMEDOUT`, or >50% of tests fail simultaneously → skip autofix, fail immediately with diagnosis.
7. **Never auto-fix by weakening RLS policies or switching to service-role client for assertions.**

### Skip When
- No database changes in this iteration
- Pure UI change (no data layer)
- Profile has no `testing.integration` config

### Relationship to Unit Tests
- **Unit tests** (existing "Scoped Testing"): Mock at Supabase client boundary. Fast, deterministic. Test logic and error handling.
- **Integration tests** (this section): No mocks. Hit real DB (localhost only). Test wiring, schema correctness, RLS policies. Slower but catches real failures.
- Write BOTH for CRUD code: unit tests for logic, integration tests for wiring.

### Safety Rules
- Service-role client is for setup/teardown ONLY — never for assertions
- Never weaken RLS policies to make integration tests pass
- All test data cleaned up via cascade delete (`deleteTestUser` in `afterAll`)
- URL must be localhost/127.0.0.1 (enforced by setup file)

---

## pgTAP Database Tests

### When
New migrations that add RLS policies, constraints, or database functions.

### Protocol
1. Check if `supabase/tests/database/` exists. If not: skip.
2. Run: `supabase test db`
3. Autofix: same structured debugging pattern (max 3 retries).

### Skip When
- No new migrations in this iteration
- Migrations don't contain RLS policies or DB functions

---

## Browser Verify

### When
UI changes at any complexity level.

### Protocol
1. Start dev server via wrapper script:
   ```bash
   uv run {shared_root}/scripts/dev_server.py start --profile {profile} --cwd {project_root}
   ```
2. Run health check:
   ```bash
   uv run {shared_root}/scripts/playwright_setup.py --cwd {project_root}
   uv run {shared_root}/scripts/browser_verify.py --cwd {project_root}
   ```
3. If JS errors: read screenshot, diagnose, fix (max 3 retries)
3b. If UI change: compare screenshot against designs/screens/{affected}.html
    mockup for layout/styling alignment before proceeding to Design Fidelity
4. Server stays running for smoke test / design fidelity

### Skip When
No UI change in this iteration.

---

## Smoke Test

### When
Dev server is already running (browser verify or design fidelity started it).

### Protocol
Quick HTTP 200 check on affected routes. Nearly free since server is up.
```bash
curl -sf http://localhost:{port}/{route} > /dev/null
```

### Blocking
Yes — if a route returns non-200, stop and investigate before proceeding.

---

## Design Fidelity Analysis

### Step 1: Structural Extraction
Run the design fidelity helper to get automated check results:
```bash
uv run {test_plugin_root}/scripts/lib/design_fidelity_check.py \
  --cwd "{project_root}" --screen {affected_screen1} --screen {affected_screen2}
```

Use `--screen` flag to filter to screens affected by this iteration.

### Step 2: Auto-Check Review
If all `auto_checks` pass for all screens → log "Design fidelity: auto-pass", skip to Escalation.

### Step 3: Agent Deep Analysis (for screens with failures)
For each screen with `status: "needs_review"`, read BOTH files:
- The mockup HTML at `{mockup_path}`
- The implementation TSX at `{implementation_files[0]}`

Compare against 5 dimensions:
1. **Layout Structure** — grid/flex match mockup?
2. **Component Order** — same visual hierarchy?
3. **Component Types** — table vs card grid? Tabs vs accordion?
4. **Card Patterns** — full composition? (CardHeader + CardTitle + CardContent + CardFooter)
5. **shadcn Rules** — gap not space-y? Semantic colors? Proper card composition?

Fix mismatches, re-run unit tests to verify no regressions, commit: `fix(fidelity): {description}`.

### Step 4: Verify fixes
Re-run `design_fidelity_check.py --screen {fixed_screens}` to confirm fixes. Max 3 retries per screen. If unresolvable after 3 attempts: **revert uncommitted changes**, park with diagnosis.

After all screens:
- Report summary (fixed vs parked screens with diagnosis)
- ASK user for direction on parked screens
- Each successful fix gets its own commit

> **Note on full pipeline:** In `/shipwright-build`, design fidelity runs per-section in Step 7.5 using the same `design_fidelity_check.py` helper + agent deep analysis. In `/shipwright-test`, design fidelity runs as a regressions-only safety net — it triages screens against `design-fidelity-report.json`. Iterate does NOT use this two-phase split — design fidelity happens once with the full analysis above.

### Escalation
If still mismatched after fix loops:
- Mark `design_fidelity: "partial"` in test results
- Log warning with diagnosis per parked screen, continue (do NOT hard-fail)

### Skip When
No UI structural change, text/color-only tweaks, logic-only fixes.

---

## Cross-Page Consistency Re-Check (medium+ UI changes)

After design fidelity analysis, verify no new cross-page inconsistencies introduced by this change:

1. **Run scoped check:**
```bash
uv run {test_plugin_root}/scripts/lib/ui_consistency_check.py \
  --cwd "{project_root}" --files {changed_files}
```

2. **New outliers introduced by THIS change:** Fix before committing — these are regressions you just created.
3. **Pre-existing outliers:** Log as WARNING, do not fix (out of scope for this iteration).
4. Record results in `shipwright_test_results.json` under `consistency` key.

### Skip When
- Trivial/small complexity
- No UI changes
- `designs/visual-guidelines.md` does not exist
- Profile has no UI config

---

## Incremental E2E Test Update

### When
Features at any complexity that change user-visible behavior (new routes, modified flows, new UI). Changes/bugs: medium+ with new flows.

### Protocol
1. Read existing `e2e/flows/*.spec.ts` to understand current coverage
2. For new routes/flows: **prefer creating a new spec file** (e.g., `course-search.spec.ts`)
   - Do NOT inline-modify existing 500+ line specs (LLMs are error-prone at surgical TypeScript edits)
3. For modified flows with simple selector changes: update inline
4. Create new Page Object Models in `e2e/pages/` if needed
5. Run affected E2E tests:
   ```bash
   npx playwright test e2e/flows/{new-or-modified-spec}.spec.ts
   ```

### Skip When
- Changes/bugs at trivial/small complexity with no new flows
- No route/flow/UI behavior changes
- Pure logic/refactor changes

---

## Dev Server Lifecycle

Always stop the dev server when done with UI verification:
```bash
uv run {shared_root}/scripts/dev_server.py stop --cwd {project_root}
```
