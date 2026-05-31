# Step 7: Project Scaffolding (NEW — Shipwright Enhancement)

**Goal:** Generate CLAUDE.md and .shipwright/agent_docs/ for the target project.

**This step only runs for Full Application scope.** Extensions already have these files.

See [project-scaffolding.md](project-scaffolding.md) for details.

## Profile detection

1. Read the interview transcript and requirements
2. Match against known profiles (e.g., "Supabase" + "Next.js" → `supabase-nextjs`)
3. Load profile from `{plugin_root}/../../shared/profiles/{profile_name}.json`
4. If no match: use a generic profile structure

## Generate these files in the project root

1. **CLAUDE.md** — from template, filled with project-specific values
2. **.shipwright/agent_docs/architecture.md** — system architecture from interview
3. **.shipwright/agent_docs/decision_log.md** — initialized with header
4. **.shipwright/agent_docs/conventions.md** — from profile's architecture rules and folder structure
5. **`.claude/rules/*.md`** — path-specific rules from profile (Claude Architect Best Practice)

## Path-specific rules generation

- Read the `"rules"` array from the loaded profile JSON (e.g., `["tests", "api", "migrations", "components", "config"]`)
- For each rule name, copy the corresponding template from `{plugin_root}/../../shared/templates/rules/{name}.md.template`
- Write to `.claude/rules/{name}.md` in the project root (strip the `.template` suffix)
- If the profile has no `"rules"` field, skip this step
- These rules load conditionally in Claude Code: test rules only activate when editing test files, API rules only for API files, etc.

## Phase-router hook (no install step needed)

The `suggest_iterate` UserPromptSubmit hook is registered in
`shipwright-iterate` plugin's own `hooks/hooks.json`; no project-level
`.claude/settings.json` install is performed. ADRs 019/020 (carrier-
shape + quoting) survive verbatim in the plugin registration, just on
the right side of the plugin/project boundary.

**If your project was adopted under a previous Shipwright version**
and `.claude/settings.json` carries a legacy `UserPromptSubmit` entry
referencing `${CLAUDE_PLUGIN_ROOT}/.../suggest_iterate.py`, Claude Code
will surface "hook is not associated with a plugin" red-banner errors
because that variable only expands in plugin context. Cleanup is a
manual one-time edit: open `.claude/settings.json`, drop the
`hooks.UserPromptSubmit` entry whose command contains
`suggest_iterate.py`, leave any other hooks intact. The plugin-
registered hook continues to fire after the cleanup. Only the legacy
entry produces the error; the plugin one is fine.

## Write config

```bash
uv run "{plugin_root}/scripts/checks/write-project-config.py" \
  --planning-dir "{planning_dir}" \
  --profile "{profile_name}" \
  --scope "{scope}"
```

On the `--status complete` (full-scaffold) path this also merges the
canonical `.shipwright/` artifact-ignore block (SSoT:
`shared/templates/shipwright-gitignore.template`) into the project's
`.gitignore` via `shared/scripts/lib/gitignore_canon.merge_canonical_block`
— closing the gap where `/shipwright-project` previously wrote no
`.gitignore` entries at all. The merge is idempotent + additive (adds only
missing rules in a managed block, never duplicates); the action is reported
to **stderr** so stdout stays a pure config JSON. This ensures transient
artifacts (`.shipwright/agent_docs/runtime/`, decision-drops, visual) are
ignored while the canonical SDLC-doc homes stay tracked.

## Write interview decisions to decision_log.md

After scaffolding, extract all project-level decisions made during the interview
(e.g., auth strategy, video hosting, CRM choice, table prefix, design style) and
log each one using the shared tool:

```bash
uv run "{plugin_root}/../../shared/scripts/tools/write_decision_log.py" \
  --section "Project Interview" \
  --commit "n/a" \
  --context "{why the decision came up}" \
  --decision "{what was decided}" \
  --consequences "{impact on downstream phases}" \
  --rejected "{alternatives considered}"
```

Run this once per decision. Only log **project-specific** decisions — not profile defaults
(those are implicit in the stack profile). Typical decisions from the project interview:

- Auth strategy (Magic Link, password, OAuth)
- Third-party services (video hosting, CRM, payments)
- Naming conventions (table prefix, folder structure overrides)
- Design choices (font, color scheme, design system flavor)
- Data model choices (UUIDs vs auto-increment, soft delete, etc.)

## Supabase Project Setup (supabase-nextjs profile only)

When the detected profile is `supabase-nextjs`, perform these additional steps after generating CLAUDE.md:

1. **Check if `supabase/config.toml` exists** in project root
2. If NOT: run `npx supabase init`
3. **Ask the user for their Supabase project ref** (from Dashboard → Settings → General → Reference ID)
4. **Check if `SUPABASE_ACCESS_TOKEN` is set** in `.env.local`:
   - If missing: prompt user to generate one at https://supabase.com/dashboard/account/tokens and add it to `.env.local`
   - Ensure it is NOT commented out (no leading `#`)
5. Run `SUPABASE_ACCESS_TOKEN="$TOKEN" npx supabase link --project-ref <ref>`
6. Verify link succeeded: check that `.supabase/` directory was created

This ensures all downstream skills (build migrations, deploy) can use `supabase db push --linked`.

## GitHub Repo Hygiene (if git remote exists)

After scaffolding, check if the project has a GitHub remote and configure branch cleanup:

```bash
# Check if remote exists
git remote get-url origin 2>/dev/null
```

If a GitHub remote is found (contains `github.com`):
```bash
# Enable auto-delete of branches after PR merge
gh api repos/{owner}/{repo} -X PATCH -f delete_branch_on_merge=true
```
This prevents stale feature branches from accumulating after Shipwright's `gh pr merge --merge --delete-branch` (in changelog phase) or manual UI merges.

**Checkpoint:** CLAUDE.md existence + `supabase/config.toml` existence (if supabase-nextjs profile).
