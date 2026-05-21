---
name: shipwright-adopt
description: |
  Onboards an EXISTING repository (brownfield) into the Shipwright SDLC.
  Analyzes the codebase (stack, routes, conventions, git history), generates
  CLAUDE.md + .shipwright/agent_docs + planning specs + compliance artifacts + all six
  shipwright_*_config.json, and writes a baseline E2E suite from a
  Playwright crawl when possible. After completion, /shipwright-iterate
  takes over for all future changes. The phase-router UserPromptSubmit
  hook is plugin-owned (registered in shipwright-iterate's own
  hooks.json); no project-level install is performed.

  TRIGGER when: user wants to onboard a brownfield repo, add Shipwright to
  an existing project, run /shipwright-adopt, import a legacy codebase, or
  bootstrap Shipwright on code that already exists.

  DO NOT TRIGGER when: shipwright_run_config.json already exists (use
  /shipwright-iterate), the user is starting a fresh greenfield project
  (use /shipwright-project), or the task is a normal SDLC operation
  (build/test/deploy/changelog/compliance).
license: MIT
compatibility: Requires uv (Python 3.11+), a git repository, and optionally
  Node + @playwright/test for route-discovery via crawl.
---

# /shipwright-adopt — Onboarding Workflow

This skill runs **once per repository**. After it completes, the project
behaves like a natively-built Shipwright project and all other skills
(`/shipwright-iterate`, `/shipwright-compliance`, `/shipwright-test`,
`/shipwright-deploy`) work as expected.

## Flags

```
/shipwright-adopt [--dry-run]
                  [--profile <name>]
                  [--scope full_app|library|cli]
                  [--include-nested]
                  [--exclude-path <path>]...
                  [--skip-crawl]
                  [--crawl-base-url <url>]
                  [--crawl-auth-token <token>]
                  [--crawl-max-depth <n>]
                  [--crawl-max-pages <n>]
                  [--no-backfill-events]
                  [--no-sync]
                  [--planning-split <name>]   # default: 01-adopted
```

## Procedure (Steps A–H)

### Step A — Pre-flight

Run:

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/checks/setup_adopt.py" \
  --project-root <cwd> \
  [--exclude-path <p>]...
```

The script emits JSON with `ok`, `hard_stops`, `warnings`,
`nested_projects`, and `existing_artifacts`. If `ok=false`, **halt and
show the reason** — no further steps. If `nested_projects` is non-empty,
**ask the user** via `AskUserQuestion` for each one: include / exclude /
adopt separately. Default recommendation: `Exclude`.

If `existing_artifacts` is non-empty, **show the list** to the user and
**ask** via `AskUserQuestion`:

> "Found N existing artifacts that adopt would touch:
>   • CLAUDE.md
>   • .shipwright/agent_docs/decision_log.md (will be auto-merged with new ADRs)
>   • .shipwright/agent_docs/architecture.md (will be backed up + overwritten)
>   • ...
>
> Adopt automatically backs each one up to .shipwright/adopt/backups/
> before any write. Load-bearing CLAUDE.md (>1 KB) is preserved untouched
> and adopt's suggested content is written to .shipwright/adopt/CLAUDE.md.adopt-suggested.
> Continue?"

Default recommendation: `Continue` (preservation is on by default; the
user can review every change via the `.preserved` files afterward).

### Step B — Codebase Analysis (Layer 1)

Run:

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/tools/analyze_codebase.py" \
  --project-root <cwd> \
  [--exclude-path <p>]... \
  [--profile-hint <name>] \
  --output <cwd>/.shipwright/adopt/snapshot.json
```

This writes the structured snapshot with stack, profile-match,
conventions, CI, test frameworks, folder layers, features (AST), git
summary, nested projects. Pure read-only.

### Step B.5 — Playwright Route-Discovery (Layer 1.5, optional)

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

### Step B.8 — Semantic Enrichment (Layer 2, inline)

Read `.shipwright/adopt/snapshot.json` and (if present)
`.shipwright/adopt/routes.json`. Read **sample files** for context:

