# Step E.5 — Env Scaffold (`.env.local`)

After the artifact generator returns, adopt MUST scaffold a
`<project_root>/.env.local` so the framework's runtime secret loader
(`shared/scripts/lib/env.py::load_shipwright_env`) and the external
review CLI (`shared/scripts/tools/external_review.py`) have a single
canonical surface to read from on this project. The artifact generator
calls `shared/scripts/validate_env.py::init_env_file(project_root,
"all", profile_dir, include_framework=True)` directly — there is no
separate subprocess invocation here. The result lands in
`results["env_local"]` for the Step H handoff banner.

What gets written:

- **Profile-specific keys** — `required_env_vars[build|deploy|plugin]`
  from the active stack profile (e.g. `NEXT_PUBLIC_SUPABASE_URL` for
  `supabase-nextjs`, `JELASTIC_TOKEN` for deploy phase, …).
- **Framework keys** — always: `OPENROUTER_API_KEY`, `GEMINI_API_KEY`,
  `OPENAI_API_KEY` (in that order — mirroring the fallback chain in
  `external_review_config.py`). These appear regardless of which
  stack profile is matched, because external review is framework-level
  and runs in every plugin's planning/iterate gate. <!-- artifact-path-canon: legacy -->

Behavior contract:

- **Idempotent — never overwrites.** Running adopt against a project
  that already has `.env.local` does NOT replace existing values.
  Missing keys are appended; the action is `created` / `updated` /
  `unchanged` accordingly.
- **`.gitignore` enforced FIRST.** Before writing `.env.local`, the
  scaffold ensures the project's `.gitignore` matches the file
  (literal `.env.local`, `.env*.local`, or `.env.*.local`). On
  enforcement failure (permission/OS error), the scaffold returns
  `action: skipped, reason: gitignore_enforcement_failed` and writes
  NOTHING — secrets must never land in a repo where the ignore rule
  could not be locked in.
- **No real values written, ever.** Every entry is comment-prefixed
  (`# KEY=    # description`) so the file is inert until the user
  uncomments and fills in the value. The user copies values from
  their password manager / secrets vault.
- **Existing user content preserved byte-for-byte** on the `updated`
  path — appended new keys only, never re-orders or rewrites pre-
  existing lines.

The result dict surfaced under `results["env_local"]` carries
`{action, path, vars, framework_keys, missing_keys, profile}` — Step
H consumes `missing_keys` (computed from the FINAL file state, not
just newly added keys) to decide what to surface in the handoff.
