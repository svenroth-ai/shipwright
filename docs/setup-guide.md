# Shipwright Setup Guide

> From zero to your first AI-built application in 5 minutes.

Shipwright is an AI-powered SDLC pipeline built on Claude Code. This guide walks you through installation, configuration, and your first run.

---

## Quick Start (5 minutes)

For experienced developers who just want to get going:

```bash
# 1. Prerequisites (skip if you have these)
curl -LsSf https://astral.sh/uv/install.sh | sh   # Python package manager

# 2. Clone and install
git clone https://github.com/svenroth-ai/shipwright.git ~/shipwright
cd ~/shipwright && uv sync

# 3. Register as marketplace (works in VSCode Extension + CLI)
#    Add to ~/.claude/settings.json:
#    "extraKnownMarketplaces": { "shipwright": { "source": { "source": "github", "repo": "svenroth-ai/shipwright" } } }
#    "enabledPlugins": { "shipwright-run@shipwright": true, ... (all 7 plugins) }
#    Or run the install script:
~/shipwright/scripts/install.sh

# 4. Open Claude Code (VSCode Extension or CLI) and type:
/shipwright-run "A simple todo app with Supabase and Next.js"
```

For the full setup (deployment, external review, etc.), read on.

---

## 1. Prerequisites

### Required

