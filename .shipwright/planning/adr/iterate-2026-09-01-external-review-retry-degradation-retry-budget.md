# External-review retry budget & partial degradation

## Problem

`shared/scripts/tools/external_review.py`'s OpenRouter/OpenAI call path never
retried a provider reply that came back HTTP 200 with empty or truncated
content — that is not a transport error, so it was invisible to the OpenAI
SDK's own transport-level retry. `llm_client.max_retries` and
`llm_client.retry_codes` existed in `shared/config/external_review.json` but
were either unused (`max_retries` was loaded but never passed anywhere) or
unwireable (`retry_codes`: the SDK's retry-eligible status set — 408/409/429/
>=500 — is hardcoded in a private `_should_retry` method with no public
customization API, confirmed against the installed `openai==2.44.0`). One
transient empty reply therefore became the permanent result for a reviewer
arm: DeepSeek's leg silently degraded across every sampled iterate run from
2026-08-13 to 2026-08-31 while GPT alone carried the cascade, with nothing in
the CLI output distinguishing that from "DeepSeek agreed with GPT."

## Decision

- Retry the completion call while `classify_reply` keeps returning
  `degraded` (empty content, or a finish_reason indicating a cut-off/
  incomplete reply), for up to `llm_client.max_retries` retries — the SAME
  value now also passed to the `OpenAI()` client constructor for the SDK's
  own transport-level retry (429/500/503).
- `retry_codes` is deleted (dead, unwireable — see Problem).
- A mixed result — one reviewer arm degraded, another succeeded — is now
  reported as `partially_degraded: true` / `partially_degraded_legs: [...]`
  in the CLI's JSON output, plus a loud stderr warning banner. `success` and
  the exit code are unaffected (one opinion is enough to proceed) — this is
  visibility, not a new failure mode.
- A partial degradation auto-files a triage card
  (`external_review_degradation` source), deduped per `(provider, leg)` per
  24h via `append_triage_item_idempotent`, so a repeated failure doesn't spam
  the tracked backlog. Filing is per-leg and best-effort: one leg's filing
  failure does not suppress filing for another, and a filing failure never
  affects the review gate's own exit code.

## One retry budget, not two

The first implementation (post internal doubt-review, Stage 3) decoupled the
app-level degraded-reply retry into its own small fixed constant
(`DEGRADED_REPLY_RETRIES = 1`), independent of `llm_client.max_retries` —
motivated by a real concern: reusing one config value for both the SDK's
transport retry and the app-level content retry could compound
multiplicatively, up to `(max_retries+1)**2` real network calls for a leg
that both errors transiently and degrades on content.

The external review cascade (GPT, `openai` leg) correctly flagged that this
violated the fix's own AC1 ("budgeted by `llm_client.max_retries`"): a
hardcoded app-level constant means changing the shipped config has no effect
on the failure mode this change exists to fix — the same "config doesn't
control behavior" bug this PR was written to close, just relocated.

**Resolution:** use `llm_client.max_retries` directly as the app-level
degraded-reply retry count too (`retrying_completion(..., max_retries=...)`).
The worst-case bound of `(max_retries+1)**2` is accepted rather than
engineered around with a second knob, because it is rarely reached in
practice: a persistent transport fault almost always ends by the SDK
*raising* once its own retry budget is exhausted (an exception on any
attempt, including the last, is NOT retried by the app-level loop — it
propagates unchanged), rather than by returning HTTP 200 with degraded
content on every attempt. The narrow tail the bound actually covers — a
fault that keeps resolving to "200 OK, but empty/truncated" across several
attempts — is exactly the shape this fix targets, and a shipped
`max_retries` of 2-5 keeps the worst case at 9-36 calls, not unbounded.

## Rejected alternatives

- **Separate hardcoded app-level budget** (the first implementation): tried,
  then reverted — it satisfies the compounding concern but reintroduces a
  config-vs-behavior mismatch for the exact axis (retry count) this PR is
  about.
- **Wiring `retry_codes`**: not viable — no public OpenAI SDK API accepts a
  custom retryable-status-code list; the field only misled editors into
  thinking it did something. Deleted instead of kept as inert documentation.
- **Capping the app-level loop at `min(max_retries, small_constant)`**: adds
  a second implicit knob (the cap) without a corresponding config surface —
  rejected for the same reason as the separate hardcoded budget, just softer.

## Evidence

The `partially_degraded` detection was live-validated by the external review
cascade's own run for this change: DeepSeek's leg returned "provider
returned an empty reply" (`status: degraded`) while GPT succeeded, the CLI
correctly reported `partially_degraded: true` / `partially_degraded_legs:
["deepseek"]`, and the wired-in auto-filing produced triage card
`trg-d920e1ab`.
