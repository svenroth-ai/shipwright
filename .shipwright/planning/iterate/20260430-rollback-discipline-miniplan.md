# Mini-Plan v3 — Rollback-Discipline Refactor (LOCKED)

**Run ID:** iterate-20260430-rollback-discipline
**Spec:** [20260430-rollback-discipline.md](./20260430-rollback-discipline.md) (v3 LOCKED)
**Branch:** `iterate/phase0-i2-rollback-discipline` (from `main`)

**Revision history:**
- v1 → first draft, plan-gate-A v2 alignment
- v2 → external plan review v1 findings (16 accepted) + Vercel deep-dive (5 docs pages) + open architecture question
- v3 (LOCKED) → external plan review v2: Architecture Decision Option B (drop discipline booleans), all 8 HIGH + 16 MEDIUM findings accepted

**Architecture Decision (locked, see Spec):**
- `rollback.discipline` boolean block dropped. Discipline encoded as schema-required mechanism fields + `confidence` field for ALL profiles.
- `confidence` is required for ALL profiles. Shipped→verified, stub→documented|inferred (semantic check enforced by validator).
- Mechanism strategy fields are strings with documented-recommended-values, not strict enums.
- `environments` modeled as `patternProperties` + `required: [dev, prod]` (extensible).
- `migrations.supported: false` uses if/then conditional (no `"n/a"` strings).
- Validator semantic-check layer for cross-field invariants (path traversal, duplicate target_id, env-var name conflicts, confidence/status consistency).
- `jsonschema` configured with remote `$ref` resolution disabled.

**Implementation file list and build order remain as in v2 (Layers 1-7).** Schema and validator surface are richer per Spec v3 ACs.

---

## Approach

Six-layer cake, build bottom-up, each layer independently verifiable.

1. **Schema layer** — JSON-Schema (draft-2020-12 with `$id`, `$schema`,
   versioning) + companion human-readable doc.
2. **Profile layer** — three profile JSONs with `$schema` link.
   Jelastic from hardcoded SKILL.md migration; Vercel from 5 docs pages;
   Compose-VPS from disciplined-subtype best practices.
3. **Validator layer** — pure library function + CLI wrapper.
4. **Validator tests** — covers happy path, schema violations, CLI
   robustness, edge cases.
5. **Discipline documentation** — SKILL.md section + new reference doc
   + cross-link header updates + guide.md updates.
6. **Status update** — phase0-iterates.md status table.

This bottom-up order pressure-tests the schema *during* profile
authoring (if a target field doesn't fit, schema is wrong, not the
profile). Discipline doc is last because its mapping tables read
directly from the three profiles — authoring it first would invite
drift.

## Files (build order)

### Layer 1 — Schema (build first)

1. **`shared/profiles/deploy-profile.schema.json`** (NEW)
   - Header: `$schema: "https://json-schema.org/draft/2020-12/schema"`,
     `$id: "https://shipwright.dev/schemas/deploy-profile/v1.json"`.
   - Root: `target_id` (`^[a-z0-9-]+$`), `target_kind`
     (`paas-cloud | edge-platform | self-hosted-vm`), `description`,
     `implementation_status` (`shipped | stub`), `confidence`
     (`verified | documented | inferred`, required when stub),
     `client` (object | null), `auth`, `environments`,
     `pre_deploy_safety`, `test_gate`, `migrations`, `smoke_test`,
     `rollback`, `profile_schema_version: "1.0"`.
   - `client` block: `{ entrypoint: string, runner: "python"|"node"|"bash" }`
     when shipped; `null` when stub. Encoded via if/then on
     `implementation_status`.
   - `auth` block: `{ required_env_vars: [{name, description}],
     optional_env_vars: [{name, description}] }`. Schema-Doku says
     EXPLICITLY: schema accepts ENV variable names; literal secrets
     never appear in profiles.
   - `environments`: required keys `dev` + `prod`, each with
     `url_pattern`, `confirmation` (`none | user`).
     `additionalProperties: false` at this level (locks v1.0 scope).
   - `rollback.discipline`: `{ revertable: bool,
     provenance_recorded: bool, procedure_documented: bool }`.
     All three required.
   - `rollback.mechanism`: `{ revertable_strategy_dev,
     revertable_strategy_prod, auto_trigger, operator_interface,
     manual_procedure_reference, data_rollback_strategy }`.
     Enums chosen to cover the three reference targets without
     premature universalism. Stays extensible
     (`additionalProperties` not locked).
   - `additionalProperties: false` at root + on `client`, `auth`
     entries, `environments` (with fixed dev/prod keys),
     `rollback.discipline`. NOT on `rollback.mechanism`,
     `smoke_test`, `migrations`, `pre_deploy_safety` (extension lanes).
   - **Conditional rule (allOf/if/then):** when
     `implementation_status == "stub"`, `client` MUST be `null`,
     `confidence` MUST be present. When `shipped`, `client` MUST be
     non-null object, `confidence` MAY be `verified`.
   - **Discipline-conformance rule** (if accepted in option C of open
     architecture question): when `shipped`, `rollback.discipline.revertable
     == true` AND `mechanism.revertable_strategy_prod` MUST be set.

