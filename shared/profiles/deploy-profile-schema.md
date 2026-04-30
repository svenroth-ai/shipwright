# Deploy Profile Schema (v1.0)

**Schema file:** [`deploy-profile.schema.json`](./deploy-profile.schema.json)
**Profiles directory:** [`deploy/`](./deploy/) — one `<target_id>.json` per target
**Validator:** `uv run shared/scripts/tools/validate_deploy_profile.py --all`

A **Deploy Profile** is the declarative descriptor for a Shipwright deploy target.
It encodes universal rollback discipline (revertable deploys, recorded provenance,
documented procedure) plus adjacent deploy concerns (auth, environments, smoke
test, migrations) in a single JSON file. Three reference profiles ship today:

| target_id     | implementation_status | confidence  | client                                                                  |
|---------------|-----------------------|-------------|-------------------------------------------------------------------------|
| `jelastic`    | shipped               | verified    | `plugins/shipwright-deploy/scripts/lib/jelastic_client.py` (python)     |
| `vercel`      | stub                  | documented  | null                                                                    |
| `compose-vps` | stub                  | documented  | null                                                                    |

This document explains every field. For the universal rollback discipline
itself (the *why* behind the fields), see
[`plugins/shipwright-deploy/skills/deploy/references/rollback-discipline.md`](../../plugins/shipwright-deploy/skills/deploy/references/rollback-discipline.md).

---

## What the schema enforces (and what the validator adds)

The JSON-Schema enforces structure: required fields, types, enums, regex
patterns, conditional shapes (e.g. `migrations.supported: false` forbids
strategy fields). The companion validator
(`shared/scripts/lib/deploy_profile_validator.py`) adds **semantic** checks
that schema can't express cleanly:

- `shipped` profile MUST have `confidence: verified`.
- `stub` profile MUST have `confidence: documented` or `inferred`.
- `client.entrypoint` MUST be repo-relative (no `..`, no absolute path).
- `--strict` mode: `client.entrypoint` resolved against `repo_root` MUST
  exist and be inside the repo (path-traversal guard).
- Filename without `.json` MUST equal `target_id`.
- No duplicate `target_id` across profiles in `--all` mode.
- No duplicate env-var name within or across `auth.required_env_vars` /
  `auth.optional_env_vars`.

Together, schema + semantic checks express the discipline that *every shipped
target must satisfy, before it can claim `confidence: verified`.*

---

## Top-level fields

### `$schema` *(optional, recommended)*

```json
"$schema": "../deploy-profile.schema.json"
```

Pointer for IDE autocompletion. Whitelisted at root despite
`additionalProperties: false`.

### `profile_schema_version` *(required)*

```json
"profile_schema_version": "1.0"
```

The schema version this profile targets. v1.0 is the only valid value today.
A future v2.0 introduction will leave v1.0 profiles validating against the
v1.0 schema unchanged.

### `target_id` *(required)*

Lowercase, hyphen-separated identifier (`^[a-z0-9-]+$`). MUST equal the profile
filename without `.json` extension.

| Profile          | `target_id`     |
|------------------|-----------------|
| `jelastic.json`  | `"jelastic"`    |
| `vercel.json`    | `"vercel"`      |
| `compose-vps.json` | `"compose-vps"` |

### `target_kind` *(required)*

Coarse classification, freeform string. Recommended values:

- `paas-cloud` — Jelastic, Heroku-style, Render
- `edge-platform` — Vercel, Cloudflare Pages, Netlify
- `self-hosted-vm` — Docker Compose on VPS, bare metal

Not a strict enum so future categories (e.g. `serverless-container`,
`managed-k8s`) don't require a schema bump.

### `description` *(required)*

Human-readable summary, `minLength: 1`. For stubs, describe scope, the
source of information (which docs, which date), and known gaps.

### `implementation_status` *(required)*

| Value      | Meaning                                                        |
|------------|----------------------------------------------------------------|
| `shipped`  | A code-backed runtime client exists in this repo.              |
| `stub`     | The profile is declarative-only (reference / future skeleton). |

