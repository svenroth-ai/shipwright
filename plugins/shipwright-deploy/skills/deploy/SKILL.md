---
name: shipwright-deploy
description: Deploy to Jelastic (Infomaniak) with smoke test verification, rollback support, and Supabase migrations. Use after /shipwright-build and /shipwright-test.
license: MIT
compatibility: Requires uv (Python 3.11+), JELASTIC_TOKEN env var, optionally Supabase CLI
---

# Shipwright Deploy Skill

Deploys to Jelastic (Infomaniak) with smoke tests and rollback.

---

## CRITICAL: First Actions

**Governing rules:** Read and follow `shared/constitution.md` (ALWAYS / ASK FIRST / NEVER boundaries).

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

### B2. Validate Environment

Check that required deploy environment variables from the stack profile are available.

```bash
uv run {shared_root}/scripts/validate_env.py \
  --project-root "{project_root}" \
  --phase deploy
```

Where `{shared_root}` = `{plugin_root}/../../shared` (relative to plugin root).

Parse the JSON output:

1. **`skipped == true`**: No profile or no vars defined — continue.
2. **`success == true`**: All required deploy vars present — continue.
3. **`success == false`**: Missing required vars — **use AskUserQuestion**:

   > **Missing environment variables for deployment**
   >
   > The following required variables are not set:
   > - `VAR_NAME` — description
   >
   > Please set the missing environment variables, then confirm to continue.

   Options: "I've set the variables — continue" / "Skip validation and proceed anyway"

   If user updates: **re-run validation** to confirm.
   If user skips: proceed with a warning.

4. **`optional_missing`**: Log a warning but do not block.

### B3. Verify Tests Passed (MANDATORY)

Before deploying, verify all tests passed:

1. Read `shipwright_test_results.json`
2. Check: `unit.status == "passed"` AND (`e2e.status == "passed"` OR `e2e.status == "skipped"`)
3. If tests failed or file does not exist:

```
================================================================================
SHIPWRIGHT-DEPLOY: Test Gate Failed
================================================================================

Cannot deploy — tests have not passed.
Unit: {status}  |  E2E: {status}

Run /shipwright-test first, or confirm to proceed at your own risk.
================================================================================
```

**Ask user for confirmation before proceeding.** Do NOT deploy silently with failing tests.

### C. Determine Target

| Flag | Target | Behavior |
|------|--------|----------|
| (none) | DEV | Automatic, no confirmation |
| `--prod` | PROD | Requires explicit user confirmation |
| `--rollback` | PROD | Restore last clone, requires confirmation |

---

## Step 1: Migrations (if applicable)

**Only runs if migration files exist** in the profile's `migrations.dir`.

Read `migrations` config from the stack profile.

### Prerequisites (check before running migrations)

1. **`supabase/config.toml` exists** — if not: run `npx supabase init`
2. **Project is linked** (`.supabase/` directory exists) — if not: run `npx supabase link --project-ref <ref>` (requires `SUPABASE_ACCESS_TOKEN`)
3. **`SUPABASE_ACCESS_TOKEN` is set** — if not: prompt user to create one at https://supabase.com/dashboard/account/tokens and add to `.env.local`

If any prerequisite fails: stop and inform user with specific remediation steps.

### Verify DEV migrations

DEV migrations are applied during Build/Iterate. Verify all are current:
```bash
{migrations.list_cmd}
```
If pending migrations exist:
- If `supports_idempotent_apply` is true: warn user, offer to apply them now
- If false or unknown: warn user, require explicit confirmation before applying

### PROD
```bash
{migrations.dry_run_cmd}
```
Present dry-run output to user (note: dry-run output format varies by stack — present raw output for human review). Require explicit confirmation before:
```bash
{migrations.apply_cmd}
```

**Destructive changes** (detected by shipwright-build hooks): always warn and require confirmation regardless of target.

### Post-Migration Manual Steps

Check `migrations.post_apply_manual_steps` from the stack profile. For each entry where `trigger_tag` matches a migration just applied, inform user via AskUserQuestion with the action and note. Wait for confirmation before proceeding.

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

**Record deploy event** (captures deployed URL for downstream consumers):
```bash
uv run {shared_root}/scripts/tools/record_event.py \
  --project-root "$(pwd)" \
  --type phase_completed \
  --phase deploy \
  --detail "https://{env_name}.jpc.infomaniak.com"
```
Where `{shared_root}` = `{plugin_root}/../../shared`.

**Phase complete — update pipeline state:**
```bash
# Mark deploy phase complete (triggers compliance update automatically)
uv run {plugin_root}/../../plugins/shipwright-run/scripts/lib/orchestrator.py \
  update-step --project-root "$(pwd)" --step deploy --status complete

# Update delivery dashboard
uv run {shared_root}/scripts/tools/update_build_dashboard.py \
  --project-root "$(pwd)" --phase deploy --detail "Deployed to {url}" \
  --session-id "{SHIPWRIGHT_SESSION_ID}"
```

**Reflection — Capture Deploy Learnings:**

If deployment had issues or required adjustments:
1. Infra configuration gotchas?
2. Environment-specific behavior?
3. Rollback insights?

If learnings exist:
- **Observations** → append to `agent_docs/conventions.md` under `## Learnings`
  Format: `- ({YYYY-MM-DD}) deploy — {summary}`
- **Cross-project insights** → save Claude Code feedback/project Memory
If none: skip.

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