| Tool | Version | Install | Verify |
|------|---------|---------|--------|
| Claude Code | Latest | [docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code) | `claude --version` |
| Python | 3.11+ | Comes with uv | `python3 --version` |
| uv | Latest | See below | `uv --version` |
| Git | 2.x+ | [git-scm.com](https://git-scm.com) | `git --version` |

**Claude Code** requires a Pro or Max subscription. Max is recommended for large projects (extended context window).

**uv** (Python package manager):
```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
winget install astral-sh.uv
```

### Optional (feature-dependent)

| Tool | Needed for | Install | Verify |
|------|-----------|---------|--------|
| GitHub CLI (gh) | PR creation, changelog | `brew install gh` / `winget install GitHub.cli` | `gh --version` |
| Node.js 22.x | supabase-nextjs profile | [nodejs.org](https://nodejs.org) or `nvm install 22` | `node --version` |
| Supabase CLI | Database migrations | `npm install -g supabase` | `supabase --version` |

### Recommended: Mermaid Preview (VSCode)

Shipwright's compliance reports use **Mermaid diagrams** for pipeline status, traceability flows, and test pyramids. To render these diagrams directly in VSCode's Markdown preview, install the Mermaid extension:

1. Open VSCode → Extensions (`Ctrl+Shift+X`)
2. Search for **"Markdown Preview Mermaid Support"** (by the Mermaid team)
3. Install and reload

Without this extension, Mermaid code blocks appear as raw text in the Markdown preview.

---

## 2. Installation

### Option A: Marketplace (recommended — works in VSCode Extension + CLI)

Add the Shipwright marketplace to your Claude Code settings. This works in both the **VSCode Extension** (sidebar) and the **CLI**.

Add this to `~/.claude/settings.json`:

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
    "shipwright-plan@shipwright": true,
    "shipwright-build@shipwright": true,
    "shipwright-test@shipwright": true,
    "shipwright-deploy@shipwright": true,
    "shipwright-changelog@shipwright": true
  }
}
```

If you already have content in `settings.json`, merge these two keys into your existing file.

**Alternatively**, in the VSCode Extension: type `/plugins` → Marketplaces tab → add `svenroth-ai/shipwright`.

**Install Python dependencies** (needed for plugin scripts):
```bash
git clone https://github.com/svenroth-ai/shipwright.git ~/shipwright
cd ~/shipwright && uv sync
```

### Option B: Shell Alias (CLI only)

If you prefer the CLI without marketplace registration, use a shell alias.

**bash / zsh** — add to `~/.bashrc` or `~/.zshrc`:

```bash
shipwright() {
  claude \
    --plugin-dir ~/shipwright/plugins/shipwright-run \
    --plugin-dir ~/shipwright/plugins/shipwright-project \
    --plugin-dir ~/shipwright/plugins/shipwright-plan \
    --plugin-dir ~/shipwright/plugins/shipwright-build \
    --plugin-dir ~/shipwright/plugins/shipwright-test \
    --plugin-dir ~/shipwright/plugins/shipwright-deploy \
    --plugin-dir ~/shipwright/plugins/shipwright-changelog \
    "$@"
}
```

Then reload: `source ~/.bashrc`

**PowerShell** — add to `$PROFILE`:

```powershell
function shipwright {
  claude `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-run `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-project `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-plan `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-build `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-test `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-deploy `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-changelog `
    @args
}
```

### Verify Installation

In Claude Code (VSCode Extension or CLI), type:
```
/shipwright-run
```
You should see the SHIPWRIGHT-RUN banner.

---

## 3. Configuration

Shipwright works out of the box for the project → plan → build cycle. Configuration is only needed for optional features.

### Deployment (Jelastic / Infomaniak)

Required for `/shipwright-deploy`. Get your token from [Infomaniak Jelastic Dashboard](https://app.jpc.infomaniak.com/) → Settings → Access Tokens.

```bash
export JELASTIC_TOKEN="your-jelastic-api-token"
```

### External Plan Review

Shipwright can send your implementation plan to external LLMs for independent review (catching blind spots Claude might miss). Three options:

All credentials go in a single `.env.local` file at the Shipwright repo root:

```bash
# Copy the template and fill in your keys
cp .env.example .env.local
```

The `.env.local` file is gitignored and will never be committed. See `.env.example` for all available variables.

#### Option A: OpenRouter (recommended)

One API key for both review models. Add to `.env.local`:

```
OPENROUTER_API_KEY=sk-or-your-key
```

Get your key at [openrouter.ai](https://openrouter.ai/).

Models used (configurable in `plugins/shipwright-plan/config.json`):
- `google/gemini-3.1-pro-preview` — Gemini review
- `openai/gpt-5.4` — OpenAI review

#### Option B: Direct API Keys

Use Google and OpenAI APIs directly. Add to `.env.local`:

```
GEMINI_API_KEY=your-gemini-key    # from ai.google.dev
OPENAI_API_KEY=sk-your-key        # from platform.openai.com
```

#### Option C: No External Review

Skip external review entirely. Shipwright works fine without it — you just don't get the second-opinion check on your implementation plan.

### Supabase Migrations

Required only for automated database migrations during deploy. Add to `.env.local`:

```
SUPABASE_ACCESS_TOKEN=your-supabase-token
```

### Where to Set Environment Variables

All Shipwright credentials go in `.env.local` at the repo root. Variables already set in your OS environment take precedence over `.env.local`.

### Verify Configuration

```bash
~/shipwright/scripts/verify-setup.sh
```

---

## 4. First Run

### Create a New Project

```bash
mkdir ~/my-first-app && cd ~/my-first-app
git init
shipwright
```

Then type:
```
/shipwright-run "A simple todo list app with Supabase and Next.js"
```

### What to Expect

The pipeline runs through these phases:

1. **SHIPWRIGHT-RUN** — Infers your stack (supabase-nextjs), asks for confirmation
2. **SHIPWRIGHT-PROJECT** — 5-10 questions about your requirements, creates specs
3. **SHIPWRIGHT-PLAN** — Creates implementation plan, optional external review
4. **SHIPWRIGHT-BUILD** — TDD implementation: write tests → implement → code review → commit
5. **SHIPWRIGHT-TEST** — Runs unit tests, smoke test, Playwright E2E
6. **SHIPWRIGHT-DEPLOY** — Deploys to Jelastic DEV (if configured)
7. **SHIPWRIGHT-CHANGELOG** — Generates changelog, creates PR

In guided mode (default), Shipwright asks for confirmation at each phase transition.

**Estimated time:** 15-30 minutes for a small app.

### Alternative Invocations

```bash
# From a requirements file
shipwright
/shipwright-run @requirements.md

# Quick iteration on existing project
shipwright
/shipwright-run --iterate "Add dark mode toggle"

