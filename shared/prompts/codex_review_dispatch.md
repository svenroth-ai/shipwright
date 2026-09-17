# Codex-Driver Internal-Review Dispatch

Checked once before spawning any of `spec-reviewer` / `code-reviewer` /
`doubt-reviewer` / `opus-plan-reviewer`: can this driving harness genuinely
spawn an Agent-tool subagent on a model independent of its own (Claude Code,
driving on an Anthropic model)? If yes, spawn as normal — this doc does not
apply. Never applies inside an Agent-tool-less Shipwright subagent (e.g.
`section-builder`, `sub-iterate-runner`) — those keep deferring to the
orchestrator exactly as they do today; this is for an orchestrator's own
spawn site only (`shipwright-build` Step 6, `shipwright-plan` Step 5-int,
`shipwright-iterate` Step 8, `shipwright-iterate` campaign-mode 3f-bis).

If not — Codex CLI itself is driving, or a Claude Code session has been
redirected to a non-Anthropic backend — run:

```bash
uv run "{shared_root}/scripts/tools/review_via_codex.py" \
  --role {spec|code|doubt|plan_review} \
  --worktree-root "{project_root}" \
  --agent-md "{the role's agent .md — plugins/shipwright-build/agents/spec-reviewer.md,
    .../code-reviewer.md, .../doubt-reviewer.md, or
    plugins/shipwright-plan/agents/opus-plan-reviewer.md}" \
  --spec-file "{the spec/section-plan file — all four roles take this}" \
  --diff-file "{the diff file — required for role spec|code|doubt, omit for plan_review}" \
  --plan-file "{the plan file — required for role plan_review only}" \
  --out-dir "{project_root}/.shipwright/planning/iterate/{run_id}/"
```

`--spec-file` is always required. `--diff-file` is required for `spec`/`code`/
`doubt` (omit `--plan-file`); `--plan-file` is required for `plan_review`
(omit `--diff-file`) — the same two paths each agent `.md` already documents
receiving from an Agent-tool spawn (code-reviewer REJECT, 2026-09-17: without
these the transport has no channel for the review subject at all).

One role's worst case is up to 600s; the three review-cascade roles run
**sequentially**, never in parallel (a flat-fee Codex subscription's own
concurrency limits), so a full cascade can take up to 1800s. Issue this call
in a way that tolerates that (a backgroundable shell invocation), not a
short-lived foreground timeout.

Parse the printed JSON line:

- **`status: "completed"`** — `canonical_path` is the already
  schema-validated payload file.
  - **`role` is `spec`/`code`/`doubt`:** record it with
    `record_review_pass.py record --run-id "{run_id}" --review-type
    {spec|code|doubt} --status completed --from {spec|code|doubt}-reviewer
    --payload-file "{canonical_path}" --transport codex` (no `--model-tier`
    — the row carries no legal Claude tier; the floor verifier already
    exempts a `codex`-transport row rather than reading one).
  - **`role` is `plan_review`:** there is no `record_review_pass.py --from`
    adapter for it (`plan_internal` is a metadata-only row with no payload
    file, see `review_payloads.py`) — read `canonical_path` directly and
    write its `findings`/`summary` into `plan.md`'s own `## Internal Plan
    Review` section, exactly as an Agent-tool `opus-plan-reviewer` spawn's
    return value would be used.
- **`status: "error"`** — `reason` names the concrete failure.
  - This session can ALSO spawn an ordinary Agent-tool subagent (a redirected
    Claude Code session, not Codex CLI itself): fall back to `Task(...)`,
    then record the resulting pass normally **plus** `--transport agent
    --transport-note "codex transport failed: {reason}; fell back to an
    ordinary Agent-tool spawn"` — this is what makes a codex-answered pass and
    a failed-then-agent-answered pass distinguishable in `reviews.json`
    (External Review, openai #8).
  - It cannot (Codex CLI is the driver): `record_review_pass.py record
    --run-id "{run_id}" --review-type {spec|code|doubt} --status not_run
    --disposition "codex transport failed: {reason}"` — never silently
    proceed as if reviewed.
