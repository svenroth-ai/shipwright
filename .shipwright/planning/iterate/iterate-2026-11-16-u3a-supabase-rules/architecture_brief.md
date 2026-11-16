# Architecture Brief: supabase-nextjs architecture rules as rule objects (U3a)

## Campaign context (read this first)
This is unit U3a of a six-unit campaign in this repository, built serially. U1 is MERGED: `shared/scripts/profile_architecture_rules.py` defines the rule object (id, text, why, enforcement from the constitution's closed vocabulary, `lint` fragment or `mechanism` list or neither), the loader and validation. U2 is being built concurrently in another worktree: a render tool that reads the rules of the resolved profile and writes them into each project's `conventions.md`. U3b (next) writes an ESLint config template that carries the `lint` fragments authored here; U4 (plugin-project profile), U5 (this repo's own profile) and U6 (reviewer instruction) follow and consume the same rules. So consumers of this change exist as scheduled work in the same repo (campaign brief section 3); this unit is the first real producer of rule objects.

## The problem
The six `supabase-nextjs` architecture rules are plain sentences that nobody can check or render. Two of them (Supabase client only via `src/lib/supabase/`, no `fetch()` in components) are mechanical and can be expressed as lint rules; four are judgement or not yet checkable. The shipped template examples also break the rules they sit next to: test templates import `createClient` from `@supabase/supabase-js`, and both API route examples write to the database directly. Four rules are also duplicated as hand-written prose in templates, with different paths.

## What already exists here
- U1's rule object and loader; `supabase-nextjs.json` with the six sentences; `conventions.md.template` and `.claude/rules/*.md` templates with code examples and duplicated prose; `integration-helpers-supabase.ts.template`.
- No ESLint config template exists (U3b).

## What would newly, permanently exist
- Six rule objects in `supabase-nextjs.json`; two carry an ESLint flat-config fragment (`no-restricted-imports`; `no-restricted-globals` + `no-restricted-properties`), class `validator`.
- Template examples changed so API routes delegate DB access to a helper in `src/lib/supabase/`; duplicated prose removed.
- A committed fixture tree built from the template examples, and a drift test that applies the profile's own lint fragments (small emulation limited to the three ESLint rules used) to it.

## Options on the table
- A (chosen): import-based client rule + fetch rule as lint fragments; judgement rules instruction only; fixture tree + drift test.
- B: regex/home-grown checker for the rules (deferred by campaign decision 2.7).
- C: keep sentences, only fix the template examples.
- D: do nothing now; author rules together with the ESLint template in U3b.

## Constraints that are not negotiable
Rule shape must satisfy U1's loader; `lint` fragment shape is frozen (eslint block with non-empty `rules`). No new FRs. Do not touch U2's files (render tool, project step 7, adopt writer, docs/stack-profiles.md).
