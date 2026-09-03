# Mini-Plan: Codex CLI as a second GPT review leg

## Chosen approach

Add one new leg function, `review_codex()`, beside `review_openrouter()` /
`review_openai()` in `shared/scripts/lib/external_review_default_legs.py`.
It shells out to `codex exec -m <model> --sandbox read-only --ephemeral
--cd <isolated tmp dir> -o <tmpfile>`, feeding it the exact same
system+user prompt text the API legs get (piped via stdin), and reads the
captured final message back through the *existing* `classify_reply()`
helper — the same empty/truncated-reply check every leg already uses. No
new output schema: the shipped reviewer prompts (`shared/prompts/*/system`)
already ask for free-form prose ending in one `SHIPWRIGHT_VERDICT: <verdict>`
sentinel line (`review_verdict.py::parse_verdict`), which is exactly what
Codex's own final-message text is. Running it in an isolated empty scratch
directory (not the real project root) keeps it seeing only the same
information the other two legs see — it does not roam the actual repo,
so the three reviewers stay comparable.

Model identity is locked through the existing
`external_review_routing.resolve_reviewer_model` mechanism: a new binding
`("openai", "codex") -> ("codex", "gpt-5.6-terra")` — same identity, same
model string as the OpenRouter/direct GPT bindings, different transport.
`shared/config/external_review.json` gets `models.codex` (identity-locked,
validated exactly like the others) plus a `codex.{timeout_seconds,
max_retries}` section (its own budget — an agentic CLI call is a different
transport than a metered HTTP completion, so it doesn't share
`llm_client`'s knobs).

Route selection is one new config field, `external_review.gpt_leg.provider`
(`"api"` default | `"codex"`), read via a new
`external_review_config.gpt_leg_provider()` helper — deep-merged from
`shipwright_iterate_config.json` through the existing per-project override
path, no new config-loading machinery. A new
`external_review_default_legs.resolve_openai_route()` combines that with
an env-key check and `is_codex_available()` to pick, per invocation:
`"codex"` (configured + available) | `"openrouter"` | `"direct"` |
`"none"`, with a graceful fallback (not a hard failure) when `"codex"` is
configured but unavailable.

Both consumers call this same resolver, then dispatch the "glm" and
"openai" legs independently (GLM's dispatch depends only on whether
`OPENROUTER_API_KEY` is set, unchanged from today) rather than the old
single `provider` string driving both legs together — this is the one
structural change to existing dispatch code, needed because the two legs
can now genuinely use different transports in the same pass. For every
config where `gpt_leg.provider` is left at its `"api"` default, the new
resolver reproduces the exact same routing decision the old code made
(verified against the existing test suite), so behavior for operators
without Codex is provably unchanged.

`external_review_degraded.is_degraded()` / `is_partially_degraded()`
currently gate on a hardcoded `_ATTEMPTED_PROVIDERS = ("openrouter",
"direct")` tuple — a "codex" (or any mixed-route) pass would silently never
be flagged degraded under that check. Generalized to derive "attempted"
from each leg's own `status` (already distinguishes `skipped` from
`degraded`/`error`) instead of the provider label — verified to reproduce
identical results for every existing test case, and now correct for any
future leg without another hand-maintained allowlist.

## Alternative considered and rejected

**Route selection via env var** (`SHIPWRIGHT_REVIEW_GPT_LEG=codex`),
matching the `SHIPWRIGHT_REVIEW_MODEL_*` override pattern used elsewhere in
this file. Rejected: the task is explicit that the model/provider choice
should be "config-driven... not silently overridable," and the existing
env-var overrides in this system exist for *model identifiers*
(caught and rejected by `resolve_reviewer_model` if they'd change the
locked identity) — an env var choosing the *transport* has no such
validation backstop and would let a stray environment variable silently
change which system answers a review, invisibly to anyone reading the
project's committed config. Config-only (shipped default + per-project
override, both committed and reviewable) is the safer default; an env-var
convenience can be added later if an operator actually asks for it.

## Files touched

- `shared/config/external_review.json` — `models.codex`, `external_review
  .gpt_leg.provider`, `codex.{timeout_seconds,max_retries}`
- `shared/scripts/lib/external_review_config.py` — `gpt_leg_provider()`,
  `"codex"` added to `_VALID_MODEL_KEYS`
- `shared/scripts/lib/external_review_routing.py` — one new
  `_REVIEW_MODEL_BINDINGS` entry
- `shared/scripts/lib/external_review_default_legs.py` —
  `is_codex_available()`, `review_codex()`, `resolve_openai_route()`
- `shared/scripts/lib/external_review_degraded.py` — generalize
  `is_degraded()` / `is_partially_degraded()`
- `shared/scripts/lib/llm_review.py` — `DEFAULT_MODELS["codex"]`, dispatch
  restructure in `run_review()`'s non-gateway branch
- `shared/scripts/tools/external_review.py` — dispatch restructure in
  `main()`
- `shared/scripts/checks/check-external-review-keys.py` — attributed extra
  (added during the doubt-review round): a `codex_configured` field so the
  operator-facing key-check reports whether the project opted the GPT leg
  into codex, alongside the existing key-presence booleans.
- `shared/scripts/checks/mark-review-state.py` — attributed extra (added
  during the external code-review round): usage-string fix, `--provider
  openrouter|openai` → `...|codex` (the argparse flag itself has no
  `choices=` restriction to update — doc-only drift fix).
- Tests: new unit tests for the new functions + route resolution +
  degraded-generalization regression; existing suites run unmodified as
  the AC7 regression gate
- `docs/hooks-and-pipeline.md`, `docs/guide.md` — document the new config
  field
- `shared/glossary.md` — attributed extra (added after this list was first
  written, at Stage-1 spec-reviewer's prompt): the External-Review entry
  now mentions the `gpt_leg.provider` route, since that entry is the
  glossary's only mention of `external_review.py` and would otherwise
  describe a stale provider chain. File is at its 540-line hard cap
  (`test_glossary_under_loc_limit`) — the edit is net-neutral (rewritten
  within the entry's existing 4-line span, no line added).
