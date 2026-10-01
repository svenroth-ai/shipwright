# Codex-Driver Internal-Review Dispatch

Checked once before spawning any of `spec-reviewer` / `code-reviewer` /
`doubt-reviewer` / `opus-plan-reviewer` / `architecture-internal-reviewer`:
**which harness is driving this session, and does it have the Agent tool?**
This is the harness's own identity — self-evident to the agent executing
these instructions, never sniffed from an env var:

| Driving harness | Dispatch |
|---|---|
| Claude Code (an Anthropic backend **or** redirected to a non-Anthropic one via the Codextender proxy, `CODEXTENDER_ACTIVE` set) | **Spawn the Agent-tool subagent as normal** — this doc does not apply. Under Codextender the proxy maps the subagent to `sol`; that is the intended path. Record the pass with the default `agent` transport. |
| Codex CLI itself (no Claude `Agent` tool) | Run `review_via_codex.py` below. |

**Codextender does NOT dispatch through `review_via_codex.py`.** The Agent
tool works there, and `codex exec` would buy no independence: its default
review model (`CODEX_REVIEW_MODEL`, `codex_review_transport.py`) is
`gpt-6.1-sol`, the same family Codextender's proxy already maps subagents to.
(Observed: Codextender sessions spawned 70+ spec/code/doubt-reviewer
subagents on `sol` and never ran `review_via_codex.py`; the old wording of
this doc described a path sessions did not take.) `CODEXTENDER_ACTIVE` still
steers the **external** review's `--driver` roster (`codex` → `{glm, opus}`)
because that is a different question — the diff's *author* was Codex-backed,
so a GPT-family second reviewer would not be independent — and that mapping
is unchanged. Do not read `--driver codex` as "the harness is Codex CLI".

Never applies inside an Agent-tool-less Shipwright subagent (e.g.
`section-builder`, `sub-iterate-runner`) — those keep deferring to the
orchestrator exactly as they do today; this is for an orchestrator's own
spawn site only (`shipwright-build` Step 6, `shipwright-plan` Step 5-int,
`shipwright-iterate` Step 8, `shipwright-iterate` campaign-mode 3f-bis),
plus plan Step 5-int-arch and iterate Step 3.5 (0b), which dispatch the
`architecture_internal` role below.

**`architecture-internal-reviewer` has its own Codex role,
`architecture_internal`** (own schema, own canonical basename
`architecture_internal_reply.json`, inputs `--brief-file` + `--spec-file`,
high reasoning effort). It is a role of its own because reusing
`role=plan_review` would collide on the fixed basename
`plan_review_reply.json` the real Internal Plan Review pass already writes,
and `plan_review` requires `--plan-file`, which this pass structurally never
has (brief + spec only). Only a **real Codex CLI driver** runs it through
`review_via_codex.py`, via the `architecture_internal` call below;
**under Codextender (and any other Claude Code session)** spawn
`shipwright-plan:architecture-internal-reviewer` through the Agent tool like
the other reviewers. Either way the pass shows `Ran: yes`.

Only when **Codex CLI itself is driving** — run:

```bash
uv run "{shared_root}/scripts/tools/review_via_codex.py" \
  --role {spec|code|doubt|plan_review|architecture_internal} \
  --worktree-root "{project_root}" \
  --agent-md "{the role's agent .md — plugins/shipwright-build/agents/spec-reviewer.md,
    .../code-reviewer.md, .../doubt-reviewer.md,
    plugins/shipwright-plan/agents/opus-plan-reviewer.md, or
    plugins/shipwright-plan/agents/architecture-internal-reviewer.md}" \
  --spec-file "{the spec/section-plan file — all five roles take this; for
    architecture_internal the SANITIZED spec copy, never the real spec}" \
  --diff-file "{the diff file — required for role spec|code|doubt, omit for plan_review}" \
  --plan-file "{the plan file — required for role plan_review only}" \
  --brief-file "{architecture_brief.md — required for role architecture_internal only}" \
  --out-dir "{project_root}/.shipwright/planning/iterate/{run_id}/" \
  [--codex-model "{a per-run override for the Codex reviewer model, e.g.
    gpt-6.1-sol — optional; unset defers to this role's session env var,
    then shipwright_model_config.json's codex_review/codex_plan_review key,
    then the hardcoded default}"]
```

A session-scoped override with no `--codex-model` flag to thread through
this fixed command: export `SHIPWRIGHT_CODEX_REVIEW_MODEL` (spec/code/doubt)
or `SHIPWRIGHT_CODEX_PLAN_REVIEW_MODEL` (plan_review) before dispatching.
Ambient env reaches this call for free — Codex CLI's own
`shell_environment_policy.inherit=all` already carries it through — so no
change to this doc's fixed per-role commands is needed to use it.

