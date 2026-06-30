# Shipwright -- The AI-Powered SDLC for Claude Code

> **Ship right, not just fast.** The harness your AI follows, turning vibe coding into agentic engineering you can trust.

## 1. What is Shipwright?

**You can only keep changing software safely if whatever builds it knows what is already true.** That means what the product is meant to do, how it is built, and why the calls were made. Giving an AI that written record is now common, and the good tools do it well; the model no longer starts from zero each session. But a written record only helps while it stays true. On their own, these tools hold a baseline, and whether a new change quietly contradicts it is left to you to notice. That is where trust actually slips: not when something is first built, but later, when a decision you had already settled gets undone and no one sees it.

That is the part Shipwright looks after. On every change it checks the work back against the baseline (the requirements, the architecture, the decisions) and it won't wave through a change that silently drops a requirement or reverses a past call. The baseline isn't a document kept on the side; it is the agent's source of truth the next time it runs. Traceability and change history just fall out of working this way.

### The Problem

AI-assisted coding promises speed, but speed without structure produces fragile, untested, undocumented software. "Vibe coding" -- asking an AI to write code from a loose description -- skips requirements analysis, testing, security review, and deployment planning. The result works on the happy path and breaks everywhere else.

### The Solution

Shipwright is a structured Software Delivery Lifecycle (SDLC) pipeline built on Claude Code. Instead of generating code from a prompt and hoping for the best, Shipwright runs your project through a cleanly orchestrated pipeline of standalone skills -- from requirements decomposition to deployment -- in a single command, or one skill at a time when that's all you need:

```
/shipwright-run "A SaaS time tracking app with Supabase and Next.js"
```

Shipwright infers your stack, interviews you about requirements, designs the UI, plans the implementation, builds with TDD, runs tests, scans for vulnerabilities, deploys, and generates a changelog. You stay in control; the pipeline does the heavy lifting.

After the initial build, daily work happens through `/shipwright-iterate` -- complexity-adaptive, keeps every artifact in sync. Every skill also works standalone, so you can reach for `/shipwright-plan`, `/shipwright-test`, or `/shipwright-security` on its own, any time.

For example, `/shipwright-iterate "Add a dark mode toggle"` lands as a failing test written first, the change, your specs and traceability updated to match, and a clean Conventional-Commit PR that is security-scanned and gated on green checks, with nothing you had already settled quietly undone.

Every phase emits events into an append-only log. That log is the single source of truth, and the raw material for audit-ready compliance documentation (traceability matrix, test evidence, SBOM, change history), regenerated automatically as a side effect of every phase completion. Drift that accumulates between sessions (manual edits, force-pushes, content rot that passes mtime checks) is caught on demand via `/shipwright-compliance`: a cross-artifact detective audit across 8 check groups (A–H). You get the compliance paperwork that usually costs weeks of manual work as a byproduct of just building the software.

You can drive all of this from the Claude Code VSCode Extension or CLI terminal, or through the **Shipwright Command Center**: a local web UI with a kanban board across every Shipwright task, live transcripts per task, and a global inbox for agent questions. Instead of hunting through terminal windows or VS Code sessions, one place shows where everything stands. When you launch a new pipeline or iterate from the Command Center, the `claude` command runs in an embedded terminal right on the task page. The Command Center never spawns Claude itself; it follows the session transcript live.

### Three ways to use it

- **Full pipeline** -- `/shipwright-run "..."` drives the complete initial build, from requirements through deployment.
- **Daily iteration** -- `/shipwright-iterate "..."` for every change after the first deploy. Classifies intent, assesses complexity, runs the right amount of process.
- **Single skill** -- `/shipwright-plan`, `/shipwright-test`, `/shipwright-security`, or any other skill on its own -- even on projects that never used Shipwright before.

All three work from the Claude Code VSCode Extension or CLI terminal directly. The Command Center WebUI layers a multi-project kanban on top. Claude runs in an embedded terminal on the task page, you just stop juggling windows and VS Code sessions to see what's where.

### Who is Shipwright for?

Shipwright is for engineers, BAs, architects, and tech leads who work with Claude Code, and have noticed that AI velocity alone does not get you to a shippable product. What they build (or oversee) gets seen by others: customers, colleagues, markets. They are not necessarily engineers in the classical sense, but they have enough technical judgment to know that more prompting does not produce more quality. They are looking for the guardrails that turn AI from "fast" into "fast *and* good." Shipwright is the discipline layer (Specs, Tests, traceable decisions, living traceability), and the Masterclass guides the path from "AI as a tool" to "AI as a professional discipline."

**Tool users, actively run Shipwright in their own projects:**

- **Developers** that want more than just vibe coding. A structured pipeline from day one, with a visual dashboard to stay on top.
- **IT Allrounders** who can't or won't use Replit-style tools: for compliance, customer reputation, or because they want to understand what is running in production.
- **Consultants and smaller boutiques** that deliver to clients and refuse to ship vibe-coded output with their name on it.
- **Serious founders** with enough technical background to know that more prompting won't give better quality, looking for the discipline that turns AI velocity into shippable products.

**Curriculum audience, typically in larger organizations, learning the discipline rather than running the tool day-to-day:**

- **Business Analysts and Requirements Engineers** looking to bring requirements discipline back into AI-coded projects: what to demand of specs, what to verify, what to reject.
- **Solution Architects** learning to recognize when AI-coded systems honor the architecture, and when they quietly drift away from it.
- **Tech Leaders** who want to understand how the current SDLC needs to evolve into a model that is AI-native.
- **Practitioners** who have already invested heavily in Claude Code and are looking for the next step: moving from "I can prompt it" to "I understand what else is possible and needed with it."

### Not for

- Hobbyists building toys without external accountability.
- Vibe-coding workflows where discipline feels like overhead.
- No-code founders without engineering judgment.
- Classical SAFe / Waterfall veterans looking for tooling around *their* existing process.

### Discipline Layer — the Harness around AI Coding

Shipwright positions itself as a **discipline layer for AI coding**, not a stack framework. The three stack profiles (`supabase-nextjs`, `vite-hono`, `python-plugin-monorepo`) and the Jelastic deploy target are reference implementations, not the product. The product is the discipline: IREB-aligned specs, ADRs, RTM, phase-gates, living traceability, compliance artifacts.

> **Sidenote.** What Shipwright builds, the wider AI engineering field is starting to call *harness engineering* (Martin Fowler, 2026). The harness is the surrounding system of guides (Specs, Conventions, Architecture docs) and sensors (Linters, Tests, Reviews, Scanners) that steers and corrects AI output before and after generation.

**Honest limit.** Shipwright takes the supervision overhead off Maintainability and Architecture-Fitness. **Behavior correctness (does this actually do what users need) remains your call.** We make that judgment cheaper, not unnecessary. The "behavior harness" is unsolved across the industry; do not expect Shipwright (or any tool) to remove the human from that loop.

