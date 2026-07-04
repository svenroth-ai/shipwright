# Shipwright SDLC

> ### Ship right, not just fast.

![Status](https://img.shields.io/badge/status-beta-blue)
![License](https://img.shields.io/badge/license-MIT-blue)

**AI can build your software now. The hard part is keeping it true to what you already decided, on every change, not just the first.**

Shipwright is **the harness your AI follows**. On every change it checks the work back against your baseline (requirements, architecture, past decisions) and won't let through a change that silently drops a requirement or reverses a call you already made. That is enforced in code, not left to the model to remember; the traceability and audit trail just fall out of it.

```
/shipwright-iterate "Add a dark mode toggle"
```

**What comes with it:** a failing test written first, the change, your specs and traceability updated to match, and a clean Conventional-Commit PR, security-scanned and gated on green checks. Nothing you'd already settled gets quietly undone.

Not a stack framework, not autonomous codegen, just the discipline layer that makes whatever generates your code something you can stand behind. Use it from the **Claude Code VSCode Extension or CLI terminal**, or for multi-project work through the **Shipwright Command Center** web UI. Built for daily iteration, not one-shot generation. It scales from a one-line change to a whole new app:

```
/shipwright-run "A SaaS time tracking app with Supabase and Next.js"
```

> **Beta:** Shipwright is in active beta. It builds itself daily, but you're an early user, so expect the occasional rough edge. [Report issues](https://github.com/svenroth-ai/shipwright/issues/new/choose) and feedback are very welcome.

## Shipwright Command Center

<table>
<tr>
<td width="50%"><img src="docs/images/command-center-board.png" alt="Shipwright Command Center: Kanban view" /></td>
<td width="50%"><img src="docs/images/command-center-task-detail.png" alt="Shipwright Command Center: Task detail" /></td>
</tr>
<tr>
<td><em>Kanban board across every Shipwright project: Backlog, In Progress, In Review, Done. One place to see where everything stands.</em></td>
<td><em>Task detail: embedded terminal, Project File Viewer, Markdown Editor.</em></td>
</tr>
</table>

The Command Center is the browser surface for the same skills you run in the terminal or VS Code Extension. Instead of keeping 4 terminal windows or VS Code sessions open for 4 projects, you get one kanban board, one inbox for agent questions, and one place to launch a new pipeline or iterate. When you launch, the `claude` command runs in an embedded terminal on the task page, and the Command Center follows the session live. It lives in its own repo. See [Start the Command Center](#start-the-command-center-optional).

## Why Shipwright?

- **Keeps your context true.** On every change, Shipwright re-checks the diff against the requirements, architecture, and decisions, and blocks anything that drops a requirement or reverses a past call. Enforced mechanically, not left to the model to remember.
- **Structure over vibes.** IREB-aligned specs, TDD with acceptance criteria, mechanical hooks, not advisory prose.
- **Flexible, not linear.** Run the full pipeline with `/shipwright-run`, iterate daily with `/shipwright-iterate`, or invoke any single skill on its own.
- **Compliance without the overhead.** Traceability matrix, test evidence, change history, SBOM, and a dashboard, all generated automatically from an append-only event log. The audit paperwork that normally costs weeks of manual work ships as a byproduct of building the software.
- **Mechanical quality gates.** Hooks block dangerous actions deterministically (exit code 2), so quality doesn't depend on the agent remembering the rules.
- **Proven on itself.** Shipwright builds Shipwright: every commit on `main` runs through the same pipeline, scanner chain, and compliance gates it ships to you.

## Who is it for?

- **Developers** who want more than vibe coding: a structured pipeline from day one, with a visual dashboard to stay on top.
- **Practitioners** who've already invested heavily in Claude Code and want the next step: from "I can prompt it" to "I understand what else is possible with it."
- **Serious Founders** with enough technical background to know that more prompting won't give better quality, looking for the discipline that turns AI velocity into shippable products.
- **IT Allrounders** who can't or won't use Replit-style tools, for compliance, customer reputation, or because they want to understand what's running in production.
- **Consultants** and smaller boutiques that deliver to clients and refuse to ship vibe-coded output with their name on it.
- **Business Analysts** bringing requirements discipline back into AI-coded projects: what to demand of specs, what to verify, what to reject.
- **Tech Leaders** who want to understand how the SDLC needs to evolve into a model that's AI-native.
- **Solution Architects** learning to recognize when AI-coded systems honor the architecture, and when they quietly drift away from it.

## Initial Pipeline

Run once via `/shipwright-run` for a new project, or invoke any single skill on its own at any time.

```
User Description
  │
  ▼
┌────────────────────────────┐
│ shipwright-run             │  Infer scope, profile, autonomy → dispatch
└─────────────┬──────────────┘
              ▼
┌────────────────────────────┐
│ shipwright-project         │  Interview → Split → IREB Specs → CLAUDE.md + .shipwright/agent_docs
└─────────────┬──────────────┘
              ▼
┌────────────────────────────┐
│ shipwright-design          │  Specs → Interview → HTML Mockups → Review Viewer → Feedback Loop
└─────────────┬──────────────┘
              ▼  (per split)
┌────────────────────────────┐
│ shipwright-plan            │  Research → Interview → Plan → External LLM Review → Sections
└─────────────┬──────────────┘
              ▼  (per section)
┌────────────────────────────┐
│ shipwright-build           │  TDD → Code Review → Conventional Commit → Feature Branch
└─────────────┬──────────────┘
              ▼
┌────────────────────────────┐
│ shipwright-test            │  Unit (Vitest) → Smoke → Playwright E2E
└─────────────┬──────────────┘
              ▼
┌────────────────────────────┐
│ shipwright-changelog       │  Parse Commits → Changelog → Version Tag → PR
└─────────────┬──────────────┘
              ▼
┌────────────────────────────┐
│ shipwright-deploy          │  Profile-driven deploy (Jelastic verified) → Smoke Test → Rollback
└────────────────────────────┘

The orchestrator runs 7 phases: project → design → plan → build → test
→ changelog → deploy. Two more skills run out-of-band, not orchestrator
phases:

  shipwright-security    Semgrep + Trivy + Gitleaks → Classify → Remediation → Report
                         (run manually after test, or via CI workflow)
  shipwright-compliance  Traceability → Test Evidence → Change History → SBOM → Dashboard
                         (auto-background after every phase + on-demand audit)
```

## Daily Iteration: `/shipwright-iterate`

After the first build, the initial pipeline is the exception. Daily work
runs through **`/shipwright-iterate`**. Give it one prompt and it
auto-detects whether you're asking for a feature, a behavior change, a
bug fix, or a refactor, then runs the right slice of the full pipeline:
it classifies intent, sizes complexity (trivial → large), writes a
failing test first, implements, runs an external code review on
non-trivial diffs, and finalizes through a clean Conventional-Commit PR,
keeping specs, the append-only event log, and compliance artifacts in
sync as it goes. No need to re-run the whole project pipeline for a
one-line change.

```
/shipwright-iterate "Add a dark mode toggle"
/shipwright-iterate "Fix the timezone bug in the weekly report"
```

For larger work it scales up to **Campaign Mode** (autonomous,
multi-iterate). The full complexity matrix and finalization steps are in
[§8 Ongoing Development with /shipwright-iterate](docs/guide.md#8-ongoing-development-with-shipwright-iterate).

## Using Shipwright

**From the Claude Code VSCode Extension or CLI terminal**

```
/shipwright-run "Build a SaaS time tracker with Supabase and Next.js"   # Full application
/shipwright-run "Add team management with invite flow"                   # Extension to existing project
/shipwright-iterate "Add dark mode toggle"                               # Daily iteration
/shipwright-plan @sections/01-auth.md                                    # Single skill, standalone
```

**From the Shipwright Command Center**

Multi-project kanban across every Shipwright task you touch. Click a task for its live transcript; click **Launch** to start a new pipeline or iterate, and the `claude` command auto-runs in an embedded terminal on the task page. The Command Center never spawns Claude itself; it follows the session live. Same skills, same events, same compliance artifacts as running directly. What you gain is the overview: 3+ projects, 8+ tasks, one board instead of a pile of windows and VS Code sessions.

**Standalone skills on any project**

`/shipwright-test`, `/shipwright-plan`, `/shipwright-security`, and every other skill also work on projects that never went through the full pipeline. Point them at a repository and they run.

## Skills

| Skill | Purpose |
|-------|---------|
| `shipwright-run` | Pipeline Initializer & Phase Coordinator: inference engine, scope detection, pipeline state machine |
| `shipwright-iterate` | Daily iteration: intent classification, complexity assessment, adaptive pipeline |
| `shipwright-project` | Requirements: IREB-aligned specs, scope detection, chat + file + inline input |
| `shipwright-design` | UI Design: snippet-assembled HTML mockups, review viewer, design system flavors |
| `shipwright-plan` | Planning: external LLM review, section-writer subagent, E2E test plan |
| `shipwright-build` | Implementation: TDD loop, code-reviewer subagent, Conventional Commits |
| `shipwright-test` | Testing: profile-aware (Vitest/Playwright), smoke test, `--fix` auto-repair |
| `shipwright-security` | Security: scanner chain, finding classification, remediation loop |
| `shipwright-deploy` | Deployment: deployment flavors, DEV auto / PROD manual, clone-based rollback |
| `shipwright-changelog` | Release: Keep-a-Changelog format, semver bump suggestion, PR creation |
| `shipwright-compliance` | Compliance: IREB traceability, RTM, SBOM, test evidence, change history, dashboard |
| `shipwright-preview` | Preview: local dev server, browser URL, profile-driven (available after first build split) |
| `shipwright-adopt` | Brownfield onboarding: analyze existing repo, generate CLAUDE.md + .shipwright/agent_docs + configs + E2E baseline |
| `shipwright-grade` | Repo grader: read-only Control Grade (A–F) for any local path or URL, reusing the compliance scoring engine — the public lead magnet |

## Stack Profiles

Profiles define the entire stack: versions, folder structure, deploy target, test strategy, linting, CI, UX patterns, and architecture rules.

| Profile | Stack | Deploy |
|---------|-------|--------|
| `supabase-nextjs` | Next.js 16 · Supabase · Tailwind 4 · shadcn/ui · Zustand · Vitest · Playwright | Jelastic (Infomaniak) |
| `vite-hono` | Vite + React (frontend) · Hono (backend) · multi-service dev server · Vitest · Playwright | — |
| `python-plugin-monorepo` | Python `uv` workspace · pytest · ruff · no web server | — |

**Custom profiles.** Drop a new JSON file into `shared/profiles/` to define your own stack: versions, folder layout, deploy target, test strategy, linting, CI, and architecture rules. Shipwright picks it up automatically and `/shipwright-run` can infer it from your project description.

## Getting Started

A five-step path from zero to a self-merging pipeline. Each step links to the full detail in **[docs/guide.md](docs/guide.md)**. Start here, dive in where you need more.

### Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (Pro or Max): VSCode Extension or CLI
- Python 3.11+ via [uv](https://docs.astral.sh/uv/)
- Git
- [GitHub CLI](https://cli.github.com/) (`gh`): *optional; needed for PRs (changelog / iterate) and auto-merge*
- Node.js 20+: *optional; for the [Command Center WebUI](https://github.com/svenroth-ai/shipwright-webui) and the `supabase-nextjs` profile's generated app*

> First-time machine? The guide has copy-paste prerequisite blocks for **Windows / macOS / Linux** ([§2.1](docs/guide.md#21-fresh-machine-baseline)).

### 1. Install the plugins

The recommended, cross-platform path (Windows PowerShell, macOS, Linux, VS Code Extension terminal): register the marketplace, then install all 13 plugins.

**bash / zsh / Git Bash:**

```bash
claude plugin marketplace add svenroth-ai/shipwright
for p in shipwright-run shipwright-project shipwright-design shipwright-plan \
         shipwright-build shipwright-test shipwright-deploy shipwright-changelog \
         shipwright-compliance shipwright-security shipwright-iterate \
         shipwright-preview shipwright-adopt shipwright-grade; do
  claude plugin install "${p}@shipwright"
done
```

**PowerShell:**

```powershell
claude plugin marketplace add svenroth-ai/shipwright
foreach ($p in @('shipwright-run','shipwright-project','shipwright-design',
                 'shipwright-plan','shipwright-build','shipwright-test',
                 'shipwright-deploy','shipwright-changelog','shipwright-compliance',
                 'shipwright-security','shipwright-iterate','shipwright-preview',
                 'shipwright-adopt','shipwright-grade')) {
  claude plugin install "$($p)@shipwright"
}
```

Verify, then **restart Claude Code** (freshly installed plugins activate only in a new session):

```bash
claude plugin list   # all 13 should show ✔ enabled
```

> **Alternatives:** a bash all-in-one installer (`./scripts/install.sh`, creates a `shipwright` shell alias), see [§2.4](docs/guide.md#24-plugin-install--option-b-scriptsinstallsh-macos-linux-git-bash-on-windows); or a manual `settings.json` edit, see [§2.6](docs/guide.md#26-plugin-install--option-d-manual-settingsjson-edit-advanced).

### 2. Run your first command

```
/shipwright-run "Build a SaaS time tracker with Supabase and Next.js"   # new project
/shipwright-adopt                                                        # existing repo
/shipwright-iterate "Add a dark mode toggle"                             # daily change
```

See [Chapter 3](docs/guide.md#3-your-first-project) (greenfield) and [Chapter 3.5](docs/guide.md#35-adopting-an-existing-repo) (brownfield).

### 3. Keep Shipwright updated

```bash
claude plugin marketplace update shipwright
claude plugin update shipwright-iterate@shipwright   # repeat per plugin
```

Then restart your session. (Installed from a clone instead? Run `bash scripts/update-marketplace.sh`.) Details: [§12](docs/guide.md#12-updating-shipwright).

### 4. Connect GitHub

Put your project on GitHub so `/shipwright-changelog` and `/shipwright-iterate` can open PRs, and CI security findings flow into triage:

```bash
gh auth login                  # one-time
gh repo create <name> --private --source=. --remote=origin --push
```

Walkthrough: [§2.9](docs/guide.md#29-connect-github).

### 5. Turn on auto-merge (optional)

Once your repo has branch protection, `/shipwright-iterate` PRs merge themselves the moment every Required Check is green, with no bot and no polling. `/shipwright-adopt` writes an `AUTOMERGE_SETUP.md` into your repo with the exact check names; the general flow (branch protection, the dormant-workflow trap, `gh pr merge --auto`) is in [§2.10](docs/guide.md#210-enable-auto-merge-optional).

### Start the Command Center (optional)

The Command Center lives in its own repository:
**[shipwright-webui](https://github.com/svenroth-ai/shipwright-webui)**.

```bash
git clone https://github.com/svenroth-ai/shipwright-webui.git ~/shipwright-webui
cd ~/shipwright-webui && make install
make dev-server    # Terminal 1: backend on :3847
make dev-client    # Terminal 2: frontend on :5173
```

The Command Center never spawns Claude itself. **Launch** runs the
`claude` command in an embedded terminal and watches its JSONL
transcript. Full install,
parallel-worktree tips, Windows autostart, and custom actions for your
own slash skills are documented in the WebUI repo's
**[docs/guide.md](https://github.com/svenroth-ai/shipwright-webui/blob/main/docs/guide.md)**.

For the full setup guide (troubleshooting, deployment targets, external LLM review, platform notes), see **[docs/guide.md](docs/guide.md)**.

## Architecture

```
shipwright/
├── plugins/                          # Claude Code plugins (one per SDLC phase)
│   ├── shipwright-run/               # Pipeline Initializer
│   ├── shipwright-project/           # Requirements decomposition (IREB)
│   ├── shipwright-design/            # UI mockups (HTML)
│   ├── shipwright-plan/              # Deep planning + external LLM review
│   ├── shipwright-build/             # TDD implementation
│   ├── shipwright-test/              # Test runner (unit/smoke/E2E)
│   ├── shipwright-security/          # Scanners + remediation
│   ├── shipwright-deploy/            # Deployment (extensible flavors)
│   ├── shipwright-changelog/         # Changelog + PR
│   ├── shipwright-compliance/        # Traceability, RTM, SBOM, dashboard
│   ├── shipwright-iterate/           # Daily iteration (complexity-adaptive)
│   ├── shipwright-preview/           # Local browser preview
│   ├── shipwright-adopt/             # Brownfield onboarding (analyze existing repos)
│   └── shipwright-grade/             # Read-only repo grader (A–F lead magnet)
# Command Center WebUI: github.com/svenroth-ai/shipwright-webui (separate repo)
├── shared/                           # Shared across plugins
│   ├── contracts/                    # Cross-plugin public API (compliance.py, iterate.py)
│   ├── profiles/                     # Stack profile definitions (JSON) + deploy profiles
│   ├── templates/                    # CLAUDE.md, .shipwright/agent_docs, CI/CD, rules templates
│   ├── prompts/                      # Shared subagent prompts (code_reviewer, iterate_reviewer)
│   ├── schemas/                      # JSON schemas (run_config v2, triage item, decision drop)
│   ├── scripts/                      # Shared Python utilities (dev_server pkg, finalize_iterate, surface_verification, …)
│   ├── glossary.md                   # Shared vocabulary (Allowlist / Ratchet / Producer / Canon-Gate / …)
│   └── constitution.md               # ALWAYS / ASK FIRST / NEVER rules for all agents
├── scripts/
│   ├── install.sh                    # All-in-one installer
│   ├── install-hooks.sh              # Pre-commit bloat anti-ratchet hook (one-shot per clone)
│   ├── check_plugin_cache_sync.py    # Detect drift between repo and ~/.claude/plugins/cache/
│   ├── update-marketplace.sh         # Sync plugin sources into Claude Code cache after a push
│   └── verify-setup.sh               # Post-install verification
├── docs/
│   ├── guide.md                      # Canonical user guide
│   └── hooks-and-pipeline.md         # Hooks registry + context loading
├── CHANGELOG-unreleased.d/           # Pending changelog drops (aggregated at release)
└── integration-tests/                # Cross-plugin integration tests
```

Each plugin follows the [Claude Code plugin structure](https://docs.anthropic.com/en/docs/claude-code):

```
plugins/shipwright-{name}/
├── .claude-plugin/plugin.json        # Plugin metadata
├── hooks/hooks.json                  # Claude Code hooks
├── agents/                           # Subagent definitions
├── skills/{name}/
│   ├── SKILL.md                      # Main skill definition
│   └── references/                   # Lazy-loaded protocol docs
├── scripts/                          # Python scripts
├── tests/                            # Plugin-specific tests
└── pyproject.toml
```

## Design Principles

1. **Describe, don't configure:** user describes what they want, agent infers settings
2. **DEV auto, PROD manual:** fast feedback loop, safe production
3. **Every skill works standalone:** `shipwright-run` orchestrates, but each skill works independently
4. **Test-first:** TDD with IREB acceptance criteria → testable specs from day one
5. **Initial build is the exception, iteration is the rule:** `/shipwright-iterate` is the daily workflow after the first deploy
6. **Resume anywhere:** file-based state allows interrupting and resuming at any point
7. **Migration safety:** destructive SQL changes always require confirmation
8. **Linters over instructions:** mechanical enforcement (hooks) beats advisory prose (CLAUDE.md rules)
9. **Progressive disclosure:** CLAUDE.md stays lean (~200 lines), details live in `@.shipwright/agent_docs/`

## Documentation

**→ [docs/guide.md](docs/guide.md) is the canonical guide.** It covers every phase, the constitution, quality gates, profiles, troubleshooting, and the full command reference.

Inheriting a Shipwright-generated repository or reviewing one without going through the pipeline yourself? Start with **[Reading a Shipwright Project from Outside](docs/guide.md#reading-a-shipwright-project-from-outside)** in the guide. It explains where each kind of fact lives so you do not have to read every file to find one answer.

Other references:

- [docs/hooks-and-pipeline.md](docs/hooks-and-pipeline.md): hooks registry, context loading matrix, between-phase actions
- [shared/glossary.md](shared/glossary.md): shared vocabulary across agents, hooks, subagents, and compliance audits (Allowlist / Ratchet / Producer / Canon-Gate / Action-Unit / Worktree-Isolation / F7b-Seal / …)
- [shared/constitution.md](shared/constitution.md): ALWAYS / ASK FIRST / NEVER behavioral boundaries for all agents
- [.shipwright/planning/adr/](.shipwright/planning/adr/): long-form ADR specs (auto-indexed in `INDEX.md` on every release)
- [shipwright-webui/docs/guide.md](https://github.com/svenroth-ai/shipwright-webui/blob/main/docs/guide.md): Command Center user guide (install, daily workflow, custom actions, autostart)
- [CONTRIBUTING.md](CONTRIBUTING.md): contribution workflow and security model
- [SECURITY.md](SECURITY.md): vulnerability disclosure

## Security

Shipwright uses its own `shipwright-security` plugin to scan every change to this repository. **Every commit on `main` passes the full scanner chain:**

- **Semgrep:** Static Application Security Testing (SAST)
- **Trivy:** Software Composition Analysis (SCA, CVE detection)
- **Gitleaks:** Secret detection in code and git history
- **Shipwright Prompt Injection Scanner:** Custom scanner for malicious patterns in skill definitions, hooks, and agent files (Claude Code specific)
- **CodeQL:** GitHub's SAST engine

We dogfood our own security tooling: the same plugin that ships with Shipwright protects Shipwright itself.

### Running the scanners locally

```bash
# Semgrep + Trivy + Gitleaks
uv run plugins/shipwright-security/scripts/tools/scan.py \
  --path . --output findings.json

# Shipwright Prompt Injection Scanner
uv run plugins/shipwright-security/scripts/tools/prompt_injection_scan.py \
  --full --path . --output prompt_risks.json

# Combined Markdown report
uv run plugins/shipwright-security/scripts/tools/generate_security_report.py \
  --input findings.json --prompt-risks prompt_risks.json \
  --output security_report.md
```

### Reporting vulnerabilities

See [SECURITY.md](SECURITY.md) for our vulnerability disclosure policy. Do not file public issues for security problems. Use [GitHub Security Advisories](https://github.com/svenroth-ai/shipwright/security/advisories/new).

## Quality & Safety

Shipwright enforces quality through mechanical hooks, not advisory prose. Hooks fire on Claude Code events and block dangerous actions deterministically.

| Hook | What it prevents |
|------|-----------------|
| Dangerous Command Guard | `git push --force` to main, `rm -rf /`, `DROP DATABASE` |
| Secret Scanning | API keys, tokens, passwords, PEM keys in source code |
| Destructive Migration Scan | `DROP TABLE` / `DROP COLUMN` without rollback SQL |
| File Size Nudge | An edit pushing a source file past the line guideline (advisory, non-blocking) |
| Bloat Anti-Ratchet | **Hard-blocks** commits that raise an allowlisted entry past its frozen `current` LOC. Three layers: pre-commit (local), Stop-Gate (in-session), CI workflow (merge gate). Exceptions go through the ADR-template at `.shipwright/planning/adr/_template-bloat-exception.md`. |
| Drift Detection | Stale CLAUDE.md when source files changed |

Blocking hooks use exit code 2 (soft-block): you can override, but the override is logged. Advisory hooks (file-size nudge, drift detection) never block; they only surface a note. The bloat anti-ratchet hook is the only one that hard-blocks unconditionally. Install it once per clone with `bash scripts/install-hooks.sh` (POSIX/Git-Bash) or `.\scripts\install-hooks.ps1` (PowerShell). See **[docs/guide.md](docs/guide.md)** for details on the constitution, TDD workflow, code review, and migration safety.

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a PR. Note that changes to skills, hooks, or agents require a preceding GitHub issue for discussion; this is part of our security model.

## Development

```bash
# Install dependencies
uv sync

# Run tests for a specific plugin
uv run pytest plugins/shipwright-project/tests/ -v

# Run all integration tests
uv run pytest integration-tests/ -v
```

---

*Early versions were forked from Pierce Lamb's [deep-project](https://github.com/piercelamb/deep-project), [deep-plan](https://github.com/piercelamb/deep-plan), and [deep-implement](https://github.com/piercelamb/deep-implement); current code has diverged substantially.*

### Acknowledgments

Shipwright adopts ideas and adapts specific snippets (with attribution in the relevant files) from these open-source projects:

- **[obra/superpowers](https://github.com/obra/superpowers)** (MIT, © Jesse Vincent): Iron-Law verification language, the anti-slop PR-template framing (`.github/PULL_REQUEST_TEMPLATE.md`), and the two-stage review pattern (`spec-reviewer` → `code-reviewer`).
- **[addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)** (MIT, © Addy Osmani): Five-axis code-review framework, change-sizing heuristics, and Chesterton-Fence checks; informs the bloat-cleanup ADR template and reviewer prompts.
- **[multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills)** (MIT, © 2025 multica-ai): the four Karpathy principles (Think Before Coding · Simplicity First · Surgical Changes · Goal-Driven Execution) cited verbatim in `shared/constitution.md` and `shared/glossary.md`.
- **[multica-ai/multica](https://github.com/multica-ai/multica)** (Apache-2.0 *modified*, hosting-restricted): architectural patterns only (WebSocket transcript streaming, multi-workspace isolation, runtime registry, "parse don't cast" config reads) inspire the Shipwright Command Center roadmap. **No code or text is copied** (patterns only, deliberately), so this repo stays cleanly MIT.

## License

[MIT](LICENSE)

Built by [svenroth.ai](https://github.com/svenroth-ai). Powered by Claude Code.
