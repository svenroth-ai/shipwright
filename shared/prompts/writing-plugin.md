# Writing & Maintaining Shipwright Plugins

> The meta-guide for changing Shipwright ITSELF (this monorepo): plugins,
> shared scripts, hooks, skills. Pointed to by `using-shipwright.md` and by the
> Stop reminder hook (`plugin_sync_reminder_on_stop.py`).
>
> Adapted from the obra/superpowers `writing-skills` meta-skill (MIT, © Jesse
> Vincent — https://github.com/obra/superpowers), retargeted to Shipwright's
> plugin-cache-drift problem.

## When this applies

You are editing framework files, not a target app, whenever a path is under
`plugins/*`, under `shared/*` (except `shared/tests/`), or named `SKILL.md`.
These are exactly the files `scripts/update-marketplace.sh` syncs into the
runtime cache at `~/.claude/plugins/cache/shipwright/`.

## The drift trap (why this guide exists)

Claude Code runs plugins from the **cache**, not your working tree. Edits to
`plugins/*` or `shared/*` land in the dev repo but the running session keeps
using the cached copy. Iterates 7–11 each shipped plugin-side fixes that
**silently never took effect** because the sync step was skipped. A new hook in
a `hooks.json` only fires in a *subsequent* session, after the cache is synced.

## Mandatory close-out (the hard gate)

After any plugin-side change, before you call it done:

1. **`git push`** — the marketplace clone tracks `origin/main`, so unpushed
   commits won't sync.
2. **`bash scripts/update-marketplace.sh`** — full file sync of `plugins/` +
   `shared/` into the installed cache (and cross-plugin symlinks).
3. **`uv run scripts/check_plugin_cache_sync.py --strict`** — per-file SHA-256
   drift check (CRLF-normalized). Exit 1 on any drift. Must be green.
4. **Restart the Claude Code session** to load the synced plugins.

The Stop reminder hook surfaces this once per session and files a
`source="plugin-sync"` triage item so it survives if you defer.

## Conventions to honor

- **Hooks** resolve paths via `${CLAUDE_PLUGIN_ROOT}` and reach shared scripts
  as `${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/...`. Quote the placeholder.
  Python hooks run via `uv run`; shell hooks via `bash`.
- **A hook registered in one plugin must usually be registered in all 12** so it
  fires regardless of which plugin is active. Hooks that emit context/blocks fire
  N times per event — make them **idempotent** (atomic O_EXCL session sentinel,
  set-merge marker, or `append_*_idempotent`). Mirror the meta-test in
  `shared/tests/` (forward: every plugin registers it; reverse: the script
  exists) — see `test_hook_registry_bloat.py` and `test_using_shipwright_hook.py`.
- **SessionStart output** uses `hookSpecificOutput.additionalContext`.
  **Stop output** uses top-level `{"decision":"block","reason":...}` (no wrapper)
  — pass-path is empty stdout. **Fail open**: a hook bug must never brick the
  agent; wrap `main()` and exit 0 on unexpected errors.
- **Update the docs you changed:** `docs/hooks-and-pipeline.md` when you touch any
  `hooks.json`, phase, validator, or startup-context read; `docs/guide.md` when a
  skill's command/flags/pipeline/constitution changes.
- **Size limits:** ≤300 LOC source/tests, ≤400 LOC runtime-prompts (SKILL.md,
  CLAUDE.md, plugin agents, shared prompts). The anti-ratchet pre-commit hook
  blocks growth past an existing baseline entry.
- **Tests live with the code:** plugin tests in `plugins/*/tests/`, shared-script
  and hook tests in `shared/tests/`. TDD: a failing test first, then the fix.

## Red flags — STOP

- "I edited the SKILL.md, it'll just work" — not until the cache is synced.
- "I'll register the hook in one plugin only" — it won't fire from the others.
- "The hook fires 12×, whatever" — duplicate context / double-blocks; dedupe it.
- "I'll skip the doc update" — `hooks-and-pipeline.md` is the SSoT; drift bites.
