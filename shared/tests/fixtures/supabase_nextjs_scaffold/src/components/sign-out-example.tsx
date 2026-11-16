// server action — returns result, no redirect
'use server'
export async function signOut() {
  const supabase = await createServerClient()
  await supabase.auth.signOut()
  return { success: true }
}

// client component — handles navigation after action completes
'use client'
export function SignOutButton() {
  async function handleSignOut() {
    const result = await signOut()
    if (result.success) window.location.href = '/login'
  }
  return <button onClick={handleSignOut}>Sign Out</button>
}