- `README.md` at the project root
- 3–5 top-level route files (sorted by LOC; from `features[].source_file`)
- 2–3 key domain files (from `folder_layers` with name `domain` or `core`)
- Top-5 commit bodies for `git.major_refactor_commits[].sha` via
  `git show --stat <sha>`
- A handful of screenshots from `.shipwright/adopt/screenshots/` if Step
  B.5 produced any

Write a **strict JSON object** to `.shipwright/adopt/enrichment.json`:

```json
{
  "product_description": "2–3 paragraphs explaining the product functionally.",
  "features": [
    {
      "route": "/dashboard",
      "label": "Active-project dashboard",
      "description": "User views current active Shipwright projects...",
      "acceptance_draft": "Given the user is logged in, when they land on /dashboard, then..."
    }
  ],
  "architecture_prose": "Data-flow narrative — Layers -> interactions -> external systems.",
  "architecture_diagram": "```\n  <ASCII box drawing>\n```",
  "conventions_prose": "Human-readable rules distilled from linter configs + code sampling.",
  "adrs": [
    {
      "commit_sha": "abc123",
      "context": "...",
      "decision": "...",
      "consequences": "..."
    }
  ]
}
```

**Quality leitplanken** (respect these in the inline enrichment):

- **Code > Prose**: if README contradicts the actual folder structure,
  the code wins. Describe what the code *does*, not what old docs *said*.
- **Don't invent.** If unclear, write `"TBD"` — the Layer-3 review and
  `/shipwright-iterate` will refine.
- **No marketing copy.** Keep descriptions nüchtern, technical,
  IREB-compatible.
- **ASCII box diagram style**: match the existing convention used in
  `webui/.shipwright/agent_docs/architecture.md` — plain ASCII box-drawing characters
  (`┌`, `─`, `│`, `└`), no Mermaid. Size: roughly 40–60 lines.

**Validation + fallback** (4.4). `generate_adoption_artifacts.py` validates
`enrichment.json` against a strict schema before consuming it. If the file
exists but is malformed (missing required keys, wrong types, missing
`route` on a feature, missing `decision`/`consequences` on an ADR), Step E
fails loud with a clear error — adopt does NOT silently fall back to
"snapshot+routes only" when Layer-2 was attempted.

If `enrichment.json` does not exist at all, a deterministic minimal
fallback is generated from the snapshot + routes. Every text field is
clearly labeled as a placeholder ("TBD — Layer-2 enrichment skipped..."),
the file carries `_fallback: true`, and the SKILL.md handoff surfaces a
loud "Layer-2 was skipped" notice. No invented prose, no plausible-sounding
lies.

### Step C — Interview (AskUserQuestion, only when Layer 1 is unsure)

Ask **one question per turn** and only when the answer cannot be
inferred from Layer 1. Examples:

- profile.confidence < 0.6 → which stack profile?
- scope ambiguity (both `src/` and `bin/`) → full_app | library | cli?
- nested_projects → include / exclude / adopt-separately (always ask)
- no test frameworks detected → mark test-complete or pending?
- no build command detected → ask for the explicit command

Also present the `enrichment.product_description` to the user once, so
they can edit before it lands in CLAUDE.md/spec.md.

### Step D — Dry-Run Branch (if `--dry-run`)

Skip Steps E–H. Invoke `dry_run_reporter.plan_standard_writes(...)` and
print the report. Exit 0.

### Step E — Artifact Generation

Run:

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/tools/generate_adoption_artifacts.py" \
  --project-root <cwd> \
  [--no-sync] [--no-backfill-events] \
  [--scope <full_app|library|cli>] \
  [--profile <name>] \
  [--split-name <name>]
