# Iteration Planning Reference

Consolidated protocol for: Repo Scout, Mini-Plan, Escape Hatch, External LLM Review trigger.

---

## Repo Scout Protocol

**Purpose:** Confirm or upgrade the Stage 1 complexity estimate via structured repo analysis.

### Quick Scout (trivial/small estimate)
1. Read `shipwright_sync_config.json` — identify affected FRs
2. Check affected file count (glob or git diff preview)
3. **Run the diff-driven detectors over that file list** and apply their
   floors — `is_cross_component_change`, `is_ci_supplychain_change`,
   `is_io_boundary_change`, `touches_build_files` (all importable from
   `classify_complexity` / `risk_detectors`). **This step is load-bearing, not
   a nicety.** Stage 1 has no diff: it fires `cross_component` and the rest
   only from *message* keywords, so a change that touches `hooks.json` or
   `churn_merge.py` without naming it raises nothing. `cross_component` floors
   at **medium** — that is a *classification* floor: it escalates the run, and
   is not what decides whether the F11 gate enforces. The F11 verifier
   `check_integration_coverage` recomputes the flag from the diff and enforces
   at **every** complexity, so a detection missed here is still caught
   mechanically at finalization (iterate-2026-08-01-coverage-gate-recompute-order).
   **That is a backstop, not a substitute.** Being caught at F11 means being
   blocked *after* the work is built, with the integration test still to write;
   catching it here is what lets the run be scoped correctly from the start. The
   file list from step 2 is already in hand; this is the first point in the run
   where a diff-shaped signal exists at all.
4. Verify risk flags from Stage 1 are accurate
5. Check if the change crosses split boundaries (cheap: the FRs from step 1)
6. Output: confirm estimate or upgrade

> **Why Quick Scout carries these two steps.** The fall-through prior is capped
> at `small` (SKILL.md §E), so most no-keyword runs now arrive here rather than
> at Thorough Scout. The cap's whole justification is that under-classification
> is recoverable *at Stage 2* — which is only true if the Stage 2 that actually
> runs can still see cross-component and cross-split changes. Steps 3 and 5
> are what make that true; without them the recovery mechanism would have been
> weakened by the same change that started relying on it
> (iterate-2026-07-31-it5-classification-calibration, doubt review objection 1).

### Thorough Scout (medium estimate)
All of Quick Scout, plus:
1. Read affected spec sections (`.shipwright/planning/*/spec.md`)
2. Scan FR neighborhood — what else is nearby?
3. Check if change crosses split boundaries
4. Identify shared components/utilities affected
5. Output: final complexity with reasoning

### Required Outputs (printed in Planned Run Summary)
- Affected files list (estimated)
- Affected FRs (from sync config or spec scan)
- Risk flags triggered (from canonical risk taxonomy in SKILL.md)
- Cross-split: yes/no
- Final complexity determination with reasoning

---

## Iterate Spec (medium+ only)

**Location:** `.shipwright/planning/iterate/{date}-{short-description}.md`

Create BEFORE mini-plan. Status lifecycle:
- `draft` → created now
- `implemented` → set during finalization when ACs checked off
- `superseded` → if escalated to full pipeline

Template: See SKILL.md Path A Step 1 (inline template). The template
includes a `## Verification (medium+)` section that pins surface +
runner + evidence path for the F0.5 gate.

### Acceptance Criteria — Verification Shape (medium+)

ACs in iterate specs MUST be assertion-shaped, not story-shaped — so
the F0.5 runner can verify them mechanically. Story-shaped ACs cannot
be empirically driven through the surface and silently degrade F0.5
to spec-only authorship (counts as no test).

**Story-shaped (do NOT use):**

- "User can save the form"
- "Settings persist across reloads"
- "API endpoint works"

**Assertion-shaped (use these):**

- "POST /api/forms with valid payload returns 200; subsequent GET
  returns the saved record with `status = 'submitted'`"
- "After clicking Save and reloading, the input
  `[data-testid='form-name']` still contains the entered value"
- "GET /api/health returns 200 with `{ status: 'ok' }` body"

### Two ACs at medium+

For each user-visible behavior, write two ACs:

- **AC-N-agent (mandatory).** Live E2E run by the agent before F6.
  Recorded in `shipwright_test_results.json.iterate_latest.surface_verification`.
  F6 blocks without it.
- **AC-N-user (optional).** User UAT walk-through before merge. Does
  NOT gate iterate finalization — it's a sanity check, not a
  blocker. Helpful for changes whose visual or interaction quality
  the agent can't fully assess (animation timing, perceived
  responsiveness, copy tone).

---

## Mini-Plan Protocol

**When:** FEATURE + small/medium, CHANGE + medium, BUG + medium

