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
