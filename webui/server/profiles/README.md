# Bundled stack profiles

This directory holds a **snapshot** of `shared/profiles/*.json` from the
Shipwright monorepo. The WebUI ships this snapshot so it can run
standalone — no Shipwright repo required at runtime.

## Lookup order (see `server/src/core/profile-loader.ts::getProfilesDir`)

1. `SHIPWRIGHT_PROFILES_DIR` — explicit user override (absolute path).
2. `SHIPWRIGHT_MONOREPO_PATH` → `<path>/shared/profiles/` — dev-loop
   helper: when you're iterating on the Shipwright monorepo itself and
   want profile edits to take effect without re-syncing the snapshot.
3. This directory (bundled snapshot) — the default when neither env
   var is set.

## Keeping the snapshot fresh

The source of truth is `shipwright/shared/profiles/`. When profiles
change upstream, re-run:

```bash
npm run sync-profiles    # (from webui/server/)
```

…or just copy the changed files manually. There is no automatic sync —
the snapshot-vs-live drift is intentional so Shipwright and the WebUI
can release independently.