> **First time seeing IREB, RTM, ADR, SBOM, or Harness?** Jump to the [Plain-Language Index in Appendix A](#plain-language-index): every industry term in this guide has a one-sentence plain-language equivalent.

### What You Get

- **IREB-aligned specs** from a structured requirements interview - testable acceptance criteria from day one
- **HTML design mockups** with visual guidelines, design tokens, and a browser-based review viewer
- **Test-Driven Development** with automated unit, integration (real DB), pgTAP (RLS), smoke, E2E, and design fidelity testing
- **Design fidelity verification** - code-level comparison of implementation vs mockup HTML catches UI drift automatically
- **Compliance documentation** generated automatically: traceability matrix, test evidence, change history, SBOM
- **Architecture docs** (`architecture.md`, `conventions.md`, `decision_log.md`) kept in sync by every phase
- **A constitution** with mechanical enforcement - hooks block dangerous actions, not advisory prose
- **Full artifact traceability** - every requirement traces to build events, test results, and commits
- **Daily iteration** with `/shipwright-iterate` - complexity-adaptive changes that keep all artifacts in sync

### How It Works

```
User Description
      |
      v
  SHIPWRIGHT-RUN ........... Infer scope, profile, autonomy --> dispatch
      |
      v
  SHIPWRIGHT-PROJECT ....... Interview --> Split --> IREB Specs --> CLAUDE.md
      |
      v
  SHIPWRIGHT-DESIGN ........ Specs --> HTML Mockups --> Review Viewer --> Feedback Loop
      |
      v  (per split)
  SHIPWRIGHT-PLAN .......... Research --> Plan --> External LLM Review --> Sections
      |
      v  (per section)
  SHIPWRIGHT-BUILD ......... TDD --> Code Review --> Conventional Commit
      |                        ↑
      |              /shipwright-preview (local browser preview, available after first split)
      v
  SHIPWRIGHT-TEST .......... Unit --> Integration (real DB) --> pgTAP --> Smoke --> E2E --> Visual
      |
      v
  SHIPWRIGHT-CHANGELOG ..... Parse Commits --> Changelog --> Version Tag --> PR
      |
      v
  SHIPWRIGHT-DEPLOY ........ Profile-driven deploy (Jelastic ref.) --> Smoke Test --> Rollback

  After initial build, ongoing changes use /shipwright-iterate:
  SHIPWRIGHT-ITERATE ....... Classify Intent --> Assess Complexity --> Adaptive Pipeline

  Out-of-band (not part of the orchestrator pipeline):
  /shipwright-security ..... OSS (Semgrep/Trivy/Gitleaks) | Aikido | CI workflow — run manually after test
  /shipwright-compliance ... Auto-background doc update after every phase + on-demand detective audit
```

The orchestrator runs **7 phases** (project → design → plan → build → test → changelog → deploy). Security and compliance are **separate skills, not pipeline phases**: security is invoked manually after test (or scheduled via `.github/workflows/security.yml`), and compliance fires as a non-blocking auto-background side-effect after every completed phase plus an on-demand `/shipwright-compliance` detective audit.

Each phase is a standalone Claude Code plugin. `/shipwright-run` orchestrates the full pipeline for the initial build, `/shipwright-iterate` drives daily changes afterwards, and every single skill can be invoked on its own. Pick the entry point that matches your moment: the terminal or VS Code Extension directly for single-project flow, or the Command Center WebUI when you're tracking multiple projects at once and want one board that says where everything stands.

### Design Principles

Shipwright follows nine design principles that shape every decision in the pipeline:

1. **Describe, don't configure.** You describe what you want to build in plain language. Shipwright infers the stack profile, scope, and settings automatically.
2. **DEV auto, PROD manual.** Development deploys happen automatically for fast feedback. Production deploys always require explicit confirmation.
3. **Every skill works standalone.** The orchestrator coordinates the pipeline, but each skill (project, plan, build, test, etc.) can be invoked independently.
4. **Test-first.** Shipwright follows TDD with IREB acceptance criteria, producing testable specifications from day one.
5. **Initial build is the exception, iteration is the rule.** Build sections and iterate changes are events in the same append-only log (`shipwright_events.jsonl`). The initial build is just the first batch of events. `/shipwright-iterate` is designed for daily workflow after the initial build -- quick changes with minimal overhead.
6. **Resume anywhere.** All pipeline state is file-based. The event log is the single source of truth for what happened, when, and with what test results. You can interrupt a run, close your session, and resume exactly where you left off.
7. **Migration safety.** Destructive database changes (DROP TABLE, DROP COLUMN) always require explicit confirmation before execution.
8. **Linters over instructions.** Mechanical enforcement through hooks beats advisory prose. Hooks block dangerous actions deterministically rather than relying on the agent to follow written rules.
9. **Progressive disclosure.** CLAUDE.md stays lean (around 200 lines). Detailed architecture docs, conventions, and decision logs live in `.shipwright/agent_docs/`.

### Integrated Learnings

Shipwright's architecture and quality practices were shaped by three external sources.

#### Claude Code Source Code Leak

When Claude Code's source code was exposed, it revealed the internal rules Anthropic uses to govern their own AI coding agent. Shipwright adopted the most impactful ones into its constitution.

**Rules added from the leak:**

- **Never claim "all tests pass" when output shows failures.** Report actual numbers honestly. This was learned the hard way during real Shipwright builds.
- **Re-read files before editing in long sessions.** After 10+ messages or context compaction, cached file content may be stale. Always re-read before modifying.
- **State explicitly when search results may be truncated.** Tool results can be silently cut off. Never work with incomplete data without flagging it.
- **Verification after edits should include linting and type-checking**, not just tests. Run `tsc --noEmit`, `npm run lint`, or equivalent project tools before reporting success.
- **Quality calibration.** When the user asks for production-grade work, ask: "What would a senior, perfectionist developer reject in code review?" -- and fix all of it.

**Rules Shipwright already enforced before the leak:**

- "Run tests before committing" -- Shipwright's constitution required this from day one.
- "Keep files under 300 lines" -- covers Claude Code's file read strategy (2,000-line cap) indirectly.
- "Fix the code, not the test" -- aligns with Claude Code's quality calibration philosophy.

#### Addy Osmani's Agent Skills

Shipwright integrated patterns from Osmani's [agent-skills](https://github.com/addyosmani/agent-skills) repository into its review and build infrastructure:

- **5-axis code review framework** -- correctness, readability, architecture, security, performance. Adopted into the code-reviewer subagent and the self-review checklist that runs on every section.
- **Anti-rationalization tables** -- structured prompts that prevent agents from explaining away test failures or rationalizing skipped checks. Applied to code review, self-review, and test result interpretation.
- **Performance and simplification patterns** -- reference docs for the build phase covering Core Web Vitals, bundle optimization, and code simplification heuristics.

#### Anthropic Claude Architect Certification

Aligned with the five domains of Anthropic's [Claude Certified Architect](https://www.anthropic.com/certification) exam guide:

- **Constitution-driven boundaries** -- the ALWAYS / ASK FIRST / NEVER tiers that govern agent behavior (see Chapter 7.5).
- **Structured error propagation** -- errors classified into 4 error categories (transient, validation, business, permission) with specific recovery strategies.
- **Compliance enforcement hooks** -- `PreToolUse` hooks that soft-block (exit code 2) when RTM coverage drops or security scans are stale. Overrides are logged to `compliance_overrides.log`.
- **Path-specific rules** -- `.claude/rules/` templates for tests, API routes, migrations, components, and config files, so the agent gets context-appropriate guidance per file type.
- **Few-shot examples in subagent definitions** -- code-reviewer, section-writer, and opus-plan-reviewer include worked examples so agents produce consistent output.
- **Progressive disclosure** -- CLAUDE.md stays lean (~200 lines), detailed docs live in `.shipwright/agent_docs/`.

#### Superpowers — Anti-Slop Framing

Patterns from [`obra/superpowers`](https://github.com/obra/superpowers) (MIT, © Jesse Vincent) drive the parts of Shipwright that say "no" to drive-by AI output:

- **Iron-Law verification language:** the "NO X WITHOUT Y FIRST" framing in the bloat Stop-gate (`shared/scripts/hooks/bloat_gate_on_stop.py`) and in the PR template's Human Authorization / Duplicate Search / Verification sections (`.github/PULL_REQUEST_TEMPLATE.md`).
- **Two-stage review pattern:** a `spec-reviewer` spec-compliance HARD-GATE runs first, then the `code-reviewer` quality stage (`plugins/shipwright-build/agents/spec-reviewer.md`; build Step 6 / `references/code-review.md`). An optional third `doubt-reviewer` (fresh-context, disprove-biased, addyosmani/agent-skills OS3) runs after for non-trivial diffs.
- **Anti-slop PR-template framing:** the "most AI-generated PRs are rejected because process is skipped" banner, the explicit "If you are an AI agent" rules, and the empirical-verification-before-checkbox stance, all citing Superpowers attribution in the template footer.

#### Karpathy — Four Pre-Phase Principles

Patterns from [`multica-ai/andrej-karpathy-skills`](https://github.com/multica-ai/andrej-karpathy-skills) (MIT, © 2025 multica-ai) live at two surfaces:

- **`shared/constitution.md`:** the Pre-Phase Principles header cites *Think Before Coding · Simplicity First · Surgical Changes · Goal-Driven Execution* verbatim. Constitution is always loaded into Claude's context, so this is enforcement, not reference.
- **`shared/glossary.md`:** same four principles listed as reference vocabulary, on-demand loaded.
- **`plugins/shipwright-build/agents/code-reviewer.md`:** applied post-hoc as review-rejection criteria.

#### Multica — Architectural Patterns (no code or text copied)

[`multica-ai/multica`](https://github.com/multica-ai/multica) is Apache-2.0 *modified* with a hosting restriction (Clause 1a), incompatible with our public-launch strategy. We deliberately copy **no code and no text** from it, and instead borrow the following architectural patterns:

- WebSocket transcript streaming (replaces 1 s JSONL polling) for the Shipwright Command Center.
- Multi-workspace isolation for multi-tenant Command Center installs.
- Runtime registry abstraction (Claude Code, Codex CLI, Copilot CLI, Gemini CLI as pluggable adapters).
- "Parse, don't cast": Pydantic schemas for cross-plugin `shipwright_*_config.json` reads.

The shipwright-webui repo carries its own Acknowledgments block referencing the same Multica patterns; the shipwright monorepo carries the constitution and code-reviewer adoptions. Both repos stay MIT.

---

## 2. Prerequisites and Installation

### 2.1 Fresh-machine baseline

Pick the block matching your OS, paste it into a terminal, then continue with §2.3 (Marketplace install). Each block installs the runtimes Shipwright needs and points you at Anthropic's installer for Claude Code itself.

**Windows 11 (PowerShell, no admin needed):**

```powershell
winget install OpenJS.NodeJS.LTS
winget install Python.Python.3.13
winget install astral-sh.uv
winget install GitHub.cli            # optional, for /shipwright-changelog
# Install Claude Code from https://docs.anthropic.com/en/docs/claude-code
# (Anthropic's installer drops claude.exe in ~/.local/bin/ — not on PATH yet.)

# Add ~/.local/bin (claude) and ~/AppData/Roaming/npm (npm-global) to User PATH:
[Environment]::SetEnvironmentVariable(
  'Path',
  ([Environment]::GetEnvironmentVariable('Path','User').TrimEnd(';') +
   ";$env:USERPROFILE\.local\bin;$env:APPDATA\npm"),
  'User'
)
# Restart your terminal so PATH takes effect, then verify:
node --version; python --version; uv --version; claude --version
```

Claude Code itself runs natively under PowerShell; Git Bash is no longer required. If you prefer a Linux-style shell on Windows, WSL2 also works (use the Linux block below from inside the WSL distro).

**macOS:**

```bash
brew install git gh node python uv
# Install Claude Code from https://docs.anthropic.com/en/docs/claude-code
```

Xcode Command Line Tools are needed for git on a fresh macOS install: `xcode-select --install`.

**Linux:**

```bash
sudo apt install nodejs npm python3 git           # adapt to your distro
curl -LsSf https://astral.sh/uv/install.sh | sh
# Install Claude Code from https://docs.anthropic.com/en/docs/claude-code
```

Some distros ship Python older than 3.11; check `python3 --version` and use your distro's deadsnakes/`pyenv`/`uv python install 3.13` path if needed. uv manages per-project venvs, but it does not install system Python on Linux.

### 2.2 Required tools reference

The baseline above already installed everything in this table. It stays here as a "what and why" reference if you are auditing an existing machine.

| Tool | Version | Purpose |
|------|---------|---------|
| Claude Code | 2.1.132+ | AI agent runtime (CLI or VSCode Extension) |
| Python | 3.11+ | Plugin scripts (run via uv) |
| uv | Latest | Python package manager + venv |
| Node.js | 20+ | Command Center WebUI; required for `npm install -g <claude>` if you went the npm route |
| Git | 2.x+ | Version control |

| Optional | Needed for |
|----------|------------|
| GitHub CLI (`gh`) | PR creation, changelog |
| Supabase CLI | Supabase migrations |
| Mermaid Preview (VSCode) | Rendering compliance Mermaid diagrams |

### 2.3 Plugin install — Option A: Marketplace via `claude plugin` CLI (recommended, cross-platform)

This is the modern, idiomatic path. It works identically on Windows PowerShell, macOS, Linux, and inside the VSCode Extension's terminal.

```bash
# End-users: install from GitHub
claude plugin marketplace add svenroth-ai/shipwright

# OR — developers / offline / pinned-version: install from a local clone
git clone https://github.com/svenroth-ai/shipwright.git ~/shipwright
claude plugin marketplace add ~/shipwright
```

Install all 13 plugins. Use the snippet for your shell:

**bash / zsh / Git Bash:**

```bash
for p in shipwright-run shipwright-project shipwright-design shipwright-plan \
         shipwright-build shipwright-test shipwright-deploy shipwright-changelog \
         shipwright-compliance shipwright-security shipwright-iterate \
         shipwright-preview shipwright-adopt; do
  claude plugin install "${p}@shipwright"
done
```

**PowerShell:**

```powershell
foreach ($p in @('shipwright-run','shipwright-project','shipwright-design',
                 'shipwright-plan','shipwright-build','shipwright-test',
                 'shipwright-deploy','shipwright-changelog','shipwright-compliance',
                 'shipwright-security','shipwright-iterate','shipwright-preview',
                 'shipwright-adopt')) {
  claude plugin install "$($p)@shipwright"
}
```

Verify:

```bash
claude plugin list
```

All entries should show `✔ enabled`. If any show `✘ failed to load` with `expected record, received undefined at path ["hooks"]`, you have an outdated `hooks.json` schema. File an issue at [github.com/svenroth-ai/shipwright](https://github.com/svenroth-ai/shipwright).

> **Important, restart Claude Code.** Freshly installed plugins only activate in a NEW Claude Code session. Close and reopen the VSCode Extension or restart the CLI before invoking `/shipwright-*` commands.

### 2.4 Plugin install — Option B: `scripts/install.sh` (macOS, Linux, Git Bash on Windows)

> **PowerShell users on Windows:** this script is bash-only and modifies `~/.bashrc` / `~/.zshrc`. Use Option A (Marketplace via `claude plugin` CLI) instead; it works natively in PowerShell.

The all-in-one bash installer: one script installs Python deps, WebUI deps, a shell alias, and runs verification.

```bash
git clone https://github.com/svenroth-ai/shipwright.git ~/shipwright
cd ~/shipwright
./scripts/install.sh
```

`install.sh` handles:

- Prerequisite checks (Claude Code, Python 3.11+, uv, git, Node.js)
- `uv sync` for Python dependencies
- A `shipwright` shell alias that loads all plugins with a single command
- `scripts/verify-setup.sh` to confirm the install

Once done, type `shipwright` in any terminal and go.

### 2.5 Plugin install — Option C: Manual `--plugin-dir` shell alias (CLI-only)

If you prefer not to register a marketplace, define a shell alias that loads all plugins from a local clone.

**bash / zsh:** add to `~/.bashrc` or `~/.zshrc`:

```bash
shipwright() {
  claude \
    --plugin-dir ~/shipwright/plugins/shipwright-run \
    --plugin-dir ~/shipwright/plugins/shipwright-project \
    --plugin-dir ~/shipwright/plugins/shipwright-design \
    --plugin-dir ~/shipwright/plugins/shipwright-iterate \
    --plugin-dir ~/shipwright/plugins/shipwright-plan \
    --plugin-dir ~/shipwright/plugins/shipwright-build \
    --plugin-dir ~/shipwright/plugins/shipwright-test \
    --plugin-dir ~/shipwright/plugins/shipwright-security \
    --plugin-dir ~/shipwright/plugins/shipwright-deploy \
    --plugin-dir ~/shipwright/plugins/shipwright-changelog \
    --plugin-dir ~/shipwright/plugins/shipwright-compliance \
    --plugin-dir ~/shipwright/plugins/shipwright-preview \
    --plugin-dir ~/shipwright/plugins/shipwright-adopt \
    "$@"
}
```

**PowerShell:** add to `$PROFILE`:

```powershell
function shipwright {
  claude `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-run `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-project `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-design `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-iterate `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-plan `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-build `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-test `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-security `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-deploy `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-changelog `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-compliance `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-preview `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-adopt `
    @args
}
```

### 2.6 Plugin install — Option D: Manual `settings.json` edit (advanced)

> Most users should prefer Option A (CLI). This manual approach is useful if you cannot run the `claude` CLI for some reason (e.g. you only use the VSCode Extension and never open a terminal), or if you are scripting a `settings.json` deployment across many machines.

Add the following to `~/.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "shipwright": {
      "source": {
        "source": "github",
        "repo": "svenroth-ai/shipwright"
      }
    }
  },
  "enabledPlugins": {
    "shipwright-run@shipwright": true,
    "shipwright-project@shipwright": true,
    "shipwright-design@shipwright": true,
    "shipwright-plan@shipwright": true,
    "shipwright-build@shipwright": true,
    "shipwright-test@shipwright": true,
    "shipwright-security@shipwright": true,
    "shipwright-deploy@shipwright": true,
    "shipwright-changelog@shipwright": true,
    "shipwright-compliance@shipwright": true,
    "shipwright-iterate@shipwright": true,
    "shipwright-preview@shipwright": true,
    "shipwright-adopt@shipwright": true
  }
}
```

If you already have content in `settings.json`, merge these two keys into your existing file. Alternatively, in the VSCode Extension, type `/plugins`, open the Marketplaces tab, and add `svenroth-ai/shipwright`.

Then clone and install Python dependencies:

```bash
git clone https://github.com/svenroth-ai/shipwright.git ~/shipwright
cd ~/shipwright && uv sync
```

### 2.7 Verification

```bash
claude plugin list
```

All 13 shipwright plugins should show `✔ enabled`. Then in Claude Code (NEW session, restart if you just installed):

```
/shipwright-run
```

You should see the SHIPWRIGHT-RUN banner.

**Common failure modes:**

- **"Plugin not found" / `/shipwright-*` autocomplete missing** → you are still in the pre-install Claude Code session. Restart it.
- **`✘ failed to load: expected record, received undefined at path ["hooks"]`** → outdated `hooks.json` schema. Open an issue.
- **"command not found: claude" in PowerShell** → `~/.local/bin` is not on User-PATH. See the PATH-fix snippet in §2.1.

### 2.8 Command Center WebUI

The Command Center WebUI lives in its own repo: [shipwright-webui](https://github.com/svenroth-ai/shipwright-webui). Clone it separately and follow its README:

```bash
git clone https://github.com/svenroth-ai/shipwright-webui.git ~/shipwright-webui
cd ~/shipwright-webui && make install
make dev-server    # Terminal 1 — Hono :3847
make dev-client    # Terminal 2 — Vite :5173
```

Autostart on Windows, port overrides for parallel worktrees, and the `SHIPWRIGHT_PROFILES_DIR` / `SHIPWRIGHT_MONOREPO_PATH` profile cascade are documented in the new repo's README + CLAUDE.md.

### 2.9 Connect GitHub

Shipwright works fully offline on a local repo, but several features come alive only once your project is on GitHub:

- **`/shipwright-changelog`** opens a release PR (`gh pr create`).
- **`/shipwright-iterate`** finalization pushes its branch and opens a PR per change, and can arm auto-merge (see §2.10).
- **`/shipwright-security`** in CI mode (and the GitHub-findings → triage producer) reads results from GitHub Actions / code scanning.

You need the **GitHub CLI** (`gh`), authenticated once:

```bash
gh --version          # installed in the §2.1 baseline; if missing, see §2.2
gh auth login         # choose GitHub.com → HTTPS → log in via browser
gh auth status        # confirm you are authenticated
```

Then create the remote and push your project (run from the project root, not the Shipwright clone):

```bash
git init -b main                       # if the repo is not under git yet
git add -A && git commit -m "chore: initial commit"
gh repo create <name> --private --source=. --remote=origin --push
```

For an existing remote, a plain `git push -u origin main` is enough. Once the repo is on GitHub with at least one PR, you can turn on auto-merge.

### 2.10 Enable auto-merge (optional)

With branch protection in place, `/shipwright-iterate` PRs can merge themselves the moment every Required Check is green: no bot, no polling loop, just GitHub-native auto-merge. `/shipwright-adopt` writes an **`AUTOMERGE_SETUP.md`** into your repo listing the exact Required-Check names *your* workflows produce; the steps below are the general flow.

**1. Know your Required-Check names.** Branch protection matches on the **rendered GitHub check name** (the job name shown on a PR), **not** the workflow file name. Open a throwaway PR and copy the names from its checks list.

> **The dormant trap.** Shipwright scaffolds `ci.yml` / `security.yml` / `codeql.yml` *dormant* (only `workflow_dispatch:` active) so they don't fire before you've reviewed them. A dormant workflow's check **never reports**, so requiring it would block *every* PR forever. Uncomment each workflow's `pull_request:` trigger and confirm the check goes green on a test PR **before** you require it.

**2. Configure branch protection.** GitHub → **Settings → Branches → Add branch ruleset** for `main`:

- ☑ **Require a pull request before merging.** Required approvals: **0** (a solo maintainer has no second approver; Shipwright's local review + the checks are the gate).
- ☑ **Require status checks to pass before merging** → add each Required-Check name you activated in step 1 (type it exactly).
- ☑ **Require branches to be up to date before merging**.

> Do **not** enable *Require signed commits*: `/shipwright-iterate` commits headless without a signing key, so requiring signatures leaves every iterate PR permanently `BLOCKED` and silently kills auto-merge. (The squash commit GitHub writes to `main` is verified on its own.)

**3. Allow auto-merge.** GitHub → **Settings → General → Pull Requests → ☑ Allow auto-merge.**

**4. Arm it on a PR.**

```bash
gh pr merge --auto --squash --delete-branch <pr-number>
```

GitHub merges automatically once all Required Checks pass; if a check goes red, the PR waits until you push a fix. `/shipwright-iterate`'s finalization arms this for you on `iterate/*` branches, so day-to-day changes merge hands-free once green.

See the generated `AUTOMERGE_SETUP.md` for your repo's specific check names, and §4.7 / `docs/security-ci-setup.md` for activating the security workflow.

---

## 3. Your First Project

> **Already have a codebase?** Skip to [Chapter 3.5: Adopting an existing repo](#35-adopting-an-existing-repo) below. `/shipwright-project` and `/shipwright-run` are optimized for greenfield starts; brownfield repos use `/shipwright-adopt` instead.

### Step by Step

Create a new project directory, initialize Git, and launch Shipwright:

```bash
mkdir ~/my-first-app && cd ~/my-first-app
git init
```

If you installed via marketplace, open Claude Code in this directory and type:

```
/shipwright-run "A simple todo list app with Supabase and Next.js"
```

If you installed via shell alias, start with `shipwright` and then type the command above.

### What to Expect

Your first run kicks off with a short confirmation of stack, scope, and autonomy. Then Shipwright asks 5-10 requirements questions and generates interactive HTML mockups you review in the browser. After that, planning, build, test, changelog, and deploy run largely unattended -- guided mode pauses at each phase transition so you stay in control, autonomous mode runs straight through. Deployment to DEV is automatic if configured; production always needs explicit confirmation. Security scanning is **out-of-band**: invoke `/shipwright-security` manually after test (or activate the GitHub Actions workflow); it's not part of the orchestrator pipeline.

Estimated time for a small app: 15-30 minutes. See Chapter 4 for the full phase-by-phase breakdown.

### Guided vs Autonomous Mode

Shipwright defaults to **guided mode**. At each phase transition, you are asked whether to continue, review artifacts first, or stop. This gives you full control over the process.

In **autonomous mode**, the pipeline runs without pausing between phases. The interactive phases (requirements interview, design review) still require your input, but build, test, and changelog run unattended. Production deployment always requires confirmation regardless of mode.

You choose your mode during the settings confirmation step at the start of each run.

### Alternative Invocations

You are not limited to a single command. Shipwright supports several input methods:

```bash
# Start from a requirements file instead of a description
/shipwright-run @requirements.md

# Quick iteration on an existing project (minimal questions, fast pipeline)
/shipwright-iterate "Add dark mode toggle"

# Use individual skills directly
/shipwright-project "Build a dashboard"
/shipwright-plan @01-auth/spec.md
/shipwright-build @sections/01-models.md
/shipwright-test
/shipwright-changelog
```

Every skill works standalone. You can run `/shipwright-test` without having used the rest of the pipeline, or invoke `/shipwright-plan` on a spec you wrote manually. The full pipeline is convenient, not mandatory.

## 3.5 Adopting an existing repo

If your repo already has code (commits, dependencies, routes, conventions), use **`/shipwright-adopt`**. It onboards the codebase into Shipwright without asking you to re-describe what the code already tells us, and it leaves the repo in a state where `/shipwright-iterate`, `/shipwright-test`, and `/shipwright-compliance` work as if the project had been built with Shipwright from day one.

### When to use it

- The repo has `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, or similar, not empty.
- There's a git history with prior commits.
- No `shipwright_run_config.json` exists yet.

If those are true, `/shipwright-adopt` is the right entry point. `/shipwright-project` and `/shipwright-run` are greenfield-optimized and will waste effort asking you to describe code that's already there.

### What it does

1. **Layer 1, deterministic analysis.** Scans manifests, tsconfig/eslint/prettier, folder layout, test frameworks, CI, and git log. Produces `.shipwright/adopt/snapshot.json`.
2. **Layer 1.5, Playwright route crawl (if web app).** Starts the dev-server, crawls the running app BFS-style, captures route + h1 + CTAs + screenshots into `.shipwright/adopt/routes.json`. Falls back to AST-based route inference if no dev-server is available.
3. **Layer 2, Claude Code semantic enrichment.** Inline with the skill, Claude reads the snapshot + sample files + screenshots and writes `enrichment.json` with a product description, FR labels, architecture prose, conventions prose, and retroactive ADR drafts.
4. **Artifact generation.** Writes `CLAUDE.md`, `.shipwright/agent_docs/{architecture,conventions,decision_log,build_dashboard}.md`, `.shipwright/planning/01-adopted/spec.md`, the six `shipwright_*_config.json` files, `shipwright_events.jsonl`, and `e2e/flows/adopted-baseline.spec.ts` (regression guard from the crawl). It also merges a `merge=union` `.gitattributes` for the append-log artifacts (`shipwright_events.jsonl`, `.shipwright/triage.jsonl`) so concurrent iterates auto-line-union those logs instead of hitting merge conflicts (an existing `.gitattributes` is preserved, only missing lines are appended).
5. **Compliance seeding.** Generates `.shipwright/compliance/{sbom,change-history,traceability-matrix,test-evidence,dashboard}.md` via the existing compliance infrastructure.
6. **Workflow scaffolding + automerge guide (CI + Security + CodeQL + Claude-Review).** Lands dormant GitHub Actions workflows in `.github/workflows/`: profile-specific `ci.yml` (with the cross-platform OS matrix `ubuntu-latest` + `windows-latest` as the default), `security.yml` (Semgrep + Trivy + Gitleaks scanner chain), `codeql.yml` (GitHub-native SAST; the `language:` matrix is rendered per detected stack profile, and `continue-on-error` on the analyze step keeps the `Analyze (<language>)` check green on a private repo without GitHub Advanced Security), and `claude-review.yml` (independent Claude Code review on PRs). All are byte-equal idempotent: pre-existing workflow files are preserved bit-for-bit. CI + Security + CodeQL ship dormant (`workflow_dispatch:` only); Claude-Review fires on `pull_request` by design. Adopt also writes a repo-root **`AUTOMERGE_SETUP.md`**, a profile-aware branch-protection / auto-merge guide whose Required-Check job names are *derived by parsing the actually-deployed workflows* (matrix-expanded; conditional `if:`-gated deploy jobs are flagged, not listed as requireable), so a brownfield repo can be wired for GitHub auto-merge without trial-and-error. (Anti-ratchet `bloat-check.yml` is a deferred follow-up.) See [docs/security-ci-setup.md](security-ci-setup.md) for the free Path-A scanner chain vs. CodeQL/GHAS Path-B trade-off.
7. **Layer 3, external LLM review.** Runs `llm_review.py` over the generated artifacts to flag hallucinations or contradictions (skipped gracefully if no API key is set).
8. **Validation + commit.** Runs `validate_adoption.py`, then a single Conventional Commit `chore(shipwright): adopt repository into Shipwright SDLC`.

### Usage

```bash
# Dry-run first to see what would happen
/shipwright-adopt --dry-run

# Apply
/shipwright-adopt
# With explicit profile / scope
/shipwright-adopt --profile supabase-nextjs --scope full_app

# Monorepo with a nested sub-project (e.g. webui/)
/shipwright-adopt --exclude-path webui
# Adopt nested sub-project too (instead of excluding it)
/shipwright-adopt --include-nested

# Skip Playwright crawl (no dev-server, auth wall, or deliberate opt-out)
/shipwright-adopt --skip-crawl
# Or: crawl from a custom URL with auth + tighter limits
/shipwright-adopt --crawl-base-url http://localhost:5173 --crawl-auth-token "$TOKEN" \
                  --crawl-max-depth 2 --crawl-max-pages 25

# Skip historical event backfill or sync-config generation
/shipwright-adopt --no-backfill-events --no-sync

# Override the default planning split name (default: 01-adopted)
/shipwright-adopt --planning-split 01-legacy-monolith
```

See Appendix B for the full reference of all 13 flags with arguments and types.

### Nested sub-projects

If Adopt finds a directory with its own `.git/`, `shipwright_run_config.json`, or `CLAUDE.md` + `.shipwright/agent_docs/`, it asks you whether to include, exclude, or adopt it separately. Default: exclude (the sub-project keeps its own pipeline state and can be adopted independently later). See `plugins/shipwright-adopt/skills/adopt/references/nested-project-policy.md` for details.

### After adoption

Everything afterward is identical to a natively-built Shipwright project:

- `/shipwright-iterate "add a profile page"`: all future changes go through this
- `/shipwright-test`: first real test run populates test-evidence compliance
- `/shipwright-compliance`: on-demand detective audit of artifacts

Do **not** run `/shipwright-project`, `/shipwright-plan`, or `/shipwright-build` on an adopted repo: adoption replaces those phases, and iterate covers ongoing work.

## 4. The Pipeline: Phase by Phase

Shipwright's orchestrator pipeline consists of **7 phases** (project, design, plan, build, test, changelog, deploy), each handling a distinct step in the software delivery lifecycle. The phases run in sequence when you invoke the full pipeline via `/shipwright-run`, but every phase can also run as a standalone command. Two additional skills (`/shipwright-security`, Section 4.7, and `/shipwright-compliance`, Section 4.10) are documented in this chapter for completeness but **run out-of-band**, not as orchestrator phases: security is manual or CI-triggered; compliance fires as an auto-background side-effect after every completed phase plus an on-demand audit.

**Phase finalization canon.** Every decision-taking phase runs a five-step finalization sequence at the end of its work, the **Minimum Phase Completion Canon** (C1–C5): record a `phase_completed` event, update the build dashboard, regenerate `session_handoff.md` with a canon marker, write an ADR (where applicable), and append a CHANGELOG bullet (where applicable). The unified verifier `verify_phase.py` enforces these cross-artifact invariants and runs automatically through `phase_validators.py` between phases. See [Chapter 9: Pipeline Verifier and Phase Completion Canon](#pipeline-verifier-and-phase-completion-canon) for the full mechanics and skip criteria per phase.

---

### 4.1 Orchestration -- /shipwright-run

**Purpose.** `/shipwright-run` is the **Pipeline Initializer & Phase Coordinator**, your single entry point. It takes a project description, infers settings, writes the pipeline spec to `shipwright_run_config.json`, prints a launch card for the first phase, and ends. Each phase then runs in its **own external Claude CLI session**: phase Stop hooks plan the next phase via the orchestrator state machine, so the pipeline progresses without the master session being open. (Multi-session lifecycle, schema v2; see [Multi-Session Pipeline Lifecycle](hooks-and-pipeline.md#multi-session-pipeline-lifecycle-v2).)

**Command and Arguments**

```
/shipwright-run "Build a SaaS time tracker with Supabase"
/shipwright-run                          (interactive -- asks what to build)
/shipwright-run @requirements.md         (from a file)
```

| Flag / Argument | Description |
|-----------------|-------------|
| `"description"` | Inline project description |
| `@file.md` | Path to a requirements file |
| *(no argument)* | Interactive mode -- Shipwright asks you what to build |

**What it needs.** Nothing beyond a project idea. For ongoing changes to existing projects, use `/shipwright-iterate` instead.

**What it produces**

- `shipwright_run_config.json` (schema v2): `runId`, frozen `runConditions`, `splits_frozen[]`, and the authoritative `phase_tasks[]` array (one entry per phase, each with a pre-bound `sessionUuid` and a `status` of `awaiting_launch | in_progress | done | failed | skipped`).
- A launch-card banner with the exact `claude --session-id <uuid> --add-dir <path> --name '...' '/shipwright-<phase>'` command to paste into a new terminal.
- Orchestration is delegated: phase Stop hooks (`phase_session_stop.py`) call `complete-phase-task`, which materialises the next `phase_tasks[]` entry. The final phase's Stop hook flips `run.status = "complete"`.

**How it works**

- Detects your input (file, inline text, or interactive chat) and asks 1-3 clarifying questions if the description is vague.
- Infers settings automatically: scope (new project vs. extension), technology profile (e.g., `supabase-nextjs`), and autonomy level (guided or autonomous).
- Presents inferred settings for your confirmation before starting.
- Writes `shipwright_run_config.json` with `phase_tasks[0]` for the project phase, prints the launch card, and ends the master session. (The `suggest_iterate.py` post-pipeline router needs no install step; it is registered in shipwright-iterate's own `hooks.json`.)
- Each phase session you launch externally runs SessionStart → UserPromptSubmit → Stop hooks that handle ownership claim, validation, and next-phase planning. Within a phase session, `guided` vs `autonomous` autonomy controls whether destructive actions ask for confirmation.

**Standalone usage.** `/shipwright-run` is the top-level coordinator. Individual phase commands (`/shipwright-project`, `/shipwright-build`, …) still run standalone if no `phase_tasks[]` match, useful for re-running or debugging a single phase without an active pipeline.

**Resume support.** If the pipeline is interrupted, re-invoking `/shipwright-run` on the existing `shipwright_run_config.json` reads `phase_tasks[]`, identifies the next `awaiting_launch` task, and prints its launch card. Stale `in_progress` tasks (likely from crashed sessions) are surfaced with a `recover-phase-task` hint. The master never mutates state during resume; it only points you at what to launch next.

---

### 4.2 Project Decomposition -- /shipwright-project

**Purpose.** Transforms your project requirements into well-scoped planning units called "splits." Each split gets its own spec file that downstream phases consume. For new projects, this phase also scaffolds `CLAUDE.md` and the `.shipwright/agent_docs/` directory.

**Command and Arguments**

```
/shipwright-project @path/to/requirements.md   (from file)
/shipwright-project "Build a SaaS app..."       (inline description)
/shipwright-project                              (interactive chat)
```

| Input Mode | Description |
|------------|-------------|
| `@file.md` | Reads and summarizes the file, then interviews you to fill gaps |
| `"description"` | Uses the text as starting context for the interview |
| *(no argument)* | Full interactive interview from scratch |

**What it needs.** A project idea -- either as a file, an inline description, or nothing at all (the interview will discover everything). For extensions to existing projects, it reads the existing `CLAUDE.md` and `.shipwright/agent_docs/architecture.md` for context.

**What it produces**

- `.shipwright/planning/` directory with numbered split subdirectories (`01-auth/`, `02-dashboard/`, etc.)
- `spec.md` inside each split directory -- an IREB-style specification with functional requirements, non-functional requirements, and scope boundaries
- `.shipwright/planning/project-manifest.md` -- execution order, dependencies between splits, and overview
- `.shipwright/planning/requirements.md` -- consolidated requirements (generated for inline/chat modes)
- `.shipwright/planning/shipwright_project_interview.md` -- full interview transcript
- `CLAUDE.md` and `.shipwright/agent_docs/` (architecture, conventions, decision log, session handoff) for new projects
- `.claude/rules/*.md` -- path-specific rules derived from the technology profile

**How it works**

- Detects scope: new project (no `CLAUDE.md`) triggers full decomposition; existing project triggers a lighter extension flow
- Conducts an adaptive interview (5-15 questions for new projects, 1-3 for extensions) to surface your mental model
- Analyzes the interview to determine whether the project needs multiple splits or is a single unit
- Writes `project-manifest.md` with the proposed structure and presents it for your approval
- Creates split directories and generates `spec.md` for each split
- For new projects: detects the technology profile, scaffolds `CLAUDE.md`, `.shipwright/agent_docs/`, and path-specific Claude rules
- Logs all project-level decisions (auth strategy, third-party services, naming conventions) to `.shipwright/agent_docs/decision_log.md`

**Standalone usage.** Yes. Run `/shipwright-project` independently whenever you want to decompose requirements without running the full pipeline. The output feeds directly into `/shipwright-plan`.

**Where the planning artifacts live.** The planning directory is `.shipwright/planning/`, under the hidden project-state folder, alongside `securityreports/`, `adopt/`, `runs/`, and `tmp/`. The same hidden home also covers `.shipwright/designs/`, `.shipwright/agent_docs/`, and `.shipwright/compliance/`. The only Shipwright-owned top-level directory is `e2e/`.

If a session start finds a legacy top-level `planning/` directory, the drift detector writes `.shipwright/stale-folders.md` with a `git mv planning .shipwright/planning` remediation hint and exits non-zero so you see it. Run `uv run shared/scripts/tools/migrate_artifact_dir.py --artifact planning` to do the move automatically. <!-- artifact-path-canon: legacy -->

---

### 4.3 UI Design -- /shipwright-design

**Purpose.** Generates interactive HTML mockups from your specs before a single line of production code is written. This lets you validate the look, feel, and user flows early -- when changes are cheap.

**Command and Arguments**

```
/shipwright-design                                       (analyze all specs, generate all screens)
/shipwright-design @.shipwright/designs/screens/02-dashboard.html    (iterate on one screen)
/shipwright-design @.shipwright/designs/design-feedback-round2.md    (process exported feedback)
/shipwright-design --upload                              (integrate uploaded designs)
```

| Flag / Argument | Description |
|-----------------|-------------|
| *(no argument)* | Full generation from specs |
| `@screen.html` | Iterate on a single existing screen |
| `@feedback.md` | Process a feedback file exported from the review viewer |
| `--upload` | Integrate existing designs from `.shipwright/designs/uploads/` |

**What it needs.** Completed specs from `/shipwright-project`: `shipwright_project_config.json`, `.shipwright/planning/project-manifest.md`, and `.shipwright/planning/*/spec.md`. Optionally, existing designs or brand guidelines in `.shipwright/designs/uploads/`.

**What it produces**

- `.shipwright/designs/screens/*.html` -- standalone HTML mockups for each screen (self-contained, responsive, realistic data)
- `.shipwright/designs/flows/*.html` -- multi-screen user flow mockups (e.g., auth flow, CRUD flow)
- `.shipwright/designs/index.html` -- a review viewer with grid view, fullscreen mode, keyboard navigation, and an integrated feedback panel
- `.shipwright/designs/design-manifest.md` -- screen registry mapping each screen to its functional requirements
- `.shipwright/designs/visual-guidelines.md` -- design tokens (colors, fonts, spacing, radii) for the build phase to consume

**How it works**

- Reads all specs and maps functional requirements to screen types (auth, dashboard, list, form, settings, detail, etc.)
- If you have an existing website, extracts brand tokens (fonts, colors, card style) automatically
- Conducts a short design interview (3-5 questions): design system flavor (Untitled UI or Material Design 3), brand character (warm, clean, or bold), layout preference, and special UX needs
- Generates 3 preview screens first for you to validate the palette and style before committing to all screens
- Assembles screens from a snippet library (layouts, components, CSS variables) for consistency and speed
- Generates multi-screen user flows and a review viewer (`.shipwright/designs/index.html`) with built-in feedback collection
- Enters a review loop: you review in the browser, export feedback, and Shipwright applies changes iteratively until you finalize

**Standalone usage.** Yes. `/shipwright-design` works independently as long as specs exist. You can also iterate on individual screens or process feedback files at any time. The review viewer at `.shipwright/designs/index.html` is your primary tool for reviewing and providing feedback.

---

### 4.4 Planning -- /shipwright-plan

**Purpose.** Creates a detailed, section-based implementation plan from a single spec file. The plan follows a TDD approach (tests defined before code) and is **reviewed by external LLMs by default** (Gemini + OpenAI via OpenRouter, or direct API keys). If no API key is set in `.env.local`, the skill **asks you interactively** whether to add one or fall back to a mandatory self-review ("2x denken") pass; it no longer silently skips review.

**Command and Arguments**

```
/shipwright-plan @path/to/01-auth/spec.md
```

| Argument | Description |
|----------|-------------|
| `@spec.md` | Path to a spec file from `/shipwright-project` (required) |

**What it needs.** A `spec.md` file generated by `/shipwright-project`. Recommended: `OPENROUTER_API_KEY` in `.env.local` at the repo root (one key covers both review models). Alternative: `GEMINI_API_KEY` + `OPENAI_API_KEY` direct provider keys. If no key is set, the skill will prompt you at Step 5.

**What it produces**

- `plan.md` -- the implementation plan with a `SECTION_MANIFEST` block that lists all sections in dependency order
- `sections/01-name.md`, `sections/02-name.md`, etc. -- self-contained section files, each describing one unit of work for `/shipwright-build`
- `shipwright_plan_interview.md` -- interview transcript with architecture and design decisions
- `claude-plan-e2e.md` -- Playwright E2E test plan (optional, if enabled in config)

**How it works**

- Reads the spec file and researches the codebase (existing patterns, structure, dependencies) or best practices for new projects
- Conducts an adaptive interview about architecture, data model, and UX preferences -- clarifying ambiguities from the spec
- Checks context pressure and summarizes research if the context window is growing large
- Writes `plan.md` with a TDD-oriented approach: for each section, it defines goals, implementation steps, and the test strategy
- Sends the plan to Gemini and OpenAI in parallel for external review by default, presents findings, and lets you accept or reject each. If no API key is available, the skill stops and asks whether to add one or fall back to the mandatory self-review ("2x denken") pass. The outcome is written to `external_review_state.json` so the compliance dashboard can show it
- Splits the plan into individual section files under `sections/`, each containing everything `/shipwright-build` needs to implement that unit
- Validates that every functional requirement from the spec is covered by at least one section, and that section dependencies are correctly ordered
- Logs all planning decisions to `.shipwright/agent_docs/decision_log.md`

**Standalone usage.** Yes. Run `/shipwright-plan @path/to/spec.md` for any spec file. This is useful when you want to re-plan a single split without re-running the entire pipeline. The output section files feed directly into `/shipwright-build`.

---

### 4.5 Implementation -- /shipwright-build

**Purpose.** Implements code from a single plan section using test-driven development. Each section goes through a full cycle: write failing tests, implement until they pass, review the code, commit with Conventional Commits, and update the project documentation.

**Command and Arguments**

```
/shipwright-build @sections/01-auth.md
```

| Argument | Description |
|----------|-------------|
| `@section.md` | Path to a section file from `/shipwright-plan` (required) |

**What it needs.** A section file generated by `/shipwright-plan`. The project must be a git repository. Environment variables required by the technology profile should be configured in `.env.local` (the phase validates this and prompts you if anything is missing).

**What it produces**

- Production code and test files as specified in the section plan
- A git commit on a feature branch (`build/{slug}-{session-id}`, e.g. `build/my-app-20260411-120000`) using Conventional Commits format
- A `work_completed` event in `shipwright_events.jsonl` (commit hash, test results, affected FRs, review data)
- Updated `.shipwright/agent_docs/decision_log.md` with implementation decisions
- Updated `.shipwright/agent_docs/build_dashboard.md` with progress tracking
- `.shipwright/agent_docs/session_handoff.md` (generated on context pressure or phase completion)
- Updated `.shipwright/agent_docs/conventions.md` with implementation learnings (when new patterns or gotchas discovered)
- SQL migration files with both `up.sql` and `down.sql` (when applicable)

**How it works**

- Reads the section spec and identifies prerequisites, files to create or modify, and the test strategy
- Creates a feature branch (or checks out an existing one for resumed sessions)
- Validates environment variables against the technology profile and prompts you to fill in any missing values
- Installs dependencies listed in the section spec
- Writes tests first (TDD red phase) -- tests should fail for the right reasons
- Implements code until all tests pass (green phase), running tests after each significant change
- For UI projects, performs a design fidelity check:
  - **Code-level fidelity** -- runs `design_fidelity_check.py` to extract structural summaries from mockup HTML and implementation TSX, then compares layout structure, component hierarchy, component types, card patterns, and shadcn/ui rules
  - Auto-checks provide quick pass/fail signals; screens that fail auto-checks get deeper agent analysis where the agent reads both source files side-by-side
- Design fidelity results are tracked in `design-fidelity-report.json` -- this artifact feeds into the test phase for regression detection
- Optionally refactors for cleanliness without changing behavior
- Runs a multi-stage reviewer cascade: a quick self-review checklist (always); then a `spec-reviewer` spec-compliance HARD-GATE (must PASS before the next stage) and a full `code-reviewer` quality review, both triggered for large diffs (>100 lines), high-risk sections, or security-sensitive files; plus a conditional adversarial `doubt-reviewer` pass for non-trivial touches (migrations, async/concurrency, cross-plugin imports, irreversible operations)
- Optionally cascades an external LLM code review (Step 6c) when `external_code_review.enabled: true` is set in `shipwright_build_config.json`. Default off. Reuses the diff from the internal subagent and writes its outcome to `external_code_review_state.json`. See `External LLM Review` in Chapter 6 for the diff-exposure caveat.
- Applies accepted review fixes, re-runs tests to confirm no regressions
- Commits with Conventional Commits format (e.g., `feat(auth): implement magic link authentication`)
- Logs decisions, updates the build dashboard, and checks context pressure -- if the context window is getting full, it saves progress and stops cleanly so you can resume in a fresh session

**Standalone usage.** Yes. Run `/shipwright-build @sections/01-auth.md` for any section file. When used standalone, you manage the section order yourself. When used within the pipeline, the orchestrator feeds sections in dependency order and handles split transitions automatically.
### 4.6 Testing -- /shipwright-test

**Purpose:** Runs your project's full test suite across multiple layers -- unit tests, integration tests (real DB), pgTAP database tests, smoke tests, end-to-end (E2E) browser tests, cross-page UI consistency checks, design fidelity verification, and performance budgets -- to catch bugs before deployment. It is profile-aware, meaning it automatically picks the right test runners and URLs based on your stack.

**Command & Arguments:**

```
/shipwright-test
/shipwright-test --fix          # auto-fix failures (max 3 retries per test)
/shipwright-test --e2e-only     # only run Playwright E2E tests
```

**What it needs:**

- `shipwright_project_config.json` in the project root (for profile detection)
- A unit test setup matching your profile (e.g., Vitest for Next.js, pytest for Python)
- For smoke tests: a running dev server or a configured `SHIPWRIGHT_DEV_URL`
- For E2E: Playwright installed and a `playwright.config.ts` in the project

**What it produces:**

- Unit test results (pass/fail counts, duration)
- Integration test results (real DB CRUD + RLS verification, pass/fail counts)
- pgTAP test results (schema-level RLS/constraint verification)
- Smoke test result (HTTP status against your dev URL)
- E2E test results (pass/fail/skip counts)
- Auto-generated E2E specs in `e2e/flows/` and `e2e/pages/` if test plans exist but specs do not
- `playwright-report/index.html` -- interactive HTML report with screenshots, linked from compliance reports
- Design fidelity verification results (code-level comparison of implementation vs mockup HTML)
- Design fidelity triage results in `shipwright_test_results.json` (regressions, persistent failures, resolved screens)
- Performance budget results in `shipwright_test_results.json.performance` (Lighthouse score + LCP, gzipped bundle size, pass/warn/fail per budget) -- when the profile or `shipwright_test_config.json` opts in
- Updated `.shipwright/agent_docs/conventions.md` with test learnings (when flaky patterns or infra quirks discovered)
- A summary report printed to the terminal

**How it works:**

1. Detects your stack profile and determines which test runners and URLs to use.
2. Runs unit tests (e.g., `npx vitest run`). In autonomous mode, failures trigger auto-fix automatically; in guided mode, you need the `--fix` flag.
3. Runs integration tests against a real (localhost) Supabase instance (`npx vitest run --config vitest.integration.config.ts`). These verify CRUD operations, RLS policies, and complex queries with no mocks. Uses cascade-delete cleanup via test users. Fast-fails on infrastructure errors (ECONNREFUSED). Skipped if profile has no `testing.integration` config or `tests/integration/` directory does not exist.
4. Runs pgTAP database tests (`supabase test db`) if `supabase/tests/database/` exists. These verify RLS policies and constraints at the schema level.
5. Runs a smoke test against your dev URL (checking for HTTP 200 on `/api/health`). If the server is not running, it attempts to diagnose and fix the issue before skipping.
6. If E2E test plans exist from `/shipwright-plan` but no `.spec.ts` files have been written yet, it generates Playwright specs from the plans using the Page Object Model pattern.
7. Runs Playwright E2E tests (starts and stops the dev server automatically). Failed tests can be debugged with a browser-fixer subagent that reads screenshots and error messages.
8. Runs design fidelity verification as a **regressions-only safety net**. Reads `design-fidelity-report.json` (what the build phase already verified) and triages each screen: regressions (was passing in build, now failing), persistent failures (build gave up), and unchecked screens (never verified). Only fixes regressions and persistent failures -- resolved screens are skipped. Uses code-level structural comparison (no screenshots) with agent deep analysis for flagged screens.
9. Runs a performance budget check when the stack profile or `shipwright_test_config.json` opts in: a Lighthouse score + LCP measurement (through the project's existing Playwright Chromium -- no extra browser install) and a gzipped bundle-size budget. The `warn` gate (default) logs missed budgets without blocking; the opt-in `block` gate fails the phase.
10. Runs an E2E results verification step: compares `shipwright_test_results.json` against Playwright's authoritative `e2e-results.json` to catch count discrepancies (e.g., setup project tests being counted as E2E tests). If numbers diverge, the pipeline corrects `shipwright_test_results.json` and documents the reason.
11. Produces a structured results summary with explicit status for every layer.

**The eight test layers and enforcement rules** are central to how the pipeline decides whether to continue:

| Layer | On Failure | Rationale |
|-------|-----------|-----------|
| Unit tests | Pipeline stops (blocking) | Unit tests are deterministic -- failure means a real bug |
| Integration tests | Autofix (3 retries, fast-fail for infra errors), then blocking | Deterministic against real DB -- failure means a real schema/RLS bug |
| pgTAP DB tests | Autofix (3 retries), then blocking | Schema-level RLS/constraint verification |
| Smoke test | Pipeline stops (blocking) | If the app is not running, deployment is pointless |
| E2E tests | Warning only (non-blocking) | E2E tests can be flaky; failures are logged but do not block |
| Cross-page consistency | Warning only (advisory) | Cross-page UI inconsistencies are logged but do not block deployment |
| Design fidelity | Warning only (advisory) | Fidelity mismatches are logged but do not block deployment |
| Performance budget | Warning only by default; blocking under the opt-in `block` gate | Lighthouse score / LCP + gzipped bundle budget; `warn` ships an honest signal without breaking flow, `block` once budgets are calibrated |

Every layer must report an explicit result (`pass`, `fail`, or `skipped: {reason}`) before the phase is considered complete. If any layer has no result, the phase stays in `incomplete` status.

**Standalone usage:** Yes. You can run `/shipwright-test` at any time against any project with a recognized profile. It works independently of the pipeline. The `--fix` flag and `--e2e-only` flag give you targeted control outside the pipeline.

---

### 4.7 Security Scanning -- /shipwright-security

> **Out-of-band skill, not part of `PIPELINE_STEPS`.** Run `/shipwright-security` manually after `/shipwright-test`, or activate `.github/workflows/security.yml` triggers for CI-driven scans. The orchestrator does not auto-insert a security phase.

**Purpose:** Scans your project for security vulnerabilities -- static analysis (SAST), dependency vulnerabilities (SCA), and leaked secrets. Supports two scanner backends: **OSS** (local CLI tools, default) and **Aikido** (cloud SaaS, legacy). When invoked manually or via CI, findings are automatically routed to a subagent for remediation.

**Scanner Backends:**

| Backend | Tools | Runs where | Status |
|---------|-------|-----------|--------|
| **OSS** (default) | Semgrep + Trivy + Gitleaks | Local (CLI binaries) | Actively maintained |
| **Aikido** (optional) | Aikido Security API | Cloud (SaaS) | Legacy: see note below |

> **Plus a prompt-injection scanner.** Beyond the SAST/SCA/secrets chain above, the plugin ships `prompt_injection_scan.py`, a Claude-Code-specific scanner for malicious patterns in skill, hook, and agent files. It runs as its own step in `.github/workflows/security.yml` (diff-scoped on PRs, full on push), emits `prompt_risks.json`, and is merged into the combined report via `generate_security_report.py --prompt-risks`. It is a **separate finding class** from the local Semgrep + Trivy + Gitleaks scan chain and surfaces in triage via the `gh-prompt:{owner}/{repo}` action-unit (§4.11.1).

**Command & Arguments:**

```
/shipwright-security                          # full scan (pipeline or standalone)
/shipwright-security issues --repo owner/repo # list open issues (Aikido only)
/shipwright-security summary                  # severity dashboard (Aikido only)
/shipwright-security report --repo owner/repo # generate Markdown report (Aikido only)
```

**What it needs (OSS backend):**

- At least one of: `semgrep`, `trivy`, `gitleaks` installed and on PATH
- See `references/oss-scanners.md` for installation instructions
- No account or API key required

**What it needs (Aikido backend):**

- An Aikido Security account with API credentials (`AIKIDO_CLIENT_ID` and `AIKIDO_CLIENT_SECRET` in your environment)
- Your GitHub repository connected in Aikido's dashboard

**Backend selection:** Auto-detected. **OSS is the default and actively maintained path.** Aikido is selected if `AIKIDO_CLIENT_ID` is set, but its API path has not been re-verified end-to-end (see note below). Override with `SHIPWRIGHT_SCANNER_BACKEND=oss|aikido` or the profile's `testing.security.provider` field.

**What it produces:**

- A table of findings with severity, type, rule, file, and line number
- A classification summary (auto-fixable / agent-fixable / needs-review / informational)
- A Markdown security report written to the project root
- `shipwright_security_config.json` with scan results (consumed by `/shipwright-compliance`)

**How it works:**

1. Detects and selects the scanner backend (OSS or Aikido). If neither is configured, prints setup instructions and stops.
2. Runs the scan -- locally via CLI tools (OSS) or via API call (Aikido).
3. In pipeline mode, classifies each finding into four categories: auto-fixable (e.g., dependency updates with known patches), agent-fixable (e.g., hardcoded credentials), needs-review (architecture issues), and informational (low-severity best practices).
4. Auto-fixable issues are patched directly, then tests are re-run to verify the fix.
5. Agent-fixable issues are handed to a `security-fixer` subagent with full context (file, line, CWE, remediation hint). Each finding gets up to 3 fix attempts.
6. Needs-review findings are presented to you with options to fix, decline, or defer.
7. Generates a Markdown report summarizing all findings and their remediation status (fixed, declined, deferred, open).

**Usage:** Always standalone (security is no longer a pipeline phase; see banner above). Runs when any scanner backend is available. With OSS tools installed, it works without any cloud account. With Aikido, the standalone commands (`issues`, `summary`, `report`, `repos`) work against any connected repository.

> **Aikido backend -- legacy / not re-verified:** The current scanner flow (report persistence, iterate handoff, orchestrator decouple) was built and verified against the OSS backend only. The Aikido path in SKILL.md Step 6 is preserved and should continue to function via `aikido_client.py report`, but has not been re-run end-to-end against it. New deployments are encouraged to use the OSS backend; if you use Aikido, please report any regressions in GitHub issues.

**CI integration:** `.github/workflows/security.yml` is shipped DORMANT -- only `workflow_dispatch` is active out of the box. The workflow is fully wired (SARIF upload to GitHub Security tab, PR-comment, fork-PR guards, weekly cron) but the auto-triggers are commented out so consumers activate them deliberately at Phase B / Go-Live. `/shipwright-adopt` Step E.13 scaffolds the same template into brownfield repos that don't already have a security workflow. **Operational details (Phase-B activation, fork-PR semantics, the `actions: read` permissions footgun, and the convention lock) live at [docs/security-ci-setup.md](security-ci-setup.md).**

---

### 4.8 Release Management -- /shipwright-changelog

**Purpose:** Analyzes your git history, generates a structured changelog from Conventional Commits, determines the appropriate version bump, creates a git tag, and optionally opens a pull request. It turns your commit discipline into a publish-ready release artifact.

**Command & Arguments:**

```
/shipwright-changelog
/shipwright-changelog --from v0.1.0   # analyze commits starting from a specific tag
```

**What it needs:**

- A git repository with commits following the Conventional Commits format (e.g., `feat:`, `fix:`, `refactor:`)
- The `gh` CLI installed (for PR creation)
- A remote repository configured (for pushing tags and PRs)

**What it produces:**

- An updated `CHANGELOG.md` in Keep-a-Changelog format
- A semver git tag (e.g., `v0.2.0`)
- A pull request on GitHub (if you are on a feature branch)
- Tags and main branch pushed to origin

**How it works:**

1. Runs a setup script that detects the last version tag and collects all commits since then. If there are no unreleased changes, it stops early.
2. Parses each commit message into type and scope using Conventional Commits conventions. Types map to changelog sections: `feat` becomes "Added", `fix` becomes "Fixed", `refactor` becomes "Changed", and so on.
3. Determines the version bump: any `BREAKING CHANGE` triggers a major bump, any `feat` triggers a minor bump, and everything else triggers a patch bump. If no previous tag exists, it suggests `v0.1.0`.
4. Aggregates the `CHANGELOG-unreleased.d/<category>/` drop files that iterate F4 has been writing since the last release, renders a Keep-a-Changelog versioned section, and inserts it at the structural point in `CHANGELOG.md` (above the first existing `## [version]` heading, NOT blindly at the top, which would corrupt the `# Changelog` title). If `CHANGELOG.md` carries legacy `## [Unreleased]` bullets from pre-refactor iterates, the aggregator emits a loud stderr WARNING so the operator can fold them in manually or accept split-brain.
5. In guided mode, shows you the entry for review with options to accept, edit, or cancel. In autonomous mode, it proceeds without prompting.
6. Commits the changelog, creates an annotated git tag, and pushes both to origin.
7. If you are on a feature branch, it creates a GitHub PR with the changelog as the body. In autonomous mode, the PR is merged immediately; in guided mode, it stays open for your review.

**Standalone usage:** Yes. You can run `/shipwright-changelog` on any git repository with Conventional Commits, whether or not it was built with Shipwright. It is a self-contained release tool.

---

### 4.9 Deployment -- /shipwright-deploy

**Purpose:** Deploys your application with automatic smoke test verification and rollback support, and applies Supabase database migrations when applicable. Deployment is **profile-driven** -- a *deploy profile* declares the target's shape (auth, environments, smoke test, rollback mechanic) so the same deploy discipline holds across mechanically different platforms.

**Deploy targets -- honest status.** Three deploy profiles ship today, and they are **not** equal in maturity:

| Target | Profile | Status |
|--------|---------|--------|
| **Jelastic** (Infomaniak, Switzerland) | `jelastic` | **Verified** (`confidence: verified`) -- the full end-to-end implementation, and the only target the `/shipwright-deploy` flow is actually exercised against. |
| **Vercel** | `vercel` | **Declarative stub** (`confidence: documented`) -- the profile captures the atomic-immutable deploy + deploy-ID rollback mechanic, but the executable flow is not implemented. |
| **Compose-VPS** | `compose-vps` | **Declarative stub** (`confidence: documented`) -- captures the image-tag rollback mechanic; executable flow not implemented. |

The two stubs exist to keep the deploy-profile schema honest across genuinely different rollback mechanics -- they are a design contract, not a shippable path. **In practice, deploying today means deploying to Jelastic.** Adding a real target means implementing the executable flow behind its profile (3-step checklist in `plugins/shipwright-deploy/skills/deploy/references/rollback-discipline.md`). The rest of this section describes the **Jelastic reference flow**.

**Command & Arguments:**

```
/shipwright-deploy                  # deploy to DEV (automatic, no confirmation)
/shipwright-deploy --prod           # deploy to PROD (requires confirmation)
/shipwright-deploy --rollback       # restore PROD from last backup clone
```

**What it needs (Jelastic):**

- `JELASTIC_TOKEN` environment variable (Jelastic API access)
- Optionally: `SUPABASE_ACCESS_TOKEN` (if your project uses Supabase migrations)
- A git repository with a configured remote
- Stack profile environment variables validated by the deploy phase

**What it produces:**

- A deployed application at `dev-{project}.jpc.infomaniak.com` (DEV) or `{project}.jpc.infomaniak.com` (PROD)
- Smoke test verification confirming the deployment is live
- For PROD: a backup clone of the environment before deployment (rollback point)
- Applied database migrations (if Supabase migration files exist)
- Updated `.shipwright/agent_docs/conventions.md` with deployment learnings (when infra gotchas or config quirks discovered)

**How it works (the Jelastic reference flow):**

1. Validates credentials and required environment variables. Missing variables are flagged, and you are prompted to set them before continuing.
2. If Supabase migration files exist in `supabase/migrations/`, they are applied. For DEV, this happens automatically. For PROD, a dry-run is shown first and you must explicitly confirm before applying. Destructive changes always require confirmation regardless of target.
3. For PROD deployments, a full clone of the production environment is created as a safety net before any changes are made. You must confirm the deployment explicitly.
4. Deploys via the Jelastic VCS Update API, pulling the latest code from your git remote.
5. Runs a smoke test against the deployed URL (polling for up to 60 seconds).
6. If the smoke test passes, the phase is marked complete. If it fails, automatic rollback kicks in.

**DEV vs. PROD -- the key difference:** DEV deployments are fully automatic with no confirmation required and use git-based rollback on failure (reverting to the last known good tag). PROD deployments require explicit user confirmation, create a backup clone beforehand, and restore from that clone if anything goes wrong. You can also trigger a manual rollback at any time with `--rollback`, which lists available backup clones and lets you choose which one to restore.

**Universal rollback discipline.** Whatever the target, three patterns hold -- revertable deploys, recorded provenance, documented procedure. They are encoded in the deploy-profile schema (`shared/profiles/deploy-profile.schema.json`; the profiles themselves live in `shared/profiles/deploy/`), so any new target is forced to declare how it satisfies each one. `validate_deploy_profile.py` enforces both the JSON-Schema structure and a layer of cross-field semantic checks. See `plugins/shipwright-deploy/skills/deploy/references/rollback-discipline.md` for the per-pattern mapping across Jelastic / Vercel / Compose-VPS and the 3-step checklist to add a new target.

**Standalone usage:** Yes. You can run `/shipwright-deploy` independently to deploy any project configured for Jelastic. It validates its own prerequisites and does not depend on prior pipeline phases, though it works best after testing has passed.

---

### 4.10 Compliance -- /shipwright-compliance

> **Out-of-band skill, not a pipeline phase.** Compliance is **not** part of `PIPELINE_STEPS`. Instead, it has two surfaces (below), both run **outside** the orchestrator state machine.

**Purpose.** `/shipwright-compliance` has two surfaces:

1. **Auto-background compliance-doc generation** (non-blocking side-effect after every phase completion). The orchestrator calls `update_compliance.py --phase <name>` after each pipeline phase as a fire-and-forget subprocess; no user interaction, no blocking. Produces the same five reports (dashboard, RTM, test-evidence, change-history, SBOM) described below.
2. **On-demand detective audit** (new). `/shipwright-compliance` invoked by a user runs `run_audit.py`, a cross-artifact consistency scan that catches drift the preventive Canon gate and reactive Phase-Quality Stop hook don't see (config ↔ event coherence, content rot in compliance docs, reverse-direction git-log scans, scope-to-doc heuristics, FR-vs-event evidence checks).

Together with preventive Canon and reactive Phase-Quality, it's a three-layer quality net; see `docs/hooks-and-pipeline.md → shipwright-compliance` for the table.

**Command & Arguments:**

```
/shipwright-compliance                          # full detective audit + report
/shipwright-compliance --fix                    # also regenerate stale compliance docs (Group E)
/shipwright-compliance --only C,F,E             # restrict to specific check groups
/shipwright-compliance --format json            # JSON output only
```

**What the detective audit checks** (8 groups):

- **A:** Artifact presence + path integrity. `npm run`, `uv run`, `make` commands in READMEs resolve; markdown links resolve; config path fields point to real files. The composite handler also runs **A5** (CI security-workflow integrity) so `.github/workflows/security.yml` parity drift surfaces here.
- **B:** Config ↔ config ↔ event-log coherence. `project_config.splits[]` matches `.shipwright/planning/NN-*/`; build section test files exist; commits on main have matching `work_completed` events; **B7** reverse-direction git-log scan catches commits without events.
- **C:** Planning internal coherence (preventive re-run): every spec FR appears in a plan section, plan section IDs valid, section manifest ↔ files.
- **D:** Implementation evidence. Every FR has at least one `work_completed` event (D5 enforces FR-or-`spec_impact=none` linkage), every built section has `test_count > 0`.
- **E:** Compliance-doc content staleness. Regenerate each doc in memory, strip volatile `Generated:` header, byte-compare against disk. Strictly deeper than Phase-Quality's mtime checks. A **snapshot-provenance audit** widens coverage to the 8 tracked compliance + agent-doc MDs and walks worktree branch lineage via `find_snapshot_commit` so post-merge state stays clean.
- **F:** ADR structural integrity (preventive re-run F1–F3): unique sequential IDs, valid status enum, supersession refs exist. **F4–F7 doc-hygiene detectors** on top: F4 flags ADRs > 60 lines without a `**Details:** [spec-folder link](...)`; F5 reconciles every decision-drop declaring `architecture_impact` against the *text* of `architecture.md` (the same content oracle the F11 `check_architecture_documented` finalize gate uses); F6 caps `CLAUDE.md` at 200 lines; F7 flags > 5 inline `Iterate X (ADR-N)` annotations leaking into CLAUDE.md.
- **G:** Agent-docs freshness vs. git activity. Conventional-commit scope ↔ architecture.md substring match (with stoplist/alias map), ADR-ID references in commit bodies vs. decision_log.
- **H:** Bloat-policy detective audit. Walks the codebase against `shipwright_bloat_baseline.json`, flags new crossings of the 300-line source / 400-line runtime-prompt budgets, and surfaces ratchets (existing entries that grew past their frozen `current` value). New crossings render as `info` triage items; ratchets are blocked at commit by the pre-commit hook (see Chapter 9 → Bloat anti-ratchet).

> **Detective-only tagging.** Every Group F4–F7 and Group H finding is tagged `SOURCE_DETECTIVE_ONLY` so the audit report distinguishes them from preventive re-runs of F1–F3 / C / B3 / B6. Failing detective checks are mirrored into `.shipwright/triage.jsonl` (source `compliance`) and auto-dismiss when the underlying drift resolves.

**What it needs (detective audit):**
- `shipwright_events.jsonl`: primary event source.
- `.shipwright/planning/*/spec.md` and `.shipwright/planning/*/plan.md`: FR definitions + section manifests.
- `.shipwright/agent_docs/decision_log.md`: ADRs.
- `.shipwright/compliance/` docs (for Group E staleness comparison).
- A git repo (Group B7 reverse-direction scan, Group G git-log activity).

**What it produces (detective audit):**
- `.shipwright/compliance/audit-report.md`: human-readable report split into Preventive re-checks (C/F/B3/B6) and Detective-only checks (everything else). Fail-first ordering, suggested `/shipwright-iterate` command per finding, per-group summary table.
- `.shipwright/compliance/audit-report.json`: structured payload (also emitted on stdout); every finding carries a `source` field (`detective-only` or `preventive-rerun`). Both reports are transient/gitignored, so the gitignore canon covers them in every adopted repo.

**What the auto-background generator produces:**
- `.shipwright/compliance/dashboard.md` -- Start-here overview. It **opens with a Control Verdict + Control Grade (A--F) block**: a plain-language verdict plus a deterministic, importance-weighted control-posture grade computed by `lib/control_grade.py`. The scoring follows **OpenSSF Scorecard's** published methodology -- a weighted average over the *measurable* dimensions, where a not-applicable dimension is **excluded from the denominator** (Scorecard's `-1` "inconclusive" convention) rather than scored 0, and an all-N/A repo renders **"Not Gradeable"** instead of an unearned `F`. Each of the seven dimensions names -- in its **Anchor** column -- the recognized **open** standard it follows (no commercial-vendor tool is cited; the plain-language map of *what each dimension checks* and *what each standard is* lives in the table below), and a `Verified from:` line stamps the event log + commit range so the grade is reproducible (the same scorer later powers the public repo-grader). **The headline can never outrun the weakest control:** a *self-relative* decline in genuine FR-tagging (the recent rate dropping below the repo's own all-time rate) depresses the requirement-traceability dimension, and the verdict is held below "A — full control" whenever a load-bearing pillar is declining, *expected but unmeasured* (e.g. the CI security gate isn't running), or outright broken — so a green headline can never mask a control that has gone dark, while the per-dimension table keeps the full detail. The **change-reconciliation** dimension is measurable from the per-FR impact map (`fr_impact`, documented under the traceability matrix below): it scores the share of behavior-affected requirements that have been re-verified since they were last touched, and is age-neutral -- an old but re-verified change is fully reconciled, while a behavior change left unverified is the gap it surfaces. The **security** dimension is lit from the **CI gate**, not a local re-scan: a producer (`refresh_ci_security.py`) pulls the latest `security.yml` run's `findings.json` and writes a tracked, **public-safe** summary (`.shipwright/compliance/ci-security.json` -- scan date, findings-by-severity, critical-gate pass/fail, and the accepted-via-`.trivyignore` register with expiry; counts + verdict only, no finding detail), rendered as a **CI Security** section below the grade block. Open high/critical from that summary feed the dimension; when no trustworthy CI summary has been ingested it stays **n/a** rather than reading the stale, FP-laden local `securityreports/` as a false CRITICAL (this is also what surfaces security on repos -- e.g. the WebUI -- that keep no local scan reports). The block renders for both adopted and greenfield projects. Then quality indicators, project velocity, and links. Two readability fixes ride along: the **"All unit tests passing" headline reads the latest *full* suite** (not the last event -- often a doc commit -- so a real suite total like `3473/3473` is shown, never a misleading `0/0`), and a **Consistency Audit summary is inlined** from `audit-report.json` rather than linking the gitignored `audit-report.md` (which 404s on public GitHub). Mode-aware: adopted projects (`run_config.adoption` set) render `Pipeline phases completed: n/a (adopted)` instead of a fake `1/7 WARN` and hide the structurally-N/A `Work events (build)` + `All sections reviewed` rows. Every WARN row carries a 4th `Why warn?` column with a one-line diagnostic pointer (`"X failing — see test-evidence.md"`, `"see sbom.md"`, ...). A `Triage open` indicator surfaces the count of open items in `.shipwright/triage.jsonl` (signal severities prominent, info-severity shown in parens, `"3 open (1 info)"`) so the inbox status lives on the compliance home page. A **`Recent changes traced to an FR`** indicator shows the share of the most recent changes that carry an FR tag and WARNs when that rate drops below the all-time rate, so a tagging freeze is visible the day it starts. (This measures genuine FR-linkage; it is the transparency counterweight to the requirement-traceability grade dimension, which also credits explicitly-classified no-FR work -- see below.) **Bloat column:** the per-phase quality matrix carries a Bloat indicator sourced from `shipwright_bloat_baseline.json`: green when no entry's measured LOC exceeds its frozen `current`, WARN when any file ratcheted past its limit, with a one-click pointer to the Group H detective audit.

  **The seven Control-Grade dimensions — in plain language.** Each row's *Anchor* in the dashboard names the open standard in parentheses; this table says what the dimension checks and what that standard actually is (so a non-expert knows exactly what to search for):

  | Dimension (weight) | What it checks — in plain words | Open standard it follows |
  |---|---|---|
  | Requirement traceability (25%) | Every requirement is linked to the work and tests that implement & verify it | **ISO/IEC/IEEE 29148** — the requirements-engineering standard that mandates bidirectional requirement→verification traceability |
  | Test health (20%) | The latest *full* test suite is green (high pass-rate) | **OpenSSF Scorecard** — the Linux-Foundation open project-health scorer this whole grade is modeled on (its automated-tests check) |
  | Change traceability (15%) | Every change links back to a commit, ADR or test run — you can see where it came from | **SLSA** — tamper-evident build & change provenance |
  | Change reconciliation (15%) | When a requirement's behaviour changes, it gets re-verified — *age is never penalised* | **ISO/IEC/IEEE 12207** — the software-life-cycle standard that requires changed items to be re-verified |
  | Security (10%) | No open high/critical vulnerabilities (read from the CI security gate) | **NIST SSDF** (SP 800-218) — secure-development practices, incl. addressing known vulnerabilities |
  | Size / maintainability (10%) | Code isn't growing unchecked (size / bloat discipline) | **ISO/IEC 25010** — the software-product-quality model that defines *maintainability* |
  | Dependency hygiene (5%) | Dependency licences are resolved and there are no copyleft surprises | **OWASP** — vulnerable/outdated-components risk (Top-10 A06) |

- `.shipwright/compliance/traceability-matrix.md` -- Every requirement mapped to the work events that verify it, with a neutral **"Last tested"** column (the date of the latest event that ran tests -- age is informational, *not* a penalty) and a per-FR **"Reconciled?"** column (✅ behavior-affected requirement re-verified since its last change · ⚠️ needs re-verification · — not behavior-touched). Full requirement titles, a column legend, and clickable cross-references round out the readability: the `(iter)` token in "Last tested" links to the event's row in the **Verification Timeline** (sorted newest-first), whose FRs link back to the matching coverage row and whose commits link to their diff on the repository host. The Requirements Coverage Status cell renders `FAIL → [trg-XXX](../agent_docs/triage_inbox.md#trg-XXX)` deep-links for every FR with an open triage card carrying `frId == row.fr_id` (overrides COVERED / COVERED (baseline) when an operator flagged a regression). The Coverage Summary section gains three operator-actionable subsections rendered only when non-empty: "FRs without tests", "FRs needing re-verification" (behavior changed without a later test run -- reconciliation-driven, never age-based), "FRs with open triage items". **FR-mapping discipline:** every iterate change is *traced* -- it either names the FR(s) it touches (`affected_frs`) or is classified as an explicit no-FR change (a recognized `change_type` of `docs`/`tooling`/`compliance`/`infra` plus a one-line reason). The fail-closed finalize verifier blocks a **behavior-affecting** change (one that declares `spec_impact` of add/modify/remove) that names no FR -- the no-FR path is reserved for behavior-preserving work, so a real behavior change can never dodge requirement linkage. The requirement-traceability grade dimension credits both forms (FR-linked and satisfied no-FR), since each represents a change consciously mapped to a requirement decision; FR coverage itself is all-time (a requirement untouched recently is under control, not a gap -- re-verification under change is the separate reconciliation signal). **Per-FR impact (`fr_impact`):** a `work_completed` event may carry an `fr_impact` map (`{FR-id: add|modify|remove|none}`) recording how each FR it touches was affected -- `add`/`modify`/`remove` are behavior-affecting, `none` is referenced-but-preserving. The change-reconciliation grade dimension reads it: a requirement whose behavior was changed counts as *reconciled* once a later-or-same test run re-verifies it, and as needing re-verification otherwise. Events that predate the map fall back to the event-level `spec_impact` applied to their `affected_frs`. The RTM's **"Reconciled?"** column and its **"FRs needing re-verification"** subsection read the *same* `_reconciliation` helper this grade dimension consumes, so the matrix and the grade can never disagree -- and both are **age-neutral**: an old change that was re-verified stays reconciled forever, while only an unverified behavior change is surfaced as a gap.
- `.shipwright/compliance/test-evidence.md` -- Test results across unit / integration / pgTAP / smoke / E2E / consistency / visual, with pass/fail counts and skip reasons. **Layer column:** the `## Test Progression` table classifies each work_completed event into `unit | e2e | mixed | —`; `## Full Suite Runs` breaks out Integration + pgTAP alongside Unit + E2E (sourced from the `layers.integration` and `layers.pgtap` keys on test_run events). The Event column prefers a plain-language `summary` when the event recorded one (falling back to the technical description), and the `Source` token links each iterate event to its row in the sibling matrix's Verification Timeline. When no `test_run` events exist, `## Full Suite Runs` is synthesized from per-iterate **unit** results and notes that the other layer columns are unavailable (breakdown absent, not tests failing). **Triage producer:** one `source="test-evidence"` triage item per failing layer in the latest test_run event, dedupKey `test-fail:<layer>`, severity layer-based (high for e2e/integration/pgtap, low for unit), `eventId` cross-link to the originating test_run, `launchPayload` carries `/shipwright-iterate --type bug`. Auto-dismisses layers that go green.
- `.shipwright/compliance/change-history.md` -- All commits + decisions (from `.shipwright/agent_docs/decision_log.md`) + version tags.
- `.shipwright/compliance/sbom.md` -- Software Bill of Materials with versions and license types. Flags copyleft licenses. **Triage producer:** when a workspace manifest (`package.json` / `pyproject.toml`) carries packages whose licenses can't be resolved from `package-lock.json` / `importlib.metadata`, one `source="sbom"` triage item per workspace lands in `.shipwright/triage.jsonl` with `dedupKey="sbom:undeclared:<manifest-rel-path>"`, the top-20 offenders in the body, and a copy-pasteable `launchPayload` (`cd <workspace> && npm install` / `uv sync`, then re-run `update_compliance.py`). Auto-resolves on the next clean run.

**How the detective audit works:**
1. `run_audit.py` loads `audit_config.json` (G2 scope stoplist, alias map, A4 path-field allowlist, B7 exclusions) and `ComplianceData`.
2. Version gate probes every symbol the audit imports. On drift, the audit aborts with exit code 3 and a single message naming every missing / reshaped symbol: no silent coverage loss.
3. Each registered group runs; failures in one group don't take down the others.
4. Group E (per-doc staleness) optionally auto-regenerates the specific stale doc when `--fix` is passed. Other groups never write to the working tree.
5. `audit_report.py` renders Markdown + JSON. stdout always carries the JSON payload with a `written` map pointing at the on-disk artifacts.

**Auto-background mode:** Fires after every `/shipwright-run` phase. If the compliance plugin is missing, the orchestrator **loud-fails** (stderr JSON warning + `compliance_update_failed` event) so a broken install is visible rather than silently skipped.

**Standalone usage:** Yes. You can run `/shipwright-compliance` at any point during or after the pipeline. The detective audit works against whatever data is present: missing inputs surface as skipped findings with a concrete reason rather than fabricating passes.

### 4.11 Triage Inbox (cross-cutting intake)

Pre-backlog buffer for findings emitted by hooks, scans, and audits. Triage and the backlog (`ExternalTask` in [shipwright-webui](https://github.com/svenroth-ai/shipwright-webui)) are separate stores; **promote** is the explicit bridge between them. The inbox is a **launch-surface**, not a finding-mirror; see § 4.11.1 below.

- **Store:** `.shipwright/triage.jsonl`, the **git-tracked SSoT** backlog (per project, append-only with history events). It is committed like `shipwright_events.jsonl`: an explicit `!/.shipwright/triage.jsonl` negation in the canonical gitignore makes it trackable inside the otherwise-ignored `.shipwright/` subtree (only the `.lock` / `.bak` siblings stay ignored). Producers append **per-tree**; iterate finalize **F6** stages it so deltas ship in that iterate's PR; concurrent cross-worktree appends reconcile automatically via the churn resolver (`resolve_churn_conflicts._reconcile_triage` → `churn_merge.dedup_triage_lines` + `validate_triage_text`, with `TRIAGE_LOG` in `CHURN_ALLOWLIST`): a union + exact-line dedup that preserves the intentional `append`+`status` shared `id` without a false dedup warning. The committed `.shipwright/agent_docs/triage_inbox.md` is a pure **derived view** of this log (regenerated by `aggregate_triage.py`), not an independent store. Keys are camelCase because the wire format is shared with the [shipwright-webui](https://github.com/svenroth-ai/shipwright-webui) `ExternalTask` schema; status resolution is last-status-wins by file order, and lines that fail JSON-decode are skipped with a stderr warning. Status enum: `triage` (new) → `promoted` (turned into ExternalTask) / `dismissed` (operator decision) / `snoozed` (defer).
- **Producers:** `audit_phase_quality_on_stop` (Tier-1 FAILs, 24h dedup), `audit_detector.mirror_findings_to_triage` (compliance findings + auto-dismiss when resolved), `generate_security_report._emit_findings_to_triage` (security-report runs), `performance_check._emit_failures_to_triage` (perf-gate runs), `check_drift._emit_drift_to_triage` and `artifact_sync._emit_drift_to_triage` (drift hooks), and the throttled SessionStart hook `import_github_findings.py` (GitHub action-units, see § 4.11.1 below).
- **Consumer:** the Stop hook `aggregate_triage_on_stop` regenerates `.shipwright/agent_docs/triage_inbox.md` after every iterate finalize. Every open item carries an optional `launchPayload` field; when present, the aggregator renders it inside a fenced markdown code block under the item header, and operators copy that fence into a new Claude session to start the matching run (§ 4.11.1). Rendered output is capped at 50 items per source, sorted by `(severity, originalTs DESC)`.
- **Operate from CLI** (first-class, parallel to the WebUI Triage tab):
  - `uv run shared/scripts/tools/triage_cli.py list`: list open items + their `launchPayload`.
  - `uv run shared/scripts/tools/triage_cli.py promote trg-XXXXXXXX --task-ref "EXT:linear-ENG-7"`: promote to backlog.
  - `uv run shared/scripts/tools/triage_cli.py dismiss trg-XXXXXXXX --reason notRelevant`: dismiss as false-positive / won't-fix.
  - The pre-existing `triage_promote.py --id …` tool is unchanged for back-compat; the new `triage_cli.py promote` subcommand delegates to the same library helper (`triage_promote.promote`), so audit-trail shape is byte-identical (only the `by` field differs: `"cli"` vs `"manualPromote"`).

Mapping is mechanical: `critical→P0 / high→P1 / medium→P2 / low→P3 / info→P3` for severity; `compliance→compliance / else→engineering` for source domain. Both values are recorded on the triage record as `suggestedPriority` + `suggestedDomain` so the promote step doesn't have to recompute them; the mapping matches the `leadwright` ExternalTask extension (see [`leadwright/docs/specs/phase-1-external-task-extension.md`](https://github.com/svenroth-ai/leadwright)). The full table lives in `shared/scripts/triage.py` (`PRIORITY_FROM_SEVERITY`, `DOMAIN_FROM_SOURCE`) and is exported as the SSoT; tests assert against the imports, not duplicated literals.

#### 4.11.1 Triage as Launch-Surface

A triage item represents **one handling**, not one finding. GitHub already has a per-finding store (Security tab, Dependabot tab, secret-scanning tab); mirroring it 1:1 would flood the operator. Instead, the GitHub producer collapses findings into a small set of **action-units**:

| Source                                | Action-unit dedup key             | Maps to                                                       |
|---------------------------------------|-----------------------------------|---------------------------------------------------------------|
| code-scanning + Dependabot (combined) | `gh-security:{owner}/{repo}`      | `/shipwright-security`                                        |
| secret-scanning                       | `gh-secrets:{owner}/{repo}`       | Manual rotation (no slash command, secret rotation is manual)|
| failed default-branch CI per workflow | `gh-ci:{workflow_id}`             | `/shipwright-iterate --type bug`                              |
| failed hard-gates on an open PR       | `gh-pr-ci:{pr_number}`            | `/shipwright-iterate --type bug` (automerge loop-closing)     |
| shipwright-security prompt-injection (artifact) | `gh-prompt:{owner}/{repo}` | `/shipwright-security` (parallels `gh-security`; separately dismissable, GHAS-independent, sourced from `prompt_risks.json`) |

**Two ingestion paths for the `gh-security` action-unit:**

- **GHAS API path** (preferred when available): `import_github_findings.py` calls the `code-scanning/alerts` + `dependabot/alerts` GitHub APIs. Requires GitHub Advanced Security on private repos.
- **shipwright-security artifact path** (fallback, fires when `cs_alerts is None`): the importer downloads the latest successful run's `security-scan-results` artifact via `gh run download` and parses `findings.json`. Gated by a freshness window (`SHIPWRIGHT_GITHUB_ARTIFACT_MAX_AGE_DAYS`, default 14d) and only attempted on the default branch. This makes Shipwright work on private repos without paying for GHAS.

Both paths produce the SAME dedup key and `launchPayload` contract; `by_source["gh-security:artifact"]` distinguishes the ingestion path for telemetry. See **[docs/security-ci-setup.md](security-ci-setup.md)** for the choice between paths and the activation procedure.

**Loop-closing for auto-merge (`gh-pr-ci:{pr_number}`).** The `gh-ci` source only watches the **default branch**. Once GitHub-native auto-merge is armed, a hard-gate that goes red on the **open PR** would leave it "armed but waiting" with no visibility. The `gh-pr-ci` source closes that loop: for each non-draft open PR carrying ≥1 failing check (`failure`/`timed_out`/`startup_failure`/`cancelled`/`action_required`), the importer emits one action-unit whose `launchPayload` starts `/shipwright-iterate --type bug`. Draft PRs are excluded (a draft can't be auto-merge-armed). Auto-resolve is **differentiated** (`prChecksResolved` for PR still open with checks green, `prMerged`, or `prClosed`) and is gated by the same symmetry rule as the other sources: if the open-PR list **or any** per-PR check-runs fetch fails, the whole PR-CI source is skipped this run (no emit, no resolve) so a transient network failure never mass-resolves open items.

Each action-unit carries a `launchPayload`: a ready-to-paste block containing the slash command + context + the relevant GitHub URL. The payload is **frozen at first append** (subsequent imports with the same key are deduplicated and the persisted payload is unchanged); live counts in `detail` are best-effort, so operators click through the GitHub URL for current state.

Operator flow has three verbs:

- **Fix now:** open `.shipwright/agent_docs/triage_inbox.md` (or run `triage_cli.py list`), copy the `launchPayload` fence into a new Claude session. The matching slash command auto-fires and the run resolves the item via the existing lifecycle hooks.
- **Promote:** `triage_cli.py promote <id> --task-ref EXT:<ref>` creates a backlog task for deferred work; the item flips to `promoted`.
- **Dismiss:** `triage_cli.py dismiss <id> --reason <reason>` for false-positives / won't-fix. (Per-finding false-positives are dismissed on GitHub at SARIF level, not in the triage inbox.)

Legacy producers (phase-quality, drift, compliance, security, performance, F0.5) stay finding-granular; they MAY emit `launch_payload=None` and the renderer falls back to the historical bullet layout. Only the GitHub action-unit emitter populates `launchPayload` today; the WebUI Triage-tab in `shipwright-webui` is a thin wrapper over the same library helpers so the CLI is the single source of truth.

#### 4.11.2 Triage Producer Contract

Codified in `shared/schemas/triage_item.schema.json`. The schema is
the SSoT for the JSONL wire shape: three
event kinds share `.shipwright/triage.jsonl`: the file header (line 1),
`append` events (one per new triage item), and `status` events (one
per Promote / Dismiss / Snooze).

Required `append` fields: `event`, `id`, `ts`, `originalTs`, `source`,
`severity`, `kind`, `title`, `detail`, `status`, `suggestedPriority`,
`suggestedDomain`.

Optional `append` fields (always persisted, `null` when omitted so
consumers can read without `.get(..., default)`):

| Field           | Purpose                                                                    |
|-----------------|-----------------------------------------------------------------------------|
| `evidencePath`  | Scanner output / log / report backing the item                              |
| `runId`         | Iterate / pipeline run that emitted it                                      |
| `commit`        | Commit SHA observed                                                         |
| `dedupKey`      | Producer-stable id for idempotent re-emit (convention `<producer>:<key>`)   |
| `launchPayload` | Ready-to-paste Fix-now block (§ 4.11.1)                                     |
| `frId`          | FR id this item is rooted in (e.g. `FR-01.05`)                              |
| `suiteId`       | Test-suite identifier, lets the RTM cross-link failing rows                |
| `eventId`       | Back-ref into `shipwright_events.jsonl`                                     |

The three FR / suite / event refs are populated opportunistically by
producers that have the context (the test-evidence emitter does; the
generic drift / phase-quality producers don't). When present, the
compliance RTM renderer emits `[FAIL → trg-XXX](triage_inbox.md#trg-XXX)`
deep-links; the aggregator stamps an HTML anchor
`<a id="trg-XXX"></a>` above each card so the link resolves in plain
markdown (VS Code preview, CommonMark, GitHub) without any WebUI
dependency.

**Inbox render layout.** The aggregator (`aggregate_triage.py`)
partitions open items by severity: `critical / high / medium / low`
render in the existing top section, severity-sorted; `info` items
collapse into a `<details>` block at the end of `triage_inbox.md` so
the surface stays signal-first.

## 5. Stack Profiles

A **stack profile** is a JSON file that defines everything about your technology stack in one place: runtime versions, frontend and backend libraries, UI component library, testing frameworks, deployment target, folder structure, CI pipeline, and architecture rules. Profiles are stored in `~/shipwright/shared/profiles/`.

When you run `/shipwright-run`, Shipwright infers the correct profile from your project description (or asks you to confirm). Every downstream skill -- project decomposition, planning, build, test, deploy -- reads the profile to make consistent decisions without you repeating configuration.

Three profiles ship out-of-the-box:

| Profile | Layout | When to use |
|---------|--------|-------------|
| `supabase-nextjs` (default) | Single-service Next.js + Supabase | Standard SaaS: Next.js full-stack with Supabase as backend |
| `vite-hono` | Multi-service: Vite (frontend) + Hono (backend) | Split frontend/backend with a separate API server (or any project that wants the Vite dev-experience) |
| `python-plugin-monorepo` | Python `uv` workspace, no web server | Libraries, frameworks, or CLI / plugin monorepos with no deployable frontend (pytest + ruff, no dev server, no deploy target) |

The `vite-hono` profile uses the multi-service `services: [...]` declaration documented in Section 7.3 (topo-ordered start, `depends_on` between services, partial-failure rollback). Legacy single-service profiles continue to use `dev_server: {...}`. The `python-plugin-monorepo` profile sets `dev_server: null` and `deploy: null`, so `/shipwright-preview` and `/shipwright-deploy` skip cleanly for projects that have nothing to serve or ship. (The Shipwright monorepo itself uses this profile.)

**Sibling concept -- Deploy Profiles.** Where stack profiles describe the build-and-run shape of a project, **deploy profiles** describe the deploy-target shape (auth, environments, smoke test, rollback discipline). They live at `shared/profiles/deploy/<target_id>.json`, are validated against `shared/profiles/deploy-profile.schema.json`, and are introduced in Section 4.9. Three reference deploy profiles ship today: `jelastic` (full implementation), `vercel` (declarative stub), `compose-vps` (declarative stub). The validator at `shared/scripts/tools/validate_deploy_profile.py --all` enforces both JSON-Schema structure and a layer of cross-field semantic checks.

### The supabase-nextjs Profile

The default profile ships a modern full-stack setup:

| Layer | Technology | Version |
|-------|-----------|---------|
| Runtime | Node.js, TypeScript | 22.x, ^5.9.3 |
| Frontend | Next.js (App Router), React, Tailwind CSS | ^16.2.0, ^19.2.4, ^4.2.0 |
| State | Zustand | ^5.0.12 |
| UI Components | shadcn/ui (react-hook-form + zod for forms) | ^4.0.0 |
| Backend | Supabase (JS client, CLI, Edge Functions) | ^2.99.3, ^2.82.0 |
| Auth | Supabase Auth (email + OAuth) | Built-in |
| Storage / Realtime | Supabase Storage, Supabase Realtime | Built-in |
| Design System | Untitled UI (for mockups) | -- |
| Unit Testing | Vitest | ^4.1.0 |
| E2E Testing | Playwright | ^1.58.2 |
| Security Scanning | OSS (Semgrep, Trivy, Gitleaks); Aikido optional/legacy | Local CLI; Aikido via Cloud API |
| Linting | ESLint (flat config), Prettier | ^10.0.3, ^3.8.1 |
| Error Tracking | Sentry | ^10.45.0 (free tier) |
| CI | GitHub Actions | On push + PR |
| Deploy | Jelastic (Infomaniak), standalone output | -- |

### Project Folder Structure

```
src/app/                    Next.js App Router pages
src/components/             React components
src/lib/                    Utility functions
src/hooks/                  Custom React hooks
supabase/migrations/        SQL forward migrations
supabase/migrations/_rollback/  SQL rollback migrations (down.sql)
supabase/functions/         Edge Functions
tests/                      Vitest unit tests
e2e/                        Playwright E2E tests
public/                     Static assets
```

### Key Architecture Rules

The profile enforces these conventions across all pipeline phases:

- Feature modules must not import from other feature modules.
- All Supabase calls go through `lib/supabase/` -- no direct client usage in components.
- All API calls go through `lib/api/` -- no `fetch()` in components.
- Server Components by default -- `'use client'` only when needed.
- No business logic in API routes -- use Edge Functions.
- All database changes via migrations in `supabase/migrations/`.

### Required Environment Variables

| Variable | Purpose | Required For |
|----------|---------|-------------|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL | Build |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anonymous key | Build |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (admin ops) | Build |
| `JELASTIC_TOKEN` | Infomaniak Jelastic API token | Deploy |
| `SUPABASE_ACCESS_TOKEN` | Supabase CLI token for migrations | Deploy (optional) |
| `OPENROUTER_API_KEY` | OpenRouter key for external plan review | Plugin (optional) |
| `GEMINI_API_KEY` | Google Gemini key (alternative to OpenRouter) | Plugin (optional) |
| `OPENAI_API_KEY` | OpenAI key (alternative to OpenRouter) | Plugin (optional) |
| `AIKIDO_CLIENT_ID` | Aikido Security API client ID | Plugin (optional, legacy; OSS preferred) |
| `AIKIDO_CLIENT_SECRET` | Aikido Security API client secret | Plugin (optional, legacy; OSS preferred) |

### Generated-App DX (Vite-based profiles)

Vite-based profiles (e.g. `vite-hono`) get three drop-in templates from `shared/templates/` baked into newly built projects:

- `vite.config.ts.template`: `defineConfig(({ mode }) => …)` form with a mode-gated slot for dev-only Vite plugins, sensible defaults (sourcemaps, `host: true` for tunnels), and `minify` switched off in dev so the runtime-error overlay shows usable stacks.
- `dev-error-overlay.tsx.template`: React component that listens for `window.error` + `unhandledrejection` and renders a modal in dev mode with the error and stack. Renders `null` in production via `import.meta.env.DEV`.
- `dev-banner.tsx.template`: small fixed-position pill so a dev tab cannot be confused with a prod tab. Customizable label (`<DevBanner label="DEV — staging" />`).

`/shipwright-build` writes these into newly generated apps automatically. `/shipwright-adopt` lists them as opt-in offers in the adoption handoff but never overwrites an existing `vite.config.ts`. Both components are self-contained, with no extra npm dependency beyond React itself.

---

## 6. Configuration

Shipwright works out of the box for the core cycle (project, plan, build). Configuration is only needed for optional features: deployment, external plan review, and security scanning.

### Environment Variables (.env.local)

All environment variables go in your **project's** `.env.local` file. This file is never committed to version control. Variables already set in your OS environment take precedence.

To generate a template with all required and optional variables:

```bash
uv run shared/scripts/validate_env.py --project-root /path/to/your-project --phase all --init
```

This creates `.env.local` with placeholders for build, deploy, and plugin variables. Fill in only the values you need.

### Deployment Setup (Jelastic)

Required for `/shipwright-deploy`. Obtain your token from the Infomaniak Jelastic Dashboard under Settings > Access Tokens, then add to `.env.local`:

```
JELASTIC_TOKEN=your-jelastic-api-token
```

The profile configures two deployment environments: **DEV** (auto-deploy on push to `develop` or `feature/*` branches) and **PROD** (manual deploy from `main`, requires confirmation and pre-deploy snapshot).

### External LLM Review

Shipwright can send artifacts to external LLMs (Gemini + OpenAI in parallel) for an independent second opinion. The same CLI -- `shared/scripts/tools/external_review.py` -- runs three review modes; which one fires depends on the phase that triggers it.

| Mode | Trigger | Reviews | Marker file |
|---|---|---|---|
| `--mode plan` | `/shipwright-plan` Step 5 | full implementation plan vs project spec | `external_review_state.json` |
| `--mode iterate` | `/shipwright-iterate` medium+ pre-build | mini-plan vs iterate spec | `external_review_state.json` |
| `--mode code` | `/shipwright-build` Step 6c (opt-in) and `/shipwright-iterate` medium+ post-build cascade | code diff vs section/iterate spec | `external_code_review_state.json` |

Plan and iterate modes share the same marker file; code mode writes a distinct one so the two gates stay independent.

**Provider configuration (same for all three modes):**

**Option A -- OpenRouter (recommended):** One key covers both review models (Gemini and OpenAI routed through OpenRouter).

```
OPENROUTER_API_KEY=sk-or-your-key
```

**Option B -- Direct API Keys:** Use Google and OpenAI APIs directly.

```
GEMINI_API_KEY=your-gemini-key
OPENAI_API_KEY=sk-your-key
```

**Option C -- Self-review fallback:** Leave keys unset. `/shipwright-plan` and medium+ `/shipwright-iterate` will prompt you at Step 5 and, if you choose to skip, run a mandatory self-review ("2x denken") pass. The opt-out decision is logged in the decision log and `external_review_state.json`, so audits still see it. Silent skipping is no longer possible.

**Code-review-mode opt-in (per phase):**

- `/shipwright-build` -- default **off**. Enable per project or per section in `shipwright_build_config.json`:
  ```json
  { "external_code_review": { "enabled": true } }
  ```
- `/shipwright-iterate` -- default **on** for medium+ runs that already triggered the internal `code-reviewer` subagent (no new threshold). Same Branch A/B/C interactive opt-out flow as the mini-plan review. To opt out at the project level: `shipwright_iterate_config.json` -> `external_code_review.enabled: false`. This flag is independent of `external_review.feedback_iterations` -- you can disable plan/iterate-mode reviews while keeping the code-review cascade on, and vice versa.

**Diff exposure warning:** Code-review mode transmits the staged diff to whichever LLM provider is configured. Diffs can contain secrets, customer data, or code under restrictive license/NDA terms more often than markdown plans do. If those risks apply to your project, leave the cascade off (build) or set `external_code_review.enabled: false` (iterate). The diff is read from `/tmp/shipwright-review-diff.txt` -- the same file the internal subagent uses.

**Empty-diff short-circuit:** Code mode skips the API call entirely if the diff file is empty or whitespace-only. The marker records `status: skipped_user_opt_out` with `reason: "empty_diff"`.

**Model overrides:** All three modes honor `SHIPWRIGHT_REVIEW_MODEL_<KEY>` env vars (`GEMINI`, `CHATGPT`, `OPENROUTER_GEMINI`, `OPENROUTER_CHATGPT`) for one-off A/B testing of different model versions without editing config.

### Security Scanning

`/shipwright-security` runs **out-of-band** (not as a pipeline phase; see Section 4.7). It supports two backends:

**Option A -- OSS Backend (recommended; local, free, actively maintained):** Install one or more CLI tools on your machine:

- **Semgrep** (SAST): `pip install semgrep` or `brew install semgrep`
- **Trivy** (SCA): `brew install trivy` or download from [GitHub releases](https://github.com/aquasecurity/trivy/releases)
- **Gitleaks** (Secrets): `brew install gitleaks` or download from [GitHub releases](https://github.com/gitleaks/gitleaks/releases)

Each tool is optional -- install at least one to enable the OSS backend. Semgrep and Trivy auto-update their rules/vulnerability databases on every scan.

**Option B -- Aikido Backend (optional, legacy, see Section 4.7 note):** Add your API credentials:

```
AIKIDO_CLIENT_ID=your-client-id
AIKIDO_CLIENT_SECRET=your-client-secret
```

**Backend selection** is automatic, but auto-detection probes **Aikido first**: if `AIKIDO_CLIENT_ID` is set, Aikido is chosen; otherwise it falls back to the OSS tools on PATH. So OSS is the recommended, actively-maintained path and the effective default *when no Aikido credentials are present*: a repo that has both configured will get Aikido (whose API path has not been re-verified end-to-end). To force OSS even with Aikido creds set, use `SHIPWRIGHT_SCANNER_BACKEND=oss` (or the profile's `testing.security.provider`).

`/shipwright-security` only runs when at least one backend is available; if neither is configured it prints setup instructions and stops.

### Performance Budgets

`/shipwright-test` runs a performance budget check when the stack profile sets `testing.performance.enabled: true`, or when the project opts in through `shipwright_test_config.json`. It measures two things:

- **Lighthouse** -- performance score and Largest Contentful Paint (LCP), run through the project's existing Playwright Chromium (no extra browser install).
- **Bundle size** -- total gzipped `*.js` / `*.css` under the build output directory.

Opt in and tune the budgets in `shipwright_test_config.json`:

```json
{
  "performance": {
    "enabled": true,
    "gate": "block",
    "lighthouse": { "min_score": 90, "lcp_max_ms": 2500 },
    "bundle": { "max_kb_gz": 300, "build_output_dir": "dist" }
  }
}
```

Override precedence, most specific wins: `--gate` CLI flag -> `shipwright_test_config.json` -> stack profile -> built-in defaults (`min_score` 85, `lcp_max_ms` 2500, `max_kb_gz` 250, `gate` `warn`). Settings are deep-merged, so a project can override one budget and inherit the rest.

The `gate` decides what a missed budget does: `warn` (default) logs it without blocking the test phase; `block` fails the phase. Start on `warn` and switch to `block` once your budgets are calibrated. The bundle sub-check needs `build_output_dir` set plus a prior production build -- without it the bundle check is skipped while Lighthouse still runs.

### Validating Your Setup

Run the verification script to check that prerequisites and configuration are correct:

```bash
~/shipwright/scripts/verify-setup.sh
```

For per-phase validation (checking only the variables needed for a specific phase):

```bash
uv run shared/scripts/validate_env.py --project-root . --phase build
uv run shared/scripts/validate_env.py --project-root . --phase deploy
uv run shared/scripts/validate_env.py --project-root . --phase all
```

---

## 7. Working with Shipwright

### 7.1 Multi-Split Projects

Large projects are automatically decomposed into **splits** -- independent, shippable chunks of functionality. The `/shipwright-project` phase interviews you about requirements, then groups related features into splits. Each split gets its own spec, plan, and build cycle.

The pipeline loops through splits sequentially: plan split 1, build all its sections, then plan split 2, build its sections, and so on. Testing, changelog, and deployment only run after all splits are complete. Compliance docs are updated as an auto-background side effect of every phase completion, not as an explicit pipeline phase (see Chapter 4.10).

For example, a SaaS app might decompose into:
- **Split 1:** Authentication and user management
- **Split 2:** Core domain features (dashboard, CRUD)
- **Split 3:** Billing and subscription management

Each split is further divided into **sections** -- the smallest unit of implementation. A section maps to a single Conventional Commit.

### 7.2 Iteration Mode

Once your project exists, use `/shipwright-iterate` for fast changes:

```
/shipwright-iterate "Add dark mode toggle"
```

`/shipwright-iterate` reads your existing `CLAUDE.md` and project structure, auto-detects intent (feature, change, or bug), assesses complexity and risk, then runs an adaptive pipeline -- from a quick fix for trivial changes to a structured mini-SDLC with planning, external review, and full testing for medium-complexity work. Large changes get an escape hatch to the full pipeline. This is the intended daily workflow after the initial build. See [Chapter 8](#8-ongoing-development-with-shipwright-iterate) for details.

### 7.3 Using Skills Individually

Every skill works standalone -- you do not always need the full pipeline:

| Command | Use Case |
|---------|----------|
| `/shipwright-project "Build a dashboard"` | Just decompose requirements into specs |
| `/shipwright-plan @spec.md` | Just plan one split from a spec file |
| `/shipwright-build @sections/01-models.md` | Just implement one section |
| `/shipwright-test` | Just run the test suite |
| `/shipwright-preview` | Start local dev server and open in browser |
| `/shipwright-test --design-fidelity` | Run design fidelity check only (code-level mockup vs implementation) |
| `/shipwright-deploy` | Just deploy to Jelastic |
| `/shipwright-changelog` | Just generate changelog and create a PR |
| `/shipwright-security` | Run security scan (out-of-band, not a pipeline phase). OSS backend by default; Aikido optional. |
| `/shipwright-compliance` | Detective cross-artifact audit (flags: `--fix` regenerate stale compliance docs, `--only C,F` restrict to groups, `--format md\|json\|both`). Out-of-band; also fires as auto-background side-effect after every pipeline phase. |

When using skills individually, provide the input artifact (spec file, section file) as an argument. The skill reads what it needs from the project's config files.

> **Note.** `/shipwright-security` and `/shipwright-compliance` are **not** part of the orchestrator pipeline (`PIPELINE_STEPS`). Security runs purely on demand or via CI. Compliance has two surfaces: a non-blocking auto-background doc update after every completed phase **and** an on-demand detective audit you trigger explicitly. See Sections 4.7 and 4.10 for the full mechanics.

**Local Preview.** `/shipwright-preview` starts the development server and shows the URL (e.g., `http://localhost:3000`). Available after at least one build split is complete. The preview uses the `dev_server` configuration from the stack profile -- new stack profiles must define `dev_server.command`, `dev_server.port`, and `dev_server.ready_path` in their profile JSON.

**Multi-service profiles.** Stack profiles can declare a `services: [...]` array instead of `dev_server: {...}` to manage projects with split frontend + backend (Vite+Hono, Next.js+separate API, Rails+Vue, …). Each entry: `{name, command, port, host?, scheme?, ready_path?, ready_timeout_seconds?, depends_on?, primary?}`. Topo order is enforced via `depends_on`; partial-failure rollback kills every started service in reverse. The `primary` flag (or first-declared) determines which service's URL appears as top-level `url` in the dev_server JSON output. See `shared/profiles/vite-hono.json` for a working example. Legacy single-service `dev_server: {...}` profiles continue to work via internal normalization. For projects without a matching profile, `/shipwright-adopt` can also pass an inline `--services-json '<array>'` to `dev_server.py`, derived from the multi-service detector's snapshot output.

### 7.4 Session Recovery and Handoff

Claude Code has a finite context window. During long builds, Shipwright monitors context pressure and, when the window is filling up, automatically generates a **session handoff** document (`.shipwright/agent_docs/session_handoff.md`) containing the current phase, split, section, completed work, and next steps.

To resume after a pause or context limit:

1. Start a new Claude Code session (or type `/clear`).
2. Shipwright reads `shipwright_run_config.json` and `.shipwright/agent_docs/session_handoff.md`.
3. The pipeline resumes from where it left off.

All state is file-based -- nothing lives only in memory. You can interrupt at any point, close your editor, and come back later.

### 7.5 The Constitution

The **constitution** (`shared/constitution.md`) defines behavioral boundaries for all Shipwright agents and subagents. It is organized into three tiers:

**ALWAYS (do without asking):**
- Run tests before committing -- tests must pass.
- Generate `down.sql` rollback for every migration.
- Use Conventional Commits (`feat:`, `fix:`, `refactor:`, etc.).
- Use parameterized queries -- never interpolate user input into SQL.
- Validate input at system boundaries.
- Run the self-review checklist before committing.
- Log deviating decisions in `.shipwright/agent_docs/decision_log.md`.
- Keep files under **300 lines (source / tests) / 400 lines (runtime-prompts: `SKILL.md`, `CLAUDE.md`, plugin agents, shared prompts)**, split if larger. The bloat anti-ratchet hook hard-blocks commits that grow an allowlisted entry past its frozen `current`; new crossings are advisory and surfaced by the Group H detective audit post-merge. Exceptions go through `.shipwright/planning/adr/_template-bloat-exception.md` with mandatory Ousterhout / YAGNI / Chesterton-Fence / Re-Review-Date / Incident-Reference fields. Allowlist / Ratchet / Anti-Ratchet vocabulary lives in `shared/glossary.md`.
- Fix the code, not the test -- never weaken assertions to pass.

**ASK FIRST (require user confirmation):**
- Destructive database operations (`DROP TABLE`, `DROP COLUMN`, `TRUNCATE`).
- Production deployments (always confirm + backup).
- Skipping test layers (must provide a valid reason).
- Overriding phase validation gates (`--force`).
- Continuing after 3 failed fix attempts.

**NEVER (hard stops):**
- `rm -rf` on root or home directories.
- `git push --force` to main/master.
- `git reset --hard`.
- `--no-verify` to bypass pre-commit hooks.
- `DROP DATABASE`.
- Skip or weaken tests to make them pass.
- Add features beyond spec (YAGNI).
- Hardcode secrets in source code.
- Commit `.env` files.

The most critical rules are also enforced programmatically by hooks (see Chapter 9).

---

## 8. Ongoing Development with /shipwright-iterate

After the initial pipeline completes, ongoing changes use `/shipwright-iterate` -- a complexity-adaptive process that scales from quick fix to structured mini-SDLC, keeping all artifacts in sync.

### Trigger

- **Automatic:** A `UserPromptSubmit` hook detects change intent from user messages and suggests `/shipwright-iterate`
- **Manual:** User calls `/shipwright-iterate` directly with `--type feature|change|bug`

### Complexity-Adaptive Phases

`/shipwright-iterate` assesses each change's complexity and runs only the phases that change needs. This happens in two stages:

1. **Quick Estimate** -- A classifier script analyzes your prompt for scope keywords and risk signals, producing an initial estimate with confidence score. When no scope keyword matches, the default is history-calibrated: the median final complexity of your last finalized iterates (capped at medium) instead of a blanket "trivial", so the estimate adapts to each project's reality (`signals.prior_source` reports `keyword`, `history`, or `default`).
2. **Repo Scout** -- The agent scans the repository (affected files, FRs, split boundaries) to confirm or upgrade the estimate. After this, complexity is locked.

The result is one of four levels:

| Complexity | Criteria | What Runs |
|------------|----------|-----------|
| **Trivial** | 1 FR, 1-2 files, no risk flags | spec update → build → self-review → unit test (`--related`) → finalize |
| **Small** | 1-2 FRs, 3-5 files, or risk flags present | + confirmation question, design text (if UI), mini-plan (features), conditional full review |
| **Medium** | 2-4 FRs, 5-10 files, or cross-split | + scoping interview (2-3 Qs), iterate spec file, mini-plan with work breakdown, user approval gate, external LLM review (mini-plan), full code review, **external LLM code-review cascade** (default on, Branch A/B/C opt-out), full test suite, **E2E Verification (author + execute)** |
| **Large** | 4+ FRs, 10+ files, cross-split + risk flags | **Escape hatch** -- recommends switching to the full pipeline |

Users can override complexity (`--complexity medium`) and adjust phases before execution ("skip design", "make it small"). However, safety floors enforced by risk flags cannot be bypassed without explicit acknowledgment.

### Spec Impact Classification

Every FEATURE and CHANGE iterate must classify how it changes the requirement spec -- this is the "spec update" step the complexity table lists, and it is **enforced**, not advisory:

- **ADD** -- a new endpoint, page, or user-visible capability: a new FR row is appended to `spec.md`.
- **MODIFY** -- an existing FR's behavior changed: its row + acceptance criteria are updated.
- **REMOVE** -- a capability was deleted: the FR row moves into a `### Removed Requirements` section (never silently dropped).
- **NONE** -- a behavior-preserving internal refactor: recorded with a one-line justification. A NONE iterate (or one explicitly classified `simplify`) runs the **Simplify sub-mode** below, which guards the "behavior-preserving" claim mechanically.

Two layers enforce it. At finalization `record_event.py` refuses (exit 1) a feature/change iterate that names no FR and gives no `spec_impact=none` justification; and the F11 verifier fails the run if its commit touched no `spec.md` without a recorded `spec_impact=none`. The on-demand `/shipwright-compliance` detective audit (Group D, check D5) additionally surfaces any historical feature/change events that landed with no FR linkage. BUG iterates are exempt from the spec-impact gate -- a fix need not change the spec.

**FR-linkage gate.** A second, broader gate fires *before* the spec-impact gate: every `work_completed` event with `source=iterate` -- **including BUG iterates** -- must record either `--affected-frs` / `--new-frs` OR `--change-type ∈ {docs, tooling, compliance, infra}` paired with `--none-reason '<one-line>'`. Hard-rejects otherwise (exit 1, nothing written). The gate exists because the spec-impact gate exempts BUG iterates entirely, which would otherwise let internal fixes ship without any classification at all; it forces a categorical answer ("this fix is tied to FR-X, or it's classified as `tooling`, …"). It runs fail-closed at both write-paths -- the `record_event.py` CLI boundary and the worktree finalize write-path inside `finalize_iterate._record_event` (F5b) -- so unclassified iterate events are rejected at write rather than flagged post-merge.

### Risk Taxonomy

Eleven canonical risk flags trigger safety minimums regardless of complexity level:

| Risk Flag | Example Trigger Paths | Enforces |
|-----------|----------------------|----------|
| `touches_auth` | `src/middleware.ts`, `**/auth/**` | mandatory code review |
| `touches_rls` | `supabase/migrations/*rls*` | mandatory code review |
| `touches_middleware` | `src/middleware.ts`, `next.config.*` | mandatory code review |
| `touches_migrations` | `supabase/migrations/` | mandatory review + down.sql |
| `touches_billing` | `**/stripe/**`, `**/payment*/**` | mandatory code review |
| `touches_shared_infra` | `src/lib/`, `src/components/ui/` | full test suite |
| `cross_split` | changes span 2+ planning splits | full review + full test suite |
| `touches_public_api` | API route handlers, exported types | mandatory code review |
| `touches_build` | `package.json`, `*-lock.*`, `*.config.*`, `tsconfig.json` | performance test layer (Lighthouse + bundle gate, /shipwright-test Step 3.8) |
| `touches_io_boundary` | `.env*`, `*_config.json`, `*_state.json`; or `json.dump/load`, `yaml.dump/safe_load`, `parse_env` | round-trip Boundary Probe in build TDD |
| `cross_component` | merge/churn/event-log resolvers, `hooks.json` / `**/hooks/*.py`, phase validators, campaign orchestration (`autonomous_loop`) | non-dodgeable integration coverage + full test suite |

### Context Loading

Before assessing intent or complexity, iterate reads all project context upfront: `CLAUDE.md`, coding conventions, the complete decision log (ADRs), architecture overview, all spec files across all planning splits, file-to-FR mappings, last test results, and the 20 most recent git commits. This ensures the agent knows what was already built, what decisions were made, and what was recently changed -- preventing regressions and duplicate work.

### Planned Run Summary

Before execution begins, iterate prints a summary of what will run:

```
SHIPWRIGHT-ITERATE: Session Plan
  Run ID:      iterate-2026-04-05-course-search
  Intent:      FEATURE
  Complexity:  Small (1 FR, ~4 files, risk: touches_migrations)
  Phases:      spec → design text → build (TDD) → self-review → scoped test → finalize
  Skipping:    iterate spec (small), mini-plan (small), full review (no risk flags)
  Safety floor: DB migration → mandatory down.sql
```

You can adjust before proceeding -- "make it medium", "skip design", "add review".

### Interview & Approval

Iterate replaces manual Plan Mode by building scoping questions directly into the workflow:

- **Small changes:** One confirmation question -- "Do I understand correctly: [restated intent]. Shall I proceed with this?" If you correct, iterate adjusts scope and may re-assess complexity.
- **Medium changes:** 2-3 scoping questions for features (what, out-of-scope, UI behavior) or 1-2 for changes (what changes, boundaries). Answers feed directly into the iterate spec and mini-plan. After the mini-plan is written, iterate presents a summary and waits for your approval before building.
- **Trivial and bugs:** No interview. Trivial changes proceed directly; bugs go through a structured debugging protocol (reproduce → localize → root cause → failing test).

This means you never need to manually trigger `/plan` -- iterate handles the right amount of upfront scoping automatically based on complexity.

### 3 Intent Paths

The three intent types still define the workflow shape, but each is now complexity-gated:

| Intent | Flow (brackets = complexity-dependent) | Key Difference |
|--------|---------------------------------------|----------------|
| **Feature** | [interview] → [spec] → [plan] → [approval] → [review] → [design] → build → test → finalize | Appends new FR to spec |
| **Change** | [interview] → [spec] → [plan] → [approval] → [review] → [design] → build → test → finalize | Updates existing FR in spec |
| **Bug** | [spec] → reproduce → [plan] → fix → test → finalize | Reproduces via failing test first, no interview |

Each path runs tests automatically, creates a conventional commit with FR references and a `Run-ID` trailer, records a `work_completed` event in the event log, and triggers incremental compliance report updates.

#### Simplify -- behavior-preserving sub-mode (OS1)

A fourth shape rides on **Change**: when you ask iterate to *simplify*, *clean up*, *declutter*, *streamline*, or *tidy* code -- or whenever a Change/Feature is classified Spec Impact **NONE** -- it runs a behavior-preserving wrap instead of a normal edit:

1. **Behavior-Snapshot** -- before touching anything, `behavior_snapshot.py snapshot` runs the test suite and stores the green state (collected test node-ids + counts + exit code + source LOC). It *refuses a red baseline* -- there is no behavior to preserve if the suite is not already green.
2. **Simplify** -- the edit follows five principles (Preserve Behavior, Follow Conventions, Clarity over Cleverness, Maintain Balance, Scope to What Changed) plus a Chesterton-Fence pre-flight: before removing any line, guard, or branch you must state *why it exists*. **Fewer lines is not the goal** -- clarity is.
3. **Behavior-Verify** -- `behavior_snapshot.py verify` re-runs the suite and **rejects** the change if any test flips green→red, a previously-collected test disappears (removed coverage), or source shrinks *while* coverage drops. A clean green→green with a large LOC drop is the win.

The gate is only as strong as the suite's coverage, so removed coverage is a hard reject and the five-principle reasoning is mandatory, not optional. Spec Impact is **NONE** by definition. The full protocol lives in the iterate skill's `references/F-simplify.md` (adapted, with attribution, from [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills), MIT).

The simplify gate and the **intelligent bloat/reducibility gate** are unified around one shared tool and one shared vocabulary: a simplify enumerates its changes with the same closed reducibility catalog (`D·A·X·C·S·M·P·T` + guardrails `G1–G6`, in `shared/reducibility-catalog.md`) the code reviewer bounces diffs back with, and the same `shared/scripts/tools/behavior_snapshot.py` snapshot/verify is the **mechanical proof** of the catalog's "keeps tests green" guardrail on every surface that can run tests (the self-contained CI reviewer, which cannot run tests, keeps its conservative LOC heuristic). A simplify is, in effect, the *apply* path for the reductions the reviewer proposes.

### Override Classes

Not all phases can be skipped. Iterate defines three categories:

| Category | Includes | User Can Skip? |
|----------|----------|----------------|
| **Mandatory** | Self-review, unit test, commit, ADR, compliance, test results JSON, iterate entry (file-per-iterate), **Confidence Calibration at medium+**, **E2E Verification at medium+** (F0.5, author + execute), **Test Completeness Ledger at small+** (F5 produce → F11 gate) | Never |
| **Safety-enforced** | Full review (when risk flags), full test suite (when shared infra), down.sql (when migrations), **E2E Verification at small with `touches_io_boundary` or UI** | Only with explicit risk acknowledgment |
| **Advisory** | Design check, mini-plan, design fidelity, external LLM review | Freely skippable |

### Escape Hatch and Escalation

**Large scope:** When the Repo Scout determines complexity is large, iterate prints a recommendation with two options: (1) hand off to `/shipwright-project --extend` via a structured handoff file, or (2) continue with iterate under mandatory full review and full test suite.

**Mid-flight escalation:** If scope grows during implementation (more files than estimated, cascading test failures), iterate can upgrade complexity dynamically. For example, small → medium triggers retroactive creation of an iterate spec and mini-plan, plus external LLM review before further code changes.

### Campaign Mode (Autonomous Multi-Iterate)

A **campaign** batches several related sub-iterates under one goal and runs them autonomously, end to end, without manual gates between them. You decompose the goal into sub-iterates once (each trivial-to-medium), then `/shipwright-iterate --campaign <slug> --autonomous` works the list on its own.

Campaigns run **interleaved-serial**, and this is the *default* -- not a choice the agent re-decides each run. Each sub-iterate is its own PR to `main`: it branches off a freshly-fetched `origin/main`, builds, and opens a PR; the orchestrator waits for the Required Checks to go green, merges, and only *then* builds the next sub-iterate -- which again branches off a fresh `main` that now contains the previous merge. There is **only ever one open sub-iterate PR at a time**. The merge is verified, never armed-and-forgotten: if a PR's CI fails, conflicts, or times out, the campaign strict-stops (already-merged sub-iterates stay durable) rather than charging ahead.

It is serial rather than "build all the PRs first, then merge them at the end" in order to avoid **merge theater**. Every sub-iterate regenerates the same *derived* artifacts -- the event log, triage, the compliance reports, the dashboard -- and sibling sub-iterates often edit the same shared source files. If they are all built before any merge, none of them sees the others, so every merge has to 3-way-resolve and regenerate those snapshots against an advancing `main`. Interleaved-serial sidesteps that entirely: because the next sub-iterate starts from a `main` that already contains the prior one, shared-file and snapshot edits compose naturally -- there is no end-stage drain and no regenerate-at-merge step.

This is encoded as `branch_strategy: serial` (the `campaign_init` default; base-freshness is enforced in code, not just documented). The full agent-facing protocol -- campaign setup, the autonomous loop, the sub-iterate-runner contract, and the release prompt -- lives in the iterate skill's `references/campaign-mode.md`.

### Finalization

Every iterate run -- regardless of complexity -- ends with the same mandatory finalization sequence. All artifact producers run **before** the commit so a single atomic F6 stages everything and no `git commit --amend` is ever needed:

0. **Fresh verification (F0)** -- run the full unit/type/integration test suite; non-zero exit means STOP, do not enter F0.5 with failing tests.
0.5. **End-to-End Verification (F0.5; medium+)** -- run the surface runner (`web` / `cli` / `api`, or `none` with justification) against the user-erlebbare Surface via `shared/scripts/surface_verification.py`. Produces the `surface_verification` block in `shipwright_test_results.json.iterate_latest`. Non-zero exit blocks the rest of finalization; the post-commit audit `check_surface_verification` in `iterate_checks.py` is the second layer.
0.6. **Test Completeness Ledger (F5 produce → F11 gate; small+)** -- enumerate every behavior the diff introduces and classify each as `tested` (evidence) or `untestable` (closed-vocabulary `reason_code`); the "could-test-but-didn't" disposition is forbidden. The ledger lands in `shipwright_test_results.json.iterate_latest.test_completeness`; the F11 audit `check_test_completeness_ledger` fails closed on any testable-but-untested behavior. This is the gate that makes a pre-merge "did you test everything testable?" question unnecessary. Trivial iterates emit an auto `n/a` line.
1. **Drift check** -- verify specs match implementation
2. **Architecture update** -- update `architecture.md` if structural changes were made
3. **ADR (decision-drop)** -- record the decision via `write_decision_drop.py`. Each field (`--context`, `--decision`, `--consequences`, `--rationale`, `--rejected`) is hard-rejected at write time if it exceeds 500 characters (`decision_log.md` is always-loaded Layer-1 context and every verbose ADR pays for itself in tokens on every future run). Move long-form prose into the flat ADR spec folder `.shipwright/planning/adr/<NNN>-<slug>.md` and link it with `--spec-ref`; the aggregator emits a `**Details:** [...]` bullet under the ADR row and rebuilds `.shipwright/planning/adr/INDEX.md` on every release pass. `--spec-ref` is also required whenever a decision needs a diagram, >3 alternatives, or non-trivial follow-up acceptance criteria.
4. **Reflection** -- capture learnings (patterns, gotchas, corrections) in `conventions.md` and/or Claude Code Memory
5. **CHANGELOG drop** -- write a drop file per bullet under `CHANGELOG-unreleased.d/<category>/<run_id>_NNN.md` via `write_changelog_drop.py`. Aggregated into `CHANGELOG.md` at release time by `/shipwright-changelog`. Replaces the legacy `[Unreleased]`-append pattern; eliminates the merge hotspot that blocked parallel iterates.
6. **Test results JSON** -- write structured test results to `shipwright_test_results.json`
7. **Update compliance** -- regenerate traceability and reports (pre-commit)
8. **Update build dashboard** -- refresh `build_dashboard.md` (pre-commit)
9. **Record iterate entry** -- `append_iterate_entry.py` writes `.shipwright/agent_docs/iterates/<run_id>.json` (last 50 entries retained; commit hash intentionally omitted, look it up in `shipwright_events.jsonl` by `run_id`). On first contact with a legacy `iterate_history` array, the tool migrates all valid rows under the same transaction lock; invalid / duplicate rows land in `.shipwright/agent_docs/iterates/_quarantine/` and the count surfaces in the handoff + verifier output.
10. **Conventional commit** -- single atomic commit with explicit `git add` list (never `-A`), `Run-ID` trailer and FR references
11. **Record event** -- the `work_completed` event is appended to **this worktree's** `shipwright_events.jsonl` at finalize (F5b, *before* the commit) and **staged in the same atomic commit** above (step 10), so it ships in the iterate PR and merges to `main` like every other artifact: a per-tree, PR-committed model. The main tree is never written, so there is no orphaned dirty line and **no separate `chore(events)` sealing commit**. The F11 verifier fails closed if a tracked log's event isn't in the commit. *(Legacy/out-of-band only: when an event is recorded into a tree it does NOT commit (replay, non-worktree phases), the **F7b** `commit_event_followup.py` seal still applies; it is a no-op for the normal worktree flow.)*
12. **Merge, push & verify** -- push branch, open PR via `gh pr create`, then **arm GitHub-native auto-merge** for the `iterate/*` branch via `gh pr merge --auto --squash --delete-branch` so the PR squash-merges itself once the Required Checks pass. The arm is gated two ways: branch-scope (`iterate/*` only; a manual human PR never self-arms, opt in per-PR yourself) and **fail-soft** (if the repo's "Allow auto-merge" / branch-protection setting is off, `gh pr merge --auto` errors → WARN and leave the PR open for a manual merge, never breaking finalize for the run). Then verify event was recorded, regenerate session handoff via the **runtime/snapshot split**: Stop hooks write live state to `.shipwright/agent_docs/runtime/` (gitignored); iterate-finalize is the **sole producer** of the tracked `session_handoff.md`, `build_dashboard.md`, and `triage_inbox.md`. The repair pass refuses to run when the session→worktree pointer is invalid; stale-pointer sessions no longer poison main.

> **Branch-integration rule.** Use `git merge` (not `git rebase` / `gh pr merge --rebase`) for branches carrying `Run-ID:` commits. Rebase rewrites the Run-ID SHAs that the snapshot-provenance audit (Group E) follows via `git log --grep=Run-ID:` and can silently strip merge-bearing trailers. Recover an accidental rebase via `git reflog`.

### Degraded Mode

When metadata is incomplete, iterate degrades gracefully rather than failing:

- **No sync config:** defaults to medium complexity, runs full test suite
- **No visual-guidelines.md:** skips design check, notes in ADR
- **External review unavailable (medium+ only):** Branch B prompts the user; on opt-out, falls back to the mandatory self-review and logs the decision in `external_review_state.json`. Trivial/small iterate runs skip external review by default.
- **Code reviewer unavailable:** self-review only, flagged as "review-limited"
- **Browser verify fails:** falls back to test-only verification

All degraded conditions are recorded in `shipwright_test_results.json` and noted in the final summary.

### Drift Check

Shipwright runs a CLAUDE.md drift check automatically at every session start (via the `check_drift.py` hook). It compares each `CLAUDE.md` against the actual filesystem structure and `package.json` scripts, and surfaces obsolete directory listings or dead `npm run` references as an informational warning -- it never blocks. There is no manual command; the check is passive by design.

### vs. /shipwright-run

| | /shipwright-run | /shipwright-iterate |
|---|---|---|
| **When** | New project or major extension | Daily changes, bug fixes, features of any size |
| **Pipeline** | Full 7-phase SDLC | Complexity-adaptive (trivial → medium, or escape to full pipeline) |
| **Complexity** | Always full | Auto-assessed: trivial, small, medium, large |
| **Duration** | Hours | Minutes (trivial/small) to ~1 hour (medium) |
| **Risk detection** | Implicit in phase structure | Explicit: 11 canonical risk flags with safety floors |
| **Artifacts** | All created from scratch | Same event log, incrementally |

---

## 8.5 Parallel Development with Worktrees

**Worktree isolation is automatic and unconditional.** Every
`/shipwright-iterate` run executes in its own git worktree + branch + PR.
You do not set this up by hand, and there is no "parallel mode" to opt
into. Git worktrees give each run a second checkout of the same repo, on
its own branch, in a sibling directory: shared git history, isolated files.

The skill's B1a step (`setup_iterate_worktree.py`) creates the worktree;
the F0/F11 leak-guard (`check_iterate_isolation.py`) fails the run closed
if isolation is ever violated. This chapter is the model plus the few
things you still do manually.

### Mental model

- A worktree is a second working directory bound to the same `.git`.
  Commits, branches, tags, and remotes are shared; the checked-out files
  are isolated.
- Every iterate run lives in `.worktrees/<slug>/` on branch
  `iterate/<slug>` (the `.worktrees/` folder is `.gitignore`'d). B1a cuts
  the branch from a freshly-fetched `origin/<default>`, never local
  `main`, never another `iterate/*`.
- The session process stays in the main repo; only the skill's working
  paths point into the worktree, so webui session discovery is unaffected.
- One iterate = one worktree = one branch = one PR. The run finalizes by
  pushing the branch and opening a PR (F11); it never merges the default
  branch itself.

### Running iterates — including in parallel

There is nothing to set up. Run `/shipwright-iterate` and B1a creates the
worktree. To run a SECOND iterate in parallel, just open another Claude
Code session against the same repo and run `/shipwright-iterate` with the
new request; it gets its own worktree automatically. The two runs cannot
share a working tree, race a `git checkout`, or cross-write each other's
files.

The former "Parallel" menu option and the canonical/secondary
session-role machinery are gone; they were a workaround for isolation
that used to be conditional. Isolation is now structural.

A worktree carries tracked files only: neither `.env*` nor
`node_modules`/`.venv` transfer. Re-hydrate after creation: copy `.env*`
from the main repo and run the project's install command (`npm install`,
`uv sync`). This per-run overhead is accepted by design.

### Resuming an interrupted iterate

If a previous run's worktree still exists, B1 detects it and offers
**Resume** / **Abandon** / **Complete**. Resume `cd`s back into that
worktree and continues; Abandon removes the worktree + branch.

### Cleanup

Worktree removal does **not** delete the branch. After a PR merges, run
both, from the main repo, not from inside the worktree:

```bash
git worktree remove .worktrees/<slug>
git branch -D iterate/<slug>
```

For an unmerged worktree you want to discard, add `--force` to the remove.
`git worktree prune` clears stale entries left behind by a deleted
worktree directory.

### Pitfalls

1. **Common artifacts are conflict-free by design.** Changelog entries
   (`CHANGELOG-unreleased.d/` drop files), `iterate_history`
   (file-per-iterate under `.shipwright/agent_docs/iterates/`), and ADRs
   (decision-drops under `.shipwright/agent_docs/decision-drops/`) are all
   per-run files; two parallel iterates never collide on them. A PR only
   conflicts if it touches the same SOURCE files; rebase the second PR
   onto the updated `origin/<default>` to resolve.
2. **`shipwright_run_config.json` is not multi-writer safe.** Several
   phase configs write to this file. Avoid concurrent *pipeline* writes on
   the same target project; iterate runs no longer touch
   `iterate_history` in it (file-per-iterate).
3. **Editor / VSCode.** Open the worktree as a separate workspace window,
   not as a subfolder of the main repo workspace; nested-worktree
   file-watching and project-wide search behave poorly.
4. **Stale iterate branches.** B1 calls
   `shared/scripts/tools/list_iterate_branches.py` to classify `iterate/*`
   branches as `active`, `stale`, or `locked`. The helper is read-only:
   it reports, the operator deletes. Limitations: (a) squash-merged
   branches stay `active` until manual `git branch -D iterate/<slug>`;
   (b) if both `main` AND `master` exist locally, pass `--main <name>`.
5. **Marketplace plugin cache is shared across worktrees.** Claude Code
   runs `~/.claude/plugins/cache/shipwright/`, a single directory shared
   by every worktree. Plugin-side edits (`plugins/*`, `shared/scripts/*`,
   any `SKILL.md`) do not reach runtime until
   `bash scripts/update-marketplace.sh` runs from main. See the repo-root
   `CLAUDE.md` "When editing plugin-side files" section.

### When to use which approach

| Situation | Approach |
|-----------|----------|
| Unrelated fix that blocks nothing | Second `/shipwright-iterate` session, its own worktree, automatically |
| Related follow-up on the same topic | Stay in the current iterate; add a sub-task |
| Conflicting change on the same files | Serialize; parallelize only disjoint file scopes |
| Quick one-line doc fix | Still goes through `/shipwright-iterate`; the worktree overhead is automatic now |

See also the skill-level enforcement in
`plugins/shipwright-iterate/skills/iterate/SKILL.md` section **B1a**.

---

## 9. Quality and Safety

Shipwright enforces quality through **mechanical enforcement** -- hooks that block or warn deterministically, not advisory prose that agents may ignore. This follows the "linters over instructions" principle.

### The Hooks System

Hooks are Python and shell scripts that fire on specific Claude Code events. They split into three groups: **safety guards** (block dangerous actions), **state hooks** (track session/phase lifecycle), and **drift detectors** (warn on inconsistency).

**Safety guards (PreToolUse / PostToolUse):**

| Hook | Trigger | What It Prevents |
|------|---------|-----------------|
| `validate_command.sh` | PreToolUse Bash | Blocks `git push --force` to main, `rm -rf /`, `DROP DATABASE` |
| `check_secrets.sh` | PostToolUse Write/Edit | Detects API keys (`sk-...`, `AKIA...`, `ghp_...`), PEM keys, passwords, connection strings |
| `check_destructive_migration.sh` | PostToolUse Write/Edit on .sql | Soft-blocks (exit 2) on destructive SQL patterns (`DROP TABLE`, `DROP COLUMN`, `ALTER TYPE`, `TRUNCATE`, `DELETE FROM` without `WHERE`) in migration/supabase `.sql` files; requires explicit confirmation |
| `check_file_size.py` | PostToolUse Write/Edit | Non-blocking nudge when an edit pushes a source file past the line guideline (default 300); silent on edits to files already over the limit. Also records `.shipwright/locks/bloat_pending.<sid>.json` markers so the Stop-Gate fires in the same session that triggered the over-limit write. |

**Bloat anti-ratchet (pre-commit + Stop + CI):**

| Layer | Trigger | What It Prevents |
|-------|---------|-----------------|
| `scripts/hooks/pre-commit` | local `git commit` | **Hard-blocks** commits that raise the measured LOC of any allowlisted entry past its frozen `current` in `shipwright_bloat_baseline.json`. New crossings (a previously-clean file gaining its first allowlist entry) are nudged, not blocked; Group H surfaces them post-merge. Installed once per clone via `bash scripts/install-hooks.sh` (POSIX/Git-Bash) or `.\scripts\install-hooks.ps1` (PowerShell). |
| `bloat_gate_on_stop.py` | Stop | Reads the session bloat marker and refuses to finalize a turn while a ratchet is pending: the gate that catches in-session ratchets the same Claude that wrote them. |
| `.github/workflows/bloat-check.yml` | CI on PRs to main | Same anti-ratchet rule on the merge gate, defense-in-depth against operators who skip the pre-commit install. |

Exception path: write an ADR using `.shipwright/planning/adr/_template-bloat-exception.md` (mandatory Ousterhout / YAGNI / Chesterton-Fence / Re-Review-Date / Incident-Reference sections), bump the entry's `current` in the allowlist with `state="exception"` and `adr="ADR-NNN"`.

**Reducibility reviewer (the qualitative complement).** The anti-ratchet hook above is purely *quantitative*: it counts lines, which cannot tell long-but-coherent code from genuinely reducible code. The reducibility reviewer closes that gap: a line-count crossing is treated as a **router**, not a verdict (`LOC-as-Router`), escalating the file to a reviewer that blocks **only** on a concrete, falsifiable reduction from a closed catalog (`D` duplication · `A` needless-abstraction · `X` dead-code · `C` control-flow · `S` data-shape · `M` comment-restating-code · `P` dependency-footprint · `T` test-repetition), each citing what-to-remove + est-LOC-saved + keeps-tests-green. No concrete finding → PASS, so coherent long code is never churned (guardrails G1–G6). It runs at two enforcement surfaces (the local diff reviewer in `plugins/shipwright-build/agents/code-reviewer.md`, bounce-back cascade, and the CI Tier-3 reviewer in `shared/prompts/pr_reviewer/system`), plus an advisory plan-stage pre-emption in `shared/prompts/iterate_reviewer/system`. The rubric and per-language idiom-map live in `shared/reducibility-catalog.md` and `shared/profiles/reducibility-idioms.json`.

**Multi-session lifecycle (orchestrator-driven phases):**

| Hook | Trigger | What It Does |
|------|---------|-----------------|
| `phase_session_start.py` | SessionStart | Multi-session ownership claim for the current phase |
| `phase_user_prompt_validate.py` | UserPromptSubmit | Validates the prompt belongs to the active phase |
| `phase_session_stop.py` | Stop | Plans the next phase via `complete-phase-task` and prints its launch card |
| `capture_session_id.py` | SessionStart | Records the Claude session ID for cross-session correlation |

**Drift, audit & handoff:**

| Hook | Trigger | What It Does |
|------|---------|-----------------|
| `check_drift.py` | SessionStart | CLAUDE.md vs filesystem drift (Structure block, package.json scripts) |
| `check_artifact_drift.py` | SessionStart | Cross-artifact drift detection (configs, planning, .shipwright/agent_docs) |
| `track_tool_calls.py` | PostToolUse | Counts tool calls for context-pressure detection |
| `audit_phase_quality_on_stop.py` | Stop | Runs the 36-check Phase-Quality audit (see Section 9 below) |
| `generate_handoff_on_stop.py` | Stop | Writes the **gitignored runtime mirror** `.shipwright/agent_docs/runtime/session_handoff.md`; iterate-finalize is the sole producer of the tracked `session_handoff.md` |
| `suggest_iterate.py` | UserPromptSubmit | Multilingual phase router; auto-suggests `/shipwright-iterate` for post-test code changes |
| `write_terminal_marker.py` | SessionStart | Writes a terminal marker the WebUI Command Center watches |

Hooks use **exit code 2 (soft-block)**: you can say "Continue anyway," but the override is logged to `.shipwright/agent_docs/compliance_overrides.log` and flagged at the next checkpoint.

### TDD Workflow

Shipwright follows a strict test-first approach:

1. **Red** -- Write a failing test based on the spec's acceptance criteria.
2. **Green** -- Write the minimum code to make the test pass.
3. **Refactor** -- Clean up while keeping tests green.

Tests must pass before every commit. The constitution rule "fix the code, not the test" means assertions are never weakened to make failing tests pass.

### Code Review

Every section goes through up to three review layers:

1. **Self-review checklist** -- The building agent checks spec compliance, error handling, security, test quality, and naming before committing.
2. **Subagent code review** -- A dedicated code-reviewer subagent examines the diff against the spec and flags issues. Triggers on diffs > 100 lines, security-sensitive files, or medium+ complexity iterates.
3. **External LLM code review (cascade)** -- Optional second-opinion gate that sends the same diff to Gemini + OpenAI in parallel against the section/iterate spec. Build: opt-in via `shipwright_build_config.json` -> `external_code_review.enabled: true`, default off. Iterate: default-on for medium+ runs that already triggered layer 2, with Branch A/B/C interactive opt-out (same flow as the mini-plan review). See `External LLM Review` in Chapter 6 for provider setup and the diff-exposure caveat.

### Migration Safety

Database migrations receive special protection:

- Every `up.sql` migration automatically gets a corresponding `down.sql` in `supabase/migrations/_rollback/`.
- Destructive patterns (`DROP TABLE`, `DROP COLUMN`, `ALTER TYPE`) trigger a hook warning and require user confirmation.
- Production migrations always run `--dry-run` first, with explicit user approval before applying.

### Secret Scanning

The secret scanner runs on every file write or edit and detects:

- AWS Access Keys (`AKIA...`)
- API keys (`sk-...`, `ghp_...`, `gho_...`, `glpat-...`)
- Slack tokens (`xoxb-...`, `xoxp-...`)
- PEM private keys
- Hardcoded passwords and connection strings with embedded credentials

It automatically skips `.env.example`, test fixtures, lock files, and vendor directories.

**Suppression syntax (`nosemgrep` adjacency rule).** A `# nosemgrep:<rule-id>` directive MUST sit on the matched line or immediately preceding it; an intervening justification comment breaks attribution and Semgrep flags the call anyway. For multi-line calls flagged on a kwarg, write the directive as an inline trailing comment on that kwarg line. Full reference: `plugins/shipwright-security/skills/security/references/suppression-syntax.md`.

### Plugin-cache drift check

After `git push` to the dev repo, plugin-side fixes (under `plugins/*`, `shared/scripts/`, any `SKILL.md`) do **not** auto-sync to the Claude Code runtime cache at `~/.claude/plugins/cache/shipwright/`. Without `bash scripts/update-marketplace.sh`, fixes land in the repo but never reach runtime. `scripts/check_plugin_cache_sync.py` compares the repo head against the lexically-latest cached plugin version via per-file SHA-256 and reports drift:

```bash
uv run scripts/check_plugin_cache_sync.py             # fail-soft WARN by default
uv run scripts/check_plugin_cache_sync.py --strict    # exit 1 on drift (CI use)
uv run scripts/check_plugin_cache_sync.py --json      # structured output for tooling
```

The check is no-op when `~/.claude/plugins/cache/shipwright/` does not exist (typical CI runners), so it slots cleanly into a sanity-check pipeline without false negatives. Scope: shipwright dev repo only; end-users consuming the plugins on their own projects run the installed cache versions and never need this step.

### Pipeline Verifier and Phase Completion Canon

Shipwright ships a **pipeline-wide finalization verifier** that runs after every phase to catch cross-artifact drift: the kind of failure mode where the code compiles, the tests pass, but `decision_log.md` is out of date, the `CHANGELOG` is missing a bullet, or the build dashboard still shows last week's state. The verifier lives at `shared/scripts/tools/verify_phase.py` and is dispatched automatically through `plugins/shipwright-run/scripts/lib/phase_validators.py` between phases; you can also invoke it manually.

**What it checks, the Minimum Phase Completion Canon (C1–C5):**

| Step | Invariant | Severity |
|------|-----------|----------|
| **C1** | `phase_completed` event exists in `shipwright_events.jsonl` for the phase | ERROR |
| **C2** | `.shipwright/agent_docs/build_dashboard.md` mentions the phase | WARNING |
| **C3** | `.shipwright/agent_docs/session_handoff.md` is fresh (canon-marker frontmatter) | WARNING |
| **C4** | `.shipwright/agent_docs/decision_log.md` has an ADR referencing the phase | ERROR (decision-taking phases only) |
| **C5** | `CHANGELOG.md [Unreleased]` has a bullet under the right category | ERROR (user-facing phases only) |

Plus per-phase preventive checks: build verifies every section's test files exist on disk (**B3**) and every recorded section commit SHA is reachable via git (**B6**); the latter catches history rewrites before they contaminate compliance. Plan verifies section manifest consistency, FR orphans, and section-id validity. Design verifies every screen in `design-manifest.md` exists and every FR is linked to at least one screen. Changelog runs two Sonder-Checks: the latest `## [vX.Y.Z]` in `CHANGELOG.md` must match an existing git tag, and the top version must match the latest `git tag --list v*`.

C4 is skipped for design (transformation, not decision), test (events, not decisions), changelog (process), deploy (execution) and compliance (derived). C5 is skipped for plan (internal), test (results live in `shipwright_test_results.json`), changelog (owns its own prepend) and compliance. Severity is fixed per-check; you cannot downgrade an ERROR without touching the code.

**Running it manually.** Against a Shipwright-managed project:

```bash
# All phases (omits iterate unless --run-id is given)
uv run shared/scripts/tools/verify_phase.py --project-root . --phase all

# Single phase
uv run shared/scripts/tools/verify_phase.py --project-root . --phase build
uv run shared/scripts/tools/verify_phase.py --project-root . --phase plan --strict

# Iterate finalization (requires --run-id + --commit)
uv run shared/scripts/tools/verify_iterate_finalization.py \
  --run-id iterate-2026-04-14-xxx --commit $(git rev-parse HEAD)
```

`--strict` treats warnings as errors. The exit code is 0 for green (or warnings-only without `--strict`) and 1 for any error.

Full canon definition, skip criteria, and per-plugin coverage matrix live in [docs/hooks-and-pipeline.md § Minimum Phase Completion Canon](hooks-and-pipeline.md#minimum-phase-completion-canon-c1c5).

### Phase-Quality Audit (Consolidated Stop-Hook)

Beyond the orchestrator-driven Canon, Shipwright runs a **consolidated Stop-Hook audit** at the end of every plugin session, orchestrated or standalone. It's observability, not a gate by default: the hook writes findings to `.shipwright/compliance/skill-compliance/` and regenerates three summary files but never blocks the session.

The audit covers six categories:

| Category | Count | Example checks |
|---|---|---|
| **Canon** | 5 (C1-C5) | phase_completed event, dashboard freshness, session handoff |
| **Workflow** | 13 (W1-W7, Sec1-Sec2, Cmp1-Cmp2, D1-D2) | TDD order, F11 external review, coverage threshold, smoke-test status, git tag existence |
| **Infrastructure** | 4 (I1-I4) | RTM/test-evidence/change-history/SBOM freshness vs phase events |
| **Traceability** | 2 (T1-T2) | every spec FR mapped in RTM, no orphan RTM rows |
| **Quality** | 2 (Q1-Q2) | ADR substance, planned sections ⊆ build completed |
| **Spec** | 10 (S1-S10) | spec.md + FR headings, iterate-spec for medium+, CLAUDE.md + README presence + freshness, FR coherence |

**Tier classification:** Of the 36 checks, 24 are Tier-1 (candidate for enforcement after burn-in) and 12 are Tier-2 (heuristic, never enforcement). Tier-2 ids are `W1`, `I4`, `T2`, `Q1`, `S3`, `S4`, `S5`, `S7`, `S9`, `S10`, `Cmp1`, `D2`; they always land as WARN/SKIP and carry `"tier": 2` so the dashboard can group them as low-signal.

**Artifacts** (deterministically regenerated, hard-capped). All four live under
the gitignored `skill-compliance` dir; the 3 `.md` roll-ups are transient derived
caches (never tracked → idle `main` stays clean):
- `.shipwright/compliance/skill-compliance/<phase>-<run_id>-<session>.json`: per-run finding (atomic, GC after 90 days)
- `.shipwright/compliance/skill-compliance/_report.md`: last 10 runs, markdown table
- `.shipwright/compliance/skill-compliance/_findings.md`: last 5 runs, source for SessionStart-Injection
- `.shipwright/compliance/skill-compliance/_dashboard.md`: phase × category matrix

**Enforcement rollout (staggered, default OFF in code):**

| Flag | Default | Effect |
|---|---|---|
| `SHIPWRIGHT_PHASE_QUALITY` | `1` (on) | `0` → hook disabled entirely (rollback lever) |
| `SHIPWRIGHT_PHASE_QUALITY_MODE` | `audit_inject` (on) | `audit_only` → disables SessionStart injection, findings only in dashboard files. Default injects ≤5 Tier-1 FAILs as `additionalContext` at next session start |
| `SHIPWRIGHT_ENFORCE_CRITICAL_GATES` | `0` | `1` → orchestrator blocks phase-transition on `W5`/`W6`/`W7` FAIL |
| `SHIPWRIGHT_SKIP_QUALITY_CHECK` | — | comma-separated check ids to mark as SKIP (e.g. `C4,S9`) |
| `SHIPWRIGHT_AUDIT_OVERRIDE_REASON` | — | required when using `SHIPWRIGHT_SKIP_QUALITY_CHECK` |

The audit hook is always greenfield-safe (silent no-op when neither `shipwright_*_config.json` nor `.shipwright/agent_docs/` is present) and non-blocking (exit 0 even on internal errors). Hook wiring, finding schema and the detailed check catalog live in [docs/hooks-and-pipeline.md § audit_phase_quality_on_stop.py](hooks-and-pipeline.md#shared-hook-audit_phase_quality_on_stoppy).

---

## 10. Generated Documentation

Shipwright generates and maintains documentation throughout the pipeline. You do not write these files manually -- they are created and updated as a side effect of each phase.

### .shipwright/agent_docs/ Directory

The `.shipwright/agent_docs/` directory is the project's knowledge base for AI agents. Its contents:

| File | Purpose | Updated By |
|------|---------|-----------|
| `architecture.md` | System overview, stack table, data flow, security model. Carries a `<!-- shipwright:architecture v=N last-sync=<sha> -->` marker that the Group F5 detective audit uses to detect diagram drift against architecture-impacting decision-drops | `/shipwright-project` |
| `conventions.md` | Code patterns, naming, git workflow, component examples | `/shipwright-project` |
| `decision_log.md` | Architecture Decision Records (ADR format). Compact one-row entries with mandatory 500-char field caps; long-form prose lives in the flat `.shipwright/planning/adr/<NNN>-<slug>.md` spec folder | All phases |
| `session_handoff.md` | Recovery document: last events, git state, resume instructions. **Single producer** = `iterate_finalize` | Iterate finalization; runtime mirror at `.shipwright/agent_docs/runtime/session_handoff.md` (gitignored) |
| `build_dashboard.md` | Project activity: recent changes, test status, pipeline, build history. **Single producer** = `iterate_finalize` | Iterate finalization; runtime mirror at `runtime/build_dashboard.md` (gitignored) |
| `triage_inbox.md` | Aggregated Triage Inbox rendered from `.shipwright/triage.jsonl` (see § 4.11) | Iterate finalization via atomic `os.replace` from the runtime mirror; Stop hooks write only to `runtime/triage_inbox.md` |
| `iterates/<run_id>.json` | Per-iterate record (one file per iterate; legacy `iterate_history` array is migration-only) | Iterate finalization (F5c, 50-entry retention) |
| `decision-drops/<run_id>.json` | Per-iterate ADR draft, aggregated at `/shipwright-changelog` release into sequentially-numbered `decision_log.md` entries (gitignored, main-repo path) | Iterate F3 |
| `compliance_overrides.log` | Audit log of hook overrides | Hooks (when user says "Continue anyway") |

**Runtime/tracked split.** Stop hooks write live mid-session state to `.shipwright/agent_docs/runtime/` (gitignored via re-exclude in the allowlist block); iterate-finalize is the single producer of the tracked variants above. The split closes the recurring "main is dirty after every session" regression class while preserving mid-session inspection: `cat .shipwright/agent_docs/runtime/triage_inbox.md` for fresh state; the tracked copy reflects the last iterate's snapshot.

### CLAUDE.md

The project master document, generated during `/shipwright-project`. It stays lean (approximately 200 lines) and follows a progressive disclosure pattern:

- **WHAT** -- Stack and purpose (2-3 lines).
- **HOW** -- Build, test, lint, deploy commands.
- **Structure** -- Folder layout.
- **Key Files** -- Important files with one-line descriptions.
- **Gotchas** -- Project-specific pitfalls.
- **Context** -- References to `@.shipwright/agent_docs/` files, loaded on demand.

### Decision Log (ADR Format)

Each decision record follows the ADR template: Status, Context, Decision, Consequences (including rejected alternatives). Profile-level decisions (stack, auth pattern, folder structure) are implicit in the stack profile. Only project-specific decisions go in the log.

**Per-field length budget (hard-enforced).** Every new ADR field (context / decision / consequences / rationale / rejected) must fit in **500 characters**. `decision_log.md` is always-loaded Layer-1 context; verbose entries inflate every future iterate's prompt. The writers (`write_decision_log.py`, `write_decision_drop.py`) exit non-zero on overflow with a message pointing at the spec folder. Existing ADRs are not rewritten; the gate is forward-only.

**ADR spec folder:** `.shipwright/planning/adr/<NNN>-<slug>.md`, flat, one file per ADR. ADR-number prefix gives collision protection. Drops opt in via `--spec-ref <path>`; aggregation renders a `**Details:** [filename](../planning/adr/...)` link and rebuilds `.shipwright/planning/adr/INDEX.md` after every release pass. Schema lives at [shared/schemas/decision_drop.schema.json](../shared/schemas/decision_drop.schema.json).

### Event Log

`shipwright_events.jsonl` is an append-only JSONL file in the project root. Every build section, iterate change, test run, and phase transition is recorded as a JSON event. This is the single source of truth for all compliance reports and the activity dashboard. Events are never edited -- corrections use `event_amended` entries that reference the original event's ID.

### Project Activity Dashboard

`.shipwright/agent_docs/build_dashboard.md` shows the project's current state, derived from the event log. The most recent changes appear at the top (newest first), followed by test status, pipeline progress, and build history grouped by split. This is the first file an agent reads to understand what has happened and what to do next.

### Compliance Reports

The `/shipwright-compliance` skill generates audit-ready documentation from the event log:

| Report | Contents |
|--------|----------|
| **Compliance Dashboard** | Quality indicators from events, project velocity, links to all artifacts |
| **Requirements Traceability Matrix (RTM)** | Maps every requirement to work events that verify it, with "Last tested" timestamps and a per-FR "Reconciled?" status |
| **Test Evidence** | Test progression timeline showing how the test suite evolved over time |
| **Change History** | Conventional Commits mapped to requirements, with commit hashes and timestamps |
| **SBOM (Software Bill of Materials)** | Dependencies with versions, extracted from `package.json` / `package-lock.json` |

Compliance is updated incrementally after each pipeline phase, so reports reflect current state at any point during the build.

### Reading a Shipwright Project from Outside

If you inherited a Shipwright-generated repository (or are reviewing one without going through the pipeline yourself), this is the orientation guide. It explains **where each kind of fact lives** so you do not have to read every file to find one answer.

The framework deliberately does not aggregate this information into a single `PROJECT.md` per repo. An aggregate file becomes a view over other files and drifts the moment any of them changes. Instead, learn the structure once, then read source-of-truth files directly. The same approach is why a Replit-style `replit.md` is not generated: views drift, conventions do not.

#### Reading Order

Read these in order. Stop as soon as you have the answer you need; most reviews never need to go past step 3.

| # | File | What you learn | Time |
|---|------|----------------|------|
| 1 | `README.md` | What this project is, how to install, how to run | ~1 min |
| 2 | `CLAUDE.md` | Stack, build/test/deploy commands, structure, key files, gotchas | ~3 min |
| 3 | `.shipwright/agent_docs/conventions.md` | Code patterns, naming, git workflow, component examples | ~5 min |
| 4 | `.shipwright/agent_docs/architecture.md` | System overview, stack table, data flow, security model | ~5 min |
| 5 | `.shipwright/agent_docs/decision_log.md` | Architecture Decision Records: why each non-obvious choice was made | scan-based |
| 6 | `.shipwright/agent_docs/session_handoff.md` | Most recent state: last commit, last test status, last completed phase | ~1 min |
| 7 | `shipwright_*_config.json` | Pipeline state machine: current step, completed steps, project metadata. Several files (run, project, plan, build, test, deploy, security, sync); grep the one whose name matches your question | scan-based |
| 8 | `shipwright_events.jsonl` | Append-only event log, single source of truth for what happened, when. Compliance reports and the activity dashboard derive from this | scan-based |

Files 1–4 are the primer. Files 5–8 are reference material: you grep them for a specific question, you do not read them cover to cover.

#### Single-Source-of-Truth Map

When you have a specific question, go directly to the file that owns the answer. Do not infer from `CLAUDE.md` if the canonical answer lives elsewhere; `CLAUDE.md` is a summary and may be a step behind on details.

| Question | Authoritative File | Why |
|----------|-------------------|-----|
| What stack / framework? | `shipwright_run_config.json` (`profile`) + `.shipwright/agent_docs/architecture.md` (Stack table) | Profile is normative; architecture.md expands it |
| What conventions / code style? | `.shipwright/agent_docs/conventions.md` | Single source, never duplicated |
| Why was X chosen over Y? | `.shipwright/agent_docs/decision_log.md` | ADR format with rejected alternatives |
| What did the last iterate do? | `shipwright_events.jsonl` (most recent `work_completed`) + `.shipwright/agent_docs/build_dashboard.md` | Event log is canonical; dashboard is a rendered view |
| What test status right now? | `shipwright_test_results.json` | Last test run, pass/fail counts per layer |
| What requirement maps to which file? | `shipwright_sync_config.json` (if present) | FR ↔ file mapping |
| What requirements does this project even have? | `.shipwright/planning/*/spec.md` | IREB-aligned FR/NFR specs |
| Where in the pipeline are we? | `shipwright_run_config.json` (`status`, `current_step`) + `phase_history` for "which step ran when" | Pipeline state machine; `current_step` is the live cursor, `phase_history` is the trail |
| What sections has build completed? | `shipwright_build_config.json` (`completed_sections`) | Per-section build state lives here, not in run config |
| What iterates have run? | `.shipwright/agent_docs/iterates/*.json` (one file per iterate); fall back to legacy `iterate_history` array in `shipwright_run_config.json` for older projects | One file per iterate; the run-config array is migration-only for older projects |
| What was the most recent decision? | `.shipwright/agent_docs/decision_log.md` (latest ADR) | Forward-only append |
| Did anyone override a hook? | `.shipwright/agent_docs/compliance_overrides.log` | Audit trail of soft-block overrides |

#### Quickstart Pattern

Every Shipwright project follows the same three-command shape, regardless of stack. The actual commands come from `CLAUDE.md` (the `## HOW` section). The pattern:

```bash
# Setup — install dependencies
<package-manager> install        # e.g. npm install, uv sync, bun install

# Run — start the dev server (a Shipwright project has one canonical dev command)
<dev-command>                    # e.g. npm run dev, uv run dev, etc.

# Test — at minimum the unit tests; CLAUDE.md lists optional integration / E2E commands
<test-command>                   # e.g. npm test, uv run pytest, etc.
```

If `CLAUDE.md` does not show one of these, that path is not used in the project; there is no second-guessing.

#### When to Reach for Which Skill

Once oriented, common follow-up actions:

| You want to... | Skill | Notes |
|----------------|-------|-------|
| Make any code change (feature / fix / refactor) | `/shipwright-iterate "<description>"` | Adaptive complexity; runs the right amount of process |
| See the running app in a browser | `/shipwright-preview` | Starts the dev server, returns the URL |
| Run tests on demand | `/shipwright-test` | Auto-detects unit/integration/E2E from profile |
| Check that artifacts are still in sync | `/shipwright-compliance` | Cross-artifact detective audit (8 check groups, A–H) |
| Tag a release | `/shipwright-changelog` | Aggregates `[Unreleased]` entries, bumps semver, opens PR |
| Deploy to DEV/PROD | `/shipwright-deploy` | DEV auto, PROD manual (per design principle) |

Avoid editing files directly when the skill exists; the skill keeps `.shipwright/agent_docs/`, `shipwright_events.jsonl`, and compliance reports in sync. Hand-edits silently produce drift that `/shipwright-compliance` will flag later.

#### Why No Aggregated Project Summary File

Frameworks like Replit ship a single `replit.md` that aggregates setup, API, deployment, troubleshooting into one file. It looks hand-off-friendly on day one. Six iterates later, half of it is wrong: the aggregate is a view over files that have moved on, and nothing forced it to update.

Shipwright takes the opposite approach: each file owns one concern. `CLAUDE.md` is the entry point and stays lean (~200 lines). Detail lives in `.shipwright/agent_docs/`. Pipeline state lives in `shipwright_*_config.json`. Compliance evidence lives in `shipwright_events.jsonl`. There is no synthesized "everything" file because there is no way to keep one in sync without paying drift in tokens or operator attention every iterate.

The price is that you read 2–3 files to onboard instead of 1. The benefit is that what you read is current.

---

## 11. Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| "Plugin not found" when typing `/shipwright-run` | Shell alias not loaded, or plugin paths wrong | Run `type shipwright` to check alias. Verify `~/shipwright/plugins/shipwright-run/.claude-plugin/plugin.json` exists. |
| `uv: command not found` | uv not in PATH after installation | Restart terminal, or add: `export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"` (the astral installer writes uv to `~/.local/bin`) |
| "Python version too old" | System Python is below 3.11 | Run `uv python install 3.11` -- uv manages Python versions for you. |
| Hooks fail with "permission denied" | Python/shell scripts not executable | Run `chmod +x ~/shipwright/plugins/*/scripts/**/*.py ~/shipwright/plugins/*/scripts/**/*.sh` |
| Context window exceeded during large project | Project too large for a single session | Type `/clear` in Claude Code. Shipwright saves state to config files and resumes from the handoff document. |
| External review prompt appears every run | No API keys set for OpenRouter, Gemini, or OpenAI | The skill prompts in Step 5 Branch B rather than silently skipping. Fix: add `OPENROUTER_API_KEY=...` to `.env.local` at the repo root. To permanently opt out, set `external_review.feedback_iterations: 0` in `shipwright_iterate_config.json` and the skill will fall straight into the self-review fallback without asking. |
| Git operations fail (PR creation, changelog) | GitHub CLI not authenticated | Run `gh auth login` and follow the prompts. |
| Deploy fails with auth error | Jelastic token expired or invalid | Generate a new token in the Infomaniak Jelastic Dashboard under Settings > Access Tokens. |
| `/shipwright-security` reports "no backend available" | No scanner installed | Install OSS tools (semgrep, trivy, gitleaks; recommended). Aikido credentials (`AIKIDO_CLIENT_ID`, `AIKIDO_CLIENT_SECRET`) work as a legacy fallback. |
| Build hangs after multiple fix attempts | Agent stuck in a debugging loop | The constitution limits retries to 3 attempts, then escalates. If it still loops, type "stop" and review the error manually. |
| Invalid JSON in `shipwright_events.jsonl` | Interrupted write or manual editing | Run `uv run shared/scripts/tools/validate_event_log.py --project-root .` -- the reader skips corrupt lines automatically, but the validator will identify them. |
| Commit exists but no event recorded | Agent crashed after commit but before event recording | Run `validate_event_log.py` -- it checks git history against events and reports unmatched commits. |
| Compliance reports empty after update | Event log missing or no events | Ensure `shipwright_events.jsonl` exists. For existing projects, run `uv run shared/scripts/tools/convert_configs_to_events.py --project-root .` to migrate from config files. |

---

## 12. Updating Shipwright

### Marketplace Installation (Recommended)

Run the update script from the Shipwright repo:

```bash
bash scripts/update-marketplace.sh
```

This fetches the latest code from GitHub (`claude plugin marketplace update`) and refreshes each plugin's local cache (`claude plugin update`). Restart your Claude Code session afterward.

**Manual alternative** (update individual plugins):

```bash
claude plugin marketplace update shipwright
claude plugin update shipwright-iterate@shipwright
claude plugin update shipwright-build@shipwright
# ... repeat for other installed plugins
```

### Shell Alias Installation

If you installed via shell alias instead of marketplace:

```bash
cd ~/shipwright && git pull && uv sync
```

`uv sync` re-installs Python dependencies if they changed. If nothing changed, it completes in under a second.

### What Takes Effect When

| Change Type | When It Takes Effect |
|-------------|---------------------|
| SKILL.md changes | After session restart |
| Python script changes | Immediately (scripts are loaded fresh each run via `uv run`) |
| Hook changes | Immediately (hooks are re-read each session) |
| Marketplace plugin updates | After `claude plugin update` + session restart |
| New plugins added | After updating your shell alias or marketplace config to include them |
| Profile changes | On next `/shipwright-run` (profile is read at pipeline start) |

### Checking What Changed

```bash
cd ~/shipwright && git log --oneline -10
```

Or read `CHANGELOG.md` in the repository root for release notes.

---

## 13. Command Center (WebUI)

Running more than one Shipwright project at once? The **Shipwright
Command Center** is an optional local web application that gives you
**one Kanban board across every project**, a live transcript per task,
and a global inbox for every "Claude needs permission to..." prompt,
so you stop hunting between VS Code windows to see where
everything stands.

The web server never spawns Claude itself. When you hit **Launch** on a
task, the `claude` command auto-runs in an embedded terminal pane on the
task detail page: the embedded terminal hosts a shell, Claude runs
inside it. The Command Center watches the resulting session transcript
live, fire and forget:
the dashboard updates while you keep coding.

The Command Center lives in its own repo:
**[shipwright-webui](https://github.com/svenroth-ai/shipwright-webui)**.

### Quick start

```bash
git clone https://github.com/svenroth-ai/shipwright-webui.git ~/shipwright-webui
cd ~/shipwright-webui
make install       # npm install in server/ + client/
make dev-server    # Terminal 1 — backend on :3847
make dev-client    # Terminal 2 — frontend on :5173
```

Then open <http://localhost:5173>. The full user guide (installation,
daily workflow, recommended terminal setup, custom actions for your
own slash skills, Windows autostart) lives at
**[docs/guide.md](https://github.com/svenroth-ai/shipwright-webui/blob/main/docs/guide.md)**
in the WebUI repo.

---

## Appendix A: Glossary

### Plain-Language Index

If you encountered an unfamiliar term in this guide, this is the fast way in. Each row leads with the plain-language description, then names the industry-standard term used in the rest of the doc. The full formal table below covers more.

| If you mean… | Official term |
|---|---|
| Description of what the app should do, who it's for, and what it must not do | **IREB-Spec** (a requirements specification written per IREB practice) |
| Log of architectural decisions with rationale (why this database, why this pattern) | **ADR** (Architecture Decision Record) |
| Coverage matrix where every requirement points at the test that proves it | **RTM** (Requirements Traceability Matrix) |
| Inventory of every third-party component in the app, for license and CVE tracking | **SBOM** (Software Bill of Materials) |
| Standardized commit-message format (`feat:`, `fix:`, etc.) so version history is machine-readable | **Conventional Commits** |
| A checkpoint between two pipeline steps where output is verified before the next step starts | **Phase Gate** / **Quality Gate** |
| The whole system of guides (Specs, Conventions) and sensors (Tests, Reviews, Scanners) that steers AI output before and after generation | **Harness** (Martin Fowler 2026: "harness engineering") |

### Formal Glossary

| Term | Definition |
|------|-----------|
| **Split** | A shippable chunk of functionality within a larger project. Shipwright decomposes projects into splits during the project phase. Each split gets its own spec, plan, and build cycle. |
| **Section** | The smallest unit of implementation within a split. Each section maps to a single Conventional Commit and produces a `work_completed` event in the event log. Sections are defined during the plan phase and built sequentially. |
| **Event Log** | An append-only JSONL file (`shipwright_events.jsonl`) recording every significant action in the project: section completions, iterate changes, test runs, and phase transitions. All compliance reports and the activity dashboard are derived from this log. |
| **Work Event** | A `work_completed` entry in the event log. Represents any unit of verified work -- whether a build section or an iterate change. Contains the commit hash, test results, affected requirements, and review data. |
| **Event Amendment** | A correction entry (`event_amended`) that references a previous event's ID and provides corrected field values. Preserves log immutability while allowing data fixes. |
| **Stack Profile** | A JSON file defining the complete technology stack: runtime versions, libraries, folder structure, deployment target, CI pipeline, and architecture rules. Stored in `shared/profiles/`. |
| **Hook** | A Python or shell script that fires on Claude Code events (session start, before/after tool use, session end). Hooks enforce safety rules programmatically -- blocking dangerous commands, scanning for secrets, detecting destructive migrations. |
| **Constitution** | The governing document (`shared/constitution.md`) defining ALWAYS, ASK FIRST, and NEVER rules for all Shipwright agents. Hooks enforce a subset; the constitution covers the complete set. |
| **Phase Validator** | A function that runs before marking a pipeline phase complete. Checks that required artifacts exist (specs, section files, test results). Returns issues with severity ASK (blocks until user confirms) or INFORM (logs and continues). |
| **RTM (Requirements Traceability Matrix)** | A compliance report mapping every requirement to work events that verify it, with "Last tested" timestamps and a per-FR "Reconciled?" status. Proves that all requirements were implemented and tested. |
| **SBOM (Software Bill of Materials)** | A compliance report listing all project dependencies with their versions, extracted from `package.json` and `package-lock.json`. Used for supply chain auditing. |
| **ADR (Architecture Decision Record)** | A structured log entry documenting an architecture decision: status, context, decision, and consequences (including rejected alternatives). Stored in `.shipwright/agent_docs/decision_log.md`. |
| **Conventional Commits** | A commit message format (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`) that enables automated changelog generation and semantic versioning. |
| **IREB** | International Requirements Engineering Board. Shipwright aligns its requirements specs with IREB practices: structured requirements with acceptance criteria that map directly to tests. |
| **Agent Docs** | The `.shipwright/agent_docs/` directory containing architecture, conventions, decision log, session handoff, and build dashboard documents. These files provide context for AI agents working on the project. |
| **Feature Branch** | A Git branch created during the build phase (`build/{slug}-{session-id}`, one per build session) or by an iterate (`iterate/<slug>`), merged to `main` via PR. |
| **Context Pressure** | A measure of how full Claude Code's context window is. Shipwright monitors tool call counts and estimates remaining capacity. When pressure is high, it triggers a session handoff. |
| **Session Handoff** | An auto-generated document (`.shipwright/agent_docs/session_handoff.md`) containing current state, completed work, and next steps. Written before context compaction so a new session can resume seamlessly. |

---

## Appendix B: Command Reference

| Command | Arguments | Flags | Purpose |
|---------|-----------|-------|---------|
| `/shipwright-run` | `"description"` or `@requirements.md` | -- | Coordinate a multi-session pipeline. Writes `shipwright_run_config.json` (schema v2) with `phase_tasks[]`, prints a launch card for the first phase, and ends. Each phase runs in its own external Claude CLI session; phase Stop hooks plan the next phase. Re-invoke on an existing config to print a resume launch card. |
| `/shipwright-iterate` | `"description"` | `--type feature\|change\|bug`, `--complexity trivial\|small\|medium\|large`, `--review`, `--pause`, `--campaign <slug>`, `--sub-iterate-id <id>`, `--autonomous` | Complexity-adaptive SDLC for ongoing changes. Auto-detects intent and complexity, scales phases from quick fix to structured mini-pipeline with planning, review, and testing. Campaign mode (`--campaign`) groups related sub-iterates; `--autonomous` runs them **interleaved-serial** -- each sub-iterate is its own PR, merged after CI-green before the next builds from a fresh `origin/main` (`branch_strategy: serial`, the default), so shared-file edits compose with no end-stage merge drain. `--campaign <slug> --sub-iterate-id <id>` on a single hand-run sub-iterate stamps `campaign`/`sub_iterate_id` into its `work_completed` event (same self-identification the autonomous runner records). |
| `/shipwright-project` | `"description"` or `@requirements.md` | -- | Decompose requirements into splits and IREB-aligned specs. Generates `CLAUDE.md`, `.shipwright/agent_docs/`, and project config. Interviews you about requirements. |
| `/shipwright-design` | -- | -- | Generate HTML mockups from specs. Produces screens with review viewer, feedback loop, and spec backflow. Runs after project, before plan. |
| `/shipwright-plan` | `@spec.md` | -- | Create implementation plan for one split. Researches stack, interviews for clarification, generates section files. Optionally sends plan to external LLMs (Gemini + OpenAI) for review. |
| `/shipwright-build` | `@section.md` | `--autonomous`, `--from <section>` | Implement one section using TDD. Writes failing test, implements code, runs code review subagent, creates Conventional Commit on feature branch. With `--autonomous`, loops through all pending sections via subagents without manual gates. |
| `/shipwright-test` | -- | `--fix` | Run test suite: unit tests (Vitest), integration tests (real DB), pgTAP (RLS), smoke test (HTTP), E2E (Playwright). The `--fix` flag enables auto-repair of failing tests. |
| `/shipwright-security` | -- | -- | **Out-of-band**, not part of `PIPELINE_STEPS`. Run security scan (OSS backend by default; Aikido optional/legacy). Classifies findings, runs remediation loop with security-fixer subagent, generates report. Runs when any scanner backend is available. CI activation steps and the GitHub Actions workflow shape live at [docs/security-ci-setup.md](security-ci-setup.md). |
| `/shipwright-changelog` | -- | -- | Parse Conventional Commits from git history, generate Keep-a-Changelog entries, suggest semver bump, create version tag, and open a pull request. |
| `/shipwright-deploy` | -- | `--prod`, `--rollback` | Deploy via the project's deploy profile (Jelastic is the verified reference target; Vercel / Compose-VPS ship as declarative stubs). DEV deploys automatically; PROD requires `--prod` and explicit confirmation. Runs a smoke test after deploy, rolls back on failure. |
| `/shipwright-compliance` | -- | `--fix`, `--only <groups>`, `--format md\|json\|both` | **Out-of-band** detective cross-artifact audit (Groups A–H). Also fires as auto-background subprocess after every completed pipeline phase via `update_compliance.py --phase <name>` (no manual flag needed). |
| `/shipwright-adopt` | -- | `--dry-run`, `--profile <name>`, `--scope full_app\|library\|cli`, `--include-nested`, `--exclude-path <p>`, `--skip-crawl`, `--crawl-base-url <url>`, `--crawl-auth-token <tok>`, `--crawl-max-depth <n>`, `--crawl-max-pages <n>`, `--no-backfill-events`, `--no-sync`, `--planning-split <name>` | Onboard an existing (brownfield) repo into Shipwright. Analyzes stack + routes + conventions + git history, writes CLAUDE.md + .shipwright/agent_docs + configs + compliance reports + an E2E baseline. Not a pipeline phase; runs once per repo. |

### Verifier and Canon Helper Scripts

These are invoked automatically by the pipeline but can also run standalone for audit and debugging. Most live under `shared/scripts/tools/`; the exception is `mark-review-state.py`, which lives under `shared/scripts/checks/`.

| Script | Purpose | Key flags |
|--------|---------|-----------|
| `verify_phase.py` | Unified finalization verifier. Dispatches to the per-phase verifier module in `verifiers/`. Runs automatically through `phase_validators.py` between phases. | `--project-root <path>` · `--phase iterate\|runtime\|project\|design\|plan\|build\|test\|changelog\|deploy\|all` · `--run-id <id>` (required for iterate) · `--commit <sha>` (iterate) · `--strict` (warnings → errors) |
| `verify_iterate_finalization.py` | Backwards-compatible wrapper around `verifiers/iterate_checks.py` for the iterate finalization gate. | `--run-id <id>` · `--commit <sha>` · `--project-root <path>` · `--strict` |
| `append_changelog_entry.py` | Atomic Keep-a-Changelog writer for canon step C5. Dedupes by entry body and holds `CHANGELOG.md.lock` via `file_lock.py` (cross-platform, 5 s timeout). | `--project-root <path>` · `--category Added\|Changed\|Fixed\|Deprecated\|Removed\|Security` · `--entry "..."` |
| `append_phase_history.py` | Atomic read-modify-write on `shipwright_run_config.json::phase_history[<phase>]`. 50-entry retention per phase, file-lock serialised. | `--project-root <path>` · `--phase <phase>` · `--entry-json '{...}'` · `--run-id <id>` |
| `generate_session_handoff.py` | Session-handoff writer. The `--canon-marker` flag lets phase finalization steps tag the handoff so the PostStop hook does not clobber it. | `--canon-marker` (emit YAML frontmatter with `canon_generated: true` + `run_id`) · `--phase <phase>` · `--reason "..."` · `--project-root <path>`. Requires `SHIPWRIGHT_RUN_ID` env var when `--canon-marker` is set (degrades safely with a stderr warning otherwise). |
| `external_review.py` | External LLM review CLI. Runs Gemini + OpenAI in parallel via OpenRouter (or direct API keys) and emits a unified `{success, provider, reviews}` JSON envelope. Three modes share the same dispatch surface. | `--mode plan\|iterate\|code` · `--plan-file <path>` (plan/iterate) OR `--diff-file <path>` (code) · `--spec-file <path>` · `--plugin-root <path>` · env: `OPENROUTER_API_KEY` or `GEMINI_API_KEY` + `OPENAI_API_KEY` · model overrides via `SHIPWRIGHT_REVIEW_MODEL_<KEY>` |
| `mark-review-state.py` | Writes the marker file that downstream phases and compliance read to confirm a review-step branch (A/B/C) ran to completion. Two filenames: `external_review_state.json` for plan/iterate, `external_code_review_state.json` for the code-review cascade. | `--planning-dir <path>` · `--status completed\|skipped_user_opt_out\|skipped_config_disabled` · `--review-type plan\|iterate\|code` (omitted = plan/iterate marker) · `--provider openrouter\|gemini\|openai` · `--findings-count N` · `--reason "..."` · `--self-review-fallback-ran` |

The per-phase verifier modules under `shared/scripts/tools/verifiers/` (`project_checks.py`, `design_checks.py`, `plan_checks.py`, `build_checks.py`, `test_checks.py`, `changelog_checks.py`, `deploy_checks.py`, `iterate_checks.py`, `runtime_checks.py`) share generic C1–C5 helpers and F1/F2/F3 ADR integrity checks from `common.py`. The full Canon Coverage matrix is in [docs/hooks-and-pipeline.md](hooks-and-pipeline.md#canon-coverage--iterate-12-final-state).
