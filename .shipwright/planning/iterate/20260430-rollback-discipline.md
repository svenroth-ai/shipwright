---
run_id: iterate-20260430-rollback-discipline
type: change
complexity: medium
status: locked-v3
phase0_iterate: I2 (T5 — Rollback-Discipline Refactor)
spec_source: .shipwright/reviews/phase0-iterates.md
strategic_frame: .shipwright/reviews/phase0-decisions.md (cluster 1b)
review_history:
  - external_plan_review_v1 (2026-04-30 — gemini + openai via openrouter, "approve with revisions", 16 findings accepted)
  - vercel_doc_research (2026-04-30 — instant-rollback, rollback-production-deployment, cli/rollback, environment-variables, cli/inspect)
  - external_plan_review_v2 (2026-04-30 — both reviewers vote Option B for arch question, 8 HIGH + 16 MEDIUM findings accepted)
architecture_decisions:
  - "Option B (validator-enforced discipline) — drop rollback.discipline boolean block, encode discipline as schema-required mechanism fields + confidence value rules"
  - "confidence is required for ALL profiles (not just stubs); shipped→verified, stub→documented|inferred"
  - "Mechanism strategy fields are documented-recommended-values strings, not strict enums (extensibility for future targets)"
---

# Iterate Spec — Rollback-Discipline Refactor (Phase 0, I2 / T5)

## Goal

Extract universal rollback discipline from the Jelastic-specific deploy
implementation and elevate it to a first-class Deploy-Profile concept,
analogous to the existing Stack-Profile concept. Ship three reference
descriptors that triangulate the schema across mechanically different
deploy targets: Jelastic (full implementation, migrated from hardcoded
SKILL.md values), Vercel (declarative stub, atomic-immutable mechanic),
and Compose-VPS (declarative stub, image-tag-rollback mechanic).

This is a discipline + schema iterate. No new live deploy capability is
introduced; the Jelastic code path is unchanged.

## Architecture Decision (locked)

**Option B accepted.** `rollback.discipline` boolean block is dropped.
The three universal patterns (revertable, provenance recorded,
procedure documented) are encoded as **schema-level requirements** on
shipped profiles + a `confidence` field that distinguishes verified
implementation from documented stubs.

Rationale (both external reviewers agreed):
- Booleans tautological for shipped (always true, otherwise not Shipwright-conform).
- Two sources of truth invite drift.
- Mechanism populated + `confidence: verified` is the discipline assertion.

Stubs may declare `confidence: inferred` to honestly admit
non-verification — they remain valid profiles, just less authoritative.

## Acceptance Criteria

- [ ] **AC-1 — Schema exists with v1.0 metadata.**
      `shared/profiles/deploy-profile.schema.json` defines a JSON-Schema
      (draft-2020-12) with `$id`, `$schema`, and root-property
      `profile_schema_version: "1.0"`. `$schema` field accepted at
      profile root (NOT rejected by `additionalProperties: false`).
      Companion `shared/profiles/deploy-profile-schema.md` documents
      every field with one-line semantics + cross-target examples + an
      "Adding a New Target" 3-step checklist + the
      "What discipline this schema enforces" explainer.

- [ ] **AC-2 — Schema covers required concerns.** Top-level fields:
      `target_id` (`^[a-z0-9-]+$`), `target_kind` (freeform string with
      documented recommended values: `paas-cloud`, `edge-platform`,
      `self-hosted-vm`), `description` (`minLength: 1`),
      `implementation_status` (`shipped` | `stub`), `confidence`
      (`verified` | `documented` | `inferred`, **required for ALL
      profiles**), `client` (object | null), `auth`, `environments`,
      `pre_deploy_safety`, `test_gate`, `migrations`, `smoke_test`,
      `rollback`, `known_gaps` (optional `[string]`).
      `additionalProperties: false` only at root + on stable leaves
      (auth-entry, env keys); `rollback`, `smoke_test`, `migrations`,
      `pre_deploy_safety` remain extensible.

