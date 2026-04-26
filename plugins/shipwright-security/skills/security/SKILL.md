---
name: shipwright-security
description: Security scanning with automated remediation. Supports two backends — OSS (Semgrep + Trivy + Gitleaks, local) or Aikido (cloud SaaS). Findings flow back to the coding agent for fixes. Use after /shipwright-build or standalone. Trigger: 'security scan', 'aikido', 'semgrep', 'vulnerabilities'.
license: MIT
compatibility: Requires uv (Python 3.11+). OSS backend needs semgrep/trivy/gitleaks on PATH. Aikido backend needs API credentials.
---

# Shipwright Security Skill

Security scanning with automated remediation. Pluggable scanner backend:
- **OSS** (default): Semgrep (SAST) + Trivy (SCA) + Gitleaks (Secrets) — local, free
- **Aikido**: Cloud SaaS with SAST, SCA, secrets, IaC scanning

---

## CRITICAL: First Actions

**Governing rules:** Read and follow `shared/constitution.md` (ALWAYS / ASK FIRST / NEVER boundaries).

### A. Print Intro Banner

```
================================================================================
SHIPWRIGHT-SECURITY: Security Scanner
================================================================================
Scans projects for vulnerabilities with automated remediation.
Backends: OSS (Semgrep + Trivy + Gitleaks) or Aikido (cloud SaaS).

Usage: /shipwright-security
   or: /shipwright-security issues --repo owner/repo     (Aikido only)
   or: /shipwright-security summary                      (Aikido only)
   or: /shipwright-security report --repo owner/repo     (Aikido only)
   or: Invoked by /shipwright-run (orchestrator)

Modes:
  Pipeline mode: Inside Shipwright project → full remediation loop
  Standalone mode: Any project → scan + report
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

### C. Select Scanner Backend

**Resolution order:**
1. `SHIPWRIGHT_SCANNER_BACKEND` env var (`oss` or `aikido`)
2. Profile `testing.security.provider` field
3. Auto-detect:
   - `AIKIDO_CLIENT_ID` set → Aikido backend
   - `semgrep` / `trivy` / `gitleaks` on PATH → OSS backend
   - Neither → show setup instructions and stop

Print detected backend:
```
Backend: OSS (Semgrep + Trivy + Gitleaks)
Available: SAST ✓  SCA ✓  Secrets ✓
```

Or for Aikido:
```
Backend: Aikido (Cloud SaaS)
Available: SAST ✓  SCA ✓  Secrets ✓  IaC ✓
```

See `references/oss-scanners.md` for OSS tool installation.
See `references/setup-guide.md` for Aikido setup.

### D. Check Prerequisites

Run: `uv run {plugin_root}/scripts/checks/validate_security.py`

If prerequisites missing → print setup instructions and stop.

---

## Step 0: Phase Session Context Recovery

If your context contains a `=== SHIPWRIGHT-PIPELINE-CONTEXT ===` block (injected
by the SessionStart hook), you are part of an active `/shipwright-run` pipeline.
Parse `phaseTaskId` from that block and run as your very first action:

```bash
uv run ${SHIPWRIGHT_PLUGIN_ROOT}/../../shared/scripts/tools/get_phase_context.py \
  --phase-task-id <phaseTaskId-from-context>
