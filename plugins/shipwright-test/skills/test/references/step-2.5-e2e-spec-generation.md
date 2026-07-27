# Step 2.5: Generate E2E Specs from Plan, and check coverage per journey

**Goal:** Implement Playwright E2E test specs from the E2E test plans generated
by `/shipwright-plan`, and make sure **every** planned journey has one — not
just the first.

**Skip this step entirely only if** the profile has no UI (backend-only, CLI
tool, library).

> **Generation is skipped once specs exist; the coverage check never is.**
> Generation used to be skipped wholesale the moment `e2e/` contained any
> `.spec.ts` file at all, so a journey added to the plan afterwards went
> uncovered and unreported. Regenerating an existing suite is still wrong — but
> "some spec exists" is not the same claim as "this journey is tested".

**Flow:**

1. **Check per-journey coverage (always):**
```bash
uv run "{plugin_root}/scripts/lib/journey_coverage.py" \
  --project-root "{project_root}" --json
```
Report per `status`:

| `status` | Meaning | What to do |
|---|---|---|
| `covered` | every planned journey is named by some spec | continue |
| `gaps` | at least one planned journey has no spec | **greenfield: exit 1 — STOP and write the missing specs.** brownfield: a follow-up per gap is filed automatically (routed to `/shipwright-adopt`); report the gaps and continue |
| `no_specs` | journeys planned, nothing generated yet | continue to step 2 — this is what generation is for. **Not an all-clear:** step 7 re-checks after generating |
| `undetermined` | no plan, or no journeys parseable from it | report the `diagnostic`; do not claim coverage either way |

Matching is a **name heuristic** (spec filename slug, or the journey title
mentioned in the spec body). It is an indication that a journey is covered,
never proof that the spec exercises it. Say so when reporting.

2. **Find E2E test plans:**
```bash
find .shipwright/planning/ -name "claude-plan-e2e.md" -type f 2>/dev/null
```
If no plans found -> skip generation with note: "No E2E test plans found in .shipwright/planning/."

3. **Skip generation if specs already exist:**
```bash
find e2e/ -name "*.spec.ts" -type f 2>/dev/null | head -1
```
If any `.spec.ts` file found -> skip generation with note: "E2E specs already
exist." (The coverage check in step 1 has already reported any journey those
specs do not cover.)

4. **Generate specs from plans:**
For each `claude-plan-e2e.md` found:
   - Read the plan file (contains user flows, page objects, test data)
   - Generate Playwright test specs following the plan's scenarios
   - Place specs in `e2e/flows/NN-flow-name.spec.ts`
   - Generate Page Object Models in `e2e/pages/*.page.ts`
   - Generate test fixtures/seed data in `e2e/fixtures/test-data.ts`
   - Create `e2e/fixtures/auth.setup.ts` for authenticated test state (if auth flows in plan)

5. **Structure:**
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

6. **Guidelines for spec generation:**
   - Each flow from the plan maps to one `.spec.ts` file
   - Use Playwright `test.describe()` to group related flows
   - Use Page Object Model pattern for element selectors
   - Use `test.beforeAll()` for auth setup where needed
   - Respect `playwright.config.ts` settings (base URL, browser, timeouts)
   - Tests must be runnable against the dev server (localhost)
   - Use `test.skip()` for flows that require external services (e.g., Stripe Checkout redirect)
   - If `.shipwright/designs/visual-guidelines.md` exists, generate basic visual assertion tests in `e2e/flows/00-visual.spec.ts`:
     - Check brand colors on key elements (header, CTA buttons, links)
     - Check font-family on body/headings
     - Check page background color

7. **Re-run the coverage check after generating (mandatory when step 4 ran):**
```bash
uv run "{plugin_root}/scripts/lib/journey_coverage.py"   --project-root "{project_root}" --json
```
Step 1 necessarily ran *before* the specs existed, so on a fresh project it
reported `no_specs` and blocked nothing — that state is what generation is for.
Generation can fail or cover only some journeys, and without this second pass a
greenfield project would finish with journeys unverified and the block never
fired. Apply the same table as step 1 to the result.

**Checkpoint:** `journey_coverage.py` reports `covered`, or reports `gaps` on a
brownfield project with a follow-up filed per gap. On greenfield, `gaps` after
generation is a STOP. `e2e/flows/` contains at least one `.spec.ts` file.
