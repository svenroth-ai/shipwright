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
# Semgrep (SAST)
semgrep scan --json --config auto {target_dir}

# Trivy (SCA)
trivy fs --format json --scanners vuln {target_dir}

# Gitleaks (Secrets)
gitleaks detect --report-format json -s {target_dir} --report-path -
```

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
