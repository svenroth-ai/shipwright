# ADR: Stop sending codex-exec-only flags to `codex login status`

## Context

`is_codex_available()` called `codex login status --ignore-user-config --ignore-rules`.
Those two flags are only defined on `codex exec`, not on `login status` — the real
CLI rejects them there with exit code 2 ("unexpected argument"). The function's
blanket `returncode != 0` -> "not authenticated" check misclassified that CLI
usage error, so `is_codex_available()` ALWAYS reported Codex unavailable
regardless of the operator's real login state, silently falling back to the
`openrouter` provider. This made the just-shipped Codex-CLI GPT-review-leg
feature (PR #672) non-functional in every repo that had opted into
`gpt_leg.provider: "codex"` (shipwright, shipwright-webui, leadwright). This
exact gap had been flagged, but never resolved or verified, as an untested
verification gap by GLM's review #4 on PR #672's own review cascade.

## Decision

Remove `--ignore-user-config`/`--ignore-rules` from the `codex login status`
subprocess call. Leave the classification branches (`TimeoutExpired`,
`OSError`, `returncode != 0`) untouched — they were already correct once the
argv stopped producing a false non-zero exit for a genuinely authenticated
operator.

## Consequences

`is_codex_available()` now correctly detects a genuinely authenticated Codex
CLI. Live-verified in this worktree against the real, authenticated binary:
`is_codex_available()` -> `(True, '')`, and `resolve_openai_route()` with
`gpt_leg.provider="codex"` -> `"codex"`. The three repos that already opted
into the codex provider will get a working Codex-CLI GPT-review-leg once this
merges and the plugin cache is synced.

## Rationale

Root-caused via live reproduction: `codex login status --ignore-user-config
--ignore-rules` exits 2 ("unexpected argument") against the real CLI, while
`codex exec` legitimately accepts and needs those same flags (kept unchanged
at that call site — `review_codex()`'s own `codex exec` invocation).

## Rejected alternatives

- Changing the `returncode != 0` classification logic itself to distinguish
  "usage error" from "not authenticated" — rejected as unnecessary complexity
  once the root cause (wrong argv) is fixed; the classification was already
  correct for the cases it's meant to handle (real auth failure, timeout,
  OSError).
