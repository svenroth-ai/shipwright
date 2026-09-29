# Mini-Plan: campaign-runner-architecture-review

- **Run ID:** iterate-2026-09-29-campaign-runner-architecture-review

## 1. Files to create/modify

| File | Change |
|---|---|
| `plugins/shipwright-iterate/skills/iterate/references/campaign-step-3-5-plan-review.md` | new — the extracted Step 3.5 body (both Branch A calls, B/C, recording, reject-halt shape) |
| `plugins/shipwright-iterate/agents/sub-iterate-runner.md` | edit — Step 3.5 shrunk to pointer + branch labels + halt rule; Output gains the escalation example + `reviews.architecture`; net −18 lines |
| `plugins/shipwright-iterate/agents/sub_iterate_runner_contract.schema.json` | edit — new `reason_code`, `architecture_review`, conditional `then`; `reviews.architecture` |
| `plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md` | edit — Step 3.5 pointer, finalize step 5 (surface halted units); paid for by condensing two stale history paragraphs (net 0) |
| `plugins/shipwright-iterate/skills/iterate/references/iteration-planning.md` | edit — step 2a: campaigns run it |
| `docs/guide.md`, `docs/hooks-and-pipeline.md` | edit — describe the wiring |
| `.shipwright/planning/01-adopted/spec.md` | edit — FR-01.11 AC39 |
| `shipwright_bloat_baseline.json` | edit — runner `current` 528 → 510 (lowered only) |
| tests | new prose-contract test (runner), new integration test (composition); update the 3 drift tests that counted the runner's moved blocks; lower the runner line ceiling |

## 2. Work breakdown

1. Extract Step 3.5 → reference; slim the runner; verify line count < 528.
2. Add the architecture call + brief instruction + halt shape to the reference.
3. Schema: reason code, `architecture_review`, conditional required fields.
4. Orchestrator: pointer + finalize step 5; offset lines inside the same file.
5. Docs + spec AC39.
6. Tests: unit prose + schema; integration through the real `autonomous_loop.py`.
7. Baseline: lower `current`.

## 3. Component hierarchy
n/a

## 4. Data model changes
`result.json` (escalated) gains `architecture_review`; nothing persisted elsewhere.

## 5. Test strategy
Prose-contract + schema tests (positive and four negative shapes); a
`category:"integration"` test driving verdict parser → schema → real
`autonomous_loop.py record` subprocess; the existing suites that pin the runner
(contract, finalization, step-3.4, driver-prose, key-consistency, cascade shape).

## 6. Alternative approach (medium only)
Keep the inlined copy and mint a new ADR-gated bloat exception for the extra
lines — rejected: it records the duplication (the cause of this divergence) as
permanent, and the operator ruled it out on 2026-09-06.
