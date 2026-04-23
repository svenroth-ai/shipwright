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

Each scanner is invoked with a default exclusion list (see below):

```bash
# Semgrep (SAST) — --exclude repeated per directory name
semgrep scan --json --config auto --exclude .venv --exclude node_modules ... {target_dir}

# Trivy (SCA) — --skip-dirs repeated per directory name
trivy fs --format json --scanners vuln --skip-dirs .venv --skip-dirs node_modules ... {target_dir}

# Gitleaks (Secrets) — reads a temp TOML config with [allowlist] paths
gitleaks detect --report-format json -s {target_dir} --report-path - --config {generated_toml}
```

## Default Exclusions

Third-party trees, build artifacts, and caches are always skipped. Without
this, Semgrep times out on `node_modules`/`.venv` and produces noise about
code that isn't yours.

Always-excluded folder names (matched as path segments at any depth):

```
.venv          node_modules   .git           .pytest_cache
dist           build          .next          __pycache__
.cache
```

### Extending the Defaults

Add project-specific folders via `SHIPWRIGHT_SCAN_EXCLUDES` — comma-separated
list of simple folder names:

```bash
export SHIPWRIGHT_SCAN_EXCLUDES=vendor,generated,.terraform
```

**The env var extends, never replaces.** The defaults above are always active;
your entries are appended. This is deliberate — an environment-controlled
full replacement would let a CI-config edit weaken the scan by excluding real
source directories.

**Validation:** entries must be simple folder names (`[A-Za-z0-9_.-]+`).
Glob wildcards (`*`, `**`), path separators (`/`, `\`), and parent traversal
(`.`, `..`) are rejected with a stderr warning and dropped. Use per-project
`.gitleaksignore` / Semgrep rule exclusions for finer-grained patterns.

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
