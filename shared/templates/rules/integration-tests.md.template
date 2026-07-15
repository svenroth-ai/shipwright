---
description: Integration testing conventions — real DB, no mocks, cascade cleanup
globs: "**/tests/integration/**,**/*.integration.test.*"
---

## Integration Testing Rules

- Integration tests hit a **real database** (localhost Supabase) — NO mocks
- Every CRUD operation gets an integration test — this is not complexity-gated
- Use `vitest.integration.config.ts` (separate from unit test config)
- Load environment from `.env.test` (must point to localhost/127.0.0.1 only)
- Run sequentially (`fileParallelism: false`) to avoid data races

## Requirement traceability tags (`@FR`)

Tag each integration test with the requirement it verifies using `@FR-XX.YY` so the
compliance `test_links` collector records integration-layer coverage per FR (the
`test → FR` backward link). A CRUD/DB requirement typically requires the `integration`
layer, so a missing tag here shows up as an uncovered integration layer in the RTM.

- **Vitest** (integration configs): title suffix — `it('creates a row @FR-02.01', …)` —
  or a `// @covers FR-02.01` comment on the line above the `it`/`describe`. A tag on the
  `describe` applies to every test in the block.
- **pytest** integration tests: `@pytest.mark.covers("FR-02.01")` (the `covers` marker is
  registered in `pyproject.toml`).

The token is additive: it does not change the assertion, and a tag only counts as covering
the layer when the test is enabled AND passing (a skipped test is not coverage).

## Safety Rules

- **Service-role client is for setup/teardown ONLY** — never use it for test assertions
- **Never weaken RLS policies to make tests pass** — fix the test or auth context instead
- **URL safety check**: Tests throw if `NEXT_PUBLIC_SUPABASE_URL` is not localhost/127.0.0.1

## Test Data Lifecycle — Cascade Delete

Use Postgres `ON DELETE CASCADE` for reliable cleanup:

1. `beforeAll`: Create a unique test user via `createTestUser()` (Admin API, service-role)
2. Each test: Create data owned by / linked to this test user
3. `afterAll`: Delete the test user via `deleteTestUser()` — all linked data cascades away

**All integration tests MUST include an `afterAll` block that deletes the test user.**

## Required Structure

```typescript
import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import {
  getServiceClient,
  getAuthenticatedClient,
  getAnonClient,
  createTestUser,
  deleteTestUser,
} from './helpers/supabase-clients'

describe('entity CRUD (integration)', () => {
  const suiteId = crypto.randomUUID().slice(0, 8)
  let testUserId: string

  beforeAll(async () => {
    const user = await createTestUser(`test-${suiteId}@integration.local`, 'TestPass123!')
    testUserId = user.id
  })

  afterAll(async () => {
    await deleteTestUser(testUserId)
  })

  it('creates a row when called by authorized user', async () => {
    // Use getAuthenticatedClient(), NOT getServiceClient()
  })

  it('blocks anon users (RLS negative test)', async () => {
    // Use getAnonClient() — expect error
  })
})
```
