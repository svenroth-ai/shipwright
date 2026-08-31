# Architecture Brief: pr-review-deepseek-model

## The problem
The Tier-3 CI PR-review gate calls one LLM per required PR push via
OpenRouter. It currently pays a much higher per-call price and gets a slower
response for roughly the same code-review benchmark score another already-
integrated model gets, on a check that runs on every gated PR push.

## What would newly, permanently exist
Nothing. This changes machinery that already exists: which model string the
existing OpenRouter call uses, and reuses an existing provider-routing
constraint (already applied to a different call site in this repo) on the new
call.
