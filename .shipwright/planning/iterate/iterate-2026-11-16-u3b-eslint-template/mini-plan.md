# Mini-plan U3b
1. Add `shared/templates/eslint/eslint.config.mjs.template` (typescript-eslint parser block, then the two fragments last, between BEGIN/END architecture-rule marker comments, JSON-valued).
2. Skill: one step in `step-7-scaffolding.md` "ESLint config (supabase-nextjs only)": copy the template to `eslint.config.mjs` if absent, else merge the two blocks last; devDependencies named; no shell command, no quoted placeholders. Doc-level test: no placeholder inside double quotes in the new step.
3. Tests: drift (fragment == template block, order, parser, typescript-eslint dependency named); replace the emulation with a real ESLint run (tmp dir, npm install eslint + typescript-eslint, fixture + seeded violations; skip without node/npm). Keep fixture==template tests.
4. Evidence: one real ESLint run recorded in the iterate folder.
5. FR-01.01 AC21-AC22 criteria; docs touch (stack-profiles/guide pointer if needed); changelog drop.
