---
name: shipwright-deploy
description: "Deploy to Jelastic (Infomaniak) with smoke test verification, rollback support, and Supabase migrations.\nTRIGGER when: user wants to deploy, push to production, deploy to dev, deploy to staging, publish the application, rollback a deployment, or check deployment status.\nDO NOT TRIGGER when: user asks to write code (/shipwright-build), run tests (/shipwright-test), fix a bug (/shipwright-iterate), create a changelog (/shipwright-changelog), create requirements (/shipwright-project), plan implementation (/shipwright-plan), or design UI (/shipwright-design)."
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
uv run "{plugin_root}/scripts/checks/validate-deploy.py"
```

Checks for:
- `JELASTIC_TOKEN` environment variable
- Optionally: `SUPABASE_ACCESS_TOKEN` (for migrations)
- Optionally: git repo with remote (for git-based deploy)

### B2. Detect Invocation Mode

Determine if running within the pipeline or standalone:

1. Read `shipwright_run_config.json` (if exists)
2. **Pipeline mode**: `status == "in_progress"` AND `current_step == "deploy"`
   - Full pipeline integration (update orchestrator state, enforce gates)
3. **Standalone mode**: file missing OR `status == "complete"` OR `current_step != "deploy"`
   - Skip pipeline state updates (no `orchestrator.py update-step` calls)
   - Skip test gate check but warn: `"No pipeline test results found. Deploying without test verification."`
   - Still produce all artifacts (deploy logs, event log)
   - Print: `"Running in standalone mode — pipeline state will not be updated."`
4. If `status == "in_progress"` AND `current_step != "deploy"`:
   - Warn: `"Pipeline is in progress at step {current_step}. Running /shipwright-deploy out of sequence may cause issues."`
   - Ask user before continuing.

Store the detected mode in a variable `invocation_mode` = `"pipeline"` | `"standalone"` for use in later steps.

### Single-Session Gate Discipline

Under single-session pipeline mode (`run_config.mode == "single_session"`), interactive gates follow a per-gate policy — resolve via `${SHIPWRIGHT_PLUGIN_ROOT}/../../shared/scripts/tools/resolve_gate_policy.py --phase deploy --list`. PROD / destructive-migration / rollback gates stay **hard-stop** (explicit human confirmation, always, regardless of autonomy). Full contract: `shared/prompts/single-session-gate-discipline.md`.

### B3. Validate Environment

Check that required deploy environment variables from the stack profile are available.

```bash
uv run "{shared_root}/scripts/validate_env.py" \
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

### B4. Verify Tests Passed (MANDATORY)

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

## Step 0: Phase Session Context Recovery

If your context contains a `=== SHIPWRIGHT-PIPELINE-CONTEXT ===` block (injected
by the SessionStart hook), you are part of an active `/shipwright-run` pipeline.
Parse `phaseTaskId` from that block and run as your very first action:

```bash
uv run "${SHIPWRIGHT_PLUGIN_ROOT}/../../shared/scripts/tools/get_phase_context.py" \
  --phase-task-id <phaseTaskId-from-context>
```

The tool prints structured JSON with `runId`, `phase`, `splitId`, `prerequisites`,
`runConditions`, and a `skill_artifacts_to_read` list. Read those artifacts
before proceeding so this phase session has full context for what came before.
Deploy is the pipeline-terminal phase — when this session's Stop hook fires
`complete-phase-task`, the run will flip to `status="complete"`.

If NO `PIPELINE-CONTEXT` block is present, this is a standalone invocation —
continue with Step 1 below as normal.

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

### Post-Apply Verification

After `apply_cmd` succeeds, run the migration verifier against the migrations that were just applied. The verifier parses `-- VERIFY:` comments from each migration and runs them via `psql`. A failed verification triggers the same rollback path as a smoke-test failure (see Step 5 → "Smoke Test Failed → Rollback").

```bash
uv run "{plugin_root}/scripts/lib/migration_verifier.py" \
  --migration {applied_migration_path_1} \
  [--migration {applied_migration_path_N}] \
  --db-url "{prod_db_url_or_pooled_url}" \
  --output .shipwright/deploy/migration-verify.json
```

