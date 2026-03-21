---
name: deploy
description: Deploy to Jelastic (Infomaniak) with smoke test verification, rollback support, and Supabase migrations. Use after /shipwright-build and /shipwright-test.
license: MIT
compatibility: Requires uv (Python 3.11+), JELASTIC_TOKEN env var, optionally Supabase CLI
---

# Shipwright Deploy Skill

Deploys to Jelastic (Infomaniak) with smoke tests and rollback.

---

## CRITICAL: First Actions

### A. Print Intro Banner

```
================================================================================
SHIPWRIGHT-DEPLOY: Deployment
================================================================================
Deploys to Jelastic Cloud (Infomaniak, Switzerland).

Usage: /shipwright-deploy                (DEV, automatic)
   or: /shipwright-deploy --prod         (PROD, requires confirmation)
   or: /shipwright-deploy --rollback     (restore last PROD snapshot)
   or: Invoked by /shipwright-run (orchestrator)

Flow:
  1. Validate credentials
  2. Run Supabase migrations (if applicable)
  3. Deploy via Jelastic API
  4. Smoke test
  5. Rollback on failure

Environments:
  DEV:  dev-{project}.jpc.infomaniak.com
  PROD: {project}.jpc.infomaniak.com
================================================================================
```

### B. Validate Credentials

```bash
uv run {plugin_root}/scripts/checks/validate-deploy.py
```

Checks for:
- `JELASTIC_TOKEN` environment variable
- Optionally: `SUPABASE_ACCESS_TOKEN` (for migrations)
- Optionally: git repo with remote (for git-based deploy)

### C. Determine Target

| Flag | Target | Behavior |
|------|--------|----------|
| (none) | DEV | Automatic, no confirmation |
| `--prod` | PROD | Requires explicit user confirmation |
| `--rollback` | PROD | Restore last clone, requires confirmation |

---

## Step 1: Supabase Migrations (if applicable)

**Only runs if migration files exist** in `supabase/migrations/`.

### DEV
```bash
supabase db push --linked
```
Automatic, no confirmation needed.

### PROD
```bash
supabase db push --linked --dry-run
```
Present dry-run output to user. Require explicit confirmation before:
```bash
supabase db push --linked
```

**Destructive changes** (detected by shipwright-build hooks): always warn and require confirmation regardless of target.

---

## Step 2: Pre-Deploy Safety (PROD only)

**Goal:** Create a rollback point before deploying to PROD.

```bash
uv run {plugin_root}/scripts/lib/jelastic_client.py clone-env \
  --env-name "{prod_env}" \
  --clone-name "{prod_env}-backup"
```

This creates a full clone of the PROD environment. If deployment fails,
we can restore from this clone.

**User confirmation:**
```
AskUserQuestion:
  question: "Deploy to PRODUCTION ({prod_env}.jpc.infomaniak.com)?"
  context: "Backup clone will be created first."
  options:
    - "Deploy to PROD"
    - "Cancel"
```

---

## Step 3: Deploy

```bash
uv run {plugin_root}/scripts/lib/jelastic_client.py deploy \
  --env-name "{env_name}" \
  --branch "{branch}"
```

This calls the Jelastic VCS Update API to pull the latest code from git.

If environment doesn't exist yet: create it first via `create-env`.

---

## Step 4: Smoke Test

```bash
uv run {shared_root}/scripts/smoke_test.py \
  --url "https://{env_name}.jpc.infomaniak.com" \
  --timeout 30 \
  --health-path "/api/health"
```

Wait up to 60 seconds for the deployment to become ready (poll every 5s).

---

## Step 5: Handle Result

### Smoke Test Passed
```
================================================================================
SHIPWRIGHT-DEPLOY: SUCCESS
================================================================================
Target:     {DEV | PROD}
URL:        https://{env_name}.jpc.infomaniak.com
Status:     {status_code} ({response_time}ms)
Migrations: {applied | skipped | N/A}
================================================================================
```

### Smoke Test Failed → Rollback

**DEV:** Git-based rollback
```bash
uv run {plugin_root}/scripts/lib/rollback.py \
  --env-name "{env_name}" \
  --strategy git \
  --target-ref "{last_known_good_tag}"
```

**PROD:** Restore from clone
```bash
uv run {plugin_root}/scripts/lib/rollback.py \
  --env-name "{env_name}" \
  --strategy clone \
  --clone-name "{prod_env}-backup"
```

Log rollback in `agent_docs/decision_log.md`.

```
================================================================================
SHIPWRIGHT-DEPLOY: FAILED → ROLLED BACK
================================================================================
Target:     {DEV | PROD}
Error:      {smoke test error}
Rollback:   {git revert to {tag} | restored from clone}
Action:     Fix the issue and re-deploy
================================================================================
```

---

## Manual Rollback (`--rollback`)

When invoked with `--rollback`:
1. List available backup clones
2. Present to user for selection
3. Require explicit confirmation
4. Restore from selected clone
5. Run smoke test on restored environment

---

## Reference Documents

- [jelastic-api.md](references/jelastic-api.md) — API endpoint reference
- [deploy-flavors.md](references/deploy-flavors.md) — Flavor architecture
- [rollback-strategy.md](references/rollback-strategy.md) — DEV vs PROD rollback
