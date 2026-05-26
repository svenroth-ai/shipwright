# Step C — Interview (AskUserQuestion, only when Layer 1 is unsure)

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
