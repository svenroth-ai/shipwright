import { describe, it, expect, vi } from 'vitest'
import { createClient } from '@supabase/supabase-js'
import { getUserProfile } from '@/lib/users'

// Mock at system boundary (Supabase client), not internal functions
vi.mock('@supabase/supabase-js', () => ({
  createClient: vi.fn(() => ({
    from: vi.fn(() => ({
      select: vi.fn(() => ({
        eq: vi.fn(() => ({
          single: vi.fn(() => ({ data: { id: '1', name: 'Test User' }, error: null })),
        })),
      })),
    })),
  })),
}))

describe('getUserProfile', () => {
  it('should return user data for valid id', async () => {
    const profile = await getUserProfile('1')
    expect(profile).toEqual({ id: '1', name: 'Test User' })
  })

  it('should throw on missing user', async () => {
    // Override mock for error path
    vi.mocked(createClient).mockReturnValueOnce({
      from: vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn(() => ({ data: null, error: { message: 'Not found' } })),
          })),
        })),
      })),
    } as any)
    await expect(getUserProfile('999')).rejects.toThrow('Not found')
  })
})
