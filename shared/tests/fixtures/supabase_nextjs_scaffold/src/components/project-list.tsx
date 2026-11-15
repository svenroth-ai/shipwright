// src/components/project-list.tsx
import { createServerClient } from '@/lib/supabase/server'

export async function ProjectList() {
  const supabase = await createServerClient()
  const { data: projects } = await supabase.from('projects').select('id, name, status')
  return (
    <ul>
      {projects?.map((p) => <li key={p.id}>{p.name} — {p.status}</li>)}
    </ul>
  )
}
