# Shipwright SDLC Framework

> This Codex operating contract is shared verbatim with the sibling
> `shipwright-webui` repository. Repository-specific architecture, commands, and
> product conventions come from the local `CLAUDE.md`; the structure and
> plugin-development sections below describe the `shipwright` framework monorepo.

## WHAT
- **Purpose**: AI-powered SDLC pipeline built on Claude Code — from user description to deployed, tested, secured application
- **Architecture**: Monorepo of Claude Code plugins (skills + hooks + scripts)
- **Stack**: Python 3.11+ scripts, Claude Code plugin system, uv package manager

## Structure
```
plugins/                    # Claude Code plugins (one per SDLC phase)
  shipwright-run/           # Orchestrator (entry point)
  shipwright-project/       # Requirements decomposition (IREB)
  shipwright-design/        # UI mockups from IREB specs (HTML)
  shipwright-plan/          # Deep planning + external LLM review
  shipwright-build/         # TDD implementation
  shipwright-test/          # Testing (unit + smoke + Playwright E2E)
  shipwright-security/      # Scanner chain + remediation loop
  shipwright-deploy/        # Deployment (extensible flavors)
  shipwright-changelog/     # Git sync + changelog + PR
  shipwright-compliance/    # IREB traceability, RTM, SBOM, dashboard
  shipwright-iterate/       # Daily iteration (complexity-adaptive)
  shipwright-preview/       # Local browser preview
  shipwright-adopt/         # Brownfield onboarding (analyze an existing repo)
  shipwright-grade/         # Read-only Control Grade (A–F) for any repo (lead magnet)
# Command Center WebUI lives at github.com/svenroth-ai/shipwright-webui since v0.4.0
shared/                     # Shared across all plugins
  contracts/                # Cross-plugin public API (B8): compliance.py, iterate.py
  profiles/                 # Stack profile definitions (JSON) + deploy profiles
  templates/                # CLAUDE.md, AGENTS.md, .shipwright/agent_docs, CI templates
  prompts/                  # Shared subagent prompts (code_reviewer, iterate_reviewer)
  schemas/                  # JSON schemas (run_config v2)
  config/                   # Shared config (external_review.json)
  scripts/                  # Shared Python utilities
  tests/                    # Tests for shared scripts and hooks
  constitution.md           # ALWAYS / ASK FIRST / NEVER rules for all agents
scripts/                    # Top-level scripts (install.sh, verify-setup.sh)
docs/                       # User-facing docs (guide.md, hooks-and-pipeline.md)
integration-tests/          # Cross-plugin integration tests
CHANGELOG-unreleased.d/     # Pending changelog drop files (aggregated at release)
```

## HOW

### Codex operating policy

- Use `gpt-5.6-terra` with `high` reasoning for ordinary implementation and finalization.
- Use `gpt-5.6-sol` with `high` reasoning for required review subagents.
- Do not use `xhigh` or `max` unless concrete risk, complexity, or a failed review justifies it.
- `shipwright_model_config.json` contains Claude model tiers. Do not reinterpret or edit those values as Codex model names.
- For triage-item implementation, follow the locally installed Shipwright iterate skill. In this monorepo its source is `plugins/shipwright-iterate/skills/iterate/SKILL.md`; the active Claude Code runtime resolves Shipwright from `~/.claude/plugins/cache/shipwright/`.
- Use one isolated worktree and branch per iterate; never push `main` directly.
- Preserve unrelated and unexplained changes. Do not rewrite, discard, or absorb them silently.
- Reviews through the configured OpenRouter route are authorized.
- Do not commit mutable derived snapshots such as the root `shipwright_test_results.json`. Preserve the required test ledger, surface evidence, and `declared_removals` through the current F5c/F6 contract in the iterate skill.
- Delivery is complete only when `deliver_pr.py` reports `DELIVERED`.
- For plugin/shared changes, follow the marketplace/cache-sync procedure below.

Detailed F0–F11 procedures belong only in the iterate skill; do not duplicate them here.

### Development
```bash
uv sync                              # Install dependencies
uv run pytest tests/ -v               # Run tests for a plugin (from plugin dir)
uv run pytest integration-tests/ -v   # Run integration tests (from root)
uvx ruff@0.15.15 check .              # Bug-focused lint — GATING in CI (ci.yml)
uv run scripts/verify_local.py        # The CI merge guards that run nowhere else
```

