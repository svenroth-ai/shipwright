---
name: shipwright-security
description: Security scanning via Aikido API with automated remediation. Scans connected GitHub repos for vulnerabilities (SAST, SCA, secrets). Findings flow back to the coding agent for fixes. Use after /shipwright-build or standalone for any Aikido-connected repo. Trigger: 'security scan', 'aikido', 'vulnerabilities', 'Sicherheitsscan', 'Schwachstellen'.
license: MIT
compatibility: Requires uv (Python 3.11+), requests. Aikido account required.
---

# Shipwright Security Skill

Security scanning with automated remediation via Aikido Security API.

---

## CRITICAL: First Actions

### A. Print Intro Banner

```
================================================================================
SHIPWRIGHT-SECURITY: Aikido Security Scanner
================================================================================
Scans GitHub repos for vulnerabilities via Aikido Security API.
Findings flow back to the agent for automated remediation.

Usage: /shipwright-security
   or: /shipwright-security issues --repo owner/repo
   or: /shipwright-security summary
   or: /shipwright-security report --repo owner/repo
   or: Invoked by /shipwright-run (orchestrator)

Modes:
  Pipeline mode: Inside Shipwright project → full remediation loop
  Standalone mode: Any Aikido-connected repo → scan + report
================================================================================
```

### B. Detect Mode

Check if `shipwright_project_config.json` exists in the project root:
- **Exists** → Pipeline mode (full remediation loop with security-fixer)
- **Does not exist** → Standalone mode (scan + report only)

If Pipeline mode, read profile:
```json
{
  "profile": "supabase-nextjs",
  ...
}
```
Load profile from `{plugin_root}/../../shared/profiles/{profile}.json`.

### C. Check Credentials

Run: `uv run {plugin_root}/scripts/checks/validate_security.py`

If credentials missing → print setup instructions and stop.

---

## Step 1: Fetch Issues from Aikido

Run the aikido_client script:
```bash
uv run {plugin_root}/scripts/lib/aikido_client.py issues --repo {repo} --severity critical,high,medium
```

Parse the JSON response. If `success: false`, show the error and follow alternatives.

Present findings as a table:

| # | Severity | Type | Rule | File | Line |
|---|----------|------|------|------|------|
| 1 | high | sast | hardcoded-credentials | scripts/api.py | 42 |
| 2 | critical | sca | CVE-2024-1234 | package.json | — |

---

## Step 2: Classify Findings (Pipeline Mode Only)

Each finding is automatically classified by `aikido_client.py`:

| Class | Examples | Action |
|-------|----------|--------|
| `auto-fixable` | Dependency update, known CVE with patch | Agent fixes directly |
| `agent-fixable` | Hardcoded credentials, XSS, missing sanitization | `security-fixer` subagent |
| `needs-review` | Architecture issues, business logic flaws | User interview |
| `informational` | Low-severity, best practices | Log only |

Show classification summary:
```
Findings: 12 total
  auto-fixable:    3  (will fix automatically)
  agent-fixable:   4  (security-fixer subagent)
  needs-review:    2  (will ask you)
  informational:   3  (logged only)
```

---

## Step 3: Auto-Fix (Pipeline Mode Only)

For each `auto-fixable` finding:

1. Identify the fix (e.g., update dependency version in package.json)
2. Apply the fix
3. Re-run relevant tests
4. If tests pass → mark finding as `fixed`
5. If tests fail after 3 attempts → escalate to user

**Max 3 retries per finding.**

---

## Step 4: Agent-Fix via security-fixer (Pipeline Mode Only)

For each `agent-fixable` finding, invoke the `security-fixer` subagent:

```
Agent: security-fixer
Input: {
  "severity": "high",
  "type": "sast",
  "rule": "python.lang.security.hardcoded-credentials",
  "cwe": "CWE-798",
  "file": "scripts/api.py",
  "line": 42,
  "description": "Hardcoded API key",
  "remediation_hint": "Move to environment variable"
}
```

Process the subagent's response:
- If `fix_description` is not null → apply fix, re-run tests
- If `escalation_reason` → move to `needs-review` category
- **Max 3 retries per finding.**

---

## Step 5: User Interview (Pipeline Mode Only)

For each `needs-review` finding, present to user via AskUserQuestion:

**Question:** "Security finding: {severity} — {rule} in {file}:{line}"

**Options:**
- **Fix** — Agent attempts to fix this finding
- **Decline** — Skip this finding (log reason)
- **Defer** — Add TODO comment, fix later

For accepted findings → run security-fixer subagent → re-run tests.

---

## Step 6: Generate Report

Run the report generator:
```bash
uv run {plugin_root}/scripts/lib/aikido_client.py report --repo {repo}
```

Write a Markdown report to the project root using the suggested filename.

**Report contents:**
- Summary: total findings, severity breakdown
- Remediation status: fixed / declined / deferred / open
- Detailed findings table
- Timestamp

---

## Step 7: Persist Results (Pipeline Mode Only)

Write results to `shipwright_security_config.json` in the project root:

```json
{
  "scan_date": "2026-03-26T10:00:00Z",
  "repo": "svenroth-ai/claude-skills",
  "scanner": "aikido",
  "total_findings": 12,
  "by_severity": {"critical": 1, "high": 3, "medium": 5, "low": 3},
  "remediation": {
    "fixed": 5,
    "declined": 1,
    "deferred": 2,
    "open": 4
  },
  "findings": [...],
  "session_id": "..."
}
```

This config is consumed by `/shipwright-compliance` for traceability.

---

## Standalone Mode Commands

When used outside a Shipwright pipeline, these commands work directly:

### `issues` — List Issues
```bash
uv run {plugin_root}/scripts/lib/aikido_client.py issues [--repo owner/repo] [--severity critical,high] [--status open] [--type sast]
```
Format output as Markdown table.

### `repos` — List Connected Repos
```bash
uv run {plugin_root}/scripts/lib/aikido_client.py repos
```
Format as bulleted list.

### `summary` — Dashboard
```bash
uv run {plugin_root}/scripts/lib/aikido_client.py summary [--repo owner/repo]
```
Format as ASCII dashboard with severity bars.

### `report` — Generate Report
```bash
uv run {plugin_root}/scripts/lib/aikido_client.py report --repo owner/repo [--output path.md]
```
Write Markdown report to working directory.

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `credentials not configured` | Missing .env | Create API credentials at Aikido |
| `401 Unauthorized` | Invalid credentials | Regenerate API credentials |
| `403 Forbidden` | Insufficient API scope | Check API permissions |
| `429 Too Many Requests` | Rate limit | Wait and retry |
| `No repos found` | GitHub not connected | Connect GitHub in Aikido settings |
| `No issues found` | Clean scan or filters too narrow | Try without filters |

---

## API Details

- **Base URL:** `https://app.aikido.dev/api`
- **Auth:** OAuth 2.0 Client Credentials → `POST /oauth/token`
- **Issues:** `GET /issues/export` with filter params
- **Repos:** `GET /code-repos`
- **Docs:** See `references/aikido-api.md`