```

Writes — **in order**:
1. `CLAUDE.md`
2. `.shipwright/agent_docs/{architecture,conventions,decision_log,build_dashboard}.md`
3. `.shipwright/planning/<split>/spec.md`
4. The six required configs (project / plan / build / iterate /
   compliance / + optional sync — `--no-sync` skips it), and
   **`shipwright_run_config.json` LAST**. The iterate config carries
   the documented opt-out fields (`external_review.feedback_iterations`
   for plan/iterate-mode review, `external_code_review.enabled` for the
   code-review cascade); both are independent gates and the cascade
   defaults to enabled.
5. `shipwright_events.jsonl` with one `adopted` event + optional
   backfill.
6. (No project-level hook write.) The `suggest_iterate` UserPromptSubmit
   hook is plugin-owned, registered in
   `plugins/shipwright-iterate/hooks/hooks.json`. If the target project
   carries a legacy `${CLAUDE_PLUGIN_ROOT}` entry from a pre-2026-05-05
   adopt run, the user must remove it manually from
   `.claude/settings.json` to silence the Claude Code "hook is not
   associated with a plugin" red-banner error. The plugin-registered
   hook fires regardless.
7. `e2e/flows/adopted-baseline.spec.ts` if routes.json exists.
8. **Visual frontend documentation (Tier 5).** Three artifacts at
   canonical paths so /shipwright-design / /shipwright-iterate consume
   them without manual fix-up:

   - **`.shipwright/designs/visual-guidelines.md`** — design-system
     view in the canonical schema (typography / colors / spacing /
     radius / shadows / component patterns). Slot-filled from extracted
     tokens; unfilled slots stay `_TBD_` rather than inventing values.
     This is the path /shipwright-design reads, so adopted projects
     can run /shipwright-design without re-authoring the file.
   - **`.shipwright/agent_docs/design_tokens.md`** — raw audit trail of
     Tailwind colors / spacing / fontSize (parsed from
     `tailwind.config.{ts,js,mjs,cjs}` via regex — no Node runtime in
     adopt) plus `:root { --var: ... }` CSS variables from
     `src/**/*.css`. Configs that build their theme dynamically yield
     empty maps; the operator can fill via /shipwright-iterate.
   - **`.shipwright/agent_docs/component_inventory.md`** — architecture
     doc: components table (name, path, props count, usage count)
     sorted by usages descending, plus a screenshot link block. Renamed
     from the legacy `guideline.md`. Adopt automatically backs the
     legacy filename up to `.shipwright/adopt/backups/` if it's present
     from a pre-Fix-1 adopt run.
   - **`.shipwright/agent_docs/visual/screenshots/`** — copies of
     `.shipwright/adopt/screenshots/` (the gitignored crawl workdir)
     so the docs reference a stable, committed location. Re-running
     adopt refreshes them.

   Opt-in: written only when the project has a frontend signal
   (multi-service frontend, components under
   src/components/src/ui/src/app, tailwind.config.*, or `:root` CSS
   variables). Backend-only profiles produce `wrote_docs: false` in
   `results.visual_docs` and write nothing under `.shipwright/`.

9. **Prior-art harvest** (Fix 2). Before writing thin auto-generated
   `decision_log.md` / `conventions.md`, adopt runs
   `prior_art_harvester` to copy any maintainer-written knowledge
   forward. Recognized sources (first hit wins, deterministic, no LLM):

   - **Decision logs:** `docs/adr/`, `docs/architecture/decisions/`,
     `docs/decisions/`, `<root>/ADRs/`, `<root>/decision_log.md`,
     `<root>/agent_docs/decision_log.md`, README "Architecture" /
     "Design decisions" sections.
   - **Conventions:** `CONTRIBUTING.md`, `STYLEGUIDE.md`,
     `docs/conventions.md`, README "Conventions" / "Code style"
     sections, AGENTS.md / CLAUDE.md "Conventions" sections.

   When found, the harvested content is appended verbatim with an
   attribution header documenting the source path. When no source
   matches, adopt falls back to today's auto-generated content. No
   merging, no NLP — operators see exactly what was there.

10. **Sibling-test acceptance criteria** (Fix 5). For every FR with
    a non-test `source_file`, adopt scans conventional sibling test
    paths (`<stem>.test.{ts,tsx,js,jsx,py}`, `<stem>.spec.*`,
    `__tests__/<stem>.test.*`, `tests/<stem>.test.*`,
    `tests/test_<stem>.py`) and harvests `describe(...)` / `it(...)` /
    `test(...)` strings (Jest / Vitest / Mocha) plus `def test_*`
    functions with their docstrings (pytest). Up to 10 ACs per FR;
    enrichment-supplied `acceptance_draft` always wins when present.
    Test files themselves are filtered out of the FR list (Fix 3a).

11. **TODO / FIXME inventory** (Fix 6). After artifact generation,
    adopt ripgreps `\b(TODO|FIXME|HACK|XXX|DEPRECATED)\b:?` over source
    files, respecting `.gitignore` (`git check-ignore -z --stdin`)
    and skipping universal artifact dirs (node_modules, dist, build,
    vendor, etc.). Output: `.shipwright/agent_docs/known_issues.md`
    with a per-marker summary table, sections per marker type, and
    `file:line — text` bullets (per-bullet 200-char cap). Cap of 200
    total entries (top 50 listed, rest summarized as counts). Empty-
    state file is written when zero markers are found — operators
    expect the file to exist either way.

12. **See-also cross-links** (Fix 4). When discoverable, adopt appends
    a `## See also` block to `architecture.md` linking
    `<root>/README.md` (always when present), and
    `<root>/docs/{guide,manual,usage,getting-started,handbook}.md`
    (only when >100 lines). `build_dashboard.md` similarly links
    `<root>/CHANGELOG.md` when present. No broken links — sections are
    omitted entirely when nothing matches.

