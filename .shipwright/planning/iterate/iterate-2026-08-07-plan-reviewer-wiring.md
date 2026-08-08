# Iterate Spec: plan-reviewer-wiring

- **Run ID:** iterate-2026-08-07-plan-reviewer-wiring
- **Type:** change
- **Complexity:** medium
- **Status:** implemented

## Goal
Wire the existing `opus-plan-reviewer` subagent into `/shipwright-plan` Step 5
so a plan is never gated by self-assessment alone: it runs an independent
internal review before branching, and that review carries the gate on the two
branches where external review is unavailable (`missing_keys` opt-out,
`user_disabled`), replacing the "2x denken" self-review checklist there.
`opus-plan-reviewer` has existed since the plugin's own history and is
referenced by no other file (verified 2026-08-07 by a full grep over
`plugins/`) — this closes that dead-registry-entry defect. Model tiering is
explicitly out of scope (trg-88621183's job); the wiring relies on the
agent's own pre-existing `model: opus` frontmatter and adds no override.

## Acceptance Criteria
- [x] AC-1: `/shipwright-plan` Step 5 always spawns `opus-plan-reviewer` over
      `plan.md` + `spec.md` before branching on `external_review_status`,
      regardless of which branch follows.
- [x] AC-2: Every internal-review finding is triaged `fix` (integrated into
      `plan.md`), `disclose` (a `**Known limitations:**` bullet in the
      `## Internal Plan Review` block AND a decision_log entry — a
      destination, not a shrug), or `decline` (recorded with a legitimate
      reason) — logged to `decision_log.md` under
      `Internal Plan Review — {split_name}`. This 3-way vocabulary is scoped
      to Step 5-int only; Branch A's existing "addressed or declined"
      wording is untouched (scope-ratchet guard, finding 7 of the internal
      review — see mini-plan §6).
- [x] AC-3: The "2x denken" Self-Review Fallback sub-block runs in exactly
      one place, checked once regardless of which branch (A degraded,
      B Option 2, or C) reached it: only when neither the internal review
      (`Ran: yes`) nor a completed Branch A external review exists. Whenever
      an independent review of either kind exists, it carries the gate
      instead — the fallback is never re-triggered per branch.
- [x] AC-4: Branch A is unaffected in its own wording/vocabulary (external
      review still runs, still writes the marker, "addressed or declined"
      stays binary) except that it now runs *after* the internal pass rather
      than being the plan's only independent check.
- [x] AC-5: A finding that would add plan/spec scope the spec itself calls
      unsupported must be declined, not integrated (scope-ratchet guard) —
      stated once, applies to every pass in Step 5 (internal, external,
      architecture).
- [x] AC-6: `external_review_state.json`'s JSON *schema* is untouched — no
      new field, no marker of its own for the internal pass (same schema
      precedent as Step 5a Architecture Review). Branch B/C DO report the
      internal pass's outcome, but through the marker's *existing*
      `--findings-count`/`--reason` values, not a schema change — so
      `check-plan-gates.py --gate review` / `review_marker.py` need no code
      change, only different values at the call site.
- [x] AC-6a: Step 5-int runs at most once per Step 5 — a resumed session or
      Branch B's retry loop must not re-spawn `opus-plan-reviewer` or
      duplicate the `## Internal Plan Review` section (checked by presence
      of that heading in `plan.md` recording `Ran: yes`; a `Ran: no` section
      is replaced in place on retry, never duplicated).
- [x] AC-6b: A declined `severity: high` internal finding stops the run and
      puts the decision to the user before Step 6 (mirrors Step 5a's
      `reject` prompt); `gate_catalog.json` carries the single_session
      auto-default for it.
- [x] AC-7: `shared/config/gate_catalog.json` entry `plan.external-review-missing-keys`
      reflects the new default behavior (internal review carries the gate,
      not self-review), and `shared/config/gate_catalog.md` is regenerated
      to match (`test_doc_matches_generated_catalog`).
- [x] AC-8: `docs/guide.md`'s description of `/shipwright-plan` Step 5 and its
      fallback narrative is updated; iterate's own separate self-review
      fallback (unrelated mechanism) is left untouched.
- [x] AC-9: `SKILL.md` stays <=300 LOC (already at the cap, zero headroom);
      `step-5-external-review.md` stays <=400 LOC.

## Spec Impact
- **Classification:** modify
- **ADD:** none
- **MODIFY:** FR-01.03 (`/shipwright-plan`) — folds one new acceptance
  criterion (draft wording in mini-plan §7, internal-review-approved): the
  review gate is never satisfied by self-assessment alone, because an
  independent internal reviewer has already checked the plan whenever the
  outside reviewers cannot be reached or are switched off. This is FOLD not
  MINT per `shared/fr-authoring.md` §3 — /shipwright-plan already had a
  review step with a documented fallback; this closes an asymmetry inside
  that same capability, it does not add a new one.
- **REMOVE:** none
- **NONE justification:** n/a

## Out of Scope
- Model-tier configuration (flags, project config, precedence) — trg-88621183.
- `/shipwright-iterate`'s own mirrored "External LLM Review Trigger" for
  iterate's inline mini-plan review (`iteration-planning.md`) — a separate
  mechanism the card did not name; its own Self-Review Fallback is untouched.
- Any change to `opus-plan-reviewer.md`'s own prompt body, schema, tools, or
  model — its `description:` frontmatter line is the one exception (it is
  discovery metadata, not behavior, and is now factually stale — see mini-plan
  §6 finding 11).
- Any change to `check-plan-gates.py`, `review_marker.py`, or the marker
  schema — the internal pass is provenance-only (plan.md + decision_log.md).

## Design Notes
n/a — no UI, no mockups. This is agent-instruction wiring (SKILL.md +
references) plus a config-doc regeneration.

## Affected Boundaries
`opus-plan-reviewer`'s JSON review-report contract already existed
(`agents/opus-plan-reviewer.md` "Output" section) but had no consumer — this
iterate wires the first one.

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `shipwright-plan:opus-plan-reviewer` subagent (Agent-tool text output) | Step 5-int instructions in `step-5-external-review.md` | JSON: `{reviewer, severity, findings[], summary}` |

No code-level `json.load`/`json.dump` boundary is touched (the consumer is
the planning agent reading subagent output at runtime, not a Python parser),
so the diff-driven `touches_io_boundary` detector is not expected to fire.
Verified empirically instead (see Confidence Calibration).

## Confidence Calibration
- **Boundaries touched:** the `opus-plan-reviewer` JSON contract above
  (pre-existing schema, first real caller).
- **Empirical probes run:**
  - Live-spawned `opus-plan-reviewer` over this iterate's own mini-plan
    (dogfooding the exact instructions being written) and confirmed the
    returned JSON matches the shape Step 5-int expects to parse — see
    `## Internal Plan Review` in this iterate's mini-plan / ADR.
  - `pytest plugins/shipwright-plan/tests/ -v` — confirms
    `test_skill_references_link.py`'s LOC/link-resolution gates still pass
    with the edited files.
  - `pytest shared/tests/test_gate_catalog.py shared/tests/test_gate_catalog_doc_sync.py -v`
    — confirms the edited catalog entry still validates and the regenerated
    `.md` matches byte-for-byte.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | `SKILL.md` stays <=300 LOC after the edit | tested | `test_kern_skill_md_under_300_loc` PASSED |
  | 2 | `step-5-external-review.md` stays <=400 LOC | tested | `test_every_new_reference_under_loc_budget` PASSED |
  | 3 | Every `references/*.md` link in Kern SKILL.md still resolves | tested | `test_every_kern_link_resolves` PASSED |
  | 4 | `opus-plan-reviewer` invocation actually returns parseable JSON matching the documented schema | tested | live dogfood spawn, this run — see ADR |
  | 5 | `gate_catalog.json` still validates (policy/fires/phase enums, auto-default carries a default_answer) | tested | `test_gate_catalog.py::test_every_gate_has_valid_fields` PASSED |
  | 6 | `gate_catalog.md` matches the regenerated render after the entry-text edit | tested | `test_doc_matches_generated_catalog` PASSED |
  | 7 | Existing plan-plugin test suite has no regression from the SKILL.md/reference edits | tested | `pytest plugins/shipwright-plan/tests/ -v` PASSED |
  | 8 | New `gate_catalog.json` entry `plan.internal-review-high-severity-declined` validates (policy/fires/phase enums, auto-default carries a default_answer, not constitution-locked+auto-default) | tested | `test_gate_catalog.py::test_every_gate_has_valid_fields` + `test_auto_default_gates_carry_a_default_answer` PASSED (generic, iterates all gates) |
  | 9 | `disclose` triage category has a real destination (not silently dropped) | tested | live dogfood run produced a genuine `disclose` disposition (finding 14, the pre-existing `\n` bug) — see mini-plan §6 row 14 and `decision_log.md` |
  | 10 | A `severity: high` finding can be legitimately declined with a recorded reason (scope-ratchet guard exercised, not just specified) | tested | live dogfood run declined finding 6 (severity medium, but same mechanism — see mini-plan §6 row 6) with a reason tied to the card's own scope language, not a rubber stamp |
- **Confidence-pattern check:** asymptote — the internal-Opus-review pattern
  was already applied once, live, to this very mini-plan before this section
  was finalized (see WICHTIG in the run's arguments), and its findings are
  folded below; no further "are you confident?" cycle pending. Coverage —
  every ledger row `tested`, 0 untested-testable. No `cross_component`
  machinery touched (not `hooks.json`, not the merge/churn/event-log
  resolver), so Integration Coverage does not apply.

## Verification (medium+)
- **Surface:** none
- **Runner command:** n/a
- **Evidence path:** n/a
- **Justification (only if surface=none):** This change edits agent
  instructions (Markdown prose consumed by an LLM at plan-time) and a
  generated config doc — there is no startable web/cli/api surface to drive.
  Verification is the pytest suites above plus the live dogfood spawn
  recorded in Confidence Calibration and the ADR.
