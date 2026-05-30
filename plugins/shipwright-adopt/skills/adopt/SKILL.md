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

The Kern below is the thin index — each step's authoritative procedure
lives in `references/step-*.md`. Load the matching reference when the
corresponding step fires.

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

### Step A.0 — Bloat Baseline (must run first)

Generate `shipwright_bloat_baseline.json` BEFORE any other artifact
write, so the Stop-Gate hook has a baseline on the first Stop event:

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/lib/baseline_generator.py" \
  --project-root <cwd>
```

Full procedure → [references/step-a-preflight.md](references/step-a-preflight.md).

### Step A — Pre-flight

Run `setup_adopt.py`. Halt on `ok=false`. Ask via `AskUserQuestion`
about nested projects (default: Exclude) and existing artifacts
(default: Continue — preservation is on by default):

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/checks/setup_adopt.py" \
  --project-root <cwd> [--exclude-path <p>]...
```

Full procedure → [references/step-a-preflight.md](references/step-a-preflight.md).

### Step B — Codebase Analysis (Layer 1)

Write the structured snapshot — stack, profile-match, conventions, CI,
test frameworks, folder layers, AST features, git summary, nested
projects. Pure read-only:

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/tools/analyze_codebase.py" \
  --project-root <cwd> [--exclude-path <p>]... [--profile-hint <name>] \
  --output <cwd>/.shipwright/adopt/snapshot.json
```

Full procedure → [references/step-b-codebase-analysis.md](references/step-b-codebase-analysis.md).
Detector heuristics → [references/codebase-analysis.md](references/codebase-analysis.md).

### Step B.5 — Playwright Route-Discovery (Layer 1.5, optional)

Gated on web-capable language + at least one of (`commands.dev` set,
non-generic profile, multi-service detected). Three branches:
matched-profile, generic+multi-service, single-service fallback.

Multi-service awareness: `playwright_setup` and `route_crawler` must
pivot into the primary frontend service dir. API mocking
(`SHIPWRIGHT_CRAWL_MOCK_API`) passes GETs through, stubs only writes.

Full procedure → [references/step-b5-route-discovery.md](references/step-b5-route-discovery.md).
Crawl-vs-AST fallback rules → [references/feature-inference.md](references/feature-inference.md).

### Step B.8 — Semantic Enrichment (Layer 2, inline)

Read snapshot + routes + sample files (README, top route files, domain
files, top-5 commit bodies, crawl screenshots). Write
`.shipwright/adopt/enrichment.json` (strict schema). Code > Prose;
don't invent; ASCII box-drawing for diagrams; no marketing copy.

`generate_adoption_artifacts.py` validates the schema strictly and
fails loud on malformed `enrichment.json`. Missing file → deterministic
minimal fallback with `_fallback: true` marker.

Full procedure → [references/step-b8-semantic-enrichment.md](references/step-b8-semantic-enrichment.md).

### Step C — Interview (AskUserQuestion, only when Layer 1 is unsure)

One question per turn; ask only when the answer cannot be inferred
from Layer 1. Examples: low profile confidence, scope ambiguity,
nested-project policy, missing test/build commands. Also present
`enrichment.product_description` for user edit.

Full procedure → [references/step-c-interview.md](references/step-c-interview.md).
When-to-ask-vs-infer → [references/interview-protocol.md](references/interview-protocol.md).

### Step D — Dry-Run Branch (if `--dry-run`)

Skip Steps E–H. Invoke `dry_run_reporter.plan_standard_writes(...)`
and exit 0.

Full procedure → [references/step-d-dry-run.md](references/step-d-dry-run.md).

### Step E — Artifact Generation

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/tools/generate_adoption_artifacts.py" \
  --project-root <cwd> [--no-sync] [--no-backfill-events] \
  [--scope <full_app|library|cli>] [--profile <name>] [--split-name <name>]
```

Writes in order: `CLAUDE.md`, agent_docs, planning spec, six configs
(`shipwright_run_config.json` LAST), events.jsonl, baseline E2E spec,
visual frontend docs (Tier 5), prior-art harvest, sibling-test ACs,
TODO/FIXME inventory, see-also cross-links, security CI scaffold,
CI workflow scaffold (profile-aware), Claude-Review workflow scaffold.

Vite DX templates are offer-only — NEVER auto-applied. Existing
`vite.config.ts` is NEVER overwritten. Features merge unions AST +
crawl by route key. Gitignore awareness surfaces `majority_gitignored`
warnings.

Full procedure → [references/step-e-artifact-generation.md](references/step-e-artifact-generation.md).
Template slot mapping → [references/artifact-templates.md](references/artifact-templates.md).
Nested-project policy → [references/nested-project-policy.md](references/nested-project-policy.md).

### Step E.5 — Env Scaffold (`.env.local`)

After the artifact generator returns, adopt MUST scaffold
`<project_root>/.env.local` via
`shared/scripts/validate_env.py::init_env_file(project_root, "all",
profile_dir, include_framework=True)`. The result lands in
`results["env_local"]` for the Step H banner.

Contract:

- **Idempotent — never overwrites** existing values. Missing keys are
  appended; action is `created` / `updated` / `unchanged`.