> **What "shipped" does NOT mean:** "officially supported via manual
> workflow." A target supported only by hand-runbooks today should be a
> `stub` until a code-backed client is written.

### `confidence` *(required for ALL profiles)*

| Value        | Meaning                                                            |
|--------------|--------------------------------------------------------------------|
| `verified`   | Backed by a working implementation (live-tested fields).           |
| `documented` | Derived from official target docs, not live-tested in this repo.   |
| `inferred`   | Derived from general industry patterns; weakest provenance.        |

Schema-enforced: shipped → `verified`; stub → `documented` or `inferred`.

### `client` *(required, nullable)*

For `shipped` profiles: object with `entrypoint` (repo-relative path) +
`runner` (`python | node | bash`).
For `stub` profiles: `null`.

```json
"client": {
  "entrypoint": "plugins/shipwright-deploy/scripts/lib/jelastic_client.py",
  "runner": "python"
}
```

### `auth` *(required)*

```json
"auth": {
  "required_env_vars": [
    {"name": "JELASTIC_TOKEN", "description": "Jelastic PAT for API access"}
  ],
  "optional_env_vars": [
    {"name": "SUPABASE_ACCESS_TOKEN", "description": "Required only if project uses Supabase migrations"}
  ]
}
```

> **Profiles describe ENV variable NAMES, never literal secret values.**
> Schema enforces `^[A-Z][A-Z0-9_]*$` on names. Validator rejects
> duplicate names within or across the two lists.

### `environments` *(required, extensible)*

Schema requires `dev` and `prod` keys. Additional environment names matching
`^[a-z][a-z0-9-]*$` (`preview`, `staging`, `uat`, …) are accepted via
`patternProperties` and validated against the same env-shape. Keys NOT matching
the regex (e.g. `Staging` uppercase, `pre/view`) are rejected via
`additionalProperties: false`. This combination means: future targets that use
`staging` don't require a schema bump, but typos do not silently pass.

```json
"environments": {
  "dev":  { "url_pattern": "dev-{project}.example.com", "confirmation": "none" },
  "prod": { "url_pattern": "{project}.example.com",     "confirmation": "user" }
}
```

