---
name: shipwright-adopt
description: |
  Onboards an EXISTING repository (brownfield) into the Shipwright SDLC.
  Analyzes the codebase (stack, routes, conventions, git history), generates
  CLAUDE.md + .shipwright/agent_docs + planning specs + compliance artifacts + all six
  shipwright_*_config.json, installs the suggest_iterate hook, and writes
  a baseline E2E suite from a Playwright crawl when possible. After
  completion, /shipwright-iterate takes over for all future changes.

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
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/checks/setup_adopt.py \
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
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/tools/analyze_codebase.py \
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
uv run ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/dev_server.py start \
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
uv run ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/dev_server.py start \
  --cwd <cwd> --services-json "$SERVICES_JSON"
```

**Branch 3 — single-service / fallback.** Same as Branch 1 with
whatever profile matched (`generic` if nothing else):

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/dev_server.py start \
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

uv run ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/playwright_setup.py \
  --cwd <cwd> --profile <matched> \
  [--multi-service-json "$MULTI_SERVICE_JSON"]   # only when multi-service detected

# (start command from one of the three branches above)

uv run ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/route_crawler.py \
  --cwd <cwd> --base-url <primary_url_from_dev_server_start_output> \
  --max-depth 3 --max-pages 50 \
  --output <cwd>/.shipwright/adopt/routes.json \
  --screenshots <cwd>/.shipwright/adopt/screenshots/ \
  [--config-dir <cwd>/<primary-frontend-root>]   # only when multi-service detected

uv run ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/dev_server.py stop --cwd <cwd>
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
PORT=3848 VITE_PORT=5174 uv run ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/dev_server.py start \
  --cwd <cwd> --profile <matched>
```

If the dev-server fails to become healthy within its profile's
`ready_timeout_seconds`, OR the crawl produces zero routes, **skip**
and fall back to AST-based `features[]` from the snapshot. Document
the skip reason in the eventual handoff.

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
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/tools/generate_adoption_artifacts.py \
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
4. The five required configs, then `shipwright_sync_config.json` (unless
   `--no-sync`), and **`shipwright_run_config.json` LAST**.
5. `shipwright_events.jsonl` with one `adopted` event + optional
   backfill.
6. `.claude/settings.json` with the `suggest_iterate` UserPromptSubmit
   hook (idempotent merge).
7. `e2e/flows/adopted-baseline.spec.ts` if routes.json exists.
8. `.shipwright/agent_docs/design_tokens.md` + `.shipwright/agent_docs/guideline.md` +
   `.shipwright/agent_docs/visual/screenshots/*.png` — **visual frontend
   documentation (Tier 5)**. Opt-in: only written when the project has
   a frontend signal (multi-service frontend, components under
   src/components/src/ui/src/app, tailwind.config.*, or `:root` CSS
   variables). Backend-only profiles produce `wrote_docs: false` in
   `results.visual_docs` and write nothing under `.shipwright/agent_docs/visual/`.

   - **design_tokens.md** lists Tailwind colors / spacing / typography
     (parsed from `tailwind.config.{ts,js,mjs,cjs}` via regex — no Node
     runtime in adopt) plus `:root { --var: ... }` CSS variables from
     `src/**/*.css`. Configs that build their theme dynamically yield
     empty maps; the operator can fill via `/shipwright-iterate`.
   - **guideline.md** is a single-page design-system summary: top color
     swatches, typography scale, a components table (name, path, props
     count, usage count) sorted by usages descending, and a link block
     for the persisted screenshots.
   - **visual/screenshots/** carries copies of `.shipwright/adopt/screenshots/`
     (the gitignored crawl workdir) so the docs reference a stable,
     committed location. Re-running adopt refreshes them.

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

### Step F — Compliance Seeding

Run:

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/tools/seed_adopt_compliance.py \
  --project-root <cwd>
```

Calls `update_compliance.py` for each retroactive phase (`project`,
`plan`, `build`, `test`). Falls back to direct-lib imports if the script
cannot be located. Populates `compliance/sbom.md`,
`compliance/change-history.md`, `compliance/traceability-matrix.md`,
`compliance/test-evidence.md`, `compliance/dashboard.md`.

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
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/checks/validate_adoption.py \
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

See .shipwright/agent_docs/decision_log.md ADR-0001.
```

3. Print a handoff message:

```
================================================================================
ADOPTION COMPLETE
================================================================================
Profile:       <matched>
Scope:         <full_app|library|cli>
Features:      <N> FR(s) in .shipwright/planning/<split>/spec.md
Crawl:         <enabled|skipped: <reason>>
Review:        <completed|skipped: <reason>>
Commit:        <sha>

Next steps:
  •  /shipwright-iterate       — for all future feature/bug/refactor work
  •  /shipwright-test          — to collect first real test-evidence
  •  /shipwright-compliance    — on-demand detective audit of artifacts
  •  /shipwright-design        — to add UI mockups (optional)

Do NOT use /shipwright-project on this repo — adoption replaces it.
Do NOT use /shipwright-plan or /shipwright-build directly — /shipwright-iterate
handles both for adopted projects.
================================================================================
```

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
