# Rollback Discipline (Universal)

This document expands the universal rollback discipline that the deploy
SKILL.md introduces. It exists so that anyone adding a non-Jelastic deploy
target — or evaluating whether their existing platform fits Shipwright's
discipline — knows exactly what to satisfy.

The discipline comprises **three patterns**. Their wording is target-agnostic;
their *mechanics* are target-specific and live in
[`shared/profiles/deploy/<target_id>.json`](../../../../shared/profiles/deploy/),
validated against
[`shared/profiles/deploy-profile.schema.json`](../../../../shared/profiles/deploy-profile.schema.json).

> **Status today (Phase 0, Iterate 2).** The Deploy Profile layer is
> declarative reference. The runtime deploy flow (`SKILL.md` Steps B-5) still
> reads its values from hardcoded SKILL.md procedure for Jelastic — migrating
> the runtime to consume the profile is a future iterate. The discipline doc
> + schema + validator + reference profiles are shippable now because they
> answer the question *"what would a non-Jelastic target need to deliver?"*
> independently of the runtime switch.

Three reference profiles ship today to triangulate the schema across
mechanically different targets:

| Profile        | implementation_status | confidence  | Mechanic family            |
|----------------|-----------------------|-------------|----------------------------|
| `jelastic`     | shipped               | verified    | clone-environment + git-tag-revert |
| `vercel`       | stub                  | documented  | atomic-immutable           |
| `compose-vps`  | stub                  | documented  | image-tag-rollback         |

---

## Pattern 1 — Revertable Deploys

> Every deploy has a documented path back to the previous working state. The
> mechanics are target-specific — git-tag revert (DEV-typical), environment-
> clone restore (Jelastic PROD), atomic deploy-ID promote (Vercel,
> Cloudflare), image-tag rollback (Kubernetes, Docker Compose) — but the
> property is universal: a deploy is not complete until its rollback is
> operable. A target without a working rollback story is not a Shipwright
> deploy target.

Application-tier rollback (Pattern 1, default reading) is well-defined: the
running code can be replaced with a previous version. **Data-tier rollback**
is its own concern: when DB schema migrated forward and now the rolled-back
app expects the older schema, the app crashes regardless of how clean the
app-tier rollback was. The Deploy Profile encodes this in
`rollback.data_rollback_strategy`.

### Mapping

| Concern                           | Jelastic                                 | Vercel                                                | Compose-VPS                              |
|-----------------------------------|------------------------------------------|-------------------------------------------------------|------------------------------------------|
| `pre_deploy_safety.prod_strategy` | `clone-environment` (full PROD clone)    | `atomic-immutable` (deploy intrinsically preserved)   | `image-snapshot` (registry tag immutable)|
| `rollback.revertable_strategy_dev`| `git-tag-revert`                         | `atomic-deploy-promote`                               | `image-tag-rollback`                     |
| `rollback.revertable_strategy_prod`| `clone-restore`                         | `atomic-deploy-promote`                               | `image-tag-rollback`                     |
| `rollback.data_rollback_strategy` | `down-migration`                         | `none-app-only` (Vercel is stateless edge)            | `down-migration`                         |

### Conformance check

A new target proves it satisfies Pattern 1 by populating, in its profile, all
three rollback-strategy fields with non-empty values. The validator rejects
shipped profiles that leave any of them blank. The values themselves are
target-specific — what matters is that *some* documented mechanism exists.

---

## Pattern 2 — Provenance Recorded

> Every deploy and every rollback leaves an auditable record before the next
> change touches the same target. Minimum: target, version/ref, outcome,
> timestamp, trigger (human or pipeline). Shipwright captures this through
> `phase_completed` events in `shipwright_events.jsonl`, an entry in
> `phase_history`, and — for rollbacks — an ADR in `decision_log.md` with
> the failure cause. The why-it-happened outlives the on-call shift.

Provenance is what lets you answer "what was deployed at 03:00 last
Wednesday, by whom, and why was it rolled back?" weeks later. The schema
does not encode the format of the provenance log (that is a runtime concern);
it documents *whether* the target supports retrieval.

### Mapping

| Concern                                  | Jelastic                                                       | Vercel                                                                                              | Compose-VPS                                                              |
|------------------------------------------|----------------------------------------------------------------|-----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|
| Pipeline-side provenance                 | `shipwright_events.jsonl` + `phase_history`                    | Same                                                                                                | Same                                                                     |
| Target-side provenance (deploy IDs etc.) | Environment names + clone-name pattern `{prod_env}-backup`     | Deployment IDs + `vercel inspect [url]` (git SHA, branch, build time, who triggered)                | Image tags in registry + `docker-compose.yml` git history                |
| Rollback-trigger record                  | Shipwright ADR in `decision_log.md` + clone-restore log entry  | Shipwright ADR + Vercel dashboard rollback log                                                      | Shipwright ADR + git history of compose-file change                      |

### Conformance check

