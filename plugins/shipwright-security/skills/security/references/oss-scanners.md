# OSS Security Scanners — Setup Guide

The OSS backend uses three open-source CLI tools for local security scanning.
Each tool is optional — install at least one to enable the OSS backend.

## Quick Start

| Tool | Scan Type | What It Finds |
|------|-----------|---------------|
| **Semgrep** | SAST | Code vulnerabilities (XSS, SQL injection, hardcoded credentials, ...) |
| **Trivy** | SCA | Vulnerable dependencies (known CVEs in npm, pip, go, ...) |
| **Gitleaks** | Secrets | Leaked API keys, tokens, passwords in source code |

## Installation

### Semgrep (SAST)

**macOS:**
```bash
brew install semgrep
```

**Windows:**
```bash
pip install semgrep
```

**Verify:**
```bash
semgrep --version
```

Semgrep auto-updates its **rules** on every scan (`--config auto`), so scan results stay current even if the binary version is not the latest.

### Trivy (SCA)

**macOS:**
```bash
brew install trivy
```

**Windows:**
```bash
winget install AquaSecurity.Trivy
```

**Download (fallback):** https://github.com/aquasecurity/trivy/releases

**Verify:**
```bash
trivy --version
```

Trivy auto-updates its **vulnerability database** on every scan, so scan results stay current.

### Gitleaks (Secrets)

**macOS:**
```bash
brew install gitleaks
```

**Windows:**
```bash
winget install Gitleaks.Gitleaks
```

**Download (fallback):** https://github.com/gitleaks/gitleaks/releases

**Verify:**
```bash
gitleaks version
```

## How Shipwright Uses These Tools

When `/shipwright-security` runs with the OSS backend:

1. **Detection:** Checks which tools are on PATH
2. **Scan:** Runs each available tool against the project directory
3. **Normalize:** Converts tool-specific JSON output to the standard finding schema
4. **Classify:** Each finding is classified as auto-fixable, agent-fixable, needs-review, or informational
5. **Remediate:** Same pipeline as Aikido — auto-fix dependencies, agent-fix code issues, user review for the rest

### CLI Commands Used

```bash
# Semgrep (SAST) — no plugin --exclude flags by default (see below)
semgrep scan --json --config auto {target_dir}

# Trivy (SCA) — --skip-dirs repeated per directory name
trivy fs --format json --scanners vuln --skip-dirs .venv --skip-dirs node_modules ... {target_dir}

# Gitleaks (Secrets) — detect mode + temp TOML config with [allowlist] paths.
# The report goes to a temp FILE that the plugin reads back: gitleaks has no
# stdout-report mode — `--report-path -` writes a literal file named `-`, not
# stdout (gitleaks report.Write → os.Create), so the plugin must read the file.
gitleaks detect --report-format json -s {target_dir} --report-path {temp_json_report} --config {generated_toml}
```

## Coverage manifest — what was NOT checked

A tool that **crashes** was always surfaced: it records a `scan_errors` marker,
`findings.json` gets `degraded: true`, and the run fails closed. A tool that was
**never installed** used to be invisible — the backend simply skipped its class,
so a machine with only Semgrep produced a report that read clean for vulnerable
dependencies and leaked secrets alike.

Every scan now writes a `coverage` array into `findings.json` and the
`latest.json` sidecar — one row per weakness class:

```json
{"class": "secrets", "tool": "gitleaks", "status": "not_available",
 "detail": "gitleaks is not installed on this machine"}
```

`status` comes from a closed vocabulary:

| Status | Meaning |
|---|---|
| `covered` | scanned to completion; findings for this class are trustworthy |
| `degraded` | the tool ran but its result cannot be trusted — no parseable output (also in `scan_errors`; fails the run) |
| `not_requested` | the caller excluded the class via `--scan-types` |
| `not_available` | the check could not run here — locally, the tool is not on PATH |

The vocabulary is CLOSED, and a manifest read back from a file is coerced into
it: a row whose status is absent or unrecognized becomes `degraded` with the
original recorded in `detail`. These rows get re-emitted (`scan.py
--input-from-cache` writes a fresh `findings.json` from them), so an invalid
status must never be laundered into a new artifact that a CI `jq` gate or the
WebUI is entitled to treat as well-formed.

