// src/app/api/projects/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { z } from 'zod'
import { createServerClient } from '@/lib/supabase/server'
import { createProject } from '@/lib/supabase/projects'

const CreateSchema = z.object({ name: z.string().min(1).max(100) })

export async function POST(req: NextRequest) {
  const supabase = await createServerClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized', code: 'AUTH_REQUIRED' }, { status: 401 })

  const parsed = CreateSchema.safeParse(await req.json())
  if (!parsed.success) return NextResponse.json({ error: 'Invalid input', code: 'VALIDATION_ERROR' }, { status: 400 })

  const result = await createProject(supabase, user.id, parsed.data)
  if (!result.ok) return NextResponse.json({ error: 'Create failed', code: 'DB_ERROR' }, { status: 500 })
  return NextResponse.json({ id: result.id }, { status: 201 })
}