### Content
1. **Files to create/modify** — list with expected change type (new/edit)
2. **Work breakdown** (medium only) — numbered implementation steps in order:
   - Each step = one logical unit of work (1 component, 1 route, 1 migration)
   - Include test expectation per step
   - Steps are executed sequentially within one iterate run
3. **Component hierarchy** (if UI) — parent→child tree
4. **Data model changes** (if any) — tables, columns, RLS
5. **Test strategy** — which tests to write/update, E2E needed?
6. **Alternative approach** (medium only) — one alternative + why rejected

### Persistence
- **Small:** Inline in session only (no file)
- **Medium+:** Save as `.shipwright/planning/iterate/{date}-{desc}-miniplan.md`
  - Include `run_id` in header
  - This file is passed to `review.py --plan-file`

---

## Escape Hatch Protocol

**Trigger:** Stage 2 Repo Scout finalizes complexity = large.

### Banner
Print the scope assessment with two options (see SKILL.md Section 8).

### Option 1: Semi-automatic pipeline transition
1. Write handoff file: `.shipwright/planning/iterate/{run_id}-handoff.json`
   - Schema: run_id, source, target, scope_description, affected_frs, risk_flags, repo_scout_findings, iterate_spec_path, reason
2. If iterate spec exists, update status to `superseded`
3. Print: "Handing off to /shipwright-project --extend --from-iterate {path}"
4. Invoke `/shipwright-project` with handoff context
5. **Failure:** If project plugin unavailable, print manual instructions + handoff file path

### Option 2: Force iterate
- Full test suite + full code review mandatory
- ADR notes: "scope exceeded iterate threshold, user chose to continue"

---

## External LLM Review Trigger

**Self-review is mandatory for ALL complexity levels** (see
[iteration-reviews.md](iteration-reviews.md) — "2x denken" protocol).
External LLM review is layered on top for medium+ complexity.

### Trivial / small complexity

External review is **NOT** run by default. Opt in via `--review` flag when
invoking iterate. Fallback is always the self-review checklist in
`iteration-reviews.md`.

No `external_review_state.json` marker is written for trivial/small iterate
runs — the self-review outcome lands in the iterate ADR.

### Medium / large complexity — default external review with interactive opt-out

Mirrors `/shipwright-plan` Step 5 Branch A / B / C flow.

1. Compute `external_review_status` via the shared helper (same detector
   used by /shipwright-plan, behavior is identical):
   ```bash
   uv run "{shared_root}/scripts/checks/check-external-review-keys.py"
   ```
   Parse the JSON output. One of: `available`, `missing_keys`, `user_disabled`.

2. **Branch A — `available`:** run external review as today.
   ```bash
   uv run "{shared_root}/scripts/tools/external_review.py" \
     --mode iterate \
     --spec-file "{iterate_spec_path}" \
     --plan-file "{miniplan_path}" \
     --plugin-root "{plan_plugin_root}" \
     --project-root "{project_root}" --run-id "{run_id}"
   ```
   (`--run-id` is additive — it records this call's real boundary as an
   `external_review` timing span, parent `planning`; omitting it just skips
   the recording, see [iterate-timings](iterate-timings.md).)
   (`--plugin-root` is the plan plugin root — used only for plan-mode prompt
   lookup. For iterate-mode it is not consulted, but the argument remains
   required for CLI shape compatibility.) Present findings, integrate into
   the mini-plan, log decisions to the iterate ADR. Then run the second call
   (step 2a) and write the marker (step 5 below).

