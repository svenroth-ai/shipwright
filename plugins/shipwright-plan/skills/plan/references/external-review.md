# External LLM Review Protocol

## Purpose

Get the plan reviewed by external LLMs (Gemini + OpenAI) to catch blind spots.
Claude reviewing its own plan misses systematic biases — external models help.

## Prerequisites

- `GEMINI_API_KEY` environment variable set (or Vertex AI ADC configured)
- `OPENAI_API_KEY` environment variable set
- `external_review.feedback_iterations > 0` in config.json

## Script

```bash
uv run {plugin_root}/scripts/llm_clients/review.py \
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
- If both fail: skip review with a warning note
- If no API keys: skip entirely (no error)
