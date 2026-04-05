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
1. Read affected spec sections (`planning/*/spec.md`)
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

**Location:** `planning/iterate/{date}-{short-description}.md`

Create BEFORE mini-plan. Status lifecycle:
- `draft` → created now
- `implemented` → set during finalization when ACs checked off
- `superseded` → if escalated to full pipeline

Template: See SKILL.md Section 2.0.

---

## Mini-Plan Protocol

**When:** FEATURE + small/medium, CHANGE + medium, BUG + medium

### Content
1. **Files to create/modify** — list with expected change type (new/edit)
2. **Component hierarchy** (if UI) — parent→child tree
3. **Data model changes** (if any) — tables, columns, RLS
4. **Test strategy** — which tests to write/update, E2E needed?
5. **Alternative approach** (medium only) — one alternative + why rejected

### Persistence
- **Small:** Inline in session only (no file)
- **Medium+:** Save as `planning/iterate/{date}-{desc}-miniplan.md`
  - Include `run_id` in header
  - This file is passed to `review.py --plan-file`

---

## Escape Hatch Protocol

**Trigger:** Stage 2 Repo Scout finalizes complexity = large.

### Banner
Print the scope assessment with two options (see SKILL.md Section 3).

### Option 1: Semi-automatic pipeline transition
1. Write handoff file: `planning/iterate/{run_id}-handoff.json`
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

**When:** Medium complexity (auto), or any complexity with `--review` flag.

### Invocation
```bash
uv run {plan_plugin_root}/scripts/llm_clients/review.py \
  --mode iterate \
  --spec-file "{iterate_spec_path}" \
  --plan-file "{miniplan_path}" \
  --plugin-root "{plan_plugin_root}"
```

### Handling Results
- Parse JSON output: `reviews.gemini.feedback` + `reviews.openai.feedback`
- Print findings summary to user
- For high-severity findings: discuss with user before proceeding to build
- For low/medium: note in ADR, proceed
- If review fails/skipped: record in `degraded` array, note in ADR
