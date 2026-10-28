# Step 7: Project Scaffolding (NEW — Shipwright Enhancement)

**Goal:** Generate CLAUDE.md, AGENTS.md, and .shipwright/agent_docs/ for the target project.

**This step only runs for Full Application scope.** Extensions already have these files.

See [project-scaffolding.md](project-scaffolding.md) for details.

## Profile detection

`{project_root}` (list, resolve and the config writer alike) is the project folder that holds or will hold `.shipwright/`: the working directory for a description, or the project being scaffolded when a requirements file is given (never that file's folder, which is `{planning_dir}`).

1. Read the interview transcript and requirements.
2. List the candidates: `uv run --no-project "{shared_root}/scripts/tools/resolve_profile.py" list --project-root "{project_root}" --json`. Each row has `name`, `source` (`project`, `user` or `bundled`), `valid` and a description; an invalid candidate is a row with `valid: false` plus `error` and `kind`. `warnings` carries directory problems only, not invalid candidates.
3. Offer the `valid: true` rows, and show the user every invalid row (name and `error`) so a broken own profile is not silently missing.
4. Pick the profile (plain-language wording, see CLAUDE.md "Asking the user questions"):
   - One candidate clearly fits the interview (for example "Supabase" + "Next.js" gives `supabase-nextjs`): propose it.
   - The user may instead name their own stack description. Ask: "Do you want to use your own stack description (a file in your project's `.shipwright/profiles/` or in `~/.shipwright/profiles/`), or one of the built-in ones?"
   - Nothing fits, or the user declines: keep `generic` (no stack file, built-in defaults) and skip to step 6.
   - **An explicit pick never falls back to `generic`.** If the named profile is listed as invalid, or is not in the list, still run step 5 and STOP with its message.
5. Load the chosen profile: `uv run --no-project "{shared_root}/scripts/tools/resolve_profile.py" resolve --project-root "{project_root}" --name "{profile_name}" --path-only` (exit 0 with empty output = built-in defaults; any other non-zero exit = stop and show the message, do not retry; name must match `^[a-z0-9][a-z0-9-]*$`, otherwise stop).
6. No match: use a generic profile structure.

### Chat-first projects (`ux_shape: chat-first`)

When the profile declares `ux_shape: chat-first` (bundled: `chat-first-json`), scaffold the app shell its `folder_structure` names, not a node project:

- `pyproject.toml` with `fastapi`, `uvicorn` and `pytest` (latest versions, not the profile's strings), `app/main.py` serving the pane from `app/static/` and the chat API, and `GET /api/health` answering 200: the profile's `dev_server` block starts `uv run uvicorn app.main:app --host 127.0.0.1 --port 3900` and waits on that path.
- `data/` for the local JSON files (the only storage) and `tests/` for pytest.
- `package.json` + `playwright.config.ts` + `e2e/` for Playwright specs (`*.spec.ts`, so per-journey coverage works) against `http://127.0.0.1:3900` (one host spelling everywhere: Node resolves `localhost` to `::1` first, while uvicorn listens on IPv4, which gives a false failure): write `playwright.config.ts` yourself with that `baseURL`, `webServer.command` = `uv run uvicorn app.main:app --host 127.0.0.1 --port 3900`, `webServer.url` = `http://127.0.0.1:3900/api/health` (the template's `npm run dev` would fail: the project has no `dev` script) and the `['json', { outputFile: 'e2e-results.json' }]` reporter the runner reads (the shared template's default is port 3000 and `playwright_setup.py` leaves an existing config alone), and set `dev_url` to `http://127.0.0.1:3900` in `shipwright_build_config.json`.
- No deploy files and no CI workflow: the profile has `deploy: null` and no CI template (`deploy_target: none`).

### Skill-backed projects (`ux_shape: skill-companion`, bundled: `skill-companion-app`)

When the profile declares `ux_shape: skill-companion`, scaffold a plugin, not a node app and not a chat app (the chat is the Claude app): `.claude-plugin/plugin.json`, `skills/<name>/SKILL.md` (the front door that starts and stops the companion), `backend/server.py`, `board/` (HTML/CSS/vanilla JS), `tests/` (pytest), `pyproject.toml` (pytest and ruff as dev dependencies), `package.json` + `playwright.config.ts` + `e2e/` (dev tooling for Playwright `*.spec.ts` only). Write `playwright.config.ts` yourself: `baseURL` `http://127.0.0.1:3911`, `webServer.command` = the profile's `dev_server.command`, `webServer.url` = `http://127.0.0.1:3911/api/health`, **`reuseExistingServer: false`** (the shared template's `true` would attach to the user's running companion and its real data), the `['json', { outputFile: 'e2e-results.json' }]` reporter, and `dev_url` `http://127.0.0.1:3911` in `shipwright_build_config.json`.

`backend/server.py` contract: it serves `board/` and the JSON API, `GET /api/health` answers 200, and it accepts `--host`, `--port` and `--data-dir`; `--data-dir` wins over `<APP_NAME>_HOME` and the default folder, and the server refuses to start rather than fall back when `--data-dir` is unusable. Harden the loopback API: check the `Host` header, no permissive CORS, require `Content-Type: application/json` (or a per-session token the skill hands the board) on state-changing routes. Real data lives in a user-owned folder outside the plugin install (see the profile's `notes` and `docs/stack-profiles.md`); `.dev-data/` (git-ignored) is for development and tests only. No deploy files and no CI workflow (`deploy_target: none`).

## Generate these files in the project root

1. **CLAUDE.md** — from template, filled with project-specific values
2. **AGENTS.md** — Codex CLI's counterpart to CLAUDE.md, see
   [project-scaffolding.md](project-scaffolding.md) step 2
3. **.shipwright/agent_docs/architecture.md** — system architecture from interview
4. **.shipwright/agent_docs/decision_log.md** — initialized with header
5. **.shipwright/agent_docs/conventions.md** — from profile's architecture rules and folder structure
6. **`.claude/rules/*.md`** — path-specific rules from profile (Claude Architect Best Practice)

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
  --profile-root "{project_root}" \
  --profile "{profile_name}" \
  --scope "{scope}"
```

`--profile-root` is `{project_root}` (lookup only; it does not move the config, which is written to the project above `<project>/.shipwright/planning`). Always pass it. The writer exits 4 when the name does not resolve to a usable profile (unknown, malformed, invalid or too new) and 1 when the shared tree is missing on a complete scaffold.

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

**Checkpoint:** CLAUDE.md existence + AGENTS.md existence + `supabase/config.toml` existence (if supabase-nextjs profile).
