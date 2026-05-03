# Iterate Spec: adopt-env-local-scaffold

- **Run ID:** iterate-2026-05-03-adopt-env-local-scaffold
- **Type:** feature
- **Complexity:** medium
- **Status:** draft

## Goal

Close the gap that brownfield onboarding via `/shipwright-adopt` never
scaffolds a `.env.local` even though the framework itself reads from it
(external review, profile-required env vars). Adopt should write a
commented placeholder `.env.local` deterministically, refuse to overwrite
an existing one, ensure `.gitignore` covers it, and the Step H handoff
should tell the user exactly which keys to fill in based on the active
profile.

## Acceptance Criteria

- [ ] **AC1 (deterministic scaffold).** `generate_adoption_artifacts.py`
  invokes the `.env.local` scaffold after the run-config is written and
  before the `seed_adopt_compliance` step. The result is exposed under
  `results["env_local"] = {"action": "created"|"updated"|"unchanged"|"skipped",
  "path": ".env.local", "vars": [...]}` so downstream consumers (Step H
  handoff, integration tests) read it deterministically rather than
  re-stat'ing the file.
- [ ] **AC2 (idempotent — never overwrites).** Re-running adopt against a
  project that already has a `.env.local` MUST NOT overwrite the file.
  - If the file exists and contains all required keys (active or
    commented): `action == "unchanged"`, no writes. Whether values are
    filled or still placeholder is independent of `action` — see AC6.
  - If the file exists but is missing some keys: append-only, action
    `updated`, existing key/value pairs preserved byte-for-byte.
  - The detector matches `KEY=value`, `KEY="value"`, `KEY='value'`,
    `# KEY=...` (commented placeholder), and `export KEY=value`
    (POSIX-style). Whitespace around `=` is tolerated.
- [ ] **AC3 (`.gitignore` coverage with hard-stop).** Adopt ensures
  `.env.local` is matched by the project's `.gitignore` BEFORE creating
  the file.
  - If `.gitignore` is missing → create one with the entry.
  - If `.gitignore` exists and already matches `.env.local` (literal,
    `.env*.local`, or `.env.*.local`) → leave it alone.
  - If `.gitignore` exists but doesn't match → append the entry.
  - **Hard-stop:** if `_ensure_gitignore` raises (permission error,
    OS error), `init_env_file` MUST return `{action: "skipped",
    reason: "gitignore_enforcement_failed", error: <str>}` and write
    NOTHING to `.env.local`. Adopt surfaces this in `results["env_local"]`
    and the Step H banner shows a loud "env scaffold skipped — fix
    .gitignore permissions and re-run adopt" line.
- [ ] **AC4 (Layer-3 review key consistency, drift-protected).** The
  scaffolded `.env.local` lists the LLM review keys in the same order
  `external_review_config.py` falls back through them: `OPENROUTER_API_KEY`
  first (preferred), then `GEMINI_API_KEY` and `OPENAI_API_KEY`
  (alternatives). These keys MUST appear in EVERY scaffolded `.env.local`,
  regardless of which stack profile is active — they are framework-level,
  not stack-level. Implementation:
  - Hardcoded list in `validate_env.py` (module-level constant
    `_SHIPWRIGHT_FRAMEWORK_VARS`).
  - **Drift-protection test** asserts the hardcoded order matches the
    keys actually checked by `external_review_config.is_external_review_enabled`
    (parsed from source via the same canonical names). If a future
    edit to `external_review_config.py` changes the fallback order
    or adds a key, the test fails loud.
  - Gating: framework merge is opt-in via `init_env_file(...,
    include_framework: bool = False)`. Adopt passes `True`; the
    pre-existing CLI `--init` invocation keeps default `False` so
    global `phase=all` semantics for direct CLI users are unchanged.
- [ ] **AC5 (Step E.5 documented in SKILL.md).** A new explicit step
  between Step E (artifact generation) and Step F (compliance seeding)
  in `plugins/shipwright-adopt/skills/adopt/SKILL.md` documents the
  `.env.local` scaffolding behavior — what runs, what gets written,
  what stays untouched.
- [ ] **AC6 (Step H "Next steps" surfaces required keys).** The Step H
  handoff banner lists which env keys the user still needs to fill in,
  derived from the active profile's `required_env_vars` plus the
  framework-level review keys, NOT hardcoded. The banner block is
  rendered whenever `results["env_local"]["missing_keys"]` is
  non-empty — independent of `action`. So an `unchanged` outcome
  whose existing entries are all still commented placeholders STILL
  prompts the user. `missing_keys` is computed from the FINAL file
  state (every key whose value is empty or matches `_is_placeholder`),
  not just the newly appended subset.
- [ ] **AC7 (no key value leakage).** The scaffold writes only key NAMES
  and DESCRIPTIONS; never invents or fills in any value, including
  `localhost` URLs or test fakes. Every scaffolded entry is
  comment-prefixed (`# KEY=  # description`) so the file is inert until
  the user uncomments it.
