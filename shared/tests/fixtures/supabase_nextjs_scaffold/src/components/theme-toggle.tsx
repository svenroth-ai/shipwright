'use client'
// src/components/theme-toggle.tsx
import { useState } from 'react'

export function ThemeToggle() {
  const [dark, setDark] = useState(false)

  return (
    <button
      onClick={() => setDark(!dark)}
      aria-pressed={dark}
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {dark ? '☀️' : '🌙'}
    </button>
  )
}
