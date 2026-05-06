# Iteration Planning Reference

Consolidated protocol for: Repo Scout, Mini-Plan, Escape Hatch, External LLM Review trigger.

---

## Repo Scout Protocol

**Purpose:** Confirm or upgrade the Stage 1 complexity estimate via structured repo analysis.

### Quick Scout (trivial/small estimate)
1. Read `shipwright_sync_config.json` — identify affected FRs
2. Check affected file count (glob or git diff preview)
3. Verify risk flags from Stage 1 are accurate
4. Output: confirm estimate or upgrade

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
     --plugin-root "{plan_plugin_root}"
   ```
   (`--plugin-root` is the plan plugin root — used only for plan-mode prompt
   lookup. For iterate-mode it is not consulted, but the argument remains
   required for CLI shape compatibility.) Present findings, integrate into
   the mini-plan, log decisions to the iterate ADR. Then write the marker
   (step 5 below).

3. **Branch B — `missing_keys`:** STOP and ask the user verbatim:

   > External LLM review is the recommended quality gate for this medium+
   > iterate, but no `OPENROUTER_API_KEY` (or `GEMINI_API_KEY` /
   > `OPENAI_API_KEY`) was found in `.env.local`.
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

5. **Write the marker** (all branches) so downstream phases and compliance
   can see the decision:
   ```bash
   uv run "{shared_root}/scripts/checks/mark-review-state.py" \
     --planning-dir "{iterate_planning_dir}" \
     --status "{completed | skipped_user_opt_out | skipped_config_disabled}" \
     --provider "{openrouter | null}" \
     --findings-count {N} \
     --reason "{optional reason}"
   ```
   Iterate writes the marker under its run-scoped planning dir
   (`.shipwright/planning/iterate/{run_id}-review-state.json` is the recommended
   location — pass that path as `--planning-dir`).

### Handling results (Branch A)
- Parse JSON output: `reviews.gemini.feedback` + `reviews.openai.feedback`
- Print findings summary to user
- For high-severity findings: discuss with user before proceeding to build
- For low/medium: note in ADR, proceed
- If review fails mid-run (both providers error): fall through to Branch B
  Option 2 flow, log in ADR with `reason: "both providers failed"`
