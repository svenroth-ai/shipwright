# Architecture-rule lint blocks survive the build phase

Follow-up of campaign profile-architecture-rules, unit U3b (PR #1066). That unit wires the two supabase-nextjs rule fragments into the scaffold's eslint config, but the Next.js app is created later by the build phase and create-next-app writes its own config; the fragments were lost without a sound and the only instruction to redo the merge sat in a project-phase skill file nothing reads at build time.

## Decision

- `shared/scripts/eslint_architecture_rules.py` checks the project's `eslint.config.*` against the resolved profile: per rule `ok`, `missing`, `stale` (differs from the profile), `unpaired`, `outside` (beyond the exported array) or `shadowed` (config code after the last block). Marker and content checks need no parsing; the two position checks run only when the exported array is recognised.
- The same module repairs: missing blocks are appended as the last elements of the exported array (a later flat-config object wins for the same rule). Supported shapes are a closed list (`export default [..]`, `defineConfig([..])`, `module.exports = [..]`, or a named const of those, which is what create-next-app writes). Anything else, damaged markers, a config that already sets no-restricted-imports/globals/properties (step 3c is a decision) or a legacy `.eslintrc*` is refused with nothing written. The result is re-checked before the atomic write; package.json is never edited.
- Wiring: the build verifier gets the check `eslint_architecture_rules_present` in its own module (`verifiers/eslint_rules_check.py`; `build_checks.py` has about six lines of bloat headroom). It runs wherever the build verifier runs (phase gate, `verify_phase.py --phase build`); no hook, no new phase. Severity: missing, unpaired or outside is an ERROR once `package.json` exists (WARNING before the app exists); stale, shadowed and legacy-only are WARNINGs, because a block folded with an existing option differs from the profile on purpose (step 7, 3c).
- Prose: build Step 12 names the repair command; project step 7 points at the same tool for the deterministic part and keeps the judgement cases.

## Alternatives considered

- Prose only ("repeat steps 2 and 3" in the build skill): that is the mechanism that failed.
- Check only, repair by the agent from the step 7 prose: both external architecture reviewers (glm, openai, verdict revise) preferred it as smaller. Kept the tool because the unit's brief asks for a deterministic repair where cheap and safe, and it is closed-list and verified before it writes; the check stands alone if the tool is ever removed.
- The build phase writes the whole eslint config itself: takes over a file create-next-app and the user own.

## Known limits

The check proves presence, equality with the profile and position inside the exported array. It does not prove ESLint loads that file or that a rule is not switched off by other means. A Prettier-reformatted block reads as stale (a warning). `apply` adds no typescript parser (the check notes a missing one) and does not fold existing options. With more than one `eslint.config.*` the first in ESLint's lookup order is checked and the others are named in a note.

Internal plan review: Ran yes, 7 fixed, 2 disclosed. Internal architecture review: Ran yes, 5 fixed, 1 disclosed.
