// src/app/api/profile/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { z } from 'zod'
import { createServerClient } from '@/lib/supabase/server'
import { updateProfile } from '@/lib/supabase/profiles'

const UpdateProfileSchema = z.object({
  name: z.string().min(1).max(100),
  bio: z.string().max(500).optional(),
})

export async function PATCH(req: NextRequest) {
  const supabase = await createServerClient()
  const { data: { user }, error: authError } = await supabase.auth.getUser()
  if (authError || !user) {
    return NextResponse.json({ error: 'Unauthorized', code: 'AUTH_REQUIRED' }, { status: 401 })
  }

  const body = await req.json()
  const parsed = UpdateProfileSchema.safeParse(body)
  if (!parsed.success) {
    return NextResponse.json(
      { error: 'Invalid input', code: 'VALIDATION_ERROR', details: parsed.error.flatten() },
      { status: 400 },
    )
  }

  const result = await updateProfile(supabase, user.id, parsed.data)
  if (!result.ok) {
    console.error('[PATCH /api/profile]', { userId: user.id, error: result.message })
    return NextResponse.json({ error: 'Update failed', code: 'DB_ERROR' }, { status: 500 })
  }

  return NextResponse.json({ success: true })
}
