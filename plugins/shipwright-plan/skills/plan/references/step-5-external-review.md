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

This runs DeepSeek and OpenAI reviews **in parallel** via ThreadPoolExecutor
(both through OpenRouter when set; direct OpenAI otherwise leaves DeepSeek unavailable).
Every DeepSeek request uses the configured, code-approved ZDR endpoint allowlist
and disables provider fallback. A missing allowed endpoint degrades only that arm.

**Process findings:**
1. Present both reviews to the user
2. Integrate accepted suggestions into `plan.md`
3. Mark each finding as addressed or declined (with reason)

### Read the two verdicts before anything else

Each reviewer ends with `SHIPWRIGHT_VERDICT: approve|revise|reject`. The CLI
reads both and reports them:

```json
"verdicts": { "deepseek": "approve", "openai": "reject" },
"contradiction": { "detected": true, "requires_resolution": true,
                   "reason": "reviewers contradict each other: deepseek=approve, openai=reject" }
```

**`requires_resolution: true` is its own outcome, not a finding count.** It
means the two reviewers cannot be compared, for one of these reasons:

- they **contradict each other** — one approves, the other rejects. Two
  independent reviewers exist so this gets noticed; a plan whose reviewers
  disagree about the approach as a whole is not a reviewed plan;
- a **verdict could not be read** (missing, ambiguous, or the reply was
  truncated). An unreadable verdict is not agreement;
- **only one reviewer answered.** One approving review is not the guarantee
  two reviewers give — proceeding on it is a decision, so it gets recorded as
  one.

(*Neither* answering is different: nothing ran, and the degraded-review gate
above already covers it.)

Put it to the user, in these terms:

> The two reviewers disagree about this plan. {deepseek} says **{verdict}**;
> {openai} says **{verdict}**. Their reasons are above. How should I proceed —
> take one side, rework the plan, or record why the disagreement does not
> block?

Do NOT average it away, and do not proceed on the approving review alone.
Carry the decision into Step 5b as `--contradiction-resolution`; Step 6 will
not begin without it, and the `W5` compliance check fails while it is missing.

`approve` vs `revise`, or `revise` vs `reject`, is a difference of degree that
the finding list already carries — those do not require a resolution.

**If the CLI exits non-zero or the JSON has `"degraded": true`** (keys were
present but every review leg failed), the external review did NOT run. Do not
record Step 5b as `completed`: surface the `degraded_reason` and treat it like
Branch B `missing_keys` — re-check keys or run the Self-Review Fallback and
mark the state accordingly. A degraded gate is not a passing review.

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

Then run **Step 5a**, then go to **Step 5b**.

---

## Step 5a — Architecture Review (the second call)

**Branch A only** — one extra call in the same step, to the same two models,
asking the one question no other pass asks: *should this be built at all, and
what is the smallest thing that would do?*

**Why a second call and not one more paragraph in the prompt above.** The
difference that produces a different answer is the **input**, not the question.
`plan.md` carries the approach together with its justification, and the
Self-Review Fallback's own item 1 asks about architectural soundness over that
same document — a reviewer handed the plan has been handed the answer. Measured
twice on the iterate side: the same two models, the same change, `approve` when
shown the plan and `reject` when shown a brief, both then naming a simpler
alternative the plan had discarded.

So this call reads a short **brief** written from
`shared/templates/architecture_brief.md`, listing the options **without** the
reasons any of them were rejected. When the plan adds nothing permanent, that
brief is three lines — see the template.

```bash
# 1. Write {planning_dir}/architecture_brief.md from the template.
#    Do NOT copy the plan's rejected-alternatives rationale into it.

# 2. Ask the same two models.
uv run --project {plugin_root} {shared_root}/scripts/tools/external_review.py \
  --mode architecture \
  --brief-file "{planning_dir}/architecture_brief.md" \
  --spec-file "{spec_file}" \
  --plugin-root "{plugin_root}"
```

The CLI **refuses `--plan-file` in this mode** (usage error, exit 2): silently
accepting the plan would restore the anchoring while the emitted envelope stayed
byte-identical.

`approve` → proceed. `revise` → integrate like any other finding. **`reject`
from either reviewer → STOP and ask the user**, before Step 6, because the whole
value is that this is seen while nothing is built yet:

> The architecture review says this should not be built this way.
> {deepseek} says **{verdict}**, {openai} says **{verdict}**. They recommend:
> **{the alternative, one line}**. The plan had considered that and rejected it
> because: **{the reason, from plan.md}**.
>
> How should I proceed — take the alternative, keep the plan (I'll record why
> the objection does not hold), or rework and re-review?

Reviewer disagreement is handled exactly as above: put it to the user, never
average it away.

**Record it** by appending to `plan.md` — this section is where the withheld
reasoning re-enters the record, so the reconciliation is written down whichever
way the user decides:

```markdown
## Architecture Review
- **Verdicts:** deepseek={approve|revise|reject} · openai={…}
- **Smallest thing that would do (per reviewers):** {one line, or `as proposed`}
- **Reconciliation:** {what the plan had rejected, why, and the user's decision}
- **Status:** {proceeding as planned | reworked | alternative adopted}
```

Log each finding to `decision_log.md` with
`--section "Architecture Review — {split_name}"`.

Step 5b is unchanged: this pass writes **no marker of its own**, and
`external_review_state.json` continues to record the plan review alone. Its
provenance is `plan.md` + `decision_log.md`, both git-tracked and both read by
the compliance audit.

Then go to **Step 5b**.

---

## Branch B — `external_review_status == "missing_keys"`

`feedback_iterations > 0` but no API key was found in `.env.local`.
**Stop** and ask the user verbatim:

> External LLM review is the recommended quality gate for this plan, but no `OPENROUTER_API_KEY` or `OPENAI_API_KEY` was found in `.env.local`.
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
  --provider "{openrouter | openai | null}" \
  --findings-count {N} \
  --reason "{optional reason for skip}" \
  --verdict deepseek={approve|revise|reject|unknown|unavailable} \
  --verdict openai={approve|revise|reject|unknown|unavailable} \
  --contradiction-resolution "{only when the reviewers disagreed}"
```

- Branch A → `--status completed --provider {actual provider}`, plus one
  `--verdict` per reviewer, copied from the CLI's `verdicts` block. The
  contradiction is **derived** from the pair — there is no flag to assert
  agreement the verdicts do not support.
- Branch B Option 2 → `--status skipped_user_opt_out --reason "{user's reason}"`
- Branch C → `--status skipped_config_disabled`

Pass `--contradiction-resolution` only when the CLI reported
`requires_resolution: true`, and only with the decision the **user** made —
which side was taken and why, why the unreadable verdict does not block, or
why proceeding on a single review is acceptable. Without it Step 6 refuses to
begin.

Reviewer names must be `deepseek` and `openai` (the two current arms), each given
once. Branch B/C skips record no verdicts, which is correct — a skipped review
has no reviewers. But a **`completed`** review with no verdicts is treated as
not-yet-recorded and blocks Step 6: omitting the flags must not be a way to
opt out of the disagreement check.

**Checkpoint:** `{planning_dir}/external_review_state.json` exists, and the
state it records is clear to proceed past — which is the same question the
resume gate and the compliance `W5` check ask, via the one shared
`lib.review_marker.evaluate_review_state`. A marker recording an undecided
disagreement sends a resumed session back to Step 5 rather than past it.
