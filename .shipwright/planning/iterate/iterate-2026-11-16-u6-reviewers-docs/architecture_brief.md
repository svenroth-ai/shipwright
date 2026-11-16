# Architecture Brief: the code reviewer reads the rendered architecture rules (U6)

## Campaign context (read this first)
This is unit U6, the last of a six-unit campaign in this repository, built serially. Merged: U1 (rule object, loader, validation), U2 (`render_architecture_rules.py` writes a profile's rules into a project's `conventions.md` in one marked block), U3a/U3b (supabase rules and ESLint template), U4 (bundled `claude-plugin` profile with plugin-project rules), U5 (Shipwright's own project profile, whose rules are now rendered into this repo's `conventions.md`). U6 is the consumer side: until now the rules are written into `conventions.md` but nothing that reviews a diff is told to read them. Operator decision (campaign brief section 3/U6): the build plugin's `code-reviewer` (also used by iterate and campaign review) gets one instruction to check the diff against that block, the context-loading matrix is updated, and a how-to-add-a-rule section is written.

## The problem
Rules reach `conventions.md`, but the reviewer that sees every diff (build sections, iterate, campaign sub-iterates) does not check against them, so a violation of a rule that no linter or hook enforces is only caught if the author remembers it.

## What already exists here
- The rendered, marked rules block in `conventions.md` (rules marked instruction-only where no mechanism runs); `render_architecture_rules.py --check` exits 1 for a stale block and 3 for damaged or duplicated markers.
- `code-reviewer` agent: 5-axis review, tools Read, Grep, Glob, input = spec file + diff file; build and iterate spawn sites pass only those two paths.
- `conventions.md` is a union-merge file, so a parallel merge can leave a stale or duplicated block.

## What would newly, permanently exist
One short section in the existing agent prompt (about 13 lines, file stays under the 400-line cap), one pin test, one row in the context-loading matrix, one docs section with example rules that a test loads with the real loader, and a link from the changelog pilot's P1 plan.

## Options on the table
- A: the reviewer reads `conventions.md` itself (Read tool), checks per rule id, treats instruction-only rules as judgement, flags a duplicated or stale block.
- B: pass the rules block as a third input at every spawn site (build, iterate, campaign).
- C: do nothing; rely on linters and hooks for the mechanical rules.
- D: a script that extracts the block and hands it to the reviewer.

## Constraints that are not negotiable
No new FRs. The agent file must not grow past the runtime-prompt cap or its bloat baseline. A mechanism counts as enforcement only if something invokes it; judgement rules need a cited rule and line before a finding.
