# Iterate Spec: campaign-declared-complexity-floor

- **Run ID:** iterate-2026-11-16-campaign-declared-complexity-floor
- **Type:** bug
- **Complexity:** medium
- **Status:** draft

## Goal
A campaign unit the operator declared `medium` must stay at least `medium` through Stage 1 and the diff-driven Step 3.4 re-check, so the plan, architecture and doubt reviews run. Today the declaration exists only as prose in the brief; the runner re-derives `small` from a 113-178 line diff (campaign profile-architecture-rules, units U1, U2, U4, U5, U6), and the reviews ran only because the orchestrator said so.

## Root cause
`campaign_init.py` writes a unit spec with no complexity field, so nothing machine-readable carries the brief's `medium`. `classify()` sees the spec text (keyword + risk regex + history prior, fall-through capped at `small`) and `diff_risk_recheck.recheck()` raises only from diff detectors; both can only land at `small` for an ordinary 100-200 line change. The F11 gates (`check_risk_recheck_recorded`, `check_review_record`, `cascade_trigger`) key off the F5c-recorded complexity, so they faithfully agree with the wrong tier.

## Acceptance Criteria
- [ ] A unit declaring `medium` classifies `medium` at Stage 1 for a message that otherwise estimates below it; a unit declaring nothing classifies exactly as before.
- [ ] The Step 3.4 re-check on a 113-line ordinary diff with Stage 1 `small` and the unit declaring `medium` reports `effective_complexity: medium` and `plan_review_required: true`; a unit declaring `small` is still raised to `medium` by a cross-component diff.
- [ ] `risk_recheck.json` carries `declared_complexity`; F11 fails a record whose effective tier is below it or whose F5c tier is below the effective one, and passes the agreeing record.
- [ ] The campaign planner writes a `Complexity:` line from the sub-iterate `complexity` key, rejects an unknown level before writing anything, and writes today's spec when none is given.

## Spec Impact
- **Classification:** modify
- **MODIFY** (existing FR changed): FR-01.11 — AC52 added (declared size is a floor)

## Out of Scope
- Back-filling `Complexity:` into the already-run profile-architecture-rules unit specs.
- Re-deriving the effective tier at F11 from the campaign spec (the recheck artifact stays a transcription-integrity record, as documented).
- Growing `campaign-mode.md` (bloat baseline cap): only one in-place 3-line edit, no net growth.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| campaign_unit_spec.render_unit_spec (`Complexity:` line) | declared_complexity.parse_declared_complexity (Stage 1, Step 3.4) | markdown line |
| diff_risk_recheck.write_recheck_record (`declared_complexity`) | risk_recheck_recording.check_risk_recheck_recorded | JSON |

## Confidence Calibration
- **Boundaries touched:** spec line (planner to classifier and re-check); risk_recheck.json (re-check to F11 gate).
- **Empirical probes run:** real campaign_init + real classify CLI + real recheck CLI on a real git repo with a 120-line ordinary diff (integration test): stays medium; under-recorded F5c fails the registered gate; agreeing record passes; undeclared unit stays small.
- **Test Completeness Ledger:** see the F5 block (all behaviors tested).
- **Confidence-pattern check:** depth: parse edge cases (prose line, wrong case, bold, quotation) probed; breadth: planner, Stage 1, recheck, CLI, verifier and integration all covered.

## Verification (medium+)
- **Surface:** none
- **Runner command:** n/a
- **Evidence path:** n/a
- **Justification (only if surface=none):** framework scripts and a verifier; no startable UI or API surface.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** high
- **Summary:** Core fix correct; planner never told to emit the key, and an unreadable or omitted spec path dropped the floor silently.
- **Findings:**
  - completeness/high: planner never told to emit `complexity` - fixed (one in-place line in campaign-mode.md, no growth; planner also rejects `large`).
  - security/medium: fail-open on unreadable `--spec` - fixed (OSError/ValueError now exit 2 in both CLIs; typo in the level is an error).
  - completeness/medium: F11 cannot detect an omitted `--spec` - disclosed (stated residual in the verifier docstring, like the existing transcription-integrity one).
  - architecture/medium: `large` accepted as declared tier - fixed (planner rejects it).
  - security/low: unquoted spec path in runner contract - fixed (quoted).
  - architecture/low: Stage 1 mined the floor from any message - fixed (read only from explicit `--spec`; a quoted line in a message is not a floor).
  - architecture/low: explicit argument could replace the spec value - fixed (maximum of both).
  - completeness/low: F5c `prior_source` still says keyword/history/default and declared-floored entries feed the history median - disclosed.
- **Known limitations:** an omitted `--spec` is not detectable at F11; `prior_source` does not name the declared floor.
- **Status:** 7 fixed, 2 disclosed, 0 declined

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** Build option A; the declared level may only raise the tier and must not be confusable with a spec own bold Complexity line.
- **Findings:** security/medium: floor must never lower and the line must be strict - fixed (max by rank, strict full-line parse, unknown level is an error, spec read only via explicit path); completeness/low: absent field at F11 - disclosed in docstring; complexity-cost/low: one shared format - covered by the planner-to-parser round-trip test.
- **Known limitations:** none
- **Status:** 1 fixed, 1 disclosed

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-11-16-campaign-declared-complexity-floor/architecture_brief.md`
- **Verdicts:** glm=approve · openai=approve
- **Smallest thing that would do (per reviewers):** as proposed (option A)
- **Findings:** none
- **Reconciliation:** the mini-plan had considered a command-line override and rejected it because nothing would persist the decision; both reviewers, shown only the brief, independently reached option A.

## External Plan Review (glm approve, openai revise)
- openai medium: legacy records without the field - handled (absent/null passes; tested). openai medium: preflight validation of all units - handled and tested (invalid second unit writes nothing). openai low: precedence of explicit vs spec - fixed (maximum, tested). glm medium: typo silently drops floor - fixed (error). glm medium: integration must prove the field lands in the record - covered (integration test asserts risk_recheck.json). glm low: declared medium plus large diff stays large - tested.

## Code Review Cascade (Step 8)
- spec-reviewer: PASS. code-reviewer: 4 low findings, all fixed (unused CLI option removed, apply_floor validates, header-only parser with tab and punctuation handling, noqa trimmed). External code review (glm, openai): both medium findings on parser order and position, fixed (first declaring header line decides and must be clean; a later valid line cannot paper over a typo).
- doubt-reviewer: (1) brief-to-key opt-in - the setup text now says MUST carry the key for every unit whose brief states a tier; the setup review of the generated campaign still shows each spec. (2) stale plugin cache without --spec - accepted and disclosed: the post-merge cache sync (update-marketplace.sh) is mandatory before the next campaign dispatch; F11 cannot tell omitted from undeclared. (3) parser scope - fixed (header only). (4) declared-floored F5c entries feed the history-prior median - accepted as a known limitation: the declared tier is an operator decision about real scope, and the fall-through prior stays capped at small.
- Known limitations (final): omitted --spec undetectable at F11; prior_source does not name the declared floor; declared entries feed the history median.