13. **Security CI scaffold.** Adopt copies the dormant scanner-chain
    workflow into `<root>/.github/workflows/security.yml` so brownfield
    repos start with a Phase-B-ready security baseline. Behavior:
    - **Absent** → write the template verbatim. Workflow ships with
      only `workflow_dispatch:` active; `pull_request:` and `schedule:`
      triggers stay commented until the user activates them at Phase B.
    - **Present** → preserve the existing file untouched, regardless
      of contents. Pre-existing CodeQL workflows, hand-rolled scanner
      configs, and earlier shipwright templates all win.

    The convention lock at `shared/scripts/lib/security_workflow.py`
    is the single source of truth for the deployed-file path, the
    critical-gate step id (`shipwright-critical-gate`), the
    minimum-required permissions, and the SARIF category. The drift
    test at `shared/tests/test_security_workflow_convention.py` pins
    the template at `shared/templates/github-actions/security.yml.template`
    against those constants — the scaffolder cannot drift from what
    `/shipwright-compliance` Group A5 audits.

    Activation guidance — including the GitHub Actions
    permission-implicit-`none` footgun, fork-PR semantics, and
    Phase-B prerequisites — lives at `docs/security-ci-setup.md`.
    The scaffolder result lands in `results.security_ci` as
    `{wrote, path, reason}` so the Step H handoff banner can show
    "installed (dormant)" vs "preserved" without re-stat'ing the file.

