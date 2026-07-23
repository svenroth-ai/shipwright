# Step C — Interview (AskUserQuestion, only when Layer 1 is unsure)

> **Follow the shared elicitation method.** The grilling discipline — one
> question at a time each with a recommended answer, **facts looked up in the
> code rather than asked**, terms challenged against the glossary, edge-case
> stress-tests, `CONTEXT.md` + ADR capture, and the **coverage checklist that is
> not finished until every context dimension is answered or recorded `Basis:
> assumed`** — is binding and lives in `shared/requirement-elicitation.md`. For
> adopt the "look it up first" rule is Layer-1 detection (below); the interview
> then spends its budget only on what the code cannot answer, and on **confirming
> the requirements derived from the code** in business language.

Ask **one question per turn** and only when the answer cannot be
inferred from Layer 1. Examples:

- profile.confidence < 0.6 → which stack profile?
- scope ambiguity (both `src/` and `bin/`) → full_app | library | cli?
- nested_projects → include / exclude / adopt-separately (always ask)
- no test frameworks detected → mark test-complete or pending?
- no build command detected → ask for the explicit command

Also present the `enrichment.product_description` to the user once, so
they can edit before it lands in CLAUDE.md/spec.md.

See [interview-protocol.md](interview-protocol.md) for the full
when-to-ask-vs-infer rules.
