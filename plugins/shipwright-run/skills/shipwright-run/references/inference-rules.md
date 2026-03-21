# Inference Rules

## Scope Detection

| Signal | Scope |
|--------|-------|
| No `CLAUDE.md` in project root | Full Application |
| `CLAUDE.md` exists + `agent_docs/` exists | Extension |
| `--iterate` flag | Iteration (uses Extension scope internally) |

## Profile Detection

Scan the user description for technology keywords:

| Keywords | Profile |
|----------|---------|
| "Supabase" + ("Next.js" OR "React") | `supabase-nextjs` |
| "Supabase" alone | `supabase-nextjs` (default React framework) |
| "Next.js" alone | `supabase-nextjs` (suggest Supabase for backend) |
| No match | Ask user to specify |

**Detection priority:**
1. Explicit mention in description
2. Existing `package.json` analysis (Extension scope)
3. Existing `shipwright_run_config.json` (Iteration)
4. Ask user

## Autonomy Levels

| Level | Name | Behavior |
|-------|------|----------|
| `guided` | Guided (default) | Ask at key decisions: scope confirm, split review, deploy confirm |
| `autonomous` | Autonomous | Proceed without asking. Exceptions: PROD deploy, destructive DB operations |

**Default:** `guided` — safer, user stays in control.