14. **CI workflow scaffold (profile-aware).** Adopt picks the CI
    template that matches the stack profile detected earlier in the
    pipeline (`snapshot.profile.matched`) and writes it to
    `<root>/.github/workflows/ci.yml`. Three profiles ship templates
    today:
    - `supabase-nextjs` → `ci-supabase-nextjs.yml.template` (single
      `test` job, security + deploy chained, Node 22.x)
    - `vite-hono` → `ci-vite-hono.yml.template` (two-workspace:
      `client-checks` + `server-checks`, both matrixed)
    - `python-plugin-monorepo` → `ci-python-plugin-monorepo.yml.template`
      (uv-driven, ruff + pyright + plugin-tests + integration-tests)

    Every template ships with the **cross-platform OS matrix**
    (`ubuntu-latest` + `windows-latest`, `fail-fast: false`) so
    OS-coupled portability bugs surface at PR time instead of leaking
    through to runtime. Originating regression: `shipwright-webui`
    v0.8.5 — 4 path-self-heal tests silently passed on the Windows dev
    machine and silently failed on Linux CI for 9 push-runs because
    the hand-written `ci.yml` only ran on `ubuntu-latest`.

    Same idempotency contract as Security CI: dormant default
    (`workflow_dispatch:` only), pre-existing `ci.yml` files are
    preserved bit-for-bit. Distinct reason codes
    (`profile_unresolved` vs `no_template_for_profile`) surface
    snapshot-parsing failures upstream rather than masking them as
    "no template available".

    The convention lock at `shared/scripts/lib/ci_workflow.py` is the
    SSoT for the profile→template map, deployed paths, and the
    cross-platform-matrix invariant. Drift test at
    `shared/tests/test_ci_workflow_convention.py` pins every template
    against those constants. The scaffolder result lands in
    `results.ci_workflow` as `{wrote, path, reason}`.

15. **Claude-Review workflow scaffold.** Adopt writes the independent
    Claude-Code-review workflow to `<root>/.github/workflows/claude-review.yml`.
    Profile-agnostic — single template, no profile branching.

    Unlike CI + Security, this workflow is **NOT dormant by default**:
    `on: pull_request` is the active trigger because firing on PR
    events is the workflow's entire purpose. Same byte-equal idempotency
    contract (pre-existing files preserved). Result lands in
    `results.claude_review_workflow`.

    Origin: commit `8aac61d` (Anthropic Architect Certification best
    practice — "write in one session, review in a different one").

**Vite DX templates (offer-only, NEVER auto-applied).** If
`package.json` lists `vite` as a dependency (any Vite-based stack), the
adoption handoff includes a one-line opt-in note pointing to:

- `shared/templates/vite.config.ts.template` — mode-gated dev plugin
  slot, allowedHosts wildcard, sensible defaults. Useful only if the
  user wants to start over from a clean baseline.
- `shared/templates/dev-error-overlay.tsx.template` +
  `dev-banner.tsx.template` — drop-in dev-mode React components for
  runtime-error modals and a visible dev-mode pill. Both are
  `import.meta.env.DEV`-gated so they no-op in prod.
- `shared/templates/path-helpers.ts.template` +
  `path-helpers.test.ts.template` — `pickPathModule(input)` heuristic
  for cross-platform path classification (returns `path.win32` or
  `path.posix` based on input shape). Drop into any Node project that
  needs to parse path strings whose platform-origin differs from the
  runner's native `path` module. The empirical Vitest suite covers
  Windows + POSIX + UNC + edge cases; passes identically on both OSes.
  Origin: `shipwright-webui` v0.8.5 cross-platform regression.

**Existing `vite.config.ts` is NEVER overwritten.** The handoff lists
the templates so the user can copy/adapt them at their own pace; adopt
itself touches no Vite files.

**Features merge (4.2)**. Layer-1 AST features and Layer-1.5 crawl routes
are unioned by route key — neither side is silently dropped when the
other is non-empty. Each merged feature carries an `origin` of
`ast | crawl | ast+crawl`. spec.md therefore lists both API FRs (from
AST scan of route handlers) and UI FRs (from the crawl), giving a
complete picture for downstream consumers.

**Gitignore awareness (4.1)**. After all writes, the tool runs
`git check-ignore` against every output path. The result lands in
`results.gitignore_report` as `{total, gitignored: [...], majority_gitignored: bool}`.

If `majority_gitignored` is true (≥50% of artifacts excluded), surface
a `**GITIGNORED OUTPUTS**` block in the handoff and ask the user via
`AskUserQuestion`:

> "N of M adopt-generated artifacts are excluded by .gitignore (e.g.
> .shipwright/agent_docs/, .shipwright/planning/, shipwright_*_config.json). They will not be
> committed unless you adjust .gitignore. Continue without changes,
> stop and review .gitignore, or proceed and adjust manually after?"

### Step E.5 — Env Scaffold (`.env.local`)

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

