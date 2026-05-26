# Step 5 — External LLM Review (Default + Fallback)

See [external-review.md](external-review.md) for the underlying protocol.

**Goal:** Get the plan reviewed for blind spots — either by external LLMs
(default) or, if unavailable, by a mandatory self-review pass ("2x denken").

**This step is NOT optional.** One of the three branches below must run
to completion, and the marker file
`{planning_dir}/external_review_state.json` must be written. Step 6 is
gated on that marker.

Read `external_review_status` from the session report (printed in
First Actions > F). It is one of: `available`, `missing_keys`,
`user_disabled`.

---

## Branch A — `external_review_status == "available"`

External review keys are present and `feedback_iterations > 0`. Run the
full external review:

```bash
uv run --project {plugin_root} {shared_root}/scripts/tools/external_review.py \
  --mode plan \
  --plan-file "{planning_dir}/plan.md" \
  --spec-file "{spec_file}" \
  --plugin-root "{plugin_root}"
```

(`{shared_root}` resolves to the monorepo's `shared/` directory — typically
`{plugin_root}/../../shared`. The CLI consolidated into `shared/` in v0.5.x;
plan-mode prompts still load from `{plugin_root}/prompts/plan_reviewer/`.)

This runs Gemini and OpenAI reviews **in parallel** via ThreadPoolExecutor
(OpenRouter when set, direct APIs otherwise).

**Process findings:**
1. Present both reviews to the user
2. Integrate accepted suggestions into `plan.md`
3. Mark each finding as addressed or declined (with reason)

**Write each finding to decision_log.md** via:
```bash
uv run "{plugin_root}/../../shared/scripts/tools/write_decision_log.py" \
  --section "External Review — {split_name}" \
  --commit "n/a" \
  --context "External LLM review finding: {finding summary}" \
  --decision "{accepted: what changed | rejected: why not}" \
  --consequences "{impact on plan}" \
  --rejected "{if accepted: original approach | if rejected: the suggestion itself}"
```

Then go to **Step 5b**.

---

## Branch B — `external_review_status == "missing_keys"`

`feedback_iterations > 0` but no API key was found in `.env.local`.
**Stop** and ask the user verbatim:

> External LLM review is the recommended quality gate for this plan, but no `OPENROUTER_API_KEY` (or `GEMINI_API_KEY` / `OPENAI_API_KEY`) was found in `.env.local`.
>
> **Option 1 (recommended):** Add `OPENROUTER_API_KEY=...` to `.env.local` at the repo root and say "ready" — I'll re-check and run the external review.
> **Option 2:** Skip external review. I'll fall back to a mandatory self-review ("2x denken") pass and log the opt-out in the decision log.
>
> Which option?

Do NOT proceed until the user explicitly chooses.

- **User picks Option 1:** wait for their "ready" confirmation, then re-check:
  ```bash
  uv run --project {plugin_root} {shared_root}/scripts/checks/check-external-review-keys.py
  ```
  If `available: true`, fall into Branch A (run `review.py`, integrate, log, then Step 5b).
  If still `false`, ask the user again (they may have edited the wrong file or forgotten to save).
- **User picks Option 2:** run the **Self-Review Fallback** sub-block below. Capture their reason (e.g., "offline", "keys not yet provisioned") for the marker.

---

## Branch C — `external_review_status == "user_disabled"`

`feedback_iterations == 0` — explicit opt-out via config. Print:

```
External LLM review disabled via config (feedback_iterations: 0).
Running mandatory self-review fallback ("2x denken") instead.
```

Run the **Self-Review Fallback** sub-block.

---

## Self-Review Fallback (sub-block)

This is the "2x denken" pass. Re-read `plan.md` with a critic's eye and
apply this checklist. For each item, write a 1–2 sentence finding to
`plan.md` under a new `## Self-Review (2x denken)` section, integrate
any corrections, and log each finding to `decision_log.md`.

1. **Architectural soundness:** Are there design decisions I would second-guess if I were reviewing someone else's plan? List concrete blind spots.
2. **Section boundaries:** Is each section self-contained? Are there hidden cross-dependencies that will surface during /shipwright-build?
3. **TDD coverage:** Does every section's test strategy validate behavior, or just implementation details?
4. **Risk hotspots:** What's the single riskiest section? What could go wrong? Is there a mitigation in the plan?
5. **Assumptions:** What assumptions did I make that the user did not explicitly confirm? List them and flag for user review.

**Output format (append to plan.md):**
```
## Self-Review (2x denken)
- **Architectural soundness:** {finding + action taken}
- **Section boundaries:** {finding + action taken}
- **TDD coverage:** {finding + action taken}
- **Risk hotspots:** {finding + action taken}
- **Assumptions:** {finding + action taken}
- **Status:** {all clear | {N} issues corrected | {N} issues flagged for user}
```

Log each non-trivial finding to `decision_log.md` using
`write_decision_log.py` with `--section "Self-Review — {split_name}"`.

Then go to **Step 5b**.

---

## Step 5b: Mark review state

After exactly one branch completes, write the marker file so Step 6
can advance:

```bash
uv run --project {plugin_root} {shared_root}/scripts/checks/mark-review-state.py \
  --planning-dir "{planning_dir}" \
  --status "{completed | skipped_user_opt_out | skipped_config_disabled}" \
  --provider "{openrouter | gemini | openai | null}" \
  --findings-count {N} \
  --reason "{optional reason for skip}"
```

- Branch A → `--status completed --provider {actual provider}`
- Branch B Option 2 → `--status skipped_user_opt_out --reason "{user's reason}"`
- Branch C → `--status skipped_config_disabled`

**Checkpoint:** `{planning_dir}/external_review_state.json` exists.