2a. **Architecture Review — the second call** (Branch A only; skipped under
   B/C with the first, since it needs the same provider).

   One extra call in the same step — not a second step and not a new gate. It
   asks the one question no other pass asks: *should this be built at all, and
   what is the smallest thing that would do?* The cascade and the plan review
   above both judge the change **within** the frame the plan set.

   **What makes it work is the input, not the prompt.** The mini-plan carries
   `Alternative approach — rejected because X`; a reviewer handed that document
   has been handed the answer. So this call reads a short **brief** instead,
   written from `shared/templates/architecture_brief.md`, which lists the
   options **without** the reasons any were rejected. Measured twice: same two
   models, same change, `approve` over the plan and `reject` over a brief
   (`iterate-2026-07-28-derived-snapshots-refresh`, and again on PR #498).

   ```bash
   # 1. Write the brief. If this change adds nothing permanent, that is THREE
   #    LINES — see the template. Do not copy the mini-plan's rejection
   #    rationale into it.
   #    → .shipwright/planning/iterate/{run_id}/architecture_brief.md

   # 2. Ask the same two models.
   uv run "{shared_root}/scripts/tools/external_review.py" \
     --mode architecture \
     --spec-file "{iterate_spec_path}" \
     --brief-file "{project_root}/.shipwright/planning/iterate/{run_id}/architecture_brief.md" \
     --plugin-root "{plan_plugin_root}" \
     --project-root "{project_root}" --run-id "{run_id}"
   ```

   The CLI **refuses `--plan-file` here** (usage error, exit 2) — a silently
   accepted plan would restore the anchoring while the envelope stayed identical.

   **It runs on every medium+ Branch A of a standalone iterate, not behind a
   trigger.** A trigger the author sets fails first on exactly the changes that
   most need the question asked, and both external reviewers said so
   independently when this pass was reviewed with itself. The brief being three
   lines when nothing permanent is added is what keeps that affordable.
   **Campaign sub-iterates do not run it yet** — the `sub-iterate-runner`
   carries its own inlined copy of this step, is at its bloat cap, and cannot
   ask an operator on a `reject`. That gap is deliberate and named, not an
   oversight (trg follow-up).

   **On a `reject` from either reviewer — STOP and ask the operator.** Do not
   build first and report after; the whole value is a human seeing it while the
   code does not yet exist:

   > The architecture review says this should not be built this way.
   > {deepseek} says **{verdict}**, {openai} says **{verdict}**. They recommend:
   > **{the alternative, in one line}**. The mini-plan had considered that and
   > rejected it because: **{the reason, from mini-plan item 6}**.
   >
   > How should I proceed — take the alternative, keep the plan (I'll record
   > why the objection does not hold), or rework and re-review?

   **Where the result goes — NOT the `plan` review row.** Step 5 records that row
   from ONE `--payload-file`, and the *first* call's envelope is what fills it; a
   completed row is immutable, so there is no second write. Both reviewers'
   verdicts, their findings and the reconciliation go into the **iterate spec
   under `## Architecture Review`** and into the iterate ADR — the same
   destination `/shipwright-plan` Step 5a uses for `plan.md`, and both ship in the
   commit. Write it whatever the operator decides; that section is where the
   withheld reasoning re-enters the record. `revise` is not a stop: integrate it
   like any other finding. The pass adds no review row and no marker of its own.

   ```markdown
   ## Architecture Review
   - **Brief:** `.shipwright/planning/iterate/{run_id}/architecture_brief.md`
   - **Verdicts:** deepseek={approve|revise|reject} · openai={…}
   - **Smallest thing that would do (per reviewers):** {one line, or `as proposed`}
   - **Findings:** {each, with accepted-and-fixed | rejected-with-reason}
   - **Reconciliation:** {what the plan had rejected, why, and the decision}
   ```

3. **Branch B — `missing_keys`:** STOP and ask the user verbatim:

   > External LLM review is the recommended quality gate for this medium+
   > iterate, but no `OPENROUTER_API_KEY` or
   > `OPENAI_API_KEY` was found in `.env.local`.
   >
   > **Option 1 (recommended):** Add a key to `.env.local` and say "ready" —
   > I'll re-check and run the review.
   > **Option 2:** Skip external review. I'll rely on the mandatory
   > self-review ("2x denken") already run in the previous step and log the
   > opt-out in the iterate ADR.
   >
   > Which option?

   - Option 1 → re-check via `check-external-review-keys.py`, then Branch A.
   - Option 2 → log opt-out (with user's reason) in the iterate ADR. Self-review
     was already completed — no second pass required.

4. **Branch C — `user_disabled`:** config explicitly sets
   `feedback_iterations: 0`. Print a notice and skip external review. Rely on
   the mandatory self-review that already ran.

5. **Record the pass** (all branches) so downstream phases, compliance and the
   Mission view can see both the decision and what the review found:
   ```bash
   uv run "{shared_root}/scripts/tools/record_review_pass.py" record \
     --project-root "{project_root}" --run-id "{run_id}" \
     --review-type plan \
     --status "{completed | not_run}" \
     --marker-status "{completed | skipped_user_opt_out | skipped_config_disabled}" \
     --provider "{openrouter | null}" \
     [--from external-review-json --payload-file "{external_review.py stdout}"] \
     [--disposition "{why it did not run — required for not_run}"]
   ```
   This writes the run's review record AND dual-writes the legacy
   `external_review_state.json` marker — once under the run-scoped planning dir
   `.shipwright/planning/iterate/{run_id}/` (what the Mission view reads) and
   once at the historic shared path (what existing verifiers read). See
   "Recording each review pass" in [iteration-reviews.md](iteration-reviews.md).

### Handling results (Branch A)
- Parse JSON output: `reviews.deepseek.feedback` + `reviews.openai.feedback`
- Print findings summary to user
- For high-severity findings: discuss with user before proceeding to build
- For low/medium: note in ADR, proceed
- If review fails mid-run (both providers error): fall through to Branch B
  Option 2 flow, log in ADR with `reason: "both providers failed"`
