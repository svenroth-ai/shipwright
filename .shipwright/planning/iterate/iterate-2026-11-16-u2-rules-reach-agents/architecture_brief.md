# Architecture Brief: getting a stack profile's architecture rules to the agents that work in a project

## Campaign context (read this first)
This is unit 2 of a six-unit campaign in this repository, built serially (campaign brief section 3). Unit 1 is already merged: it froze the rule object (id, text, why, enforcement class, lint or mechanism, note) and a loader that returns the valid rules of a profile plus its errors. Units that follow consume this change: U3a turns the six `supabase-nextjs` sentences into rule objects (built concurrently), U3b adds an ESLint template for the lint fragments, U4 adds a plugin-project profile with rules, U5 gives this repo its own profile (and runs the render for it), U6 makes the code-reviewer agent check diffs against the rendered rules. Today nobody renders the rules: only `/shipwright-project` step 7 writes them into `conventions.md`, as prose the agent composes by hand, and `/shipwright-adopt` writes none, so in an adopted repo the rules reach no agent. The consumers exist as scheduled work, not speculation.

## The problem
Agents working in a project (new or adopted) never see the architecture rules of the project's stack profile unless a human or the scaffolding agent copies sentences into `conventions.md` by hand. In adopted projects they are never copied. Rules that are only instructions cannot be told apart from rules that are checked.

## What already exists here
- Loader/validator `shared/scripts/profile_architecture_rules.py` (U1) and `resolve_profile.py` (resolves project > user > bundled).
- `conventions.md.template` with a `{ARCHITECTURE_RULES}` placeholder that project step 7 fills from prose instructions.
- Adopt's `generate_adoption_artifacts.py`, which writes `conventions.md` from scratch (with a backup) and already holds the resolved profile.
- `profile_consumer.config_profile` (profile name from the run config).

## What would newly, permanently exist
One small shared tool, `render_architecture_rules.py`, which writes the rules into one marked block of `conventions.md` (replace-in-place, byte-identical on a second run, "none declared" line when empty, instruction-only rules labelled). Two call sites (project step 7 prose, adopt's generation script). The tool and its tests are kept correct by the repo's tests; the block itself is derived output, regenerated from the profile.

## Options on the table
- A: A shared render tool writing a marked block into `conventions.md`, called from project step 7 and from adopt.
- B: Keep step 7 prose filling the placeholder; teach adopt to do the same prose-style write (no shared tool).
- C: Agents read the profile JSON directly at run time (no copy in `conventions.md`).
- D: Do nothing; wait for U6 to make reviewers read the profile.

## Constraints that are not negotiable
Existing scaffolded/adopted projects must not be rewritten except by an explicit run; text outside the block must never be touched; the render comes from the resolved profile (bundled, user or project), nothing is committed as a render for other projects; adopt's artifact files are at their size baseline (no net growth allowed there).