**Run `verify_local.py` before pushing.** `ci.yml`'s required job carries three
bespoke guards — the CI-gate guard and the two surface verifiers — that no local
step runs, so they are learned about from a red CI run *after* the iterate
reports done. Measured at 4-6 s from a worktree (Windows); expect longer from a
clone whose `.worktrees/` holds other checkouts, which `grade.py` also walks. It
reports all three in one pass (never short-circuiting, so one push fixes
everything CI would reject) and names what would block.

It is a pre-flight, not a substitute: CI checks a clean checkout on a pinned
interpreter, and its `Repair-PR safety (gate)` reads the PR's *base* revision so
a branch cannot vouch for itself. Note also that it vets your **working tree**
while CI vets the commit you **push** — it prints which, and warns when the tree
is dirty. **F0 runs it for you** inside an iterate (after the leak-guard, before
the suite, guarded on the file existing); typing it yourself is still how you
check a tree outside a run.

**Lint is a hard CI gate.** `.github/workflows/ci.yml` runs `uvx ruff@0.15.15
check .` with no `|| true` / `continue-on-error`, so a lint failure blocks merge.
The ruleset is deliberately curated (Pyflakes + a few bug-class pycodestyle
rules, cosmetic rules omitted) and lives in the root `pyproject.toml`
`[tool.ruff.lint]` — run it locally before pushing. ruff is pinned (not a project
dependency) so a new release can't silently change the gate.

### Plugin Structure (each plugin follows this pattern)
```
plugins/shipwright-{name}/
  .claude-plugin/plugin.json          # Plugin metadata
  hooks/hooks.json                    # Claude Code hooks
  agents/                             # Subagent definitions (markdown)
  skills/{name}/SKILL.md              # Main skill definition (folder = slash command suffix)
  scripts/                            # Python scripts (checks, hooks, lib, tools)
  tests/                              # Plugin-specific tests
  pyproject.toml                      # Plugin dependencies
```

### Conventions
- All scripts invoked via `uv run`; Claude Code hooks resolve paths via `${CLAUDE_PLUGIN_ROOT}`
- Env var prefix `SHIPWRIGHT_` (`SHIPWRIGHT_SESSION_ID` = unified session id;
  `SHIPWRIGHT_PLUGIN_ROOT` = active plugin dir); config-file prefix
  `shipwright_` (`shipwright_*_config.json`, written to the target project)

### Hooks & Pipeline Reference
`docs/hooks-and-pipeline.md` is the single source of truth for what fires when:
the context-loading matrix (who reads what), the artifact-write matrix (who
writes what), the Claude Code hooks registry, config data flow, and between-phase
actions. **ALWAYS read it first** when working on any plugin. **Rule:** modifying
a hook (`hooks.json`), adding/removing a pipeline phase, changing phase validators
or between-phase actions, or changing what a plugin reads at startup means you
MUST update it in the same diff.

### When editing plugin-side files

Changes under `plugins/*`, `shared/scripts/`, or any `SKILL.md` file do
NOT auto-sync to the plugin cache at `~/.claude/plugins/cache/shipwright/`
that Claude Code uses at runtime. After `git push`, run:

```bash
bash scripts/update-marketplace.sh
```

Then verify with `uv run scripts/check_plugin_cache_sync.py --strict`.
Without the sync, plugin-side fixes land in the dev repo but never reach
runtime — that silently cost iterates 7-11 their fixes.

**Scope:** monorepo-only. End-users consuming the plugins on their own
projects run the installed versions and never need this.

**Full procedure + rationale:** `shared/prompts/writing-plugin.md`.

### Documentation Guide
`docs/guide.md` is the primary user-facing documentation (README.md is a
summary that links to it). **Rule:** a new skill, a changed skill
command/argument/flag, a pipeline-flow change, or a constitution change means
checking whether the guide needs an update — its Chapter 4 (phases),
Chapter 7.5 (constitution), Chapter 8 (quality gates) and Appendix B (command
reference) are the sections that go stale.

### Where documents live

**`docs/` holds hand-written instructions** — for users and for developers
alike. The test is not who reads it, but that someone *wrote* it and someone
*reads* it. `guide.md` and `hooks-and-pipeline.md` sit there as equals.

**`.shipwright/` holds the artifacts Shipwright itself keeps** — specs under
`.shipwright/planning/`, evidence under `.shipwright/compliance/`, architecture
and decision memory under `.shipwright/agent_docs/`. They come out of runs;
they are not composed by hand.

