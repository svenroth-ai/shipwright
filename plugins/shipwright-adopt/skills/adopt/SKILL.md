---
name: shipwright-adopt
description: |
  Onboards an EXISTING repository (brownfield) into the Shipwright SDLC.
  Analyzes the codebase (stack, routes, conventions, git history), generates
  CLAUDE.md + agent_docs + planning specs + compliance artifacts + all six
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

The script emits JSON with `ok`, `hard_stops`, `warnings`, and
`nested_projects`. If `ok=false`, **halt and show the reason** — no
further steps. If `nested_projects` is non-empty, **ask the user** via
`AskUserQuestion` for each one: include / exclude / adopt separately.
Default recommendation: `Exclude`.

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
language (`typescript`, `javascript`, `python`, `ruby`, `php`), a
`dev`-command was detected, and `--skip-crawl` was not passed.

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
all branches:

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/playwright_setup.py \
  --cwd <cwd> --profile <matched>
# (start command from one of the three branches above)
uv run ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/route_crawler.py \
  --cwd <cwd> --base-url <primary_url_from_dev_server_start_output> \
  --max-depth 3 --max-pages 50 \
  --output <cwd>/.shipwright/adopt/routes.json \
  --screenshots <cwd>/.shipwright/adopt/screenshots/
uv run ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/dev_server.py stop --cwd <cwd>
```

The `--base-url` is read from the `url` field in `dev_server.py
start`'s JSON output (top-level — points to the primary service in
multi-service mode).

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
  `webui/agent_docs/architecture.md` — plain ASCII box-drawing characters
  (`┌`, `─`, `│`, `└`), no Mermaid. Size: roughly 40–60 lines.

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
2. `agent_docs/{architecture,conventions,decision_log,build_dashboard}.md`
3. `planning/<split>/spec.md`
4. The five required configs, then `shipwright_sync_config.json` (unless
   `--no-sync`), and **`shipwright_run_config.json` LAST**.
5. `shipwright_events.jsonl` with one `adopted` event + optional
   backfill.
6. `.claude/settings.json` with the `suggest_iterate` UserPromptSubmit
   hook (idempotent merge).
7. `e2e/flows/adopted-baseline.spec.ts` if routes.json exists.

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

2. If validation passes, create a single Conventional Commit:

```
chore(shipwright): adopt repository into Shipwright SDLC

Adopted via /shipwright-adopt using profile=<profile>, scope=<scope>.
Inferred <N> functional requirements from existing codebase.
Seeded compliance artifacts (SBOM, change-history, RTM skeleton).
Test evidence starts collecting from next /shipwright-test run.

See agent_docs/decision_log.md ADR-0001.
```

3. Print a handoff message:

```
================================================================================
ADOPTION COMPLETE
================================================================================
Profile:       <matched>
Scope:         <full_app|library|cli>
Features:      <N> FR(s) in planning/<split>/spec.md
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