A new target proves it satisfies Pattern 2 by ensuring rollbacks are not
silent. The pipeline-side guarantee is universal (Shipwright always writes
the event + ADR). The target-side guarantee — that the platform itself
keeps a record — is the new contributor's responsibility to document. If
the platform truly has no native record, the contributor must bolt one on
externally.

---

## Pattern 3 — Procedure Documented

> Both rollback paths — automatic (smoke-test-fail) and manual
> (operator-initiated) — must be runnable from the documentation alone.
> Manual rollback requires explicit confirmation; automatic rollback logs
> its trigger and announces itself in the deploy output. A silent rollback
> is the failure mode worse than the failure that caused it.

The schema separates *trigger* (`rollback.auto_trigger`), *interface*
(`rollback.operator_interface`), and *manual procedure* (a freeform
documentation reference, never executed by the runtime).

### Mapping

| Concern                              | Jelastic                                          | Vercel                                                                  | Compose-VPS                                                    |
|--------------------------------------|---------------------------------------------------|-------------------------------------------------------------------------|----------------------------------------------------------------|
| `rollback.auto_trigger`              | `smoke-test-fail`                                 | `off` (Vercel has no built-in health-check rollback — honest)           | `off` (plain Compose has no built-in; Watchtower/Argus extend) |
| `rollback.operator_interface`        | `cli`                                             | `cli`                                                                   | `cli` (over SSH)                                               |
| `rollback.manual_procedure_reference`| `/shipwright-deploy --rollback`                   | `vercel rollback [url]` / `vercel promote [url]` (`vercel inspect` for provenance) | Update tag in `docker-compose.yml`, `ssh && docker compose pull && up -d --force-recreate` |

> **Note on `operator_interface`.** All three reference targets above happen to
> use `cli` — but that is target-coincidence, not discipline. UI-only platforms
> (Cloudflare Pages: rollback is dashboard-only via the ⋯ menu on a deployment),
> API-only services, or mixed (CLI for trigger + UI for confirmation) are
> equally valid. Recommended values: `cli` | `ui` | `api` | `mixed`. A
> UI-only target merely means the operator clicks instead of types — the
> discipline (procedure must be runnable from documentation alone) is the same.

### Conformance check

A new target proves it satisfies Pattern 3 by populating
`rollback.manual_procedure_reference` with a runnable, copy-pasteable
description. The validator does not check the procedure's correctness —
that is a documentation review concern. But the field's existence is
mandatory: a rollback you cannot articulate is one you cannot execute.

---

## Adding a real target — 3-step checklist

This list mirrors the schema-doc's checklist; both must stay in sync.

1. **Declare a stub.** Create `shared/profiles/deploy/<your-target>.json`:
   - First field: `"$schema": "../deploy-profile.schema.json"`
   - `implementation_status: "stub"`, `confidence: "documented"` or `"inferred"`
   - `client: null`
   - Fill all required fields from official target docs / known patterns
   - Use `known_gaps: [...]` for honest limitations
   - Run `uv run shared/scripts/tools/validate_deploy_profile.py --profile shared/profiles/deploy/<your-target>.json`
   - **Also: add a column for your target to each Pattern × Target mapping
     table above** (Pattern 1 / Pattern 2 / Pattern 3) so future readers see
     how your target's mechanics map to the discipline. The validator
     does NOT check for this — it is a documentation-quality contract.
2. **Implement the client** (Python, Node, or Bash) under a profile-named
   path. Update `client` to point at it.
3. **Promote to shipped.** Flip `implementation_status: "shipped"`,
   `confidence: "verified"`. Run
   `uv run shared/scripts/tools/validate_deploy_profile.py --strict --profile <path>`
   to verify the entrypoint resolves under `repo_root`.

---

## Known gaps in the v1.0 reference profiles

These are documented honestly so a contributor inheriting a stub doesn't
waste cycles re-discovering them.

- **Vercel custom aliases** are NOT auto-rolled-back during instant
  rollback; they remain pointed at the previously-aliased deployment unless
  manually re-aliased.
- **Vercel auto-rollback on health-check fail** is not built in; the
  Vercel stub honestly declares `auto_trigger: "off"`. Auto-rollback must
  be implemented by external CI/CD logic if desired.
- **Vercel Hobby plan** is limited to rolling back to the immediately
  previous production deployment. Pro and Enterprise plans can roll back
  to any eligible (previously production-aliased) deployment.
- **Vercel preview-vs-prod deployments** are not modeled in v1.0 of the
  schema (which fixes `dev` + `prod`). Vercel's preview-per-branch could
  be added under `environments.{branch-name}` in v2.0 via the existing
  `patternProperties`.
- **Vercel env vars + cron jobs** are baked into the deployment at build
  time — rolling back also rolls back to that snapshot. The schema does
  not model this nuance per-field; the Vercel stub's `known_gaps` calls
  it out.
- **Compose-VPS mutable-tag setups** (`:latest`, server-side builds) are
  out of scope. The profile describes the *disciplined* subtype only.
- **Coolify / Dokku / Caprover / Kubernetes / Docker Swarm** are sibling
  targets, not Compose-VPS variants. Each can get its own profile when
  someone implements a runtime client.