2. **`shared/profiles/deploy-profile-schema.md`** (NEW)
   - One section per top-level field: name, type, required y/n,
     1-2-sentence semantics, an example value from each of the three
     reference profiles.
   - "Why discipline + mechanism split" explainer section.
   - "Auth never contains secrets" callout.
   - "Adding a New Target" 3-step checklist:
     (a) declare profile JSON with `$schema` link, fill mechanism
     block, set `implementation_status: stub`, `confidence: documented`,
     `client: null`. Run `validate_deploy_profile.py --profile`.
     (b) implement the client (`client.entrypoint`, `client.runner`).
     (c) flip `implementation_status: shipped`, `client: { entrypoint, runner }`.
     Run `validate_deploy_profile.py --strict --profile` to confirm.

### Layer 2 — Profiles

3. **`shared/profiles/deploy/jelastic.json`** (NEW)
   - `"$schema": "../deploy-profile.schema.json"`
   - `implementation_status: "shipped"`, `confidence: "verified"`
   - `client: { entrypoint: "plugins/shipwright-deploy/scripts/lib/jelastic_client.py", runner: "python" }`
   - `auth.required_env_vars: [{name: "JELASTIC_TOKEN", description: "Jelastic PAT for API access (Infomaniak datacenter)"}]`
   - `auth.optional_env_vars: [{name: "SUPABASE_ACCESS_TOKEN", description: "Required only if project uses Supabase migrations"}]`
   - `environments.dev.url_pattern: "dev-{project}.jpc.infomaniak.com"`,
     `environments.prod.url_pattern: "{project}.jpc.infomaniak.com"`
   - `pre_deploy_safety: { dev_strategy: "none", prod_strategy: "clone-environment", backup_naming_pattern: "{prod_env}-backup" }`
   - `smoke_test: { health_path: "/api/health", timeout_seconds: 30, poll_interval_seconds: 5, max_wait_seconds: 60 }`
   - `migrations: { supported: true, dev_strategy: "auto-apply", prod_strategy: "dry-run-then-confirm", verify_after_apply: true }`
   - `rollback.discipline: { revertable: true, provenance_recorded: true, procedure_documented: true }`
   - `rollback.mechanism: { revertable_strategy_dev: "git-tag-revert", revertable_strategy_prod: "clone-restore", auto_trigger: "smoke-test-fail", operator_interface: "cli", manual_procedure_reference: "/shipwright-deploy --rollback", data_rollback_strategy: "down-migration" }`

