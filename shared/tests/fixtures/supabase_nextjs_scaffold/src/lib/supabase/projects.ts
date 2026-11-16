// src/lib/supabase/projects.ts
import type { SupabaseClient } from '@supabase/supabase-js'

export async function createProject(supabase: SupabaseClient, userId: string, input: { name: string }) {
  const { data, error } = await supabase.from('projects').insert({ ...input, user_id: userId }).select('id')
  if (error) return { ok: false as const, message: error.message }
  return { ok: true as const, id: data?.[0]?.id as string | undefined }
}
