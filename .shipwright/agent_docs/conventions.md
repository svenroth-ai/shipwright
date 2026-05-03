# Conventions — shipwright

## Linter / Formatter

- **Linter**: _none detected_
- **Formatter**: _none detected_
- **TypeScript strict**: no
- **.editorconfig**: _none_

## Project-specific rules

Python 3.11+ with uv as package manager. All scripts are invoked via uv run. Hooks resolve plugin paths via ${CLAUDE_PLUGIN_ROOT}. Config files written to target projects use the prefix shipwright_ (e.g. shipwright_run_config.json) and environment variables use SHIPWRIGHT_ (e.g. SHIPWRIGHT_SESSION_ID, SHIPWRIGHT_PLUGIN_ROOT). Commits follow Conventional Commits with the plugin name as scope (e.g. fix(adopt): ..., feat(security): ...). Branches for self-monorepo work follow iterate/<short-kebab-description>. After any push that touches plugin-side files, scripts/update-marketplace.sh syncs the runtime plugin cache. Linting uses ruff; type-checking uses pyright; tests use pytest. The canonical user-facing documentation is docs/guide.md; the canonical hook + pipeline reference is docs/hooks-and-pipeline.md. CLAUDE.md captures operational rules; generated agent_docs link back rather than duplicating these sources of truth.

## Commit messages

- Use Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- Scopes should reflect module boundaries (e.g., `feat(auth): ...`)

## Files

- Keep files under 300 lines; split larger modules.
- Tests live alongside implementation with `.test.*` / `_test.*` suffix OR in a `tests/` directory — whichever is consistent with the rest of the codebase.

## Learnings

- **Always quote `uv run <placeholder>` path arguments in shell snippets.** Any documented or installed shell command of the shape `uv run ${CLAUDE_PLUGIN_ROOT}/...`, `uv run {plugin_root}/...`, `uv run {shared_root}/...`, etc. must wrap the path in double quotes: `uv run "${CLAUDE_PLUGIN_ROOT}/..."`. Without quoting, target projects on paths containing spaces (OneDrive-synced "AI Backup - Documents", Windows usernames with spaces, paths under "Program Files") get word-split by the shell and uv exits non-zero. For the suggest_iterate UserPromptSubmit hook this exit non-zero blocks every user prompt. Same risk class for the documentation snippets the agent renders into shell at runtime. Add `--no-project` to `uv run` for hook commands so a corrupt target-project `.venv` cannot stall uv on resolution. Out of scope for this rule (today): `plugins/*/hooks/hooks.json` between-phase commands — different blast radius (only fail when the *plugin install path* contains spaces, which today only happens on Windows usernames with spaces). See ADR-020.
- **Hook-installer-style code that detects "already-present" must also upgrade legacy forms in place, not just refuse to add a duplicate.** Recognition without rewrite leaves an already-broken installation broken on re-run. Tests should assert the canonical literal after run, not just absence of duplicates. When BOTH the carrier shape (Shape A vs Shape B per ADR-019) and the command literal can be wrong, the upgrade must fix both — recognizing one without rewriting the other still produces a broken hook. Surface the rewrite via an `upgraded: true` field in the return dict so callers/telemetry can observe that re-running adopt actually fixed something.
- **Drift-protection tests across two SSoTs use AST + source-position sort, not substring grep.** When one module hardcodes a list that mirrors logic in another module (e.g. `_SHIPWRIGHT_FRAMEWORK_VARS` vs `is_external_review_enabled`), a substring-based test only catches removal, not reordering or insertion. Parse the source-of-truth file via `ast.parse`, walk to extract the calls/keys, then sort by `(node.lineno, node.col_offset)` because `ast.walk` order is unspecified. Compare ordered list-vs-list with a clear failure message naming both sources. Reviewer caught this on iterate-2026-05-03-adopt-env-local-scaffold; the original test only asserted names appeared somewhere. See ADR-021.
- **`.env.local` is the single secrets surface; `.gitignore` enforcement is a hard-stop.** Anything writing to `.env.local` must first ensure `.gitignore` matches it. If enforcement fails (OS error, permission), abort the write — never stage secrets in a repo where the ignore rule could not be locked in. Implementations should return an explicit `{action: "skipped", reason: "gitignore_enforcement_failed"}` so the caller can surface a loud handoff message rather than half-completing. See ADR-021.

---

## Imported from `CONTRIBUTING.md`

_Copied verbatim by /shipwright-adopt during onboarding. Edit in place; future adopt re-runs back this file up to `.shipwright/adopt/backups/`._

# Contributing to Shipwright

Thanks for your interest in contributing to Shipwright! This document explains how to set up your environment, the rules for code contributions, and our trust model.

