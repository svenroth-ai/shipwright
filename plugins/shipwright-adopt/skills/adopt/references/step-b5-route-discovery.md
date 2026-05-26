# Step B.5 — Playwright Route-Discovery (Layer 1.5, optional)

**Gate**: only run if `snapshot.stack.primary_language` is a web-capable
language (`typescript`, `javascript`, `python`, `ruby`, `php`),
`--skip-crawl` was not passed, AND **at least one** of:

- `snapshot.commands.dev` is non-null (root `package.json` has a `dev`
  script — the legacy single-package signal), OR
- `snapshot.profile.matched != "generic"` (a stack profile matched, so
  Branch 1 of the Service-Resolution hierarchy below is authoritative
  for service start), OR
- `snapshot.stack.multi_service.detected == true` (multi-service layout
  detected — e.g. monorepo with `client/package.json` + `server/package.json`
  but no root `package.json`; Branch 2 of the hierarchy applies).

Why three signals: in the multi-service model (introduced 2026-04-25,
`dev_server.py` v0.5.0) the root `package.json` is no longer the
primary signal for `dev`. `analyze_codebase.py::_commands_from_pkg`
only reads `<root>/package.json`, so monorepos legitimately yield
`commands.dev = null`. A profile-match or multi-service detection is
sufficient to enter the Service-Resolution hierarchy below — closing
the gate on `commands.dev` alone would make the crawl unreachable for
exactly the projects that have the richest service metadata.

**Service-resolution hierarchy** (introduced 2026-04-25 with multi-
service `dev_server.py` v0.5.0). Choose ONE of three branches:

**Branch 1 — matched profile (any non-generic).** If
`snapshot.profile.matched != "generic"`, the matched profile is
authoritative. It knows what to start (single-service via `dev_server`
block, or multi-service via `services: [...]` array). Run:

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/dev_server.py" start \
  --cwd <cwd> --profile <matched>
```

The detector's `multi_service` signal is informational here; the
profile's intent wins.

**Branch 2 — generic match + multi-service detected.** If
`snapshot.profile.matched == "generic"` AND
`snapshot.stack.multi_service.detected == true`, build a transient
services array from the detector's output and pass it inline:

- `confidence: high` → proceed without prompting.
- `confidence: medium` + interactive run → ask via `AskUserQuestion`:
  *"Detected multi-service layout: <names>. Run all of them for the
  crawl?"* Default Yes. On Yes → inline path. On No → fall through to
  Branch 3.
- `confidence: medium` + non-interactive run (autonomous adopt,
  `--non-interactive`, missing `AskUserQuestion`) → fall through to
  Branch 3 silently. **Autonomous adopt never spawns extra services on
  a guess.**

```bash
SERVICES_JSON='[
  {"name":"<name>","command":"<dev_command>","port":<port>,
   "host":"localhost","scheme":"http","ready_path":"/"},
  ...
]'
uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/dev_server.py" start \
  --cwd <cwd> --services-json "$SERVICES_JSON"
```

**Branch 3 — single-service / fallback.** Same as Branch 1 with
whatever profile matched (`generic` if nothing else):

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/dev_server.py" start \
  --cwd <cwd> --profile <matched-or-generic>
```

After the dev server is up, run the crawl + stop sequence common to
all branches.

**Multi-service awareness.** If
`snapshot.stack.multi_service.detected == true`, both `playwright_setup`
and `route_crawler` need to pivot into the primary frontend service dir
(e.g. `client/`) — that's where `package.json` and (typically)
`playwright.config.ts` live. Without the pivot:
- `playwright_setup` reads `<cwd>/package.json`, finds none, and `npm install -D @playwright/test` fails at the root.
- `route_crawler` installs the spec at `<cwd>/e2e/`, but `client/playwright.config.ts` defines `testDir: './e2e'` relative to `client/` — Playwright finds no config and falls back to defaults.

```bash
# Compute MULTI_SERVICE_JSON when snapshot.stack.multi_service.detected:
MULTI_SERVICE_JSON='{"detected":true,"services":[<services-array-from-snapshot>]}'
# CONFIG_DIR = primary frontend service root (the entry with primary:true,
# else the entry named "frontend"/"client"/"web", else services[0]).

uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/playwright_setup.py" \
  --cwd <cwd> --profile <matched> \
  [--multi-service-json "$MULTI_SERVICE_JSON"]   # only when multi-service detected

# (start command from one of the three branches above)

uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/route_crawler.py" \
  --cwd <cwd> --base-url <primary_url_from_dev_server_start_output> \
  --max-depth 3 --max-pages 50 \
  --output <cwd>/.shipwright/adopt/routes.json \
  --screenshots <cwd>/.shipwright/adopt/screenshots/ \
  [--config-dir <cwd>/<primary-frontend-root>]   # only when multi-service detected

uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/dev_server.py" stop --cwd <cwd>
```

The `--base-url` is read from the `url` field in `dev_server.py
start`'s JSON output (top-level — points to the primary service in
multi-service mode).

**Avoiding port collisions.** Profiles with port placeholders (e.g.
`vite-hono.json` uses `${PORT:-3847}` / `${VITE_PORT:-5173}`) let adopt
override the bind ports via env, so the crawl never collides with a
user dev server already on the defaults. When running adopt against a
project that uses such a profile, set non-default ports in the
subprocess env BEFORE `dev_server.py start`:

```bash
PORT=3848 VITE_PORT=5174 uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/dev_server.py" start \
  --cwd <cwd> --profile <matched>
```

If the dev-server fails to become healthy within its profile's
`ready_timeout_seconds`, OR the crawl produces zero routes, **skip**
and fall back to AST-based `features[]` from the snapshot. Document
the skip reason in the eventual handoff.

**API mocking semantics.** `SHIPWRIGHT_CRAWL_MOCK_API` (default on)
installs a `context.route('**/api/**')` that **passes GETs through**
to the real backend (so consumers receive real response shapes — both
`{ ... }` and `[ ... ]` — and pages render correctly), and stubs
**only writes** (POST/PUT/PATCH/DELETE) with an empty `{}` 200. This
preserves the crawl-without-side-effects invariant while keeping
object-shape endpoints (e.g. `/api/health`, `/api/diagnostics`) from
crashing consumers that do `data.something`. Set
`SHIPWRIGHT_CRAWL_MOCK_API=0` to disable mocking entirely (writes hit
the real backend) — usually only needed if the test bed lacks a live
API and even GETs need to be stubbed manually upstream.

**Screenshot fall-back signal.** `route_crawler.py` returns
`screenshots_succeeded` and `screenshots_failed` in its summary. Each
route runs in a fresh page (page-isolation invariant), so an isolated
screenshot failure no longer cascades — a low ratio just means a
handful of routes raced their re-renders. If
`screenshots_succeeded == 0` and `routes > 0`, treat as a degraded
crawl (the entire app likely tears down mid-render — common with
router-level guards that redirect on a 401 from a mocked endpoint).
Either retry with `SHIPWRIGHT_CRAWL_MOCK_API=0` in the subprocess env
or fall back to AST features and note the reason in the handoff.

See [feature-inference.md](feature-inference.md) for the crawl-vs-AST
fallback rules.
