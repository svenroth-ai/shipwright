# Internal architecture-review arm for /shipwright-plan and /shipwright-iterate

## Context
Today the "should this be built at all" question is asked only by the
external pair of LLMs (Branch A). When external review is unavailable,
declined, or not yet configured, it is never asked. The Internal Plan
Review (`plan_internal`) already closed this exact hole for the narrower
plan-soundness question; this run mirrors that pattern for the
architecture question with a new, separate fresh-context agent
(`shipwright-plan:architecture-internal-reviewer`, distinct from
`opus-plan-reviewer`) so the architecture pass never inherits the plan
reviewer's own anchored frame.

## Decision
Add Step 5-int-arch (plan, unconditional) and a new iteration-planning
sub-step (iterate, medium+ only — mirrors `plan_internal`'s gating
exactly) that run always-first, before Branch A/B/C, authoring
`architecture_brief.md` and a `## Internal Architecture Review` section.
Add `architecture_internal` to `REVIEW_TYPES`/`OPTIONAL_PRESENCE_TYPES`
(additive, metadata-only, no `--from` adapter). Reuse the `plan_review`
model tier already resolved for Step 5-int/Internal Plan Review — no
second `resolve_model_tier.py` call. The pass does not carry the Pre-5b
gate (only `opus-plan-reviewer`/Step 5-int and Branch A do).

## Anchoring defense (Stage-3 doubt review, D1 — HIGH, fixed)
On the plan side the anchoring defense holds by construction: the
internal passes write to `plan.md`, never to `spec.md`, which is what
Branch A/`external_review.py` reads. On the iterate side there is only
ONE document — the iterate spec — which both carries the Acceptance
Criteria and receives the `## Internal Plan Review` / `## Internal
Architecture Review` / `## Self-Review` sections, and that same file is
passed as `--spec-file` to `external_review.py --mode architecture`.
This was a genuine leak: the pass built to escape anchoring was being fed
the most on-topic anchor there is. Fixed with a code-level backstop —
`strip_prior_review_sections()` in `shared/scripts/lib/
external_review_modes.py`, wired into `external_review.py`'s `main()`
for `--mode architecture` only (iterate mode intentionally keeps the
rationale visible; only the architecture pass's anchoring defense needs
the strip). Covered by
`shared/tests/test_architecture_review_anchoring_defense.py` (asserts
both that the strip fires for architecture mode and does NOT fire for
iterate mode).

## Other doubt-review objections (D2-D8), disposition
- **D2** (medium, fixed — escalated to a hard BLOCK by the F11 local
  PR-review preflight, run independently of this doubt review, before this
  fix landed): the new agent's own anchoring defense was prose-only
  (Read/Grep/Glob over the whole repo, no code enforcement), and its agent
  file inaccurately claimed parity with the external pass's own instruction
  (the external prompts have no such ignore-prior-review clause). Fixed the
  inaccurate cross-reference in `architecture-internal-reviewer.md`, AND —
  closing the harder structural gap the doubt review had deferred as
  **trg-16c08322** — added `shared/scripts/tools/
  prepare_architecture_internal_spec.py` (reuses `strip_prior_review_sections`)
  and wired it into `iteration-planning.md` step 0b: the agent is now handed
  a sanitized spec copy's path, never the real iterate spec, on the side
  that actually carries a prior-review section. Covered by
  `shared/tests/test_prepare_architecture_internal_spec.py` and a new
  contract-prose assertion. `trg-16c08322` dismissed as fixed, not deferred.
- **D3** (medium): the iterate spec's Reconciliation paragraph overstated
  GLM's agreement with the separate-agent decision as independent/
  unprompted, when GLM was handed a spec whose AC1 already stated that
  decision. Reworded so the decision rests on the operator's own
  confirmation, GLM's exposure to the AC1 wording noted explicitly.
- **D4** (medium): under a Codex-driven run, both sides always record
  `Ran: no` with no tracked follow-up card. Filed **trg-2b46f709**
  (dedicated Codex-CLI transport for `architecture_internal`) and cited
  its id in `shared/prompts/codex_review_dispatch.md`'s `Ran: no`
  wording.
- **D5** (medium): the new agent has never been executed once; the Test
  Completeness Ledger's "every AC has a direct mechanical assertion"
  overstated what prose-anchor tests actually prove. Added a Scope
  caveat to the iterate spec's ledger naming prose/wiring as tested and
  the agent's own live JSON-reply/degraded-path behavior as unexercised,
  rather than fabricate a throwaway spawn outside this run's own
  accounting.
- **D6** (low): `pending_types` counts an absent `architecture_internal`
  row as pending, so any medium+ run (or campaign sub-iterate) whose
  `reviews.json` predates the plugin-cache sync will STOP at F11 after
  the sync — same precedent as `plan_internal`'s own rollout. Accepted
  as precedent-equivalent; remediation for in-flight runs is
  `close-missing --only architecture_internal` (same tool, same flag
  shape `plan_internal` already established).
- **D7** (low): the Pre-5b Checkpoint section (plan skill) didn't name
  the `architecture_internal` exclusion, and Branch B's user-facing
  prompt text was ambiguous once two internal reviews existed. Fixed
  both: Branch B's prompt now names Step 5-int explicitly, and the
  Pre-5b Checkpoint paragraph now states "(Step 5-int-arch does not
  count.)" inline — both net-zero-line edits to keep
  `step-5-external-review.md` at its hard 400-line cap.