4. **`shared/profiles/deploy/vercel.json`** (NEW, accuracy improved by Vercel deep-dive)
   - `"$schema": "../deploy-profile.schema.json"`
   - `implementation_status: "stub"`, `confidence: "documented"`
   - `description: "Vercel atomic-immutable deploy. Stub derived from
     official docs (instant-rollback, rollback-production-deployment,
     cli/rollback, cli/inspect, environment-variables, accessed
     2026-04-30). Known gaps: (a) custom aliases NOT auto-rolled
     during instant-rollback, (b) Vercel has no built-in
     health-check-rollback — auto_trigger requires custom CI logic,
     (c) Hobby plan limited to previous deployment, Pro/Enterprise can
     rollback to any eligible deployment, (d) preview deployments not
     modeled in this v1 schema. Refine when first Vercel client is
     implemented."`
   - `client: null`
   - `auth.required_env_vars: [{name: "VERCEL_TOKEN", description: "Vercel API token (CLI auth)"}]`
   - `auth.optional_env_vars: [{name: "VERCEL_ORG_ID", description: "Org ID, optional if linked locally"}, {name: "VERCEL_PROJECT_ID", description: "Project ID, optional if linked locally"}]`
   - `environments.dev.url_pattern: "{project}-{branch-hash}.vercel.app"`,
     `environments.prod.url_pattern: "{project}.vercel.app"`
   - `pre_deploy_safety: { dev_strategy: "atomic-immutable", prod_strategy: "atomic-immutable", backup_naming_pattern: null }`
   - `smoke_test: { health_path: "/", timeout_seconds: 30, poll_interval_seconds: 5, max_wait_seconds: 60 }`
   - `migrations: { supported: false, dev_strategy: "n/a", prod_strategy: "n/a", verify_after_apply: false }` (Vercel is stateless edge platform; DB migrations are external concern)
   - `rollback.discipline: { revertable: true, provenance_recorded: true, procedure_documented: true }`
   - `rollback.mechanism: { revertable_strategy_dev: "atomic-deploy-promote", revertable_strategy_prod: "atomic-deploy-promote", auto_trigger: "off", operator_interface: "cli", manual_procedure_reference: "vercel rollback [deployment-url] || vercel promote [deployment-url]", data_rollback_strategy: "none-app-only" }`

5. **`shared/profiles/deploy/compose-vps.json`** (NEW)
   - `"$schema": "../deploy-profile.schema.json"`
   - `implementation_status: "stub"`, `confidence: "documented"`
   - `description: "Disciplined Docker Compose deploy on a single VM
     (Hetzner / Strato / Hosteurope / generic VPS). Requires
     immutable image tags, registry-backed images, no \`:latest\` tag.
     Setups using mutable tags or local-build-on-server are out of
     scope for this profile. Coolify / Dokku / Caprover / Kubernetes /
     Docker Swarm are sibling targets that may get their own profiles
     when needed."`
   - `client: null`
   - `auth.required_env_vars: [{name: "DOCKER_REGISTRY_USER", description: "Image registry username"}, {name: "DOCKER_REGISTRY_TOKEN", description: "Image registry token"}, {name: "SSH_HOST", description: "VM hostname or IP"}, {name: "SSH_USER", description: "SSH user with docker compose privileges on VM"}]`
   - `environments.dev.url_pattern: "dev.{domain}"`,
     `environments.prod.url_pattern: "{domain}"`
   - `pre_deploy_safety: { dev_strategy: "image-snapshot", prod_strategy: "image-snapshot", backup_naming_pattern: "{image}:{previous-semver}" }`
   - `smoke_test: { health_path: "/health", timeout_seconds: 30, poll_interval_seconds: 5, max_wait_seconds: 60 }`
   - `migrations: { supported: true, dev_strategy: "auto-apply", prod_strategy: "manual", verify_after_apply: false }`
   - `rollback.discipline: { revertable: true, provenance_recorded: true, procedure_documented: true }`
   - `rollback.mechanism: { revertable_strategy_dev: "image-tag-rollback", revertable_strategy_prod: "image-tag-rollback", auto_trigger: "off", operator_interface: "cli", manual_procedure_reference: "Update image tag in docker-compose.yml; ssh && docker compose pull && docker compose up -d --force-recreate", data_rollback_strategy: "down-migration" }`

### Layer 3 — Validator (library + CLI split)

