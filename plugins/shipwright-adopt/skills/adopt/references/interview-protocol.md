# Interview Protocol — When to Ask, When to Infer

## Defaults: infer, don't ask

Layer 1 + Layer 2 together should answer the vast majority of questions
without any user interaction. Only fall back to `AskUserQuestion` when
all of the following are true:

1. The answer cannot be inferred deterministically from Layer 1
2. Layer 2 (Claude inline) also couldn't provide a confident answer
3. The question affects a **strategic** decision (profile, scope,
   nested-projects handling) — not a cosmetic one

## Strategic questions (always ask)

| Condition | Question |
|---|---|
| `nested_projects[]` non-empty | "Found nested project `<path>`. Options: include / exclude (recommended) / adopt separately" |
| `profile.confidence < 0.6` and no `--profile` flag | "Which stack profile best matches? [top 3 candidates + `generic`]" |
| `src/` + `bin/` both present and no `--scope` flag | "Is this a `full_app`, `library`, or `cli`?" |
| No test framework detected | "No tests found. Mark test-phase complete anyway or leave as pending for later?" |
| No `dev`/`build` command | "How do you build/run this project? (e.g. `npm run build`, `cargo build`)" |

## Content review (once, at the end of Layer 2)

Before writing artifacts, present `enrichment.product_description` to
the user with two options:

- "Accept as-is" (recommended if description looks correct)
- "Edit" → open interactive edit via AskUserQuestion with the current
  text as context

This is the **only** content-review beat — do not ask the user to review
every FR description individually. The Layer-3 `llm_review.py` step
catches hallucinations afterward.

## What NOT to ask

- Framework (`next`, `express`, `fastapi`) — inferred from manifests
- Test framework — inferred from dev-deps
- Node/Python version — inferred from engines/requires-python
- Folder layer assignment — inferred from convention names
- CI provider — inferred from `.github/` etc.
- File-by-file FR confirmation — takes too long, Layer-2 handles it

## Tone

Questions should be **neutral and concise**, not presumptive. Example:

Bad:
> "It looks like this is a Next.js Supabase app, right?"

Good:
> "Stack detection returned `supabase-nextjs` with confidence 0.82. Accept or choose another?"
