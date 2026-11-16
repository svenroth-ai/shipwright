import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import {
  getServiceClient,
  getAuthenticatedClient,
  getAnonClient,
  createTestUser,
  deleteTestUser,
} from './helpers/supabase-clients'

describe('courses CRUD (integration)', () => {
  const suiteId = crypto.randomUUID().slice(0, 8)
  let serviceClient: ReturnType<typeof getServiceClient>
  let testUserId: string

  beforeAll(async () => {
    serviceClient = getServiceClient()
    // Create a test user — all data will cascade-delete when user is removed
    const user = await createTestUser(`test-${suiteId}@integration.local`, 'TestPass123!')
    testUserId = user.id
  })

  afterAll(async () => {
    // Cascade-delete all test data by removing the test user
    await deleteTestUser(testUserId)
  })

  it('creates a course row in the database when called by an authenticated user', async () => {
    const authClient = await getAuthenticatedClient('admin')
    const title = `Integration Test Course ${suiteId}`

    const { data, error } = await authClient.from('courses').insert({
      title,
      description: 'Integration test course',
      status: 'draft',
      created_by: testUserId,
    }).select().single()

    expect(error).toBeNull()
    expect(data).toMatchObject({ title, status: 'draft' })
    expect(data.id).toBeDefined()

    // Verify row exists independently via service client (setup/teardown use only)
    const { data: verify } = await serviceClient
      .from('courses').select().eq('id', data.id).single()
    expect(verify?.title).toBe(title)
  })

  it('blocks anon users from creating courses (RLS negative test)', async () => {
    const anonClient = getAnonClient()

    const { data, error } = await anonClient.from('courses').insert({
      title: `Anon attempt ${suiteId}`,
      description: 'Should be blocked by RLS',
      status: 'draft',
    }).select().single()

    expect(error).not.toBeNull()
    expect(data).toBeNull()
  })
})