### Step E.16 — Triage Inbox Scaffold

After the env scaffold, adopt MUST initialize the triage inbox so
hook-emitted findings (Phase-Quality Tier-1 FAILs, Compliance audit
findings) have a place to land from the first iterate onward.

Run:

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/tools/scaffold_triage_inbox.py" \
  --project-root <project_root> \
  --json
```

The scaffolder is idempotent. It does three things:

1. **Create `.shipwright/triage.jsonl`** with a single schema-header
   line: `{"v":1,"schema":"triage","created":"<ISO-8601 Z>"}`.
   Producers (`audit_phase_quality_on_stop.py`,
   `audit_detector.mirror_findings_to_triage`) auto-bootstrap the
   header if missing, but writing it here guarantees a known shape
   for the operator's first git-status view.
2. **Create `.shipwright/agent_docs/triage_inbox.md`** with the empty
   "No triage items pending. ✓" skeleton. The Stop-hook
   `aggregate_triage_on_stop.py` regenerates this file after every
   iterate finalize.
3. **Update `.gitignore`** to cover `.shipwright/triage.jsonl` and
   `.shipwright/triage.jsonl.lock`. Idempotent: detects existing lines
   and skips them. Creates `.gitignore` if absent.

The result dict surfaced under `results["triage_inbox"]` carries
`{wrote, results: {jsonl, markdown, gitignore}}` — Step H reads this
to print a one-line summary in the handoff banner. Action values:
`created`, `preserved`, `appended`, `already-present`.

Behavior contract:

- **Idempotent.** Safe to re-run on an already-adopted project; no
  pre-existing file is rewritten.
- **No producer wiring side-effects.** Just the three artifacts; the
  Stop-hook that regenerates `triage_inbox.md` is wired by the iterate
  plugin's `hooks.json`, not by adopt.
- **No migration of existing `known_issues.md` entries.** The two
  files coexist; `known_issues.md` continues to capture TODO/FIXME
  source markers, `triage_inbox.md` captures hook-emitted findings.
  Reference: `docs/guide.md` § 4.11 for the pattern.

### Step F — Compliance Seeding

Run:

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/tools/seed_adopt_compliance.py" \
  --project-root <cwd>
```

Calls `update_compliance.py` for each retroactive phase (`project`,
`plan`, `build`, `test`). Falls back to direct-lib imports if the script
cannot be located. Populates `.shipwright/compliance/sbom.md`,
`.shipwright/compliance/change-history.md`, `.shipwright/compliance/traceability-matrix.md`,
`.shipwright/compliance/test-evidence.md`, `.shipwright/compliance/dashboard.md`.

### Step G — Layer-3 Review

Run `review_runner.run_review(...)` (from `scripts/lib/review_runner.py`).
Writes `.shipwright/adopt/review.md`. Without any API key, the review
documents `status: skipped, reason: no_api_key` — acceptable.

If the review returns HIGH/MAJOR findings about hallucinations or
contradictions, **AskUserQuestion**: `fix (re-run enrichment)` /
`accept with caveat` / `abort`.

### Step H — Validate, Commit, Handoff

1. Validate:

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/checks/validate_adoption.py" \
  --project-root <cwd>
```

The output now carries `errors` AND `warnings`. Hard-stop on
`errors[]`. **Surface `warnings[]`** in the handoff (currently includes
the "few ADRs for repo size" plausibility check) — they're informational,
not blocking.

If `.shipwright/adopt/preservation_log.json` exists, also surface a
"Preserved files" section in the handoff: count of files preserved, list
of `.preserved` backup paths, and a special call-out if any
`action: skipped_loadbearing` entry is present (the user must review
`.shipwright/adopt/CLAUDE.md.adopt-suggested` and merge manually).

2. If validation passes, create a single Conventional Commit:

```
chore(shipwright): adopt repository into Shipwright SDLC

