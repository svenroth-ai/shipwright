# Step 5 — External LLM Review (Default + Fallback)

See [external-review.md](external-review.md) for the underlying protocol.

**Goal:** Get the plan reviewed for blind spots — always by an internal
reviewer first (Step 5-int; `plan_review` role — inherit unless configured),
then a separate fresh-context reviewer asking whether the change should be
built at all (Step 5-int-arch, no Pre-5b gate of its own), then external
LLMs by default. Self-review ("2x denken") is the last resort, only when
neither Step 5-int (`Ran: yes`) nor a completed Branch A review exists (Pre-5b).

**This step is NOT optional.** Step 5-int and Step 5-int-arch always run first,
then a branch runs to completion, and `{planning_dir}/external_review_state.json` must be written — Step 6 gates on both.

Read `external_review_status` from the session report (First Actions > F):
`available`, `missing_keys`, or `user_disabled`.

---

## Step 5-int — Internal Plan Review (always, before branching)

**Runs exactly once, before Branch A/B/C, regardless of `external_review_status`.**
An external-only gate degrades to the plan's own author whenever external review
is unavailable — this pass is what keeps the gate independent even then. If
`## Internal Plan Review` already exists in `plan.md` **and records `Ran: yes`**
(a resumed session, or Branch B's retry loop re-entering Step 5), skip straight
to the branch below — do not re-spawn. A recorded `Ran: no` is not a completed
pass — retry it.

Resolve the model tier first (no `--plan-review-model` override here — that
per-run flag is `/shipwright-iterate`'s to expose; this standalone phase reads
only the project's `shipwright_model_config.json`):

```bash
uv run "{shared_root}/scripts/tools/resolve_model_tier.py" --project-root "{project_root}"
```
**Dispatch rule:** see `shared/prompts/codex_review_dispatch.md` for the full Codex-driver procedure (`role="plan_review"`). Codex CLI driving → `review_via_codex.py`; Claude Code incl. Codextender → spawn as normal (proxy-mapped to `sol`). on an unrecovered failure record `Ran: no` in `plan.md` naming the reason instead of the `not_run` row the doc describes for the standalone cascade.
Parse `.plan_review.agent_param`. Spawn `shipwright-plan:opus-plan-reviewer`
(Read/Grep/Glob only) over `{planning_dir}/plan.md` + `{spec_file}`, passing the
Agent tool's `model=` parameter when `agent_param` is non-null (a configured
tier); omit it when `null` (`inherit` — the frontmatter carries no pin of its
own, so an omitted parameter runs the subagent on the session's own model).
Behavior change for an unconfigured project: the agent used to be pinned to
`opus` in its own frontmatter; a project that wants that back must now set
`plan_review: opus` explicitly. Tell it in the prompt when the plan is
infrastructure/documentation-shaped rather than an application feature, so its
security/performance/architecture/completeness rubric maps sensibly instead of
forcing categories that do not apply.

**Degraded handling.** If the subagent cannot be spawned (Agent tool unavailable),
its reply has no parseable JSON block, or the JSON parses but lacks a recognizable
`findings` array or `summary` (garbage-in still counts as a parse failure): the
internal pass did NOT run. Record `Ran: no` (reason: capability or parse failure)
in the `## Internal Plan Review` section and in `decision_log.md`, then
**continue to the branch below as normal** — do not fall back yet. Branch A may
still produce an independent (external) review; the single checkpoint right
before Step 5b is what decides whether the Self-Review Fallback is actually
needed, so the same rule covers every branch instead of one condition per branch.

**Triage every finding — one of three, always with a reason:**
- **fix** — integrate into `plan.md` now.
- **disclose** — accepted as a known limitation, not acted on now. Record it under
  `**Known limitations:**` below — a disclosed finding with no bullet is
  indistinguishable from a dropped one.
- **decline** — record why. **Scope-ratchet guard:** a finding that would add plan
  or spec scope the spec itself calls unsupported must be declined, not integrated
  — this applies to every pass in this step (internal, external, architecture).

A declined or disclosed `severity: high` finding is not the planning agent's call
alone: **STOP and ask the user** before Step 6, in the same shape as Step 5a's
`reject` prompt. Under `single_session`, `gate_catalog.json`'s
`plan.internal-review-high-severity-declined` entry carries the auto-default.

**Write, always** (even when `findings` is empty — a `Ran: yes` section with no
findings still reads as a completed clean pass; a missing section reads as "did
not run", which must never be true after this step runs once). If a `## Internal
Plan Review` section already exists (a `Ran: no` retry), REPLACE it in place —
never append a second one; `plan.md` holds exactly one. Never paste the
reviewer's raw JSON or fenced blocks through — `plan.md` is parsed downstream
for `SECTION_MANIFEST`, and unbounded content risks corrupting that parse:

```markdown
## Internal Plan Review (opus-plan-reviewer)
- **Ran:** {yes | no (capability failure) | no (parse failure)}
- **Severity:** {low|medium|high, or n/a if Ran: no}
- **Summary:** {reviewer's one-line assessment, or the failure reason if Ran: no}
- **Findings:** {one line per finding: category, severity, disposition, one-line reason}
- **Known limitations:** {each disclosed finding, one line, or `none`}
- **Status:** {clean | N fixed | N fixed, M disclosed, K declined | not_run}
```

**Log every finding** (fixed, disclosed, or declined — none omitted) to
`decision_log.md` (`write_decision_log.py`) with `--section "Internal Plan
Review — {split_name}"`, `--decision` one of `{fixed: what changed | disclosed:
why accepted as-is | declined: why not}`, and `--rejected` the declined finding
itself (or, if fixed, the prior approach).

**No marker of its own** — same precedent as Step 5a Architecture Review.
Provenance is `plan.md` + `decision_log.md`. Step 5b's *existing*
`--findings-count`/`--reason`/`--self-review-fallback-ran` flags carry this
pass's outcome where relevant (see Step 5b) — the marker schema is unchanged.

---

## Step 5-int-arch — Internal Architecture Review (always, right after 5-int)

Runs once, right after Step 5-int, before Branch A/B/C — a separate
fresh-context agent (`architecture-internal-reviewer`, not an extension of
`opus-plan-reviewer`) over a fresh brief + `{spec_file}`, never `plan.md`.
Full procedure: [step-5-int-arch.md](step-5-int-arch.md).

Then branch on `external_review_status`:

---

## Branch A — `external_review_status == "available"`

External review keys are present and `feedback_iterations > 0`. Run the
full external review:

```bash
uv run --project "{plugin_root}" {shared_root}/scripts/tools/external_review.py \
  --mode plan \
  --plan-file "{planning_dir}/plan.md" \
  --spec-file "{spec_file}" \
  --plugin-root "{plugin_root}" \
  --driver "$([ -n "${CODEXTENDER_ACTIVE:-}" ] && echo codex || echo claude)"
```

(`--driver` is **required, no default** — `claude` here, except `codex` under
Codextender mode; see `external-review.md` for why. `{shared_root}` is
typically `{plugin_root}/../../shared`; plan-mode prompts load from
`{plugin_root}/prompts/plan_reviewer/`.)

This runs GLM and OpenAI reviews **in parallel** (both via OpenRouter when
set; direct OpenAI otherwise leaves GLM unavailable — GLM uses the
configured, code-approved ZDR endpoint allowlist with provider fallback
disabled, so a missing allowed endpoint degrades only that arm). **Process
findings:** present both to the user, integrate accepted suggestions into
`plan.md`, mark each finding addressed or declined (reason).

### Read the two verdicts before anything else

Each reviewer ends with `SHIPWRIGHT_VERDICT: approve|revise|reject`. The CLI
reads both and reports them:

```json
"verdicts": { "glm": "approve", "openai": "reject" },
"contradiction": { "detected": true, "requires_resolution": true,
                   "reason": "reviewers contradict each other: glm=approve, openai=reject" }
```

**`requires_resolution: true` is its own outcome, not a finding count.** The
two reviewers cannot be compared: they **contradict each other** (one
approves, the other rejects — two independent reviewers exist so this gets
noticed), a **verdict could not be read** (missing, ambiguous, truncated —
not agreement), or **only one reviewer answered** (one approving review is
not the guarantee two give — proceeding on it is a decision, so it is
recorded as one). *Neither* answering is different: nothing ran, and the
degraded-review gate above already covers it.

Put it to the user, in these terms:

> The two reviewers disagree about this plan. {glm} says **{verdict}**;
> {openai} says **{verdict}**. Their reasons are above. How should I proceed —
> take one side, rework the plan, or record why the disagreement does not
> block?

Do NOT average it away, and do not proceed on the approving review alone.
Carry the decision into Step 5b as `--contradiction-resolution`; Step 6 will
not begin without it, and the `W5` compliance check fails while it is missing.

`approve` vs `revise`, or `revise` vs `reject`, is a difference of degree that
the finding list already carries — those do not require a resolution.

**If the CLI exits non-zero or the JSON has `"degraded": true`** (keys present
but every review leg failed), the external review did NOT run. Do not record
Step 5b as `completed`: surface the `degraded_reason`, mark the state
`skipped_user_opt_out` with the `; both external providers failed` reason
suffix from Step 5b below (re-checking keys and retrying Branch A remains
available too). A degraded gate is not a passing review — whether the plan
still has one depends on Step 5-int's `Ran:` value. **Skip Step 5a** (the
same two providers just failed) and **go straight to the Pre-5b Checkpoint
below**, which resolves it.

**Log each finding** to `decision_log.md` with `--section "External Review —
{split_name}"` (same `write_decision_log.py` shape as Step 5-int above,
`--context`/`--decision` covering accepted/rejected instead of
fixed/disclosed/declined).

Then run **Step 5a**, then the **Pre-5b Checkpoint**, then **Step 5b**.

---

## Step 5a — Architecture Review (the second call)

**Branch A only** — one extra call in the same step, to the same two models,
asking the one question no other pass asks: *should this be built at all, and
what is the smallest thing that would do?*

**Why a second call and not one more paragraph in the prompt above.** The
difference that produces a different answer is the **input**, not the
question. `plan.md` carries the approach with its justification, and the
Self-Review Fallback's own architectural-soundness check asks over that same
document — a reviewer handed the plan has been handed the answer. Measured
twice on the iterate side: the same two models, same change, `approve` when
shown the plan and `reject` when shown a brief, both naming a simpler
alternative the plan had discarded.

So this call reads a short **brief** (`shared/templates/architecture_brief.md`)
listing the options **without** the reasons any were rejected — three lines
when the plan adds nothing permanent, see the template.

```bash
# 1. Re-read the brief Step 5-int-arch already wrote (always runs first, so
#    the file exists). Update it in place if Step 5-int-arch's own triage OR
#    Branch A's integration (above) changed the option — never re-author.

# 2. Ask the same two models (same driver resolution as Branch A above).
uv run --project "{plugin_root}" {shared_root}/scripts/tools/external_review.py \
  --mode architecture \
  --brief-file "{planning_dir}/architecture_brief.md" \
  --spec-file "{spec_file}" \
  --plugin-root "{plugin_root}" \
  --driver "$([ -n "${CODEXTENDER_ACTIVE:-}" ] && echo codex || echo claude)"
```

The CLI **refuses `--plan-file` in this mode** (usage error, exit 2): silently
accepting the plan would restore the anchoring while the emitted envelope stayed
byte-identical.

`approve` → proceed. `revise` → integrate like any other finding. **`reject`
from either reviewer → STOP and ask the user**, before Step 6, because the whole
value is that this is seen while nothing is built yet:

> The architecture review says this should not be built this way.
> {glm} says **{verdict}**, {openai} says **{verdict}**. They recommend:
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
- **Verdicts:** glm={approve|revise|reject} · openai={…}
- **Smallest thing that would do (per reviewers):** {one line, or `as proposed`}
- **Reconciliation:** {what the plan had rejected, why, and the user's decision}
- **Status:** {proceeding as planned | reworked | alternative adopted}
```

Log each finding to `decision_log.md` with `--section "Architecture Review —
{split_name}"`.

Step 5b is unchanged: this pass writes **no marker of its own**, and
`external_review_state.json` continues to record the plan review alone. Its
provenance is `plan.md` + `decision_log.md`, both git-tracked and both read by
the compliance audit.

Then go to the **Pre-5b Checkpoint**.

---

## Branch B — `external_review_status == "missing_keys"`

`feedback_iterations > 0` but no API key was found in `.env.local`.
**Stop** and ask the user verbatim:

> External LLM review is the recommended quality gate for this plan, but no `OPENROUTER_API_KEY` or `OPENAI_API_KEY` was found in `.env.local`.
>
> **Option 1 (recommended):** Add `OPENROUTER_API_KEY=...` to `.env.local` at the repo root and say "ready" — I'll re-check and run the external review.
> **Option 2:** Skip external review. The Internal Plan Review (Step 5-int) already checked the plan and carries the gate — I'll log the opt-out in the decision log.
>
> Which option?

Do NOT proceed until the user explicitly chooses.

- **User picks Option 1:** wait for their "ready" confirmation, then re-check:
  ```bash
  uv run --project {plugin_root} {shared_root}/scripts/checks/check-external-review-keys.py
  ```
  If `available: true`, fall into Branch A and follow it to the end
  (`external_review.py`, integrate, log → Step 5a → Pre-5b Checkpoint → Step
  5b). If still `false`, ask the user again (they may have edited the wrong
  file or forgotten to save).
- **User picks Option 2:** the **Internal Plan Review**'s `Ran:` value decides
  whether this needs the Self-Review Fallback — see the **Pre-5b Checkpoint**
  below. Capture the user's reason (offline, no keys yet) for the marker either way.

---

## Branch C — `external_review_status == "user_disabled"`

`feedback_iterations == 0` — explicit opt-out via config. Print:

```
External LLM review disabled via config (feedback_iterations: 0).
Internal Plan Review (Step 5-int) already ran and carries the gate.
```

Go to the **Pre-5b Checkpoint** below, which resolves whether Step 5-int's
`Ran:` value leaves this branch needing the Self-Review Fallback.

---

## Pre-5b Checkpoint — did an independent review actually complete?

**One rule, checked once, whichever branch ran:** has the plan been independently
reviewed at all — Step 5-int with `Ran: yes`, OR a completed Branch A external
review? (Step 5-int-arch does not count.) If **either** is true, skip straight
to Step 5b. If **neither** is true, the plan has had no independent review yet —
run the **Self-Review Fallback** below now, before Step 5b. This is the single
place that decides it; no other section re-triggers or skips it.

---

## Self-Review Fallback (sub-block) — last resort only

**Runs only when the Pre-5b Checkpoint above says no independent review completed.**
This is the true last resort — every other path relies on Step 5-int or a
completed Branch A review instead.

This is the "2x denken" pass: re-read `plan.md` with a critic's eye against five
checks — **architectural soundness** (design decisions worth second-guessing),
**section boundaries** (hidden cross-dependencies), **TDD coverage** (behavior
vs. implementation detail), **risk hotspots** (riskiest section + mitigation),
**assumptions** (unconfirmed by the user) — integrate corrections, and append:

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
`write_decision_log.py --section "Self-Review — {split_name}"`. Then go to
**Step 5b**.

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
  --verdict glm={approve|revise|reject|unknown|unavailable} \
  --verdict openai={approve|revise|reject|unknown|unavailable} \
  --contradiction-resolution "{only when the reviewers disagreed}" \
  [--self-review-fallback-ran]
```

- Branch A, external review completed → `--status completed --provider {actual
  provider}`, plus one `--verdict` per reviewer, copied from the CLI's
  `verdicts` block. The contradiction is **derived** from the pair — no flag
  asserts agreement the verdicts do not support.
- Branch A degraded, Branch B Option 2, and Branch C share one shape
  (`--status skipped_user_opt_out` for A/B, `skipped_config_disabled` for C;
  omit `--provider`, defaults `null`), set by the Pre-5b Checkpoint's outcome
  plus the branch's reason suffix — `"; both external providers failed"` (A
  degraded), `"; user opt-out: {reason}"` (B), or `"; external review
  disabled in config (feedback_iterations: 0)"` (C):
  - **Checkpoint found an independent review** (Step 5-int `Ran: yes`) →
    `--findings-count {its finding count} --reason "internal review
    (opus-plan-reviewer) carried the gate{suffix above}"`.
  - **Checkpoint ran the Self-Review Fallback** (neither completed) →
    `--findings-count 0 --reason "self-review fallback ran instead (no
    independent review completed){suffix above}" --self-review-fallback-ran`.

Pass `--contradiction-resolution` only when the CLI reported
`requires_resolution: true`, with the decision the **user** made; without it
Step 6 refuses to begin. Reviewer names must be `glm` and `openai`, each
given once. Branch A degraded, Branch B and Branch C all record **no
verdicts** — refused even when the degraded CLI reported
`glm`/`openai: unavailable`, correctly (a skipped review has no reviewers).
A **`completed`** review with no verdicts is treated as not-yet-recorded and
blocks Step 6 — omitting the flags is not a way to opt out of the
disagreement check.

**Checkpoint:** `{planning_dir}/external_review_state.json` exists and its
state is clear to proceed past — the same question the resume gate and
compliance `W5` ask, via `lib.review_marker.evaluate_review_state`. A marker
recording an undecided disagreement sends a resumed session back to Step 5.