- [ ] **AC-3 — `client` block is structured.** `client: { entrypoint:
      string, runner: "python" | "node" | "bash" } | null`. When
      `implementation_status: "shipped"`, `client` MUST be a non-null
      object AND `confidence` SHOULD be `verified`. When `stub`,
      `client` MUST be `null` AND `confidence` MUST be `documented` or
      `inferred`. Schema-doc clarifies `implementation_status =
      code-backed runtime support` (not "officially supported via
      manual workflow").

- [ ] **AC-4 — Auth specifies env-var NAMES, never values.**
      `auth.required_env_vars: [{name, description}]`,
      `auth.optional_env_vars: [{name, description}]`.
      `name` constrained by `^[A-Z][A-Z0-9_]*$`. `description` and
      `name` both `minLength: 1`. Schema-doc and every profile header
      say explicitly: *the schema accepts ENV variable names; literal
      secrets must never appear in profile JSON.* Validator-level
      semantic check: no env-var name appears in both required and
      optional lists; no name appears twice in either list.

- [ ] **AC-5 — Rollback section: mechanism only (no discipline
      booleans).** `rollback` sub-block carries
      `revertable_strategy_dev`, `revertable_strategy_prod`,
      `auto_trigger`, `operator_interface`,
      `manual_procedure_reference`, `data_rollback_strategy`. All as
      strings with documented-recommended-values (not strict enum).
      Schema requires that shipped profiles populate all six fields
      with non-empty strings. `manual_procedure_reference` is
      explicitly defined in schema-doc as
      *documentation-only freeform reference (CLI command, doc URL,
      or prose description); never executed by Shipwright runtime*.

- [ ] **AC-6 — `environments` modeled as patternProperties + required.**
      `patternProperties: { "^[a-z][a-z0-9-]*$": <env-shape> }`,
      `required: ["dev", "prod"]`. Permits future env names
      (preview, staging, uat) without schema bump. Each env-shape
      object has `url_pattern` (`minLength: 1`), `confirmation`
      (`none` | `user`).

- [ ] **AC-7 — Migrations: if/then conditional, no "n/a" string.**
      When `migrations.supported: false`, schema FORBIDS
      `dev_strategy`, `prod_strategy`, `verify_after_apply` (or
      requires them to be `null`). When `true`, all three required.
      Removes the "n/a" string-as-enum-value pattern.

- [ ] **AC-8 — Three reference profiles ship with `$schema` link.**
      `shared/profiles/deploy/jelastic.json` (status `shipped`,
      `confidence: verified`), `shared/profiles/deploy/vercel.json`
      (status `stub`, `confidence: documented`),
      `shared/profiles/deploy/compose-vps.json` (status `stub`,
      `confidence: documented`). Each profile's first JSON field is
      `"$schema": "../deploy-profile.schema.json"`. Each profile may
      include `known_gaps: [string]` for honest limitations.

- [ ] **AC-9 — Validator: library + CLI split.** Pure validation
      function in `shared/scripts/lib/deploy_profile_validator.py`:
      ```python
      def validate(
          profile: dict,
          schema: dict,
          *,
          profile_path: Path | None = None,
          strict: bool = False,
          repo_root: Path | None = None,
          known_target_ids: set[str] | None = None,
      ) -> list[ValidationError]
      ```
      Pure (no side effects beyond reading file existence in `--strict`
      mode if `repo_root` provided). CLI wrapper in
      `shared/scripts/tools/validate_deploy_profile.py` handles file
      I/O, path resolution, error formatting, duplicate-target_id
      tracking across `--all` runs.

- [ ] **AC-10 — Validator handles documented edge cases.**
      Error format: `FAIL <profile-file> :: <json-pointer> :: <message>`.
      Multi-error reporting (all errors per file). CLI flags:
      `--profile <path>`, `--all`, `--profiles-dir <path>`, `--strict`,
      `--repo-root <path>`. Argument validation: `--profile + --all`
      → usage error exit 2. Filename ↔ `target_id` consistency check.
      Duplicate `target_id` across `--all` profiles fails. Empty
      `--all` directory → exit 0 with warning. `--all` is
      non-recursive, skips symlinks, skips hidden files (starting `.`),
      skips `*.schema.json`. `jsonschema` configured to disable
      remote `$ref` resolution.

- [ ] **AC-11 — Validator semantic checks (cross-field invariants).**
      Beyond JSON-Schema structure: (a) shipped profiles MUST have
      `confidence: verified`; (b) stub profiles MUST have
      `confidence: documented` or `inferred`; (c) shipped profiles
      MUST have non-null `client`; (d) `client.entrypoint`, when
      present, must be repo-relative (no `..`, no absolute path); (e)
      `--strict` mode: `(repo_root / client.entrypoint).resolve()` MUST
      be `is_relative_to(repo_root)` AND `.is_file()`; (f) duplicate
      `target_id` across profiles fails; (g) duplicate env-var name
      within or across required/optional lists fails. Each violation
      emits a `ValidationError` with descriptive message.

- [ ] **AC-12 — Validator tests cover full surface.**
      `shared/tests/tools/test_validate_deploy_profile.py`:
      Library-level (in-process):
      (a) all three real profiles pass via `validate()` directly,
      (b) missing required field fails with field path,
      (c) `additionalProperties: false` violation fails,
      (d) stub with non-null `client` fails,
      (e) shipped with null `client` fails,
      (f) shipped with `confidence: inferred` fails (semantic rule),
      (g) stub with `confidence: verified` fails (semantic rule),
      (h) filename ↔ target_id mismatch fails,
      (i) duplicate target_id across profiles fails,
      (j) duplicate env-var name within required list fails,
      (k) env-var name violating regex fails,
      (l) empty string in required string field fails,
      (m) `migrations.supported: false` with strategy fields fails,
      (n) `--strict` with absolute `client.entrypoint` fails,
      (o) `--strict` with `..` traversal in entrypoint fails,
      (p) `--strict` with valid path passes; `--strict` with bogus
      path fails,
      (q) `$schema` field in profile is accepted (not flagged),
      (r) `known_gaps` field accepted as optional array.
      CLI-level (subprocess, sparing):
      (s) happy-path `--all` exits 0,
      (t) malformed JSON file exits 1 with descriptive message,
      (u) nonexistent path exits 1,
      (v) `--profile + --all` exits 2 (usage error),
      (w) empty profiles dir exits 0 with warning.
      All other CLI behavior tested via in-process `main()` with
      `unittest.mock.patch('sys.argv', ...)` to keep test suite fast.

- [ ] **AC-13 — Discipline section in deploy SKILL.md.** New top-level
      section `## Rollback-Discipline (Universal)` placed between
      `## Manual Rollback (--rollback)` and `## Reference Documents`.
      Documents the three patterns + introduces Deploy Profiles as
      first-class concept. Reference list updated with
      `rollback-discipline.md`. Discusses Application-tier vs
      Data-tier rollback as a sub-concern of Pattern 1; the
      `data_rollback_strategy` field encodes the target's stance.

- [ ] **AC-14 — Pattern × target mapping.** New file
      `plugins/shipwright-deploy/skills/deploy/references/rollback-discipline.md`
      with per-pattern section (Revertable / Provenance / Procedure):
      Discipline statement (1 paragraph), Mapping table (4 columns:
      Concern / Jelastic / Vercel / Compose-VPS), Conformance check
      (1 paragraph: how does a new target prove it satisfies the
      pattern via the profile schema?). Plus "Status today" callout,
      "Adding a real target" 3-step checklist (matches schema-doc),
      "Known gaps" caveat-block (Vercel custom aliases not auto-rolled,
      Vercel auto_trigger off, Hobby plan rollback range limit,
      Compose-VPS mutable-tag setups out of scope).

- [ ] **AC-15 — Existing references cross-link.**
      `references/rollback-strategy.md` gets a 3-line header pointing
      to `rollback-discipline.md` + jelastic profile.
      `references/deploy-flavors.md` gets a similar header pointing
      to declarative profile location; Flavor-Interface section
      preserved.

- [ ] **AC-16 — guide.md cross-references the discipline.**
      `docs/guide.md` Section 4.9 (Deployment) gains 1 paragraph;
      Section 5 (Stack Profiles) gains 1 paragraph cross-referencing
      Deploy Profiles.

- [ ] **AC-17 — Validator passes in CI-equivalent run.**
      `uv run shared/scripts/tools/validate_deploy_profile.py --all`
      exits 0. Same with `--strict --repo-root <repo>` exits 0
      (Jelastic profile's `client.entrypoint` resolves to a real
      file).

- [ ] **AC-18 — Reader without Jelastic context understands the
      discipline.** Acceptance test (manual): a reader who has never
      touched Jelastic reads `rollback-discipline.md` +
      `shared/profiles/deploy/vercel.json` and can articulate
      (a) what every target must satisfy, (b) how those satisfaction
      rules are encoded in a Deploy Profile, (c) what they would have
      to write to contribute a real Vercel client.

- [ ] **AC-19 — `jsonschema` dep declared in shared scope.** Verify
      `jsonschema>=4.18` is declared in the appropriate `pyproject.toml`
      that owns `shared/scripts/`. Run `uv sync` after adding if
      missing. Lockfile committed.

- [ ] **AC-20 — Repo compatibility scan.** Before commit:
      `grep -rn 'shared/profiles/\\*.json'` and similar to catch any
      stack-profile loader scanning the flat directory. Verify the
      new `shared/profiles/deploy/` subdirectory does not break
      existing consumers. Document scan result in iterate ADR.

## Affected FRs

Self-iterate mode — no FR map exists for the Shipwright monorepo.
Phase-0 spec source: `.shipwright/reviews/phase0-iterates.md` Iterate 2.

## Out of Scope

- **No Jelastic code refactor.** `jelastic_client.py` and `rollback.py`
  unchanged.
- **No SKILL.md flow refactor.** Steps B-5 untouched; Discipline
  section additive only.
- **No Stack-Profile schema change.** `deploy.target = "jelastic"`
  remains a string.
- **No live Vercel or Compose deploy capability.**
- **No coverage of Coolify / Dokku / Caprover / Kubernetes /
  Docker Swarm.**
- **No multi-auth-modes per target.**
- **No `enabled: bool` pattern on `test_gate`/`smoke_test`.**
- **No Vercel preview-vs-prod distinction in schema** — but
  patternProperties pattern allows future addition without schema bump.
- **No `deprecated` implementation_status value.**
- **No file-existence check for `client.entrypoint` in default
  validator mode.** Only `--strict` checks.
- **No automated docs↔profile conformance test.**
- **No `evidence: {basis, references}` structured provenance field**
  — `known_gaps` + Description-prose adequate for v1.
- **No `deployment_model` higher-level classification field.**
- **No severity levels in ValidationError** — errors only, no
  warnings (YAGNI).

## Risks

1. **Vercel-stub fidelity.** Stub fields derived from 5 official
   Vercel docs pages. `confidence: documented` honestly reflects this.
   Known gaps captured in `known_gaps` field + description.

2. **Schema premature crystallization.** Validated against 1 shipped
   + 2 stub targets. Mitigation: `additionalProperties: false` only
   at root + leaf objects; sub-blocks extensible; mechanism fields
   are strings with recommended values, not strict enums;
   `profile_schema_version: "1.0"` allows v2.0 without breaking v1
   profiles.

3. **Schema drift from hardcoded Jelastic values.** SKILL.md still
   hardcodes Jelastic constants. Migration to profile-as-runtime-source
   is a future iterate. Mitigation: explicit "Status today" callout
   in discipline doc.

4. **`shared/profiles/` structure additive change.** New
   `shared/profiles/deploy/` subdirectory could break tooling.
   Mitigation: AC-20 explicit grep-scan before commit; schema sibling
   at `shared/profiles/deploy-profile.schema.json` (not in `deploy/`)
   intentional so glob-loaders don't validate it as a stack profile.

## Reflection Notes (filled at finalize)

_Filled during F3a after build is complete._
