---
name: shipwright-preview
description: "Start local dev server and show browser preview URL. Available after first build split.\nTRIGGER when: user wants to see the app, preview changes, check the UI, open the browser, show me the app, start the dev server, or view the running application.\nDO NOT TRIGGER when: user asks to write code, run tests, deploy, or any other SDLC phase."
license: MIT
compatibility: Requires Node.js and project dependencies installed (npm install).
---

# SHIPWRIGHT-PREVIEW — Local Browser Preview

Start the development server and show the preview URL so the user can open the app in their browser.

## CRITICAL: First Actions

### A. Print Intro Banner

```
╔══════════════════════════════════════════════╗
║           SHIPWRIGHT-PREVIEW                 ║
║                                              ║
║  Usage:                                      ║
║    /shipwright-preview                       ║
║    "show me the app"                         ║
║    "preview"                                 ║
╚══════════════════════════════════════════════╝
```

### B. Run Checks and Start Preview

Execute these checks in order. Stop at the first failure and help the user fix it.

#### Step 1: Build Check

Check if `shipwright_build_config.json` exists in the project root and has at least one section with `"status": "complete"`.

- **If no build config or no complete sections:** Tell the user:
  > "Preview is not available yet. Complete at least one build split first (`/shipwright-build`)."
  
  Stop here.

#### Step 2: Environment Check

Run the shared environment validator:

```bash
uv run "${SHIPWRIGHT_PLUGIN_ROOT}/../../shared/scripts/validate_env.py" \
  --project-root ${SHIPWRIGHT_PROJECT_ROOT} \
  --phase build
```

- **If validation fails (missing env vars):** Do NOT just tell the user to "check logs". Instead, actively help them create or fix `.env.local`. Read the error output, identify which variables are missing, and guide them through setting the values.

#### Step 3: Dev Server Status

Check if the dev server is already running:

```bash
uv run "${SHIPWRIGHT_PLUGIN_ROOT}/../../shared/scripts/dev_server.py" \
  status --cwd ${SHIPWRIGHT_PROJECT_ROOT}
```

Parse the JSON output. If `"running": true`, skip to Step 5.

#### Step 4: Start Dev Server

Start the dev server using the stack profile:

```bash
uv run "${SHIPWRIGHT_PLUGIN_ROOT}/../../shared/scripts/dev_server.py" \
  start --profile supabase-nextjs --cwd ${SHIPWRIGHT_PROJECT_ROOT}
```

Parse the JSON output:
- `"ready": true` → proceed to Step 5
- `"ready": false` or error → investigate. Read the server logs, check for port conflicts, missing dependencies, or build errors. Fix the issue and retry. Do not just report the error — help resolve it.

#### Step 5: Show Preview URL

Display the preview URL prominently:

```
┌────────────────────────────────────────────┐
│  Preview running at:                       │
│  http://localhost:{port}                   │
│                                            │
│  Open this URL in your browser.            │
│  The server stays running until you stop   │
│  it or end the session.                    │
└────────────────────────────────────────────┘
```

The port comes from the dev server status output (default: 3000 for supabase-nextjs).

## Stopping the Preview

The user can ask to stop the preview at any time in chat (e.g., "stop preview", "kill the server"). When asked:

```bash
uv run "${SHIPWRIGHT_PLUGIN_ROOT}/../../shared/scripts/dev_server.py" \
  stop --cwd ${SHIPWRIGHT_PROJECT_ROOT}
```

The dev server also stops automatically when the Claude Code session ends (state file cleanup).

## Profile Extensibility

Preview uses the `dev_server` configuration from the stack profile JSON (`shared/profiles/{profile}.json`). When adding a new stack profile (e.g., SQLite + Flask, or Postgres + Django), define the `dev_server` section:

```json
{
  "dev_server": {
    "command": "npm run dev",
    "port": 3000,
    "ready_timeout_seconds": 60,
    "ready_path": "/"
  }
}
```

The `dev_server.py` shared script reads this configuration automatically. No changes to the preview plugin are needed for new stacks — only the profile JSON.
