# Iterate: shipwright-adopt — scaffold `.gitleaks.toml` + harden `security.yml.template`

- **run_id:** `iterate-2026-06-07-adopt-gitleaks-allowlist`
- **Intent:** CHANGE (defect-class: every adopted repo's first Security Scan is a guaranteed false-red)
- **Complexity:** medium (user-confirmed; classifier said trivial@0.6 — keyword-based, under-scoped)
- **Spec Impact:** MODIFY adopt scaffolding behavior (additive `.gitleaks.toml` deliverable; no artifact-schema change)
- **Triggering principle:** `trg-27b6f6ba`; empirically proven on leadwright 2026-06-07 (run `27086046885` RED → `27086178138` GREEN after adding `.gitleaks.toml`).

## Problem

`security.yml.template` runs `gitleaks detect --no-git` with **no `--config`**, so
gitleaks auto-loads `.gitleaks.toml` from the repo root *if present*. The hardened
critical-gate blocks on **any** gitleaks result. But adopt **never scaffolds**
`.gitleaks.toml`, so the built-in `sidekiq-secret` rule false-matches the magic-hex
placeholder `cafebabe:deadbeef` and every adopted repo gets a red, misleading
"secret leak" first run. Secondary: the template lags the monorepo `security.yml` +
webui on supply-chain hardening (gitleaks `wget|tar` without SHA256 verify;
`peter-evans/create-or-update-comment@v4` mutable tag).

## Acceptance Criteria

- **AC-1** `shared/templates/github-actions/gitleaks.toml.template` exists, identical
  in allowlist semantics to `shipwright-webui/.gitleaks.toml`: `[extend] useDefault = true`,
  `[allowlist]` with `regexTarget = "match"`, `regexes = ['''cafebabe:deadbeef''']`,
  `stopwords = ["cafebabe", "deadbeef"]`.
- **AC-2** `generate_adoption_artifacts.py` writes the template to `<root>/.gitleaks.toml`
  during adopt (beside the `security.yml` scaffold, Step E.13). **Never overwrites** an
  existing `.gitleaks.toml`.
- **AC-3** A scaffolder test (mirroring `test_security_workflow_scaffold.py`) asserts:
  (a) created from template on a clean repo; (b) pre-existing file left untouched;
  (c) written content carries the `cafebabe`/`deadbeef` allowlist; (d) idempotent.
- **AC-4** `security.yml.template` hardened: gitleaks SHA256-verified download
  (`GITLEAKS_SHA256` pinned, `sha256sum -c` before extract) and
  `peter-evans/create-or-update-comment@71345be0265236311c031f5c7866368bd1eff043  # v4`.
  `fetch-depth: 1` already correct — no change.
- **AC-5** `step-e-artifact-generation.md` documents the new `.gitleaks.toml` scaffold.
- **AC-6** After merge: `bash scripts/update-marketplace.sh` + `uv run scripts/check_plugin_cache_sync.py --strict`.
- **AC-7** (regression) A fresh adopt of a trivial repo → dispatch the scaffolded
  `security.yml` → green (no `cafebabe` red). Empirically already proven on leadwright;
  scaffolder-level coverage via the new test + subprocess pipeline test.

## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| `shared/templates/github-actions/gitleaks.toml.template` (new) | adopted repo `<root>/.gitleaks.toml` | TOML, auto-loaded by `gitleaks detect` from source root |
| `shared/scripts/lib/security_workflow.py` `GITLEAKS_CONFIG_*` constants (new) | scaffolder + drift test | Python constants (SSoT convention lock) |
| `gitleaks_config_scaffolder.scaffold_gitleaks_config` (new) | adopted repo working tree | file copy (never-overwrite) |
| `security.yml.template` (hardened) | adopted repo `.github/workflows/security.yml` | YAML workflow |

## Architecture decision (user-confirmed)

Dedicated `gitleaks_config_scaffolder.py` (mirrors `security_workflow_scaffolder.py`)
+ paths declared in the `shared/scripts/lib/security_workflow.py` convention lock as
`GITLEAKS_CONFIG_TEMPLATE_PATH` / `GITLEAKS_CONFIG_PATH` (single source of truth — the
convention lock's docstring forbids hard-coding paths). Drift test in
`shared/tests/test_security_workflow_convention.py` pins the new template + constants
(registry-driven SSoT meta-test rule: forward = constant resolves to file; the template's
required shape is pinned by the same test).

## Mini-Plan

1. TDD red — `plugins/shipwright-adopt/tests/test_gitleaks_config_scaffold.py` +
   drift assertions (`TestGitleaksConfigTemplate`, `TestSupplyChainHardening`) in
   `shared/tests/test_security_workflow_convention.py`.
2. Add `gitleaks.toml.template` (= webui allowlist, retitled generically).
3. Add `GITLEAKS_CONFIG_TEMPLATE_PATH` + `GITLEAKS_CONFIG_PATH` to `security_workflow.py`.
4. Create `gitleaks_config_scaffolder.py` (loads constants by file path like the
   security scaffolder; never-overwrite).
5. Wire `scaffold_gitleaks_config` into `generate_adoption_artifacts.py` beside Step E.13.
6. Harden `security.yml.template` (gitleaks SHA-verify block + peter-evans SHA pin).
7. Doc update + `update-marketplace.sh` + `check_plugin_cache_sync.py --strict` (post-merge).

**Alternative considered:** inline the copy in `generate_adoption_artifacts.py` with
hardcoded paths. Rejected — breaks the scaffolder-per-artifact pattern, violates the
convention-lock "never hard-code paths" rule, and is not unit-testable in isolation.

## Confidence Calibration

- **Boundaries touched:** (1) new template `gitleaks.toml.template` → adopted-repo
  `<root>/.gitleaks.toml` (TOML auto-loaded by `gitleaks detect --no-git`); (2) new
  SSoT constants in `security_workflow.py` → scaffolder + drift test; (3)
  `scaffold_gitleaks_config` → repo working tree (file copy, never-overwrite); (4)
  hardened `security.yml.template` → adopted-repo workflow YAML.

- **Empirical probes run:**
  - Ran the **real** `generate_adoption_artifacts.py` as a uv subprocess
    (`test_full_pipeline_e2e_via_subprocess`) → `.gitleaks.toml` is written at repo
    root, `results.gitleaks_config = {wrote:true, reason:"scaffolded"}`, content
    carries `useDefault = true` + `cafebabe:deadbeef`. Proves the wiring fires, not
    just the unit.
  - `yaml.safe_load` of the hardened template parses clean; `TestSupplyChainHardening`
    confirms `GITLEAKS_SHA256` + `sha256sum -c` present and `peter-evans@<sha>` pinned
    with no residual `@v4`.
  - `test_content_matches_template` proves the scaffolded file is byte-for-byte the
    template (drift guarantees carry into adopted repos).
  - `ruff@0.15.15` clean on all 7 changed Python files.
  - Leadwright 2026-06-07: run 27086046885 RED → 27086178138 GREEN after `.gitleaks.toml`
    added by hand — the production proof this scaffold automates.

- **Test Completeness Ledger:** _principle: testable ⇒ tested._

  | # | Behavior (this diff) | Disposition | Evidence |
  |---|---|---|---|
  | 1 | Scaffolds `.gitleaks.toml` when absent | `tested` | `test_writes_when_absent` ✓ |
  | 2 | Copies template byte-for-byte | `tested` | `test_content_matches_template` ✓ |
  | 3 | Written content carries cafebabe allowlist | `tested` | `test_written_content_has_cafebabe_allowlist` ✓ |
  | 4 | Never overwrites an existing file | `tested` | `test_idempotent_existing_file_preserved` ✓ |
  | 5 | Idempotent on repeat call | `tested` | `test_idempotent_when_called_twice` ✓ |
  | 6 | Fails loud (no half-write) on missing template | `tested` | `test_raises_loudly_when_template_missing` ✓ |
  | 7 | Adopt pipeline actually wires the scaffold | `tested` | `test_full_pipeline_e2e_via_subprocess` (real subprocess) ✓ |
  | 8 | SSoT constants resolve to a real template of the right shape | `tested` | `test_gitleaks_config_convention.py` (4 tests) ✓ |
  | 9 | `.gitleaks.toml` path is the root name gitleaks auto-loads | `tested` | `test_gitleaks_config_path_is_root_toml` ✓ |
  | 10 | Template gitleaks install is SHA256-verified | `tested` | `test_gitleaks_download_is_sha256_verified` ✓ |
  | 11 | peter-evans pinned to commit SHA (no `@v4`) | `tested` | `test_comment_action_pinned_to_commit_sha` ✓ |
  | 12 | Adopted repo's first **GitHub Actions** Security Scan goes green | `untestable` | `requires-external-nondeterministic-service` — needs a live GH Actions run; empirically proven on leadwright 2026-06-07 (red→green) |

  0 testable-but-untested rows. The single `untestable` row (12) carries a valid
  closed-vocab `reason_code` and is backed by the leadwright production proof.

- **Confidence-pattern check:**
  - *Asymptote (depth):* the error path (missing template) and the never-overwrite
    branch are both exercised, not just the happy path — depth is real, not assumed.
  - *Coverage (breadth):* unit (scaffolder) + integration (real subprocess) + drift
    (SSoT constants + template shape + supply-chain pins) cover producer, consumer,
    and convention-lock simultaneously. The only gap is the live-CI leg, which is
    external and already production-proven.
