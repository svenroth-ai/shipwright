# Iterate Spec: eslint-rules-survive-build

- **Run ID:** iterate-2026-11-16-eslint-rules-survive-build
- **Type:** bug
- **Complexity:** medium (operator-set)
- **Status:** implemented

## Goal
For supabase-nextjs projects the two architecture-rule lint fragments written at scaffold time are lost when the build phase creates the Next.js app and its own eslint config replaces the file; lint then passes silently. A deterministic check finds the missing fragments and a safe merge puts them back.

## Acceptance Criteria
- [x] AC36: Given a Supabase web app project whose lint configuration no longer carries the profile's architecture lint rules, when the build phase is checked, then every missing rule is reported as a failure that names the rule and the repair, a changed rule is only a warning, and the check passes once the rules are back.
- [x] AC37: Given the same project, when the repair is applied, then the missing rules are appended to the existing lint configuration without touching anything else, a second run changes nothing, and a configuration the tool cannot edit safely is reported and left untouched.

## Spec Impact
- **Classification:** none for FRs; two ACs added under FR-01.01 (the profile FR)
- **ADD:** none (no new FR)
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** restores the behaviour AC21 already promises (the profile's lint rules reach the project) across the build phase.

## Out of Scope
- Editing package.json (devDependencies stay the scaffold step's job; the check only warns).
- Non-eslint lint tools (ruff) and judgement parts of the scaffold step (legacy .eslintrc migration, folding existing no-restricted-* options).

## Design Notes
n/a (no UI).

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| create-next-app, project step 7, the repair tool (eslint.config.*) | the check tool, ESLint itself | JS flat config with marker comments |

## Confidence Calibration
- **Boundaries touched:** eslint.config.* (JS source text) written by three producers.
- **Empirical probes run:** create-next-app style configs (defineConfig array, plain array, CJS) through check and apply; apply output re-inspected; template drift against the profile.
- **Test Completeness Ledger:** see F5.
- **Confidence-pattern check:** idempotency and marker-damage cases covered by tests.

## Verification (medium+)
- **Surface:** cli
- **Runner command:** uv run shared/scripts/tools/check_eslint_architecture_rules.py --project-root <fixture>
- **Evidence path:** shared tests (pytest)

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** Option A is the right shape; the indirect `export default eslintConfig` form and a stale-as-error rule had to be fixed first.
- **Findings:** (1) high completeness, create-next-app exports through a named const: fixed, `_array_close` follows `export default <name>` to its one declaration, fixtures are the verbatim Next 15 and Next 16 files. (2) high architecture, stale blocks are legitimate after step 7 option folding: fixed, stale is a WARNING only, a folded block passes as warning (test). (3) medium, appending would silently override existing no-restricted-* options: fixed, apply refuses (step 3c stays a decision). (4) medium, typescript parser (step 3d): disclosed, the check prints a note, apply does not add a parser. (5) medium, no-config / legacy states: fixed, no config is an ERROR once package.json exists (WARNING before), legacy only is a WARNING, each pinned by a test. (6) medium, build_checks.py bloat headroom: fixed, the check lives in its own module, build_checks gets one import and one line. (7) medium, exact-text comparison breaks after Prettier: disclosed, a reformatted block reads as stale (warning, not an error). (8) low, JSON-only splice, atomic write, line endings: fixed (blocks come from json.dumps of the validated block, os.replace, CRLF kept). (9) low, guide and cache sync: guide has no entry for per-check verifier names (checked), cache sync is a post-push delivery step. (10) low, ledger field shapes: noted for F5.
- **Known limitations:** Prettier-reformatted blocks read as stale; no typescript parser is added by apply.
- **Status:** 7 fixed, 2 disclosed, 0 declined

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** Build a deterministic check; take the merge tool only if step 7 uses it too, else check-only.
- **Findings:** necessity low (B, D, E ruled out): accepted. smallest-option medium (C is smaller; A only with one merge path): fixed, step 7 prose now points at the same tool for the deterministic part and keeps the judgement cases. completeness medium (marker presence does not prove the rule is active): fixed in part, the check proves presence, equality with the profile and position inside the exported array and reports code after the last block as shadowing; "ESLint loads the file / rule not switched off elsewhere" is a documented limit. completeness low (undefined no-config/legacy/no-rules results): fixed, see above. security low (data-only splice): fixed. complexity-cost low (closed list of shapes): fixed, anything else is refused.
- **Known limitations:** see docs known limits.
- **Status:** 5 fixed, 1 disclosed, 0 declined

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-11-16-eslint-rules-survive-build/architecture_brief.md`
- **Verdicts:** glm=revise · openai=revise (no reject)
- **Smallest thing that would do (per reviewers):** option C: a check in the build verifier only, repair by the agent from the step 7 prose.
- **Findings:** both reviewers: the merge tool is a permanent second writer of the eslint config for a rare, recoverable event (rejected-with-reason below).
- **Reconciliation:** the operator's brief for this unit asks for a deterministic repair "where it is cheap and safe", and the repair prose in step 7 is exactly what failed (nothing reads it at build time and an agent redo is the silent path). The tool is kept small (closed list of shapes, refuses anything else, verifies before writing, never touches package.json) and the check itself carries no dependency on the editor, so the loud finding stands alone even if the tool is later removed. Step 7 now names the same tool, so there is one deterministic merge path, with the judgement cases left to the agent.
