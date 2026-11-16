# Architecture Brief: keep the profile's lint rules in the project's eslint config through the build phase

## Campaign context (read this first)
Follow-up of the six-unit campaign "profile-architecture-rules" (units U1-U6 merged). A stack profile can declare architecture rules; for supabase-nextjs two rules carry an ESLint fragment (markers `// BEGIN architecture-rule: <id>`). /shipwright-project step 7 writes or merges an ESLint config template with those fragments at scaffold time (unit U3b). The Next.js app usually does not exist at that point; the build phase creates it later and create-next-app writes its own eslint.config.mjs.

## The problem
The scaffold-time config can be replaced (or never created); the fragments are lost and lint passes with no architecture rules. The only instruction to redo the merge sits in a project-phase skill file nothing reads during build.

## What already exists here
- Profile rules with `lint: {tool, target, block}`; a template carrying the same blocks (drift-tested).
- Phase verifiers (`verifiers/build_checks.py`) run by the phase validator at the end of build and by `verify_phase.py`.
- Instruction prose in step 7 for the merge (agent-judged).

## What would newly, permanently exist
One library module and one CLI under shared/scripts, one build verifier check, one sentence in the build skill, tests, docs.

## Options on the table
- A: a deterministic check plus a safe automatic merge tool; the check becomes a build-phase verifier finding.
- B: prose only: add the "repeat steps 2 and 3" instruction to the build skill.
- C: check only, no merge tool; the agent repairs by hand from the step 7 prose.
- D: make the build phase write the whole eslint config itself.
- E: do nothing; rely on review to notice.

## Constraints that are not negotiable
No new FRs; skill files are protected paths and stay minimal; no network or npm in default-tier tests; a missing rule must be a loud finding, never silent.
