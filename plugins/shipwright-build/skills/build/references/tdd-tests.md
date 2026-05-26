# TDD Tests Reference

Detail for Kern Step 3 (Write Tests First).

**Goal:** Write failing tests that define the expected behavior.

1. Create test files as specified in the section
2. Write test cases with clear assertions
3. Run tests — they should **fail** (red phase)

```bash
# Verify tests fail as expected
npm test  # or: uv run pytest
```

## Integration Tests

(if profile has `testing.integration` AND section involves CRUD/DB)

Check the profile for a `testing.integration` config block. If present AND this section creates, reads, updates, or deletes database records:

1. **Scaffold helpers** (if not already present):
   - `tests/integration/helpers/supabase-clients.ts` — from `integration-helpers-supabase.ts.template`
   - `vitest.integration.config.ts` at project root — from `vitest.integration.config.ts.template`
   - `.env.test` at project root — from `env.test.template`

2. **Write integration test files** in `tests/integration/{entity}.integration.test.ts`:
   - **Mandatory:** One test per CRUD operation (create, read, update, delete)
   - **Mandatory:** One RLS negative test per entity (prove unauthorized access is blocked)
   - **Mandatory:** `afterAll` block that calls `deleteTestUser(userId)` for cascade cleanup
   - **Forbidden:** Using `getServiceClient()` for test assertions — it is for setup/teardown ONLY
   - **Forbidden:** Weakening RLS policies to make tests pass

3. **Use cascade-delete pattern:**
   - `beforeAll`: `createTestUser()` to get a unique test user
   - Tests: create data linked to this test user
   - `afterAll`: `deleteTestUser()` — all data cascades away

4. **Run integration tests** (must fail in red phase):
   ```bash
   npx vitest run --config vitest.integration.config.ts
   ```

## pgTAP Tests

(if section adds migrations with RLS policies)

If this section creates SQL migrations containing RLS policies (`CREATE POLICY`, `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`):

1. Scaffold `supabase/tests/database/000-setup-tests-hooks.sql` from `pgtap-setup.sql.template` if missing
2. Write `supabase/tests/database/{migration-name}.test.sql`
3. Run: `supabase test db`

## E2E Tests

(if section changes user-visible behavior)

If this section adds new user-facing routes/pages or modifies existing user flows (regardless of complexity):

1. Write Playwright spec in `e2e/flows/{feature}.spec.ts`
2. Create Page Object Models in `e2e/pages/` if needed
3. Run: `npx playwright test e2e/flows/{feature}.spec.ts`

## Decision Table — Which Test Type to Write

| What you're testing | Test type |
|---|---|
| Service function logic | Unit (mocked boundary) |
| API route -> real DB row created/updated/deleted | Integration |
| RLS policy blocks unauthorized access | Integration + pgTAP |
| Complex query (joins, filters, aggregations) | Integration |
| Input validation rejects bad data | Unit |
| Component renders with props | Unit |
| User journey / multi-page flow | E2E (Playwright) |

**Checkpoint:** Test files exist and fail for the right reasons.

**Dashboard update:**

```bash
uv run "{shared_root}/scripts/tools/update_build_dashboard.py" \
  --project-root "$(pwd)" --section "{section_name}" --step 3 --detail "Tests written (red phase)" --session-id "{SHIPWRIGHT_SESSION_ID}"
```
