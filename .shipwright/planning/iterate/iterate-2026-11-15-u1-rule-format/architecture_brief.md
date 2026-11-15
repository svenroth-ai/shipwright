# Architecture Brief: machine-readable architecture rules in stack profiles (format + loader + validation)

## Campaign context (read this first)
This change is unit 1 of a planned six-unit campaign, all in this repository, built serially, each unit merged before the next starts:
- U1 (this change): freeze the rule format, loader and validation.
- U2: a render tool that reads the rules of the resolved profile and writes them into each project's `conventions.md`. It consumes the loader and the rule object from U1.
- U3a: the six `supabase-nextjs` rules become rule objects (the real first producer), with `why` and `lint` fragments.
- U3b: an ESLint template carrying the `lint` fragments. U4: a new `claude-plugin` profile with plugin-project rules. U5: this repo's own project profile. U6: the code-reviewer agent checks the diff against the rendered rules.
U2, U3a, U4 and U5 each read the format U1 freezes. The order is settled (campaign brief section 3): the format is frozen first because a rule object that U2 renders and U3a/U3b/U4 author must have one shape. So the consumers exist as scheduled work in the same repository, not as speculation; U1 itself adds none.

## The problem
Only one stack profile (`supabase-nextjs`) carries architecture rules, as six plain sentences nobody can check or render, with no statement of how each rule is kept (linter, test, or instruction only). Other profiles say nothing. The follow-up units need a frozen, validated shape before they can render the rules to agents or generate lint config from them.

## What already exists here
- `shared/scripts/profile_model.py` / `profile_resolver.py`: profile loading and JSON-schema-lite validation (resolver at its 300-line cap).
- `shared/schemas/stack_profile.schema.json`: deliberately lax schema, no enum/oneOf support.
- `resolve_profile.py validate`: CLI that reports a profile as ok.
- `shared/scripts/lib/constitution_register.py`: closed `ENFORCEMENT` vocabulary and a drift-test pattern for per-rule "enforced how".
- `docs/stack-profiles.md`: user doc for profiles.

## What would newly, permanently exist (kept minimal)
- One new Python module next to `profile_model.py`: the rule object (id, text, why, enforcement, `lint` or `mechanism` or neither, note), shape validation, and a loader that also accepts the old string list.
- A table of allowed combinations: which enforcement class may carry a `lint` fragment, which needs a `mechanism` list, which carries neither (and then needs a note).
- A copy of the enforcement vocabulary with a drift test against the constitution register (a settled campaign decision: profiles must not import from the constitution's `lib/`).
- An explicit empty `architecture_rules` list in two profiles that have none (so "no rules" is distinguishable from "key never considered").
- A warning when a project profile shadows a bundled one that actually has rules and the shadowing one declares none.
- Loader result for one bad rule: that rule is dropped from the returned rules and reported as an error; the other rules and the profile stay valid. `validate` prints errors and the old-list warning; every other phase sees none of it.
- The six existing `supabase-nextjs` sentences stay as they are in U1 (U3a converts them), so U1 changes the behaviour of no project.
Nothing renders or enforces the rules inside U1.

## Options on the table
- A: Rule objects validated in a new Python module; schema types the key loosely; errors are phase-local messages.
- B: Rule objects validated by tightening the JSON schema (needs extending the schema checker with enum/oneOf).
- C: Keep plain sentences; record enforcement in a separate register file (like the constitution's).
- D: Do nothing now; define the format inside U2 together with its renderer.

## Constraints that are not negotiable
A wrong-shaped rule must not make a profile invalid for every phase (many phases load profiles). `shared/scripts/lib/` and `shared/contracts/` must not be edited. No behaviour change for any project.