6. **`shared/scripts/lib/deploy_profile_validator.py`** (NEW)
   - Pure-function module. No I/O, no argparse.
   - `def validate(profile: dict, schema: dict, *, profile_path: Path | None = None, strict: bool = False) -> list[ValidationError]`
   - Returns list of error objects. Empty list = pass.
   - `ValidationError` dataclass: `file_path: Path | None`,
     `json_pointer: str`, `message: str`, `severity:
     "error" | "warning"`.
   - `__str__` formats as `FAIL <file> :: <pointer> :: <message>` when
     `file_path` set; otherwise `FAIL :: <pointer> :: <message>`.
   - Multi-error: collect all `jsonschema` errors via
     `iter_errors()`, not `validate()`.
   - Filename ↔ target_id check happens here when `profile_path`
     is provided.
   - `--strict`: if `client` non-null, check
     `(repo_root / client.entrypoint).is_file()`.

7. **`shared/scripts/tools/validate_deploy_profile.py`** (NEW)
   - argparse CLI: `--profile`, `--all`, `--profiles-dir`, `--strict`,
     `--repo-root`.
   - Loads schema from a fixed path relative to repo root.
   - Resolves `--profiles-dir` default relative to `__file__` if not
     given (avoids cwd-dependence).
   - Argument validation: `--profile + --all` is rejected with usage
     error and exit 2.
   - Loads profile(s); on JSON parse error, emits a clean
     `ValidationError` with `severity: "error"`, exit 1.
   - On nonexistent profile path, emits descriptive error, exit 1.
   - Prints all errors per file, sums errors across files in `--all`
     mode, exit 0 only if total errors == 0.

### Layer 4 — Validator Tests

8. **`shared/tests/tools/test_validate_deploy_profile.py`** (NEW)
   - Test cases per AC-9 (a) through (k).
   - Uses `pytest`, calls library function directly for unit tests +
     CLI subprocess for integration tests.
   - Fixtures: minimal valid profile (constructed in test), broken
     variants (each test mutates one field).
   - **Note:** integration tests for the CLI use `subprocess.run`
     against the actual Python script, so they run end-to-end.

### Layer 5 — Discipline Documentation

9. **`plugins/shipwright-deploy/skills/deploy/SKILL.md`** (UPDATE)
   - Insert new `## Rollback-Discipline (Universal)` section between
     `## Manual Rollback (--rollback)` (line ~395) and
     `## Reference Documents` (line ~397).
   - ~55 lines: 2-sentence frame, Pattern 1/2/3 (each ~9 lines, with
     Pattern 1 calling out app-vs-data rollback), "How discipline
     becomes target" pointer to profile + reference.
   - Reference Documents list: add
     `[rollback-discipline.md](references/rollback-discipline.md)`.
   - **No other changes** — Steps B/B2/B3/B4/C/0/1/2/3/4/5 untouched.

10. **`plugins/shipwright-deploy/skills/deploy/references/rollback-discipline.md`** (NEW)
    - ~140 lines.
    - Frame (~5 lines).
    - Three pattern sections, each ~35 lines:
      - Discipline statement (1 paragraph).
      - Mapping table (Concern / Jelastic / Vercel / Compose-VPS).
      - Conformance check (1 paragraph).
    - **Pattern 1 sub-section: Application vs Data rollback** —
      explicit framing that DB-schema and app-code are separate
      concerns; `rollback.mechanism.data_rollback_strategy` field
      encodes this.
    - "Status today" callout (declarative-only in I2; runtime
      consumption deferred).
    - "Adding a real target" 3-step checklist (matches schema-doc).
    - "Known gaps" caveat-block: Vercel custom aliases, Vercel
     auto-trigger off, Compose-VPS mutable-tag setups out of scope,
     Hobby plan rollback range limit.

11. **`plugins/shipwright-deploy/skills/deploy/references/rollback-strategy.md`** (UPDATE)
    - Prepend 3-line header:
      > **Jelastic Reference Implementation.** Universal rollback
      > patterns: see `rollback-discipline.md`. Profile:
      > `shared/profiles/deploy/jelastic.json`.
    - No other changes.

12. **`plugins/shipwright-deploy/skills/deploy/references/deploy-flavors.md`** (UPDATE)
    - Prepend 3-line header:
      > Deploy target descriptors now live declaratively in
      > `shared/profiles/deploy/<id>.json` (validated by
      > `shared/profiles/deploy-profile.schema.json`).
      > This file preserves the **code-side flavor-client interface**.
    - No other changes.

