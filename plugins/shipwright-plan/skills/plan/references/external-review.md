# External LLM Review Protocol

## Purpose

Get the plan reviewed by external LLMs (Gemini + OpenAI) to catch blind spots.
Claude reviewing its own plan misses systematic biases — external models help.

External review is the **default** for /shipwright-plan. If keys are missing,
the skill interactively asks the user whether to add one or fall back to a
mandatory self-review pass. Silent-skip is not an option.

## Prerequisites

- **Recommended:** `OPENROUTER_API_KEY` (single key for both models) in the
  project's `.env.local` at the repo root.
- **Alternative:** `GEMINI_API_KEY` (or `GOOGLE_API_KEY` / Vertex AI ADC) and
  `OPENAI_API_KEY` as direct provider keys.
- `external_review.feedback_iterations > 0` in `config.json` (default: `1`).
  Set to `0` only for explicit opt-out — the skill will then run the
  mandatory self-review fallback.

## Script

```bash
uv run --project {plugin_root} {plugin_root}/scripts/llm_clients/review.py \
  --plan-file "{planning_dir}/plan.md" \
  --spec-file "{spec_file}" \
  --plugin-root "{plugin_root}"
```

## How It Works

1. Loads system + user prompts from `{plugin_root}/prompts/plan_reviewer/`
2. Sends plan + spec to Gemini and OpenAI **in parallel** (ThreadPoolExecutor)
3. Collects feedback from both
4. Returns structured JSON with findings

## Handling Feedback

1. Present both reviews to the user
2. Discuss which suggestions to adopt
3. Integrate accepted feedback into plan.md
4. Mark feedback as "addressed" or "declined (reason)"

## Graceful Degradation

- If one LLM fails: continue with the other's feedback
- If both fail: log the failure, fall through to the self-review fallback block
  (see SKILL.md Step 5), and write the marker with
  `status: skipped_user_opt_out` plus `reason: "both providers failed"` so the
  outcome is visible in the decision log.
- If no API keys: the skill prompts the user interactively (SKILL.md Step 5
  Branch B). Either keys are added + review runs, or the user opts out and the
  self-review fallback runs. Never silently skipped.
