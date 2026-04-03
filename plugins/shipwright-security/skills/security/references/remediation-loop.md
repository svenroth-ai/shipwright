# Security Remediation Loop

## Overview

The remediation loop automatically fixes security findings from Aikido scans.
It follows the same patterns as shipwright-build's validation loop and code review interview.

## Finding Classification

Each finding is classified into one of four categories:

| Category | Criteria | Handling |
|----------|----------|----------|
| `auto-fixable` | SCA/dependency issues with known patches | Agent fixes directly (e.g., version bump) |
| `agent-fixable` | SAST/secret issues with clear remediation | `security-fixer` subagent analyzes + fixes |
| `needs-review` | Architecture, business logic, complex issues | User decides: Fix / Decline / Defer |
| `informational` | Low severity, best practices | Log only, no action |

### Classification Rules

```
IF severity in (low, info) → informational
ELSE IF type in (dependency, sca) → auto-fixable
ELSE IF type in (sast, secret_detection) → agent-fixable
ELSE → needs-review
```

## Retry Limits

- **Max 3 attempts** per finding with the same root cause
- After 3 failures → escalate to user
- This matches shipwright-build's validation loop pattern

## Auto-Fix Flow

```
1. Identify fix (e.g., bump lodash from 4.17.20 to 4.17.21)
2. Apply change (edit package.json / requirements.txt)
3. Run package manager (npm install / uv sync)
4. Run tests
5. If tests pass → mark as "fixed"
6. If tests fail → retry (max 3) → escalate
```

## Agent-Fix Flow (security-fixer subagent)

```
1. Send finding details to security-fixer subagent
2. Subagent reads affected file, diagnoses root cause
3. Subagent applies minimal fix
4. Re-run tests
5. If subagent returns escalation_reason → move to needs-review
6. Max 3 retries
```

## User Interview Flow

Follows shipwright-build code-review-interview pattern:

```
1. Present finding to user via AskUserQuestion
2. Options:
   - Fix: Agent attempts remediation
   - Decline: Skip with logged reason
   - Defer: Add TODO comment for later
3. Accepted findings → security-fixer subagent → tests
```

## Status Tracking

Each finding gets a `_remediation_status`:
- `open` — not yet processed
- `fixed` — successfully remediated
- `declined` — user chose to skip
- `deferred` — marked for later

Final status is written to `shipwright_security_config.json` for compliance.

## Integration with Compliance

`shipwright-compliance` reads `shipwright_security_config.json` and includes:
- Security findings in the Traceability Matrix (RTM)
- Remediation status in Test Evidence Report
- Dependency vulnerabilities in SBOM
