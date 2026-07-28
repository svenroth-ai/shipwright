# Mini-Plan — the reviewer cascade gets an owner

Run: `iterate-2026-07-28-cascade-delegated-to-nobody` · BUG · medium
**Revision 2** — after the external plan review (gemini + openai, both `revise`,
11 findings). The campaign before-merge cascade is deferred; see spec §4a/§5.

## Implementation order (TDD — every step red first)

### S1 — Failing tests (`shared/tests/test_review_cascade_owner.py`, new)

Prose assertions follow `shared/tests/test_review_cascade_decoupled.py` (#476).

1. `SKILL.md` Step 8 names the three stages, says **this session** spawns them,
   and says it runs before F6. **RED**
2. `iteration-reviews.md`'s cascade section is not conditioned on the runner
   contract delegating it. **RED**
3. `sub-iterate-runner.md` Step 3.7 records the external run as `external_code`
   and never as `code`. **RED**
4. `sub-iterate-runner.md` carries a status-transition table naming the actor
   per review type. **RED**
5. `sub_iterate_runner_contract.schema.json` still *contains*
   `delegated_to_skill` (back-compat) but marks it deprecated, and
   `delegated_to_orchestrator` is described campaign-only. **RED**
6. `campaign-mode.md` does not claim the orchestrator spawns the cascade "in
   parallel with the runner after Build", and states the current residual gap.
   **RED**

### S2 — Integration test (`cross_component`, non-dodgeable)

`shared/tests/test_review_record_campaign_shape.py` (new). Composes **CLI →
record → verifier**, not markdown order:

- `record_review_pass.py record` writes the exact rows the fixed runner contract
  prescribes (`self` completed, `plan` completed, `code` not_run + capability
  disposition, `doubt` not_run + disposition, `external_code` completed);
  `check_review_record` at `complexity=medium` → **PASS**.
- The shape the *current* contract produces — `code` completed sourced from the
  external run — is no longer written by any documented command (asserted
  against the contract text, since the record itself cannot know provenance).
- A bare `--disposition "delegated"` is **rejected** by `disposition_ok`
  (< 12 chars / one word), so the capability disposition must be spelled out.
- `doubt` left `pending` → verifier FAILS, proving the runner cannot push
  without recording it.

Recorded as `category:"integration"` in the ledger.

### S3 — Prose fixes (AC1, AC2, AC7)

- `SKILL.md` Step 8 — owner, three stages, Stage-1 block, pre-F6 placement.
- `SKILL.md:203` — campaign-only marker on the ADR-029 sentence.
- `iteration-reviews.md:148-154` — decouple the cascade description from the
  runner contract; standalone owner first, campaign delegation second.
- `campaign-mode.md:10-22` — replace the impossible "in parallel after Build"
  claim with the actual current behaviour + the tracked follow-up.

### S4 — Runner contract (AC4, AC5)

- `sub-iterate-runner.md` Step 3.6/3.7: `record_review_pass.py` for `self`,
  `code` (not_run + capability disposition), `doubt`, `external_code`.
- Status-transition table (actor · allowed status · required disposition).
- `mark-review-state` stays LAST where still dual-written (memory:
  `--marker-status` drops verdicts).
- `sub_iterate_runner_contract.schema.json`: `delegated_to_skill` kept +
  marked deprecated; `delegated_to_orchestrator` described campaign-only.

### S5 — Floor message (AC6)

`review_record_check.py::_code_review_floor` — when only `external_code` carries
the pass at medium+, say that Stage-1 and Stage-3 have no external counterpart.
**No matrix re-encoding**; the module docstring's rejection of that stands.

### S6 — Docs, drift, follow-ups

- `docs/hooks-and-pipeline.md` + `docs/guide.md` Ch. 8 per CLAUDE.md rules.
- Re-run `test_sub_iterate_runner_contract.py` (25 structural tests) — headings
  and labels must survive the rewrite.
- File two triage items: the `spec` review type (E) and the campaign
  before-merge cascade, each carrying the spec §4a/§5 analysis.

## Risk

`cross_component` fires (touches `campaign-mode.md`) → integration coverage
mandatory (S2). No source file crosses 300 LOC; `SKILL.md` is a runtime-prompt
under the 400 cap and grows by ~6 lines. No migration, no schema-version bump,
no enum value removed.