- [ ] **AC8 (test-evidence).** New / extended tests cover at minimum:
  - **Unit (`shared/scripts/tests/test_validate_env.py`):**
    framework-vars rendered when profile is empty AND `include_framework=True`;
    framework-vars NOT rendered when `include_framework=False` (default);
    dedup when profile already lists a framework key (profile description
    wins, single entry); dedup when same key appears in build+plugin of
    the profile (first-occurrence wins); `export KEY=value` parses as
    "present"; placeholder-detection counts blank values as missing for
    `missing_keys`; idempotent re-run with framework keys (action=unchanged,
    file byte-equal); drift-protection — hardcoded framework order matches
    `external_review_config.py` fallback order; `_ensure_gitignore` raising
    OSError causes `init_env_file` to return action=skipped with
    `reason=gitignore_enforcement_failed` and `.env.local` is NOT written.
  - **SKILL.md snapshot (new file
    `plugins/shipwright-adopt/tests/test_skill_md_env_scaffold.py`):**
    asserts the new Step E.5 heading + body wording; Step H banner gains
    "Edit .env.local" line. Substring-based, not full-file equality.
  - **Adopt subprocess integration
    (`plugins/shipwright-adopt/tests/test_adopt_pipeline_subprocess.py`):**
    `created` path (no pre-existing `.env.local`); `unchanged` path
    (idempotent second run, byte-for-byte equal); `updated` path
    (pre-populate file with one of the three framework keys, assert
    only the missing two are appended and existing user content is
    preserved); `.gitignore` ends up with `.env.local`; the
    `payload["env_local"]` dict has the documented shape.

## Affected FRs

- None directly. `/shipwright-adopt` is framework-level — its own behavior
  doesn't sit under a project-level FR. The change is recorded as an
  ADR and as iterate evidence; the only spec touched is this iterate
  spec itself.

## Out of Scope

- **Filling secrets for the user.** Adopt never writes real values into
  `.env.local`, ever. Operators copy values from password manager / 1Password.
- **Profile-specific deploy/build keys for the shipwright monorepo
  itself.** This iterate runs against the `python-plugin-monorepo`
  profile (empty `required_env_vars`), so the only keys scaffolded
  here are the three framework-level review keys. Filling out
  `vite-hono` or other profiles' `required_env_vars` is a separate
  follow-up.
- **`.env.example` checked-in convention.** Decision: NOT scaffolded by
  this iterate. `.env.local` already serves as the per-machine config
  surface; an `.env.example` would duplicate it without a single user
  benefit (nobody is cloning the shipwright repo for the first time
  outside an already-adopted state). Defer until there's a concrete
  ask. Documented as a deliberate non-goal in the ADR.
- **Greenfield `/shipwright-project`.** Greenfield projects flow
  through a different pipeline. Their env scaffold is a sibling
  problem; this iterate scopes itself to `/shipwright-adopt`.
- **`phase_parameters` v0.4 secrets surface (security plugin).**
  Foundation only — this iterate ensures every adopt-touched repo has
  a single canonical `.env.local` so the eventual `phase_parameters`
  work can read from there instead of inventing a second secrets
  source. Cross-reference in the ADR's "Forward-compat" section, no
  code in this iterate.

## Design Notes

- **Scaffold call site.** `generate_adoption_artifacts.py` ~ line 432
  (after `write_all` returns the configs and `shipwright_run_config.json`
  has been written, before `seed_adopted_event` and `install_suggest_iterate_hook`).
  Reason: `validate_env.init_env_file` needs `shipwright_run_config.json`
  to exist so it can read the `profile` field; running it after is the
  earliest safe point.
- **Framework-vars set, hardcoded in `validate_env.py`.**
  ```python
  _SHIPWRIGHT_FRAMEWORK_VARS = [
      {"name": "OPENROUTER_API_KEY",
       "description": "OpenRouter API key for external plan/iterate/code reviews "
                      "(preferred — single key for both Gemini and OpenAI)",
       "optional": True},
      {"name": "GEMINI_API_KEY",
       "description": "Google Gemini API key (alternative to OpenRouter)",
       "optional": True},
      {"name": "OPENAI_API_KEY",
       "description": "OpenAI API key (alternative to OpenRouter)",
       "optional": True},
  ]
  ```
  Order mirrors `external_review_config.py` lines 72-76 + 96-100 fallback chain.
  Section label in the rendered file: `# --- Framework / External Review ---`.
- **Dedup rule.** When `phase=all`, the existing `_collect_phase_vars`
  iterates over `["build", "deploy", "plugin"]`. Add a synthetic
  `Framework` section APPENDED after those, then dedup by `name` —
  if the profile already lists `OPENROUTER_API_KEY` under any phase,
  the framework-section entry is suppressed (the profile entry wins,
  preserving its custom description). Order within sections is preserved.
- **`results["env_local"]` shape (passes through to Step H banner).**
  ```json
  {
    "action": "created" | "updated" | "unchanged" | "skipped",
    "path": "<abs path to .env.local>",
    "missing_keys": ["KEY1", "KEY2", ...],
    "framework_keys": ["OPENROUTER_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"],
    "reason": "<populated only on action=skipped>"
  }
  ```
  - `missing_keys` is computed from the FINAL file state — every key
    whose value (after stripping comments / `export ` prefix) is empty
    OR matches `_is_placeholder`. Not just the newly added subset.
    This guarantees Step H prompts the user even on `action=unchanged`
    when the file still has commented placeholders from a prior adopt
    run.
- **No SKILL.md churn in unrelated sections.** Only the new Step E.5
  block and the Step H banner block are touched. All existing wording
  stays.

## Forward-compat (v0.4 phase_parameters)

The eventual `shipwright-security` `phase_parameters` work (memory note
`project_post_v030_followups.md`) needs a single canonical secrets
surface inside the target project. By making `.env.local` that surface
today and routing every plugin's secret read through `load_shipwright_env`
(`shared/scripts/lib/env.py`), the future `phase_parameters` machinery
can read from the same file rather than inventing a second source. The
ADR records this dependency explicitly so future-me reading the v0.4
roadmap finds the breadcrumb.
