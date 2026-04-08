/**
 * Integration Test Helpers — Supabase Client Factories
 *
 * These helpers create Supabase clients for integration tests.
 * Tests run against a LOCAL Supabase instance only (localhost/127.0.0.1).
 *
 * SAFETY RULES:
 * - getServiceClient() is for setup/teardown ONLY — never for test assertions
 * - Never weaken RLS policies to make tests pass
 * - All test data must be cleaned up via cascade delete (deleteTestUser)
 */

import { createClient, type SupabaseClient } from '@supabase/supabase-js'

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL!
const ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
const SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY!

// --- URL Safety Check ---
// Prevent accidental execution against remote/production Supabase
const url = new URL(SUPABASE_URL)
if (!['localhost', '127.0.0.1'].includes(url.hostname)) {
  throw new Error(
    `SAFETY: Integration tests must only run against localhost Supabase.\n` +
    `Current NEXT_PUBLIC_SUPABASE_URL points to: ${url.hostname}\n` +
    `Set .env.test to use http://127.0.0.1:54321`
  )
}

/**
 * Service-role client — bypasses RLS.
 * USE FOR SETUP/TEARDOWN ONLY. Never for test assertions.
 */
export function getServiceClient(): SupabaseClient {
  return createClient(SUPABASE_URL, SERVICE_KEY)
}

/**
 * Anonymous client — subject to RLS anon policies.
 * Use for testing unauthenticated access.
 */
export function getAnonClient(): SupabaseClient {
  return createClient(SUPABASE_URL, ANON_KEY)
}

/**
 * Authenticated client — signs in as a test user, subject to RLS.
 * Use for testing role-based access.
 */
export async function getAuthenticatedClient(
  role: 'admin' | 'member'
): Promise<SupabaseClient> {
  const envMap = {
    admin: {
      email: process.env.TEST_ADMIN_EMAIL!,
      password: process.env.TEST_ADMIN_PASSWORD!,
    },
    member: {
      email: process.env.TEST_MEMBER_EMAIL!,
      password: process.env.TEST_MEMBER_PASSWORD!,
    },
  }
  const creds = envMap[role]
  if (!creds.email || !creds.password) {
    throw new Error(
      `Missing test credentials for role "${role}". ` +
      `Set TEST_${role.toUpperCase()}_EMAIL and TEST_${role.toUpperCase()}_PASSWORD in .env.test`
    )
  }
  const client = createClient(SUPABASE_URL, ANON_KEY)
  const { error } = await client.auth.signInWithPassword(creds)
  if (error) {
    throw new Error(`Failed to sign in as ${role}: ${error.message}`)
  }
  return client
}

/**
 * Create a unique test user for cascade cleanup.
 * All data created by/for this user will be cascade-deleted when the user is removed.
 */
export async function createTestUser(
  email: string,
  password: string
): Promise<{ id: string; email: string }> {
  const serviceClient = getServiceClient()
  const { data, error } = await serviceClient.auth.admin.createUser({
    email,
    password,
    email_confirm: true,
  })
  if (error) {
    throw new Error(`Failed to create test user ${email}: ${error.message}`)
  }
  return { id: data.user.id, email: data.user.email! }
}

/**
 * Delete a test user and cascade-delete all associated data.
 * Call this in afterAll() to clean up test data.
 */
export async function deleteTestUser(userId: string): Promise<void> {
  const serviceClient = getServiceClient()
  const { error } = await serviceClient.auth.admin.deleteUser(userId)
  if (error) {
    console.warn(`Warning: Failed to delete test user ${userId}: ${error.message}`)
  }
}