```

The tool prints structured JSON with `runId`, `phase`, `splitId`, `prerequisites`,
`runConditions`, and a `skill_artifacts_to_read` list. Read those artifacts
before proceeding so this phase session has full context for what came before.

If NO `PIPELINE-CONTEXT` block is present, this is a standalone invocation —
continue with Step 1 below as normal.

---

## Step 1: Run Security Scan

**For OSS backend:**

The OSS backend runs available tools via subprocess and normalizes the output.
Use the scanner_backend API:

```python
# In the plugin's Python scripts:
from scanner_backend import get_backend
backend = get_backend()
findings = backend.scan(target_dir)
```

Each tool runs with default path exclusions (`.venv`, `node_modules`, `.git`,
`.pytest_cache`, `dist`, `build`, `.next`, `__pycache__`, `.cache`) to avoid
timeouts and third-party noise. Extend via `SHIPWRIGHT_SCAN_EXCLUDES` — see
`references/oss-scanners.md` for the full exclusion contract and validation
rules.

- Semgrep: `semgrep scan --json --config auto --exclude <each-default> {target}`
- Trivy: `trivy fs --format json --scanners vuln --skip-dirs <each-default> {target}`
- Gitleaks: `gitleaks detect --report-format json -s {target} --report-path - --config <temp-toml-with-allowlist>`

**For Aikido backend:**

Run the aikido_client script:
```bash
uv run --project {plugin_root} {plugin_root}/scripts/lib/aikido_client.py issues --repo {repo} --severity critical,high,medium
```

Parse the JSON response. If `success: false`, show the error and follow alternatives.

**Both backends** return findings in the same normalized schema.

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

**For OSS backend (standalone or pipeline):**

Run the wrapper. It handles scan + redaction + report + history archiving + best-effort `.gitignore`:

```bash
uv run {plugin_root}/scripts/tools/run_scan_and_report.py --project-root {project_root} --repo {repo}
```

Output:
- `{project_root}/.shipwright/securityreports/latest.md` — human-readable Markdown report
- `{project_root}/.shipwright/securityreports/latest.json` — machine-readable sidecar (`schema_version: 1`, `scan_id`, full normalized findings)
- `{project_root}/.shipwright/securityreports/history/scan-YYYYMMDD-HHMMSS-{6hex}.{md,json}` — archived (last 20 pairs retained)
- `{project_root}/.gitignore` — `/.shipwright/` appended if file exists and entry missing (legacy `/securityreports/` recognised as already-present so we don't double-write during migration)

The wrapper redacts secret evidence by default (Gitleaks `match`/`secret`/`commit`/`author`/`email` fields; high-entropy strings in `description` / `remediation_hint`). Use `--full-evidence` to retain raw values for explicit local debugging — refused when `CI` env is set.

After the wrapper exits, read `{project_root}/.shipwright/securityreports/latest.json` for the structured scan summary (total_findings, by_severity, by_source, risk_level).

**Migration note:** projects from before this iterate may have a `securityreports/` directory at project root. The wrapper detects it and emits a one-time stderr notice on the first run pointing at the new location; the old folder is gitignored, stale, and safe to delete (or `git mv securityreports .shipwright/` if you want to preserve archived scans).

**For Aikido backend (path preserved, untouched by v0.3 restructuring):**
```bash
uv run --project {plugin_root} {plugin_root}/scripts/lib/aikido_client.py report --repo {repo}
```

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

## Step 8: Iterate Handoff (OSS standalone mode only)

After Step 6 completes for the OSS backend in standalone mode, offer the user a one-question handoff into `/shipwright-iterate` so they can work through fixes.

**Skip Step 8 entirely if any of:**
- `total_findings == 0` in `.shipwright/securityreports/latest.json`
- `os.environ.get("CI")` is set (any truthy value)
- `os.environ.get("SHIPWRIGHT_NON_INTERACTIVE")` is set
- `sys.stdin.isatty()` returns False
- Pipeline mode is active (`shipwright_project_config.json` exists in project root) — the remediation loop in Steps 2-5 already handled it

**Pre-flight check:** verify `shipwright_run_config.json` exists in `project_root`.
- If missing → print: `"To fix these findings, open /shipwright-iterate in a Shipwright-managed project and point it at .shipwright/securityreports/latest.md"`, then exit 0.
- If present → proceed.

**Ask the user via AskUserQuestion:**

> Scan complete: {total_findings} findings ({by_severity summary}).
> Start an iterate to work through fixes?
>
> - **YES** — start `/shipwright-iterate` (the report path is passed as context)
> - **NO** — done, just the report

**On YES:** invoke the `/shipwright-iterate` skill with this generic brief (no scanner prose interpolated, no prompt-injection surface):

> Review and fix security findings from the most recent scan.
> Report: `.shipwright/securityreports/latest.md` (machine-readable sidecar: `.shipwright/securityreports/latest.json`).
> Work through findings with the user — pick what to fix, what to suppress, what to defer. Favor small iterate scopes (one rule-family or one fix category per iterate) to keep review tight.

**Failure handling:** if the `/shipwright-iterate` invocation raises or exits non-zero, print the same brief verbatim to the terminal, log the error to stderr, and exit 0. The report (`.shipwright/securityreports/latest.*`) remains written regardless of handoff success.

---

## Standalone Mode Commands

When used outside a Shipwright pipeline, these commands work directly:

### `issues` — List Issues
```bash
uv run --project {plugin_root} {plugin_root}/scripts/lib/aikido_client.py issues [--repo owner/repo] [--severity critical,high] [--status open] [--type sast]
```
Format output as Markdown table.

### `repos` — List Connected Repos
```bash
uv run --project {plugin_root} {plugin_root}/scripts/lib/aikido_client.py repos
```
Format as bulleted list.

### `summary` — Dashboard
```bash
uv run --project {plugin_root} {plugin_root}/scripts/lib/aikido_client.py summary [--repo owner/repo]
```
Format as ASCII dashboard with severity bars.

### `report` — Generate Report
```bash
uv run --project {plugin_root} {plugin_root}/scripts/lib/aikido_client.py report --repo owner/repo [--output path.md]
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

## Backend Details

### Aikido (Cloud SaaS)
- **Base URL:** `https://app.aikido.dev/api`
- **Auth:** OAuth 2.0 Client Credentials → `POST /oauth/token`
- **Issues:** `GET /issues/export` with filter params
- **Repos:** `GET /code-repos`
- **Docs:** See `references/aikido-api.md`

### OSS (Local CLI Tools)
- **Semgrep:** SAST scanner, auto-updating rules
- **Trivy:** SCA scanner, auto-updating vulnerability DB
- **Gitleaks:** Secrets detector
- **Docs:** See `references/oss-scanners.md`