- **D8** (low): `plan_gate_extras.py`'s `_PLAN_DECISION_PREFIXES` didn't
  include "Internal Architecture Review", so gate #8
  (`decisions_recorded`) silently ignored every entry Step 5-int-arch
  logs. Fixed by adding the prefix (gate #10, `findings_addressed`,
  correctly stays unchanged — `architecture_internal` never carries the
  Pre-5b gate and never sets `findings_count`).

## Consequences
Both `/shipwright-plan` and `/shipwright-iterate` now ask the
architecture question on every run that reaches this step, regardless of
external-review availability, with the same code-level anchoring
guarantee the external pass already had. The Codex-driven path and the
campaign sub-iterate-runner path both still record `architecture_internal`
as a documented `Ran: no` / `not_run` gap (tracked, not silently
degraded); this run's own `architecture_internal` review is itself
recorded `not_run` — a bootstrap gap, not a skip: the type did not exist
when this run's own iteration-planning phase executed.

## F11 local PR-review preflight (Stage-3 CI gate, run independently of doubt review)
Two findings, both about `prepare_architecture_internal_spec.py` /
`architecture-internal-reviewer.md`:
- **Path traversal (high, fixed).** `--run-id` was joined unchecked into
  the output path, so a value like `../../somewhere` could redirect the
  write outside `.shipwright/runs/`. Fixed: the tool now refuses any
  `--run-id` that does not match `iterate_entry.RUN_ID_STRICT` (the same
  `iterate-YYYY-MM-DD-slug` format every caller of this tool already
  produces — only `iteration-planning.md` step 0b calls it, with the
  iterate's own run_id) and additionally verifies the resolved output
  directory stays under the intended runs root before writing, so a
  second bug in the format check can't reopen the same hole. Covered by
  two new tests in `test_prepare_architecture_internal_spec.py`.
- **Tool-access residual (declined, with reason).** The reviewer's
  broader point — the agent's own `Read`/`Grep`/`Glob` grant means a
  prose instruction not to seek out the original spec "does not enforce"
  the guarantee, and the agent's live behavior here is untested — is
  real but not new: it is D5 above, reached independently. No Shipwright
  or Claude Code primitive scopes a subagent's `Read`/`Grep`/`Glob` to a
  single file; every fresh-context reviewer in this codebase (including
  `opus-plan-reviewer`, `code-reviewer`, `doubt-reviewer`) already
  operates on the same trust model — a cooperative agent following its
  brief, not an adversarial sandbox. The D2 fix's actual guarantee is
  behavioral, not absolute: handing the agent the file it needs removes
  any task-motivated reason to look elsewhere, it does not make looking
  elsewhere impossible. Declining a fix that does not exist to write
  rather than disclosing this as new: D5's ledger caveat already states
  the agent's live JSON-reply/degraded-path behavior — which includes
  whether it in fact stays inside its given inputs — is unexercised. No
  further action beyond what D5 already tracks. Reworded
  `architecture-internal-reviewer.md`'s parenthetical from "this is now a
  code-level guarantee" to explicitly name the tool-access residual and
  call the sanitized copy risk-reduction, not enforcement — the finding's
  own fallback ask ("otherwise remove the claim") for the part that has
  no code fix.
- **Contributor-authored "DO NOT RE-OPEN" language (low, fixed).** The
  mini-plan's Alternative B rejection used that phrase for a decision
  already settled in an earlier pass of this same spec; reworded to
  neutral, non-directive language so text a contributor wrote cannot read
  as an instruction to a reviewer.
- **Resume-path gap (medium, fixed, a third F11 preflight pass).**
  `iteration-planning.md` step 0b stated the early "spec already says
  `Ran: yes` -> skip straight to step 1" rule BEFORE the separate
  paragraph reconciling a still-`pending` `architecture_internal` row on
  resume. A crash between writing the spec section and recording the row
  left the early rule reachable without ever reaching the reconciliation
  paragraph, so a resumed run could skip past step 1 with the row
  permanently `pending` — the exact case `check_review_record` (F11)
  fails closed on. Fixed by folding reconciliation into the same rule,
  ordered before the skip, so it cannot be structurally bypassed. Covered
  by a new ordering-sensitive test,
  `test_iterate_step_0b_reconciles_the_pending_row_before_skipping`.

## Rejected alternatives
- **Merge the new agent into `opus-plan-reviewer`** instead of a separate
  fresh-context agent. Rejected: `opus-plan-reviewer` is defined by
  reading the plan and its withheld rejection rationale; merging the two
  roles reintroduces exactly the anchor the fresh-context split exists to
  remove. Confirmed with the operator in-session (2026-09-28); GLM's
  review reached a similar conclusion independently of the merge
  question, though not independently of having read this spec's own AC1
  (see D3 above).
- **Run a real smoke-spawn of the new agent during this iterate** to
  close D5's untested-behavior gap. Declined: it would either need to
  count as this run's own `architecture_internal` pass (already
  `not_run` for a documented, temporal reason) or be a throwaway spawn
  outside that accounting — this run declines to fabricate either.