> **Early Access Beta:** Shipwright is currently in Early Access. Breaking changes are possible. Please open an issue before investing significant time in a large contribution.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Before You Contribute](#before-you-contribute)
- [Development Setup](#development-setup)
- [Running Tests Locally](#running-tests-locally)
- [Running Security Scans Locally](#running-security-scans-locally)
- [Pull Request Process](#pull-request-process)
- [Commit Guidelines](#commit-guidelines)
- [Graduated Trust Model](#graduated-trust-model)
- [High-Sensitivity Areas](#high-sensitivity-areas)
- [Reporting Security Issues](#reporting-security-issues)

---

## Code of Conduct

Be kind. Be patient. Assume good intent. Critique ideas, not people. If a discussion turns hostile, take a break. The maintainer reserves the right to close issues and block users who violate this.

## Before You Contribute

**Small changes (typos, docs, tests for existing code):** Open a PR directly.

**Bug fixes:** Open an issue first or reference an existing one. This helps track context and avoid duplicate work.

**New features, refactors, or changes to skills/hooks/agents:** **Open an issue first** to discuss the approach. Shipwright has strong opinions about its architecture, and we want to save you effort by aligning upfront. PRs that modify core behavior without prior discussion may be closed.

**Changes to security scanning, prompt injection detection, or the orchestrator:** These are high-sensitivity areas. See [High-Sensitivity Areas](#high-sensitivity-areas).

## Development Setup

Follow **[docs/guide.md §2 — Prerequisites and Installation](docs/guide.md#2-prerequisites-and-installation)** for the canonical setup. It covers required tools (Claude Code, Python 3.11+, uv, Git), optional tools (`gh`, Node.js 22.x, Supabase CLI), and platform-specific notes for Windows, macOS, Linux, and WSL.

Short version for contributors who already have the base setup:

```bash
git clone https://github.com/svenroth-ai/shipwright.git ~/shipwright
cd ~/shipwright && uv sync
```

### Additional requirements for contributors

Working on a specific plugin additionally requires that plugin's own dependencies:

```bash
cd plugins/shipwright-build && uv sync
# or any other plugin under plugins/
```

Working on the **WebUI** is done in the separate
[`shipwright-webui`](https://github.com/svenroth-ai/shipwright-webui) repository
— not in this repo. See its own `CONTRIBUTING.md` for setup.

Working on **`shipwright-security`** additionally requires the OSS scanners (see [Running Security Scans Locally](#running-security-scans-locally)).

Working on **`shipwright-deploy`** additionally requires the Jelastic setup described in [docs/setup-guide-jelastic-infomaniak.md](docs/setup-guide-jelastic-infomaniak.md).

## Running Tests Locally

### Python tests

```bash
# Run all tests for one plugin
cd plugins/shipwright-security
uv run pytest tests/ -v

# Run the integration test suite
cd /path/to/shipwright
uv run pytest integration-tests/ -v
```

### Linting

```bash
# Python
uv run ruff check .

# Type-checking
uv run pyright
```

(WebUI test/lint commands live in the separate
[`shipwright-webui`](https://github.com/svenroth-ai/shipwright-webui) repo.)

## Running Security Scans Locally

Shipwright uses its own `shipwright-security` plugin to scan every contribution. You can (and should) run the same scans locally before pushing:

### Install OSS scanners (one-time)

```bash
# macOS
brew install semgrep trivy gitleaks

# Linux
pip install semgrep
# trivy: https://aquasecurity.github.io/trivy-repo/deb/
# gitleaks: https://github.com/gitleaks/gitleaks/releases

# Windows
pip install semgrep
winget install AquaSecurity.Trivy
winget install Gitleaks.Gitleaks
```

### Run the scans

```bash
# Semgrep + Trivy + Gitleaks
uv run plugins/shipwright-security/scripts/tools/scan.py \
  --path . --output /tmp/findings.json

# Shipwright Prompt Injection Scanner (custom)
uv run plugins/shipwright-security/scripts/tools/prompt_injection_scan.py \
  --full --path . --output /tmp/prompt_risks.json

# Combined Markdown report
uv run plugins/shipwright-security/scripts/tools/generate_security_report.py \
  --input /tmp/findings.json \
  --prompt-risks /tmp/prompt_risks.json \
  --output /tmp/security_report.md
```

Fix anything flagged as `critical` or `high` before submitting your PR. `medium` and `low` findings are reviewed during merge.

## Pull Request Process

1. Fork the repository and create a feature branch from `main`:
   ```bash
   git checkout -b fix/descriptive-name
   ```
2. Make your changes with clear, atomic commits (see [Commit Guidelines](#commit-guidelines)).
3. Add or update tests for any code changes.
4. Run tests and security scans locally.
5. Push to your fork and open a PR against `main`.
6. Fill out the PR template completely — the checklist is there for a reason.
7. Wait for automated checks (CI, security scan) to complete.
8. Address review comments and iterate.

**Automated checks your PR must pass:**
- Unit tests (Python + TypeScript)
- Type checks (pyright, tsc)
- Linting (ruff, oxlint)
- `shipwright-security` scan (Semgrep + Trivy + Gitleaks + Prompt Injection Scanner)
- CodeQL analysis

## Commit Guidelines

### Conventional Commits

All commits must follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`, `ci`, `build`

**Examples:**
```
feat(shipwright-build): add retry loop for flaky tests
fix(security): resolve false-positive in prompt injection scanner
docs(contributing): explain graduated trust model
test(security): add fixture for typosquatting detection
```

### DCO Sign-off

All commits must be signed off with the [Developer Certificate of Origin](https://developercertificate.org/). Add the `-s` flag to your commit:

```bash
git commit -s -m "feat(scope): your message"
```

This adds a `Signed-off-by:` line confirming you have the right to contribute the code.

### Signed Commits (GPG/SSH)

Signing commits with GPG or SSH keys is **strongly encouraged**. For the main branch, signed commits will eventually become required.

## Graduated Trust Model

Shipwright uses a graduated trust model to balance openness with security. Different levels of access unlock different types of contributions:

### Level 1 — First-time contributor

**You can contribute:**
- Typos and grammar in docs
- Clarifications in comments
- Tests for existing code
- Examples in `references/` folders
- Bug reports and reproduction cases

**You cannot yet contribute:**
- Changes to skills, hooks, or agents
- New scripts or refactors of existing ones
- New dependencies
- CI/workflow changes

### Level 2 — Established contributor

After 3+ merged PRs with no security concerns:

**Additionally, you can contribute:**
- Bug fixes in scripts (`plugins/*/scripts/`)
- New test fixtures
- Documentation expansions
- Performance improvements with benchmarks

**Still require pre-discussion:**
- Changes to skills, hooks, or agents (must have an issue first)
- New dependencies (must be justified in an issue)

### Level 3 — Trusted contributor

By invitation only, for contributors who have demonstrated consistent quality and alignment with the project's direction.

**Additionally, you can contribute:**
- New skills, hooks, or agents (after design discussion)
- Architecture changes with maintainer approval
- Direct reviews from the maintainer

There is no formal promotion process — the maintainer simply starts treating your PRs with less scrutiny once you've proven yourself.

## High-Sensitivity Areas

These parts of the codebase require extra care and will be reviewed more strictly:

| Path | Why |
|------|-----|
| `plugins/*/hooks/` | Hooks run shell commands — malicious changes could compromise any user's machine |
| `plugins/*/skills/` | Skill definitions are Claude instructions — prompt injection risks |
| `plugins/*/agents/` | Agent definitions share risks with skills |
| `plugins/shipwright-security/` | The security scanner itself — must remain trustworthy |
| `plugins/shipwright-run/` | The orchestrator controls the entire pipeline |
| `.github/workflows/` | CI/CD — could be abused to leak secrets or compromise releases |
| `shared/` | Shared code affects every plugin |

**Rules for high-sensitivity changes:**
- Must have a prior GitHub issue with design discussion
- Must be reviewed by the maintainer (no auto-merge)
- Must include tests covering the security-relevant behavior
- Cannot introduce new external dependencies without justification
- Cannot add shell commands, `eval()`, `exec()`, or similar dynamic execution

## Reporting Security Issues

**Do not file public issues for security vulnerabilities.** See [SECURITY.md](SECURITY.md) for the disclosure process.

---

Thanks for contributing! If anything in this guide is unclear, please open an issue with the `docs` label.

## Convention Updates

- **ADR-017** (2026-05-02): Repo cleanup post self-adoption: webui drift, legacy plans, FR populate

- **ADR-018** (2026-05-02): Adopt plugin: drift detection, test-fixture filter, compliance fallback fix

- **ADR-019** (2026-05-02): Hook installer writes canonical matcher-group shape

- **ADR-020** (2026-05-03): Quote uv-run path placeholders + upgrade legacy hook entries (Shape + command) in place

- **ADR-021** (2026-05-03): Adopt scaffolds .env.local with profile + framework keys (Layer-3 SSoT)

- **ADR-022** (2026-05-03): Quote ${CLAUDE_PLUGIN_ROOT} in plugins/*/hooks/hooks.json