Read the JSON output. Branch on `all_passed`:
- **`true`** — proceed to "Post-Migration Manual Steps".
- **`false`** — present the failing report (per-file, per-VERIFY-statement) to the user via AskUserQuestion. Two options:
  - **Rollback now (recommended)** — fall through to Step 5's clone-restore path immediately.
  - **Override and continue** — the user must explicitly acknowledge that the verifier is reporting a real schema mismatch the deploy is choosing to ignore. **Before proceeding, write an ADR entry** to `.shipwright/agent_docs/decision_log.md` capturing: the migration file(s), the failing VERIFY statement(s), the user's stated reason for override, and the timestamp. This is mandatory — a one-click override on a failed PROD VERIFY without an audit trail is exactly the kind of "did anyone notice that?" event compliance reports must surface afterward. Use `write_decision_log.py` (see Step 9) with title `"Override: failed migration verification"`.

**Backwards-compat:** migrations without any `-- VERIFY:` comment are reported as `skipped=True, all_passed=True` and do not cause a rollback. New migrations should always include at least one `-- VERIFY:` block — see `shared/templates/rules/migrations.md.template` for the convention and examples.

### Post-Migration Manual Steps

Check `migrations.post_apply_manual_steps` from the stack profile. For each entry where `trigger_tag` matches a migration just applied, inform user via AskUserQuestion with the action and note. Wait for confirmation before proceeding.

---

## Step 2: Pre-Deploy Safety (PROD only)

**Goal:** Create a rollback point before deploying to PROD.

```bash
uv run "{plugin_root}/scripts/lib/jelastic_client.py" clone-env \
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
uv run "{plugin_root}/scripts/lib/jelastic_client.py" deploy \
  --env-name "{env_name}" \
  --branch "{branch}"
```

This calls the Jelastic VCS Update API to pull the latest code from git.

If environment doesn't exist yet: create it first via `create-env`.

---

## Step 4: Smoke Test

```bash
uv run "{shared_root}/scripts/smoke_test.py" \
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
uv run "{shared_root}/scripts/tools/record_event.py" \
  --project-root "$(pwd)" \
  --type phase_completed \
  --phase deploy \
  --detail "https://{env_name}.jpc.infomaniak.com"
```

**Phase complete — update pipeline state:**

Deploy runs the Minimum Phase Completion Canon at C1/C2/C3 only. **C4 is skipped**
(decided in plan) and **C5 is skipped** — deployment is operational history
(`events.jsonl` + `phase_history`), not a product change; a per-deploy CHANGELOG
`[Unreleased]` bullet would duplicate the changelog plugin's release block.

```bash
: "${SHIPWRIGHT_RUN_ID:=deploy-$(date +%Y%m%d-%H%M%S)-{env_name}}"
export SHIPWRIGHT_RUN_ID

# C1 — already emitted as the phase_completed event above.

# C2 — delivery dashboard
uv run "{shared_root}/scripts/tools/update_build_dashboard.py" \
  --project-root "$(pwd)" --phase deploy --detail "Deployed to {url}" \
  --session-id "{SHIPWRIGHT_SESSION_ID}"

# C3 (NEW 12.4) — canon-marker handoff
uv run "{shared_root}/scripts/tools/generate_session_handoff.py" \
  --project-root "$(pwd)" --canon-marker --phase deploy \
  --reason "deploy to {env_name}: {status}"

# C4 — SKIPPED by policy (execution, not decision).
# C5 — SKIPPED by policy (operational history, not product change;
#      release narrative belongs to the changelog plugin).

# phase_history (NEW 12.4)
uv run "{shared_root}/scripts/tools/append_phase_history.py" \
  --project-root "$(pwd)" --phase deploy --run-id "$SHIPWRIGHT_RUN_ID" \
  --entry-json '{"target":"{env_name}","url":"{url}","version":"v{version}","outcome":"success"}'

# Mark deploy phase complete (triggers compliance update automatically).
# _validate_deploy() (new in 12.4) runs the test-gate pre-condition
# plus the deploy_checks verifier (C1/C2/C3 + phase_history).
uv run "{plugin_root}/../../plugins/shipwright-run/scripts/lib/orchestrator.py" \
  update-step --project-root "$(pwd)" --step deploy --status complete
```