### Layer 6 — User Documentation

13. **`docs/guide.md`** (UPDATE)
    - Section 4.9 (Deployment): insert one paragraph after "DEV vs.
      PROD — the key difference" and before "Standalone usage":
      Universal rollback discipline frame + pointer to
      `rollback-discipline.md` + concept of Deploy Profiles + mention
      of three reference profiles (1 shipped, 2 stubs).
    - Section 5 (Stack Profiles): insert one paragraph at the chapter
      end: deploy targets now have first-class profiles in
      `shared/profiles/deploy/`, three ship today, validator at
      `shared/scripts/tools/validate_deploy_profile.py --all`.

### Layer 7 — Status & Compatibility

14. **`shared/pyproject.toml`** (UPDATE if needed) or root
    `pyproject.toml` (which owns shared/scripts/) — verify and add
    `jsonschema>=4.18` if missing. Run `uv sync`. Lockfile committed.

15. **Repo compatibility scan** (no file change, finalize-step
    artifact)
    - `grep -rn 'shared/profiles/\*.json'`
    - `grep -rn "Path('shared/profiles')"` and similar
    - Document scan result in iterate ADR.

16. **`.shipwright/reviews/phase0-iterates.md`** (UPDATE during F-step)
    - Status table: I2 → ✅ done with date + commit hash.
    - Done-Definition Iterate 2: check off all 5 items.

## Test Strategy

- **Schema correctness**: validator pytest suite (Layer 4 step 8).
  Library function tested directly (fast); CLI tested via subprocess
  (slow but authentic).
- **Profile validity**: validator's `--all` mode in CI-equivalent run
  + as part of pytest.
- **Doc consistency**: manual self-review in F0 — does the discipline
  doc's mapping table for Pattern X agree with the corresponding
  field in profile X?
- **No new TDD-driven feature code** for the schema/profile artifacts
  themselves — they are declarative. Only the validator gets TDD.

## External Review Cadence

- **Plan review v1** (done) — mode plan, gemini + openai. 16 findings
  accepted, 4 deferred to schema-doc.
- **Plan review v2** (next) — same mode, includes the open
  architecture question. **Specific ask:** does the
  discipline-Boolean+mechanism hybrid (option C) hold up, or should we
  drop the booleans and rely on validator-enforced mechanism
  requirements (option B)?
- **Code review (final diff)** — `external_review.py --mode code`
  after Layer 6 self-review, before commit.

## Estimated Effort

- Layer 1 (Schema + doc): ~3 hours.
- Layer 2 (Profiles): ~2.5 hours.
- Layer 3 (Validator lib + CLI): ~2 hours.
- Layer 4 (Validator tests): ~2 hours.
- Layer 5 (Discipline doc + SKILL.md + 2 reference headers): ~3.5 hours.
- Layer 6 (guide.md): ~30 minutes.
- Layer 7 (deps + compat scan + status): ~1 hour.
- External reviews + revisions: ~1 hour each (plan-v2, code).

**Total: ~16 hours of focused work, 1.5-2 working sessions.** Spec
budget is "1-2 days"; this is at the upper end of that.

## Alternatives Considered

**A — Pure-doc Hybrid** (rejected at plan-gate-A v1): discipline
section in SKILL.md + single reference file, no schema. Rejected:
user wants profile-mässig treatment for curriculum value + machine-
checked anchor.

**B — Validator-only discipline** (the alternative to current
Discipline-Boolean approach, will be evaluated at plan review v2):
Drop `rollback.discipline` block entirely; encode discipline as
schema-level requirement that `shipped` profiles must have non-null
mechanism fields. Profile is leaner; reader of profile alone doesn't
see the discipline assertion.

**C — Hybrid Discipline-Boolean + Validator** (current draft): both
explicit booleans AND validator enforcement. Booleans redundant for
shipped, useful for stubs that intentionally fail discipline (e.g.
hypothetical "FTP-deploy-without-rollback" stub demonstrating why
schema rejects it).
