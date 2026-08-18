# Architecture Brief: external-review-project-flag

## The problem
Every documented `uv run .../external_review.py` invocation in shipwright-iterate
and shipwright-build's instruction files omits uv's own `--project` flag, so
outside this monorepo `uv run` cannot find the `openai` dependency the script
imports and the external review cascade silently degrades to internal-only
reviewers.

## What would newly, permanently exist
Nothing. This changes prose/config in existing instruction files plus a new
static regression test; no new mechanism, service, credential, or schedule.
