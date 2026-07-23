# Mini-Plan — REQ-3 Phase 1 — shared requirement-elicitation module

**Run ID:** iterate-2026-07-23-req3-elicitation-module

## Approach (chosen)

TDD, mirroring the `fr-authoring.md` iterate exactly:

1. **Red** — write `shared/tests/test_requirement_elicitation_refs.py` first:
   forward (both docs exist, non-empty, retain their cited section anchors +
   attribution + the coverage-checklist stop-condition + the glossary
   distinction) and reverse (the three interview surfaces each cite
   `requirement-elicitation.md`). It fails: docs and citations don't exist yet.
2. **Green** — author the two shared docs and add the three citations:
   - `shared/requirement-elicitation.md` — method (grilling discipline) +
     universal coverage checklist with `Basis: assumed` stop-condition + shared
     question bank + "how each plugin applies it" + attribution + "where the
     output lands (our FR/AC artifacts, not a PRD)".
   - `shared/context-format.md` — the `CONTEXT.md` domain-glossary format,
     modelled on Pocock's real CONTEXT.md (Language / Relationships / Flagged
     ambiguities), with the explicit `CONTEXT.md ≠ shared/glossary.md` warning.
   - Citations: `project/…/interview-protocol.md`,
     `adopt/…/step-c-interview.md`, `iterate/…/path-a-feature.md`.
3. **Spec** — MINT a new cross-cutting `FR-01.16` (Guided requirement
   elicitation) row + AC block (operator decision). FR-01.02/11/13 unchanged.
4. **Verify** — mutation probe (delete doc / strip citation → red), full suite
   green, `update-marketplace` reachability check.
5. **Reviews** — self-review, internal code-reviewer, external GPT-5.4 + Gemini
   3.1 Pro (medium auto). File the two Phase-4 follow-up triage items.

## Alternative considered (rejected)

**Pure method-only shared doc, question topics per-plugin** (interview Q2 Option
A). Rejected on the operator's reasoning: a method doc with no coverage guarantee
lets each plugin under-grill when embedded later → "then it's pointless / halb
shared". The chosen design centralizes the *completeness contract* (checklist +
stop-condition), which is precisely what forces enough grilling everywhere, while
still letting greenfield/brownfield/change specifics stay local as additions.

**Second alternative: also consolidate the three interview flows now** (interview
Q1 Option B). Deferred to Phase 4 by operator choice — keeps this PR reviewable
and lets Phase 2 dogfooding validate the module's shape before it's spread.

## Files

| File | Action |
|---|---|
| `shared/requirement-elicitation.md` | new |
| `shared/context-format.md` | new |
| `shared/tests/test_requirement_elicitation_refs.py` | new |
| `plugins/shipwright-project/skills/project/references/interview-protocol.md` | cite |
| `plugins/shipwright-adopt/skills/adopt/references/step-c-interview.md` | cite |
| `plugins/shipwright-iterate/skills/iterate/references/path-a-feature.md` | cite (FEATURE surface) |
| `plugins/shipwright-iterate/skills/iterate/references/path-b-change.md` | cite (CHANGE surface — both iterate surfaces pinned, per code review) |
| `.shipwright/planning/01-adopted/spec.md` | +FR-01.16 row + AC block (MINT) |
| `integration-tests/test_requirements_catalog_contract.py` | FR-count pins 15→16 (forced by the mint) |
| `integration-tests/test_requirements_catalog_parsers.py` | FR-count pins 15→16 + priority list + de-counted test names |
| `integration-tests/test_fr_table_shape_convergence.py` | FR-count pins 15→16 + FR-01.16 `Basis: interview` / `Layers: unit` pinned per-FR |
| `.shipwright/compliance/traceability-matrix.md`, `test-traceability.json` | **GENERATED, not hand-edited** — regenerated via `plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate` so the RTM carries `#fr-0116`; F5b regenerates again at finalize |
| `docs/guide.md` | **no change (decided)** — interview descriptions are not stale and no FR count is hardcoded; the module is discovered via plugin citations + the drift test, exactly like `fr-authoring.md` (which is in no index either) |
