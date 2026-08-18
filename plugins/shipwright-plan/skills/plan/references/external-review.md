# External LLM Review Protocol

## Purpose

Get the plan reviewed by external LLMs (DeepSeek + OpenAI) to catch blind spots.
Claude reviewing its own plan misses systematic biases — external models help.

External review is the **default** for /shipwright-plan, layered on top of an
internal review (`opus-plan-reviewer`, SKILL.md Step 5-int) that always
runs first. If keys are missing, the skill interactively asks the user
whether to add one or skip and rely on the internal review, which already
carries the gate. Silent-skip is not an option.

## Prerequisites

- **Recommended:** `OPENROUTER_API_KEY` (single key for both models) in the
  project's `.env.local` at the repo root.
- **Alternative:** `OPENAI_API_KEY` runs the GPT arm directly. DeepSeek has no
  direct-provider fallback and remains unavailable without OpenRouter.
- `external_review.feedback_iterations > 0` in
  `shared/config/external_review.json` (default: `1`). Set to `0` only for
  explicit opt-out — the internal review (Step 5-int) still runs and
  carries the gate. Each reviewer identity is locked to its shipped model; a
  differing config value or environment override fails before client creation.

## Script

```bash
uv run --project "{plugin_root}" {shared_root}/scripts/tools/external_review.py \
  --mode plan \
  --plan-file "{planning_dir}/plan.md" \
  --spec-file "{spec_file}" \
  --plugin-root "{plugin_root}"
```

`{shared_root}` is the monorepo's `shared/` directory (typically
`{plugin_root}/../../shared`). The CLI moved into `shared/` in v0.5.x to
serve plan, iterate, and any future SDLC plugin uniformly.

## How It Works

1. Loads system + user prompts from `{plugin_root}/prompts/plan_reviewer/`
   (plan-mode prompts stay plugin-local — they're plan-specific)
2. Sends plan + spec to DeepSeek and OpenAI **in parallel** (ThreadPoolExecutor);
   every DeepSeek request carries the fail-closed ZDR provider policy
3. Collects feedback from both
4. Returns structured JSON with findings

## Handling Feedback

1. Present both reviews to the user
2. Discuss which suggestions to adopt
3. Integrate accepted feedback into plan.md
4. Mark feedback as "addressed" or "declined (reason)"

## Graceful Degradation

- If one LLM fails: continue with the other's feedback
- If both fail: log the failure, and write the marker with
  `status: skipped_user_opt_out` plus `reason: "both providers failed"` —
  whether a further fallback is needed depends on Step 5-int's outcome, which
  the **Pre-5b Checkpoint** (step-5-external-review.md) resolves.
- If no API keys: the skill prompts the user interactively (SKILL.md Step 5
  Branch B). Either keys are added + review runs, or the user opts out and
  the internal review already on record carries the gate. Never silently
  skipped.