# Use individual skills directly
shipwright
/shipwright-project "Build a dashboard"
/shipwright-plan @01-auth/spec.md
/shipwright-build @sections/01-models.md
```

---

## 5. Platform Notes

### Windows

- Claude Code on Windows uses bash (Git Bash). Ensure [Git for Windows](https://gitforwindows.org/) is installed.
- Use the PowerShell alias (Section 2) or run from Git Bash.
- `uv` works natively on Windows: `winget install astral-sh.uv`

### macOS

- Install prerequisites via Homebrew: `brew install git gh node uv`
- Xcode Command Line Tools needed: `xcode-select --install`

### Linux

- Most straightforward setup — all tools available via package managers.
- Ensure Python 3.11+ (some distros ship older versions).

### WSL (Windows Subsystem for Linux)

- Alternative to native Windows. All Unix commands work natively in WSL2.
- Claude Code CLI works in WSL.
- Recommended if you prefer a Linux workflow on Windows.

---

## 6. Troubleshooting

### "Plugin not found" when typing /shipwright-run

**Cause:** Shell alias not loaded, or `--plugin-dir` paths are wrong.

**Fix:**
```bash
# Check alias exists
type shipwright

# Verify plugin directory exists
ls ~/shipwright/plugins/shipwright-run/.claude-plugin/plugin.json
```

### "uv: command not found"

**Cause:** uv not in PATH after installation.

**Fix:** Restart your terminal, or add uv to PATH manually:
```bash
export PATH="$HOME/.cargo/bin:$PATH"  # Default uv install location
```

### "Python version too old"

**Cause:** System Python is < 3.11.

**Fix:** uv manages Python versions. Run `uv python install 3.11` to install a compatible version.

### Hooks fail with permission denied

**Cause:** Python scripts not executable.

**Fix:**
```bash
chmod +x ~/shipwright/plugins/*/scripts/**/*.py
chmod +x ~/shipwright/plugins/*/scripts/**/*.sh
```

### Context window exceeded during large projects

**Cause:** Large projects can fill Claude's context window.

**Fix:** Type `/clear` in Claude Code. Shipwright saves state to config files and resumes automatically from where you left off.

### External review skipped

**Cause:** No API keys set.

**Fix:** Copy `.env.example` to `.env.local` at the repo root and add your `OPENROUTER_API_KEY`. See Section 3.

### Git operations fail

**Cause:** GitHub CLI not authenticated.

**Fix:**
```bash
gh auth login
```

---

## 7. What's Next

### Three Ways to Use Shipwright

| Mode | Command | When |
|------|---------|------|
| **Full App** | `/shipwright-run "description"` | New project from scratch |
| **Extension** | `/shipwright-run "Add feature X"` | Extend existing project |
| **Iterate** | `/shipwright-run --iterate "Quick fix"` | Fast change to existing project |

### Use Skills Individually

Each skill works standalone — you don't always need the full pipeline:

- `/shipwright-project` — Just decompose requirements
- `/shipwright-plan @spec.md` — Just plan one split
- `/shipwright-build @section.md` — Just implement one section
- `/shipwright-test` — Just run tests
- `/shipwright-changelog` — Just generate changelog + PR

### Customize Stack Profiles

Profiles are JSON files in `~/shipwright/shared/profiles/`. Currently available:
- `supabase-nextjs` — Next.js 16 + Supabase + Tailwind 4 + shadcn/ui

To add a new profile, create a JSON file following the `supabase-nextjs.json` structure.

### Updating Shipwright

Shipwright is installed as a local git clone. Updates are a single command:

```bash
cd ~/shipwright && git pull && uv sync
```

`uv sync` re-installs Python dependencies if they changed. If nothing changed, it's a no-op (< 1 second).

**What happens on update:**
- SKILL.md changes → take effect on next `shipwright` session (exit and restart)
- Python script changes → take effect immediately (loaded fresh each run via `uv run`)
- New plugins added → update your shell alias to include them

**Check what changed:**
```bash
cd ~/shipwright && git log --oneline -10
```

Or read `CHANGELOG.md` for release notes.

---

Built by [svenroth.ai](https://github.com/svenroth-ai). Powered by Claude Code.
