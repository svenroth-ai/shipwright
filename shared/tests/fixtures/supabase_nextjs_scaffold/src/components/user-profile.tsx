// src/components/user-profile.tsx  (NO 'use client' — this is a Server Component)
import { createServerClient } from '@/lib/supabase/server'

export async function UserProfile({ userId }: { userId: string }) {
  const supabase = await createServerClient()
  const { data: profile } = await supabase.from('profiles').select('*').eq('id', userId).single()

  if (!profile) return <p>User not found</p>

  return (
    <section aria-labelledby="profile-heading">
      <h2 id="profile-heading">{profile.name}</h2>
      <p>{profile.bio}</p>
    </section>
  )
}
