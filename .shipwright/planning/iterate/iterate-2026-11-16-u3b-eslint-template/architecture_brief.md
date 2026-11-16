# Architecture Brief: ESLint config template for Supabase scaffolds (U3b)

## Campaign context (read this first)
Unit U3b of a six-unit campaign in this repository, built serially. Merged: U1 (rule object, loader, validation), U2 (render tool writes a profile's rules into each project's `conventions.md`), U3a (the six `supabase-nextjs` rules as rule objects; two are mechanical `validator` rules carrying an ESLint flat-config fragment in the profile; a committed fixture tree of the templates' examples; a drift test that checks the fixture with a small Python emulation of three ESLint rules). Following: U4 (plugin profile), U5 (this repo's own profile), U6 (code-reviewer reads the rules). Decision 4.5 of the campaign brief (operator, settled) says the ESLint template is built here.

## The problem
The two lint fragments exist only inside the profile JSON. No new project receives an `eslint.config.mjs`, so the rules marked `validator` are checked by nothing in a scaffolded project, and the Python emulation is the only thing that exercises the fragments (it is not ESLint).

## What already exists here
- Profile fragments (`lint.block`: files, ignores, rules) for `supabase-client-through-helpers` and `no-fetch-in-components`.
- The project skill's scaffolding step writes CLAUDE.md, conventions.md and `.claude/rules/*.md`; no lint config.
- Fixture tree + Python emulation test.

## What would newly, permanently exist
- `shared/templates/eslint/eslint.config.mjs.template`: flat config with the typescript-eslint parser block (needed for `allowTypeImports`) followed by the two fragments, last, delimited by marker comments.
- One short step in the project skill's scaffolding reference: write the file into new `supabase-nextjs` projects when none exists.
- A drift test (always runs) that each profile fragment equals the template's marked block and the parser block precedes them; a real-ESLint test over the fixture and seeded violations that skips without Node/npm (replaces the Python emulation).

## Options on the table
- A (chosen): static template file with the fragments pasted between markers, equality pinned by a test.
- B: generate the config from the profile at scaffold time with a tool (single source, no duplication).
- C: do nothing; leave the fragments in the profile only.

## Constraints that are not negotiable
Fragments in the profile stay the source of truth for their content; no new FR; scaffold step must not interpolate values into a shell command.