> **JSON-Schema Draft 2020-12 nuance:** when `patternProperties` and
> `additionalProperties: false` are combined, pattern-matched keys are accepted
> (validated against the pattern's subschema) and non-pattern-matched keys are
> rejected. Verified against `jsonschema 4.26+` in
> `shared/tests/tools/test_validate_deploy_profile.py`
> (`test_extra_environment_via_pattern_properties_passes` +
> `test_environment_name_with_uppercase_rejected`).

### `pre_deploy_safety` *(required)*

How a rollback point is established before each deploy. Strategy values
are recommended-not-enum strings (extensibility):

- `dev_strategy` — recommended: `none`, `git-tag`, `image-snapshot`, `atomic-immutable`
- `prod_strategy` — recommended: `clone-environment`, `atomic-immutable`, `image-snapshot`, `backup-restore`
- `backup_naming_pattern` — string or `null` (e.g. `"{prod_env}-backup"`; `null` for atomic-immutable targets)

### `test_gate` *(required)*

```json
"test_gate": {
  "policy": "strict",
  "results_source": "shipwright_test_results.json"
}
```

`policy ∈ {strict, warn, skip}`. `strict` blocks deploy on test failure.

### `migrations` *(required, conditional shape)*

```json
"migrations": { "supported": false }
```

When `supported: false`, schema FORBIDS `dev_strategy`, `prod_strategy`,
`verify_after_apply` (avoids `"n/a"` string-as-enum-value pattern).

When `supported: true`, all three required:

```json
"migrations": {
  "supported": true,
  "dev_strategy": "auto-apply",
  "prod_strategy": "dry-run-then-confirm",
  "verify_after_apply": true
}
```

- `dev_strategy` — recommended: `auto-apply`, `user-confirm`, `manual`
- `prod_strategy` — recommended: `dry-run-then-confirm`, `atomic-with-app`, `manual`

### `smoke_test` *(required)*

```json
"smoke_test": {
  "health_path": "/api/health",
  "timeout_seconds": 30,
  "poll_interval_seconds": 5,
  "max_wait_seconds": 60
}
```

### `rollback` *(required)*

The discipline pattern. Schema requires all six mechanism fields populated
with non-empty strings — that is the discipline assertion. There are no
separate `discipline.{revertable,provenance_recorded,procedure_documented}`
booleans; their existence would be tautological for shipped targets and
invite drift between two sources of truth (decided 2026-04-30 after two
external plan reviews, see iterate spec).

```json
"rollback": {
  "revertable_strategy_dev":  "git-tag-revert",
  "revertable_strategy_prod": "clone-restore",
  "auto_trigger":             "smoke-test-fail",
  "operator_interface":       "cli",
  "manual_procedure_reference": "/shipwright-deploy --rollback",
  "data_rollback_strategy":   "down-migration"
}
```

| Field                          | Recommended values                                                |
|--------------------------------|-------------------------------------------------------------------|
| `revertable_strategy_dev`      | `git-tag-revert`, `image-tag-rollback`, `atomic-deploy-promote`, `none` |
| `revertable_strategy_prod`     | `clone-restore`, `atomic-deploy-promote`, `image-tag-rollback`    |
| `auto_trigger`                 | `smoke-test-fail`, `verify-fail`, `off`                           |
| `operator_interface`           | `cli`, `ui`, `api`, `mixed`                                       |
| `manual_procedure_reference`   | freeform documentation (CLI command, doc URL, or prose)           |
| `data_rollback_strategy`       | `down-migration`, `backup-restore`, `none-app-only`, `manual`     |

> **`manual_procedure_reference` is documentation-only.** It is NEVER executed
> by Shipwright runtime — operators read and run it themselves. Stating this
> explicitly so future runtime consumers do not pipe profile strings into a
> shell.

### `known_gaps` *(optional)*

Honest-limitations array. Especially valuable for stubs to surface caveats
that would otherwise be buried in `description` prose:

```json
"known_gaps": [
  "Custom aliases are NOT auto-rolled-back during instant-rollback",
  "Vercel has no built-in health-check rollback — auto_trigger:'off' is honest",
  "Hobby plan limited to previous deployment; Pro/Enterprise rollback to any eligible deployment"
]
```

---

## Adding a New Target — 3-step checklist

1. **Declare a stub.** Create `shared/profiles/deploy/<your-target>.json`:
   - First field: `"$schema": "../deploy-profile.schema.json"`
   - `implementation_status: "stub"`, `confidence: "documented"` or `"inferred"`
   - `client: null`
   - Fill all required fields based on official target docs / known patterns
   - Optionally fill `known_gaps` for honest limitations
   - Run `uv run shared/scripts/tools/validate_deploy_profile.py --profile shared/profiles/deploy/<your-target>.json`
2. **Implement the client.** Write the runtime code (Python, Node, or Bash)
   under a profile-named path. Update `client` to point at it.
3. **Promote to shipped.** Flip `implementation_status: "shipped"`,
   `confidence: "verified"`, populate `client.entrypoint` + `client.runner`.
   Run `uv run shared/scripts/tools/validate_deploy_profile.py --strict --profile <path>`
   to verify the entrypoint resolves.

---

## What this schema does NOT cover (deliberately)

- **Multi-auth modes per target.** One auth shape per target for v1.0.
- **`enabled: bool` pattern on `test_gate` / `smoke_test`.** All shipping targets
  enable both. May land in v2.0.
- **Higher-level `deployment_model` classification** (mutable-in-place /
  atomic-immutable / snapshot-restore / image-redeploy). Implicit in
  `pre_deploy_safety` + `rollback` strategy fields today.
- **Structured `evidence: {basis, references}` field.** Description prose +
  `known_gaps` adequate for v1.0.
- **Severity levels in validator output.** Errors only — no warnings (YAGNI).

These can be added in v2.0 when a real second target stresses the schema.

---

## Versioning

`profile_schema_version: "1.0"` is the contract. v2.0 will introduce a new
schema file alongside this one; v1.0 profiles will continue to validate
against v1.0 indefinitely. Migrations are explicit, never silent.