Unlike the project-config key, an env-var override leaves no durable trace
anywhere (no git history, no `reviews.json` entry) — only the resolved model
in this call's own stdout. Set it per-invocation
(`SHIPWRIGHT_CODEX_REVIEW_MODEL=... uv run ...`), not `export`ed into a
standing shell, so a forgotten value cannot silently steer every later
review in that shell.

`--spec-file` is always required. `--diff-file` is required for `spec`/`code`/
`doubt` (omit `--plan-file`); `--plan-file` is required for `plan_review`
(omit `--diff-file`); `--brief-file` is required for `architecture_internal`
(omit `--diff-file` and `--plan-file` — this pass never sees a plan) — the same two paths each agent `.md` already documents
receiving from an Agent-tool spawn (code-reviewer REJECT, 2026-09-17: without
these the transport has no channel for the review subject at all).

One role's worst case is up to 600s; the three review-cascade roles run
**sequentially**, never in parallel (a flat-fee Codex subscription's own
concurrency limits), so a full cascade can take up to 1800s. Issue this call
in a way that tolerates that (a backgroundable shell invocation), not a
short-lived foreground timeout.

Parse the printed JSON line:

- **`status: "completed"`** — `canonical_path` is the already
  schema-validated payload file. `model` is the EFFECTIVE Codex model that
  actually ran (config/override resolved, or the hardcoded default).
  - **`role` is `spec`/`code`/`doubt`:** record it with
    `record_review_pass.py record --run-id "{run_id}" --review-type
    {spec|code|doubt} --status completed --from {spec|code|doubt}-reviewer
    --payload-file "{canonical_path}" --transport codex --transport-note
    "{transport_note}"` (no `--model-tier` — the row carries no legal Claude
    tier; the floor verifier already exempts a `codex`-transport row rather
    than reading one). `{transport_note}` is the JSON result's own
    `transport_note` field verbatim (e.g. `<model> effort=<effort>
    sandbox=<mode>` for these three roles) — never hand-assemble it, and
    never hardcode the example values themselves (`CODEX_REVIEW_MODEL`/
    `CODEX_REVIEW_REASONING_EFFORT`/`CODEX_REVIEW_SANDBOX_MODE` can change
    independently of this doc — code-reviewer, low, 2026-09-20) — so a
    project pinning `codex_review` away from the hardcoded default, or
    a future change to the reasoning-effort/sandbox contract, leaves that
    choice visible in the evidence, not just in config. **For `spec`/`code`/
    `doubt`, `{transport_note}` now contains embedded spaces** (`<model>
    effort=<effort> sandbox=<mode>`) — the double quotes around
    `"{transport_note}"` above are REQUIRED, not decorative: dropping them
    hands `record_review_pass.py` three positional words instead of one
    argument and the record call errors out, silently losing the very
    evidence row this step exists to write (doubt-reviewer, medium,
    2026-09-20).
  - **`role` is `architecture_internal`:** like `plan_review`, no
    `--from` adapter exists (the `architecture_internal` row is metadata-only).
    Read `canonical_path` directly, write its `findings`/`summary` into the
    `## Internal Architecture Review` section (`Ran: yes`), and — on the
    iterate side only, plan has no run_id — record the row:
    `record_review_pass.py record --run-id "{run_id}" --review-type
    architecture_internal --status completed --recorded-by
    architecture-internal-reviewer --transport codex --transport-note
    "{transport_note}"` (no `--model-tier`, as for the other Codex rows).
  - **`role` is `plan_review`:** there is no `record_review_pass.py --from`
    adapter for it (`plan_internal` is a metadata-only row with no payload
    file, see `review_payloads.py`) — read `canonical_path` directly and
    write its `findings`/`summary` into `plan.md`'s own `## Internal Plan
    Review` section, exactly as an Agent-tool `opus-plan-reviewer` spawn's
    return value would be used.
- **`status: "error"`** — `reason` names the concrete failure.
  - Rare: this Codex-CLI-driven session can nonetheless spawn an ordinary
    Agent-tool subagent (normally it cannot — then see the next bullet; a
    Claude Code / Codextender session never reaches this step): fall back to
    `Task(...)`, then record the resulting pass normally **plus** `--transport agent
    --transport-note "codex transport failed: {reason}; fell back to an
    ordinary Agent-tool spawn"` — this is what makes a codex-answered pass and
    a failed-then-agent-answered pass distinguishable in `reviews.json`
    (External Review, openai #8).
  - It cannot (Codex CLI is the driver): for `architecture_internal` record
    `Ran: no (capability failure)` in the section and let Step 7's sweep
    close the row; otherwise `record_review_pass.py record
    --run-id "{run_id}" --review-type {spec|code|doubt} --status not_run
    --disposition "codex transport failed: {reason}"` — never silently
    proceed as if reviewed.
