# Brief-Intake (K2c)

The WebUI Intent Wizard (K2) asks four plain-language questions and hands
`/shipwright-run` a **pre-delivered brief** with the answers. Brief-intake
maps those answers to the profile + deploy/env choices and asks ONLY the
still-missing questions — so the terminal interview never re-asks what the
wizard already answered.

**No brief → nothing changes.** When Step 1 finds no brief, skip this entire
file and run Step 1-3 exactly as today. Brief-intake is purely additive.

## The four wizard answers

| Field | Wizard question | Values |
|-------|-----------------|--------|
| `description` | "Describe it like you'd tell a friend." | free text |
| `users` | "Who's going to use it?" | `just_me` · `team` · `public` |
| `persistence` | "Should it remember things?" | `yes` · `no` · `unsure` |
| `run_location` | "Where should it live for now?" | `local` · `web` |

## How a brief arrives

A brief is either a **file path** (optionally `@`-prefixed, e.g.
`@wizard-brief.json`) or an **inline prompt payload** (a JSON object, or a
markdown block carrying a fenced ```json {...}``` block or `key: value` lines).
The WebUI writes the JSON object shape. Detect a brief when the invocation
carries one of these; otherwise treat the input as a plain description
(sources 1-3 of Step 1).

If a brief FILE is missing, unreadable, oversized, or has an unrecognized
suffix, the helper does NOT fail the run — it degrades to the legacy interview
(re-asks the four questions). That is the spec-sanctioned fallback (webui A09:
"without B4, run double-asks — ok"), safer than proceeding on a half-read brief.

## Run the intake

```bash
uv run "{plugin_root}/../../shared/scripts/lib/brief_intake.py" --brief "{brief_path_or_payload}"
```

The helper (`shared/scripts/lib/brief_intake.py`, shared by `run` + `adopt`,
unit-tested in `shared/tests/test_brief_intake.py`) returns:

```json
{
  "has_brief": true,
  "brief": {"description": "...", "users": "public",
            "persistence": "yes", "run_location": "web"},
  "profile": "supabase-nextjs",
  "profile_reason": "persistence=yes -> real database (supabase-nextjs)",
  "deploy_target": "jelastic-dev",
  "auth_scope": "public",
  "answered": ["description", "users", "persistence", "run_location"],
  "remaining_questions": ["autonomy"],
  "env_questions": ["NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"]
}
```

## Mapping rules (what the helper decides)

| Answer | Effect |
|--------|--------|
| `persistence == yes` | profile `supabase-nextjs` (needs a free account) |
| `persistence == no` or `unsure` | profile `vite-hono` — the zero-signup local **default** |
| `run_location == web` | deploy target set (`jelastic-dev`); env questions become relevant |
| `run_location == local` | deploy target `none` — fastest start, ship later |
| `users` | `public → public`, `team → team`, `just_me → none` auth scope (context) |
| supabase **and** web | ask the Supabase env vars (`env_questions`); otherwise skip them |

**Env questions fire only on `web + persistence`.** A local run (even with a
database) defers env setup; a web run without persistence (`vite-hono`) has no
Supabase env to ask. This is the Vercel pattern — ask expert questions only
when genuinely needed.

## Wiring into Steps 1-4

1. **Step 1** — if a brief was supplied, run the intake. `answered` lists the
   questions the wizard covered; do NOT re-ask any of them. `description` is the
   brief for the pipeline.
2. **Step 2** — skip `inference.py` for profile: `profile` + `deploy_target` are
   already fixed from the wizard answers. Only fall back to inference for a
   field the brief left `null`.
3. **Step 3** — present the same INFERRED SETTINGS card, pre-filled from the
   brief. Ask only `remaining_questions` (typically just `autonomy`) plus each
   entry of `env_questions` when non-empty.
4. **Step 4** — pass `--profile {profile}` and `--deploy-target {deploy_target}`
   to `orchestrator.py write-config` exactly as the legacy flow would.

## Partial brief

When a field is missing (or an answer is unrecognized), it appears in
`remaining_questions` and the interview asks for that single gap — everything
the brief did answer is still suppressed. A missing `persistence` leaves
`profile` `null`, so Step 2 falls back to inference / a direct question for the
profile only.