**Reflection — Capture Deploy Learnings:**

If deployment had issues or required adjustments:
1. Infra configuration gotchas?
2. Environment-specific behavior?
3. Rollback insights?

If learnings exist:
- **Observations** → append to `.shipwright/agent_docs/conventions.md` under `## Learnings`
  Format: `- ({YYYY-MM-DD}) deploy — {summary}`
- **Cross-project insights** → save Claude Code feedback/project Memory
If none: skip.

### Smoke Test Failed → Rollback

**DEV:** Git-based rollback
```bash
uv run "{plugin_root}/scripts/lib/rollback.py" \
  --env-name "{env_name}" \
  --strategy git \
  --target-ref "{last_known_good_tag}"
```

**PROD:** Restore from clone
```bash
uv run "{plugin_root}/scripts/lib/rollback.py" \
  --env-name "{env_name}" \
  --strategy clone \
  --clone-name "{prod_env}-backup"
```

Log rollback in `.shipwright/agent_docs/decision_log.md`.

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

## Rollback-Discipline (Universal)

Shipwright treats rollback as a property of every deploy target, not a
feature of one. Three patterns apply universally; their mechanics are
target-specific. The Jelastic flow above is one reference implementation —
the same discipline applies to any target Shipwright would call shipped.

### Pattern 1 — Revertable Deploys

Every deploy has a documented path back to the previous working state. The
mechanics are target-specific — git-tag revert (DEV-typical), environment-
clone restore (Jelastic PROD), atomic deploy-ID promote (Vercel), image-tag
rollback (Docker Compose, Kubernetes) — but the property is universal: a
deploy is not complete until its rollback is operable. **Application-tier**
and **data-tier** rollback are separate concerns; the schema's
`rollback.data_rollback_strategy` field captures how each target handles
DB-schema-vs-app-code drift.

### Pattern 2 — Provenance Recorded

Every deploy and every rollback leaves an auditable record before the next
change touches the same target. Pipeline-side: `phase_completed` events in
`shipwright_events.jsonl`, an entry in `phase_history`, and — for rollbacks
— an ADR in `decision_log.md` with the failure cause. Target-side: deploy
IDs, clone names, image-tag history, or whatever the platform exposes via
`vercel inspect` / `getenvinfo` / registry API. The why-it-happened
outlives the on-call shift.

### Pattern 3 — Procedure Documented

Both rollback paths — automatic (smoke-test-fail) and manual
(operator-initiated) — must be runnable from the documentation alone.
Manual rollback requires explicit confirmation; automatic rollback logs
its trigger and announces itself in the deploy output. A silent rollback
is the failure mode worse than the failure that caused it.

### How discipline becomes target

A target proves it satisfies the discipline by filling in a Deploy Profile
at `shared/profiles/deploy/<target_id>.json`, validated against
`shared/profiles/deploy-profile.schema.json`. Three reference profiles
ship today: **Jelastic** (full implementation, `confidence: verified`),
**Vercel** (declarative stub, `confidence: documented`), and
**Compose-VPS** (declarative stub, `confidence: documented`). The two
stubs exist to keep the schema honest — they describe how targets with
fundamentally different rollback mechanics (atomic vs. snapshot vs. clone)
fill the same shape. To add a real implementation: write the client, fill
the profile, run `validate_deploy_profile.py --strict`. See
[`references/rollback-discipline.md`](references/rollback-discipline.md)
for the pattern-by-pattern mapping.

---

## Reference Documents

- [jelastic-api.md](references/jelastic-api.md) — Jelastic API endpoint reference
- [deploy-flavors.md](references/deploy-flavors.md) — Flavor architecture (code-side interface)
- [rollback-strategy.md](references/rollback-strategy.md) — Jelastic-specific DEV vs PROD rollback procedure
- [rollback-discipline.md](references/rollback-discipline.md) — Universal rollback discipline + per-target mapping (Jelastic / Vercel / Compose-VPS)