- **`.gitignore` enforced FIRST.** On enforcement failure, the scaffold
  returns `action: skipped, reason: gitignore_enforcement_failed` and
  writes NOTHING.
- **No real values written, ever.** Comment-prefixed entries only.
- **Existing user content preserved byte-for-byte** on `updated`.

Profile-specific keys come from `required_env_vars[...]` on the active
stack profile. Framework keys (always written): `OPENROUTER_API_KEY`,
`GEMINI_API_KEY`, `OPENAI_API_KEY`.

Full procedure → [references/step-e5-env-scaffold.md](references/step-e5-env-scaffold.md).

### Step E.6 — Canonical Gitignore Propagation (MANDATORY)

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/lib/gitignore_canon.py" \
  --project-root <project_root>
```

Merges the canonical `.shipwright/` artifact-ignore block (SSoT:
`shared/templates/shipwright-gitignore.template`) into the project's
`.gitignore`. **Idempotent + additive** — line-level merge that adds only
missing rules inside a managed BEGIN/END block (never duplicates), so
re-running self-heals an already-adopted repo. Closes the gap where
framework-added ignore rules (e.g. `/.shipwright/agent_docs/runtime/`,
ADR-089) never reached consuming projects: transient artifacts get
ignored while the canonical SDLC-doc homes stay tracked. JSON output:
`{action, path, added, already_present, total_canonical}`. Drift vs. the
framework's own `.gitignore` block is guarded by
`shared/tests/test_gitignore_template_congruent.py`.

Full procedure → [references/step-e-artifact-generation.md](references/step-e-artifact-generation.md) (Step E.6 section).

### Step E.16 — Triage Inbox Scaffold

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/tools/scaffold_triage_inbox.py" \
  --project-root <project_root> --json
```

Idempotent — writes `.shipwright/triage.jsonl` (schema header),
`.shipwright/agent_docs/triage_inbox.md` (empty skeleton), and updates
`.gitignore` to cover both. Result in `results["triage_inbox"]`.

Full procedure → [references/step-e16-triage-inbox.md](references/step-e16-triage-inbox.md).

### Step F — Compliance Seeding

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/tools/seed_adopt_compliance.py" \
  --project-root <cwd>
```

Populates SBOM, change-history, traceability-matrix, test-evidence,
dashboard.

Full procedure → [references/step-f-compliance-seeding.md](references/step-f-compliance-seeding.md).

### Step G — Layer-3 Review

Run `review_runner.run_review(...)` from
`scripts/lib/review_runner.py`. Writes `.shipwright/adopt/review.md`.
Without API key: `status: skipped, reason: no_api_key` (acceptable).
HIGH/MAJOR findings about hallucinations → AskUserQuestion: fix /
accept with caveat / abort.

Full procedure → [references/step-g-layer3-review.md](references/step-g-layer3-review.md).

### Step H — Validate, Commit, Handoff

Validate via `validate_adoption.py` — hard-stop on `errors[]`, surface
`warnings[]` in handoff. If validation passes, build the commit message
via `lib.adopt_commit_template.build_adopt_commit_message` (Run-ID
regex enforced by the helper). Print the handoff banner — the
"Edit .env.local" block derives the list from
`results["env_local"]["missing_keys"]` (NOT hardcoded; the merge of
profile `required_env_vars` and framework keys), and renders whenever
`missing_keys` is non-empty (independent of `action`).

Full procedure → [references/step-h-validate-commit-handoff.md](references/step-h-validate-commit-handoff.md).

## Backfilling `shipwright_iterate_config.json` on already-adopted projects

See [references/backfill-iterate-config.md](references/backfill-iterate-config.md).

## References

- `references/step-a-preflight.md` — Step A.0 + Step A pre-flight
- `references/step-b-codebase-analysis.md` — Step B codebase analysis
- `references/step-b5-route-discovery.md` — Step B.5 Playwright crawl
- `references/step-b8-semantic-enrichment.md` — Step B.8 Layer-2 enrichment
- `references/step-c-interview.md` — Step C AskUserQuestion protocol
- `references/step-d-dry-run.md` — Step D dry-run branch
- `references/step-e-artifact-generation.md` — Step E artifact writes
- `references/step-e5-env-scaffold.md` — Step E.5 .env.local scaffold
- `references/step-e16-triage-inbox.md` — Step E.16 triage inbox
- `references/step-f-compliance-seeding.md` — Step F compliance
- `references/step-g-layer3-review.md` — Step G Layer-3 review
- `references/step-h-validate-commit-handoff.md` — Step H validate / commit / handoff
- `references/backfill-iterate-config.md` — backfill helper for pre-2026-05-05 adopts
- `references/integration.md` — Phase-Quality / cross-plugin / marketplace wiring
- `references/codebase-analysis.md` — detector heuristics and edge cases
- `references/feature-inference.md` — Playwright crawl vs AST fallback rules
- `references/interview-protocol.md` — when to ask, when to infer
- `references/artifact-templates.md` — template slot mapping
- `references/nested-project-policy.md` — webui-style nested-project handling

## Integration

See [references/integration.md](references/integration.md) — Phase-Quality
audit registration, cross-plugin doc pointers, marketplace registration.