**A file that is neither belongs nowhere:**

- A **record of finished work** is deleted. Git history keeps it.
- A **generated file** is not filed among the hand-written ones. If it is
  committed at all, it lives **next to the source it is generated from**, so
  source and render are read together and the drift test has an obvious
  subject. `shared/config/gate_catalog.json` + `gate_catalog.md` is the shape.

For neither case is the answer "then put it under `.shipwright/`". The
`agent_docs`, `planning` and `compliance` trees are read as well — they are not
a parking lot for files nobody reads. Relocating an unread file into a read
directory is filing, not deciding.

### Testing
```bash
cd plugins/shipwright-build && uv run pytest tests/ -v   # single plugin
uv run pytest integration-tests/ -v                      # integration
```

**One test root per pytest process — a hard rule, enforced by the repo-root
`conftest.py` (exit 4).** Roots: `integration-tests`, `shared/tests`,
`shared/scripts/tests`, `shared/scripts/tools/tests`, each `plugins/*/tests`.
Each needs `scripts`/`lib`/`tools` to mean a *different* directory, and Python
caches whichever package loads first — `sys.path` order cannot fix it
(ADR-044). One root per invocation, one `--junitxml` per root; merge
afterwards. Why, plus the two gaps the guard does not cover:
`.shipwright/planning/iterate/iterate-2026-07-27-pytest-root-composition.md`.

## Context
- **Guide**: docs/guide.md (primary user-facing documentation)
- **Hooks & Pipeline**: docs/hooks-and-pipeline.md (context loading, hooks registry, between-phase actions)
- **Glossary**: shared/glossary.md (mandatory-read — shared vocabulary
  used by hooks, agents, subagents, and compliance audits — Allowlist,
  Ratchet, Anti-Ratchet, Producer, Action-Unit, Canon-Gate, …)

## Pre-commit hooks

Contributors must install the bloat anti-ratchet pre-commit hook
**once per clone**:

```bash
bash scripts/install-hooks.sh       # POSIX / Git-Bash on Windows
.\scripts\install-hooks.ps1         # PowerShell on Windows
```

This sets `git config core.hooksPath scripts/hooks` (idempotent;
refuses to overwrite an existing different value without `--force`).
The hook only blocks commits that ratchet an existing entry in
`shipwright_bloat_baseline.json` — new crossings are surfaced by the
Group H detective audit post-merge. See `shared/glossary.md` for the
terminology and `shared/scripts/lib/anti_ratchet.py` for the rule.

## Review subagents: standing request. Workflows: ask every time.

**The review cascade is requested by default — spawn it with `gpt-5.6-sol` and
`high` reasoning, never pause to ask, and never record a review `not_run` citing
a session policy.** That is `spec-reviewer` → `code-reviewer` →
`doubt-reviewer` plus the review subagents other phase skills prescribe (build
Step 6, campaign review). Codex withholds subagent spawning until the user asks;
**this file is that request, and it stands for every session.** **The grant
covers reviewers, not fan-out.** Dynamic workflows, deep-research, and parallel
implementation subagents (build's `section-builder` loop) spend openly and stay
the operator's call — ask explicitly, every time, and never infer them from the
grant above. A project that does not want this can delete the section; it is
deliberately plain and must not be compressed further, because it has to read as
the user's request at runtime.

## Asking the user questions (plain language)

Every interactive question — clarification, choice, confirmation — must be
answerable by a **non-senior developer or a normal user** without decoding
jargon. The person answering may not know the internals.

- **Lead with the functional meaning:** what the choice changes about how the
  app behaves, not the implementation. "Should a deleted item be recoverable,
  or gone for good?" — not "soft delete with a tombstone flag, or hard delete?".
- **Gloss any unavoidable term** in parentheses (e.g. "idempotent — safe to run
  twice without doubling the effect").
- **Make options concrete and comparable:** each in plain words with its
  real-world trade-off ("A is simpler but slower to load; B is faster but adds
  a setup step"), never a raw technical menu.
- **Rule of thumb:** a product owner should be able to answer without asking
  "what does that mean?". If they couldn't, rewrite it.

This applies to every interactive question — clarifications, plan approvals,
design feedback, and remediation choices alike. It governs *phrasing only*;
the underlying rigor of the work is unchanged.
