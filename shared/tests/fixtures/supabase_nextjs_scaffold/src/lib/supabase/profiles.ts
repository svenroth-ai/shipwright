// src/lib/supabase/profiles.ts
import type { SupabaseClient } from '@supabase/supabase-js'

export async function updateProfile(supabase: SupabaseClient, userId: string, input: { name: string; bio?: string }) {
  const { error } = await supabase.from('profiles').update(input).eq('id', userId)
  return error ? { ok: false as const, message: error.message } : { ok: true as const }
}