An **empty or absent** manifest means "coverage was not reported", never
"everything was covered": the report renders *Coverage not reported* rather than
a clean pass. That state is deliberately distinct from *Incomplete Coverage* (a
manifest that exists and names a gap) — which is why nothing synthesizes a row
onto an empty manifest just to have one.

The manifest is derived from `(capabilities, scan_types, scan_errors)` by
`scan_coverage.build_coverage()` — a pure function, not a channel each backend
populates, so no backend or test mock can forget to report it. A class a backend
offers that has no local tool (Aikido's `iac`) still gets a row, with
`tool: null`. The prompt-injection scan gets one too: it cannot be "missing", but
omitting the class from a report reads as clean, so it is named either way — and
only when its output was actually READ, not merely because `--prompt-risks` was
passed.

**The manifest is untrusted on the way back in.** `--input` and
`--input-from-cache` both take it from a caller-supplied file, and its labels
reach a Markdown report AND (in a later change) a triage payload an agent
executes. `coverage_sanitize` normalizes it at the boundary; `class_label` is the
single chokepoint that renders it.

## Scanner-Exclusion Contract

The plugin no longer maintains a single global exclusion list. Each scanner
gets the minimum set it cannot resolve from its own ignore file or from the
project `.gitignore`. The single source of truth for "what should be scanned"
is the project gitignore — for the tools that natively support it.

### Truth table — what each scanner does with `.gitignore` and plugin excludes

| Scanner | Respects `.gitignore`? | Built-in ignores? | Plugin list | What this means |
|---------|------------------------|-------------------|-------------|-----------------|
| **Semgrep** | Yes (untracked files) + supports `.semgrepignore` | Yes — `.semgrepignore` covers `node_modules`, `build`, `dist`, `vendor`, `.venv`, `.tox`, `.npm`, `.yarn` etc. | **Empty** | Project `.gitignore` is the SSoT. Plugin adds nothing by default. |
| **Trivy** | No | None (manifest-only by design) | Conservative cross-language list | Plugin keeps a minimum set since Trivy crawls every directory otherwise. |
| **Gitleaks** | No (in `detect` mode it scans git history) | None | Same as Trivy, applied as TOML `[allowlist] paths` | Detect-mode covers history — historical secrets that were committed and later removed are still found. |

### Trivy / Gitleaks plugin defaults

These segment names are skipped by Trivy and Gitleaks at any depth:

```
# Python
.venv  .pytest_cache  .mypy_cache  .ruff_cache  .tox  __pycache__
# JS/TS
node_modules  .next
# VCS + generic caches
.git  .cache
# Generic build outputs
dist  build
# Polyglot build/dependency dirs
target   bin   obj   vendor   .gradle   .terraform   .direnv
# Coverage outputs
coverage  htmlcov
# Shipwright parallel-iterate worktrees (gitignored at project level,
# but neither tool honors .gitignore)
.worktrees
```

`.shipwright/` is **not** in this list — projects opt into scanning their
agent_docs / specs / ADRs by tracking them in git, opt out by gitignoring
them or by adding `.shipwright` to `SHIPWRIGHT_SCAN_EXCLUDES`. See "Migration
notice" below.

### Migration notice — `.shipwright/` is now scanned

Before Sub-Iterate H (v0.10+), the plugin maintained a single
`_DEFAULT_EXCLUDES` list that **silently skipped** the entire `.shipwright/`
tree, including `.shipwright/agent_docs/` (decision_log.md, conventions.md,
session_handoff.md, etc.). Projects that took artifacts out of gitignore in
the hope of getting them scanned would still find them silently skipped.

The new contract:

- **Semgrep** respects your `.gitignore`. Whatever your project gitignores
  is what Semgrep skips for untracked files. For tracked files use
  `--no-git-ignore` semantics natively.
- **Trivy** and **Gitleaks** do NOT read `.gitignore`. To exclude a
  directory from those scanners, either add it to the plugin list (PR) or
  set `SHIPWRIGHT_SCAN_EXCLUDES` (per-environment).

What this means for `.shipwright/`:

| Your `.gitignore` says | Semgrep | Trivy | Gitleaks (`detect`) |
|------------------------|---------|-------|---------------------|
| `/.shipwright/` (default for new projects) | skips (untracked) | scans (no manifests inside → no findings) | skips (gitignored = never in history) |
| `.shipwright/` removed; `agent_docs/` tracked | scans agent_docs | scans agent_docs (markdown → no SCA findings) | scans history once committed |

**Recommendation:** if you start tracking `.shipwright/agent_docs/`, keep
`.shipwright/securityreports/` separately gitignored — those reports often
quote vulnerability descriptions verbatim, which can re-trigger Gitleaks
patterns on subsequent scans.

> **Scope note:** The snippet below is a `.gitignore` change. It controls
> what gets committed and what Semgrep walks into (Semgrep respects
> `.gitignore` for untracked files). It does **not** affect Trivy or
> Gitleaks — those tools ignore `.gitignore` natively, and their
> directory-level skips are governed by the plugin defaults plus
> `SHIPWRIGHT_SCAN_EXCLUDES`. The snippet works for our use case because
> uncommitted reports are invisible to Gitleaks `detect` (history-only)
> and Trivy `--scanners vuln` finds nothing in our markdown/JSON
> reports — but if you ever commit reports or extend Trivy with
> `--scanners misconfig`, you must also add `securityreports` to
> `SHIPWRIGHT_SCAN_EXCLUDES`.

The default Shipwright gitignore line is `.shipwright/` (whole tree ignored).
git can't re-include a child once the parent directory is fully ignored, so
to track `agent_docs/` while keeping reports ignored, replace the directory-
level ignore with a contents-level one:

```gitignore
# Default: ignore everything in .shipwright/ ...
.shipwright/*

# ... but track agent_docs so the security scanner can analyze it.
!.shipwright/agent_docs/

# Scan outputs stay ignored — they round-trip through Gitleaks otherwise.
.shipwright/securityreports/
```

### Extending the Defaults

Add project-specific folders via `SHIPWRIGHT_SCAN_EXCLUDES` — comma-separated
list of simple folder names. The env var extends every scanner uniformly:

```bash
export SHIPWRIGHT_SCAN_EXCLUDES=generated,.shipwright
```

**The env var extends, never replaces.** Plugin defaults are always active;
your entries are appended. An environment-controlled full replacement would
let a CI-config edit weaken the scan by excluding real source directories.

**Validation:** entries must be simple folder names (`[A-Za-z0-9_.-]+`).
Glob wildcards (`*`, `**`), path separators (`/`, `\`), and parent traversal
(`.`, `..`) are rejected with a stderr warning and dropped. Use per-project
`.gitleaksignore` / Semgrep rule exclusions for finer-grained patterns.

### Known edge cases

- **Symlinks**: Trivy and Gitleaks follow symlinks by default. Plugin
  excludes match on segment name, not target — a symlinked
  `node_modules` is still skipped, but a symlink pointing into a scanned
  directory is followed.
- **Nested gitignore**: Semgrep respects nested `.gitignore` files. Trivy
  and Gitleaks do not — every scanner-relevant exclude must be in the
  plugin list or env var, regardless of where it sits.
- **Tracked files in gitignored paths**: A tracked file that lives under a
  gitignored path is still scanned by Semgrep (it follows git tracking
  state, not pure gitignore rules). Trivy and Gitleaks see the tree as-is.

## Backend Selection

The OSS backend is auto-detected when no Aikido credentials are configured.
To force a specific backend:

```bash
# Force OSS backend (even if Aikido credentials exist)
export SHIPWRIGHT_SCANNER_BACKEND=oss

# Force Aikido backend
export SHIPWRIGHT_SCANNER_BACKEND=aikido
```

Or set it in the project profile (`shared/profiles/*.json`):
```json
"security": {
    "provider": "oss",
    "scope": ["sast", "sca", "secret-detection"]
}
```