Adopted via /shipwright-adopt using profile=<profile>, scope=<scope>.
Inferred <N> functional requirements from existing codebase.
Seeded compliance artifacts (SBOM, change-history, RTM skeleton).
Test evidence starts collecting from next /shipwright-test run.

See .shipwright/agent_docs/decision_log.md for the adoption ADR
(id is `max(existing) + 1`, 3-digit zero-padded — ADR-001 on greenfield).
```

3. Print a handoff message. The `Env scaffold:` line and the optional
   "Edit .env.local" block are populated from `results["env_local"]`
   (see Step E.5). Render the "Edit .env.local" block whenever
   `missing_keys` is non-empty — independently of `action`, so an
   `unchanged` outcome with placeholder-only entries STILL prompts the
   user. The list of keys MUST be derived from
   `results["env_local"]["missing_keys"]` (which already merges the
   profile's `required_env_vars` with the framework keys), NOT
   hardcoded:

```
================================================================================
ADOPTION COMPLETE
================================================================================
Profile:       <matched>
Scope:         <full_app|library|cli>
Features:      <N> FR(s) in .shipwright/planning/<split>/spec.md
Crawl:         <enabled|skipped: <reason>>
Review:        <completed|skipped: <reason>>
Security CI:   <installed (dormant) | preserved (existing file untouched)>
Env scaffold:  <created|updated|unchanged|skipped: <reason>>  → <abs path to .env.local>
Commit:        <sha>

Next steps:
  •  Edit .env.local — fill in the keys still flagged as missing:
       <one bullet per key in results["env_local"]["missing_keys"]>
  •  /shipwright-iterate       — for all future feature/bug/refactor work
  •  /shipwright-test          — to collect first real test-evidence
  •  /shipwright-compliance    — on-demand detective audit of artifacts
  •  /shipwright-design        — to add UI mockups (optional)

Do NOT use /shipwright-project on this repo — adoption replaces it.
Do NOT use /shipwright-plan or /shipwright-build directly — /shipwright-iterate
handles both for adopted projects.
================================================================================
```

If `results["env_local"]["action"] == "skipped"` AND
`reason == "gitignore_enforcement_failed"`, surface a loud line in
the banner instead of the "Edit .env.local" block:

```
  ⚠  Env scaffold skipped — fix .gitignore permissions and re-run /shipwright-adopt
     ({results["env_local"]["error"]}). No .env.local was written.
```

## Backfilling `shipwright_iterate_config.json` on already-adopted projects

Projects adopted before 2026-05-05 ship without
`shipwright_iterate_config.json`. To backfill:

```bash
uv run python -c "
from pathlib import Path
import sys
sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
from lib.config_writer import write_iterate_config
write_iterate_config(Path('.'))
"
```

This writes the config with the documented defaults
(`external_review.feedback_iterations: 1`,
`external_code_review.enabled: true`). Both fields are operator opt-out
knobs — flip after the file exists, no re-adopt needed. The framework
ignores the file's absence (defaults stay in effect), so this is purely
about giving the operator a flat surface to edit.

## References

- `references/codebase-analysis.md` — detector heuristics and edge cases
- `references/feature-inference.md` — Playwright crawl vs AST fallback rules
- `references/interview-protocol.md` — when to ask, when to infer
- `references/artifact-templates.md` — template slot mapping
- `references/nested-project-policy.md` — webui-style nested-project handling

## Integration

- **Phase-Quality audit**: Adopt registers as phase `adopt` in
  `shared/scripts/lib/phase_quality.py` (`PLUGIN_TO_PHASE`, `C4_PHASES`,
  `_WORKFLOW_PHASE_DISPATCH`). `shared/scripts/tools/verifiers/adopt_compliance.py`
  runs A1–A8 canon checks on every Stop hook.
- **Cross-plugin docs**: `plugins/shipwright-project/skills/project/SKILL.md`
  Step A.1 points users to /shipwright-adopt when code already exists.
- **Marketplace**: this plugin is registered in `scripts/update-marketplace.sh`
  so it lands in `~/.claude/plugins/cache/shipwright/` after sync.
