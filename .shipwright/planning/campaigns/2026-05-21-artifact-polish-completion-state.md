# Campaign State — Artifact-Polish Completion (B.2 → C.3)

> Running log. The session executing this campaign updates this file
> after each iterate's merge so a future session can resume on
> context-loss. See the handover prompt at
> `.shipwright/planning/campaigns/2026-05-21-artifact-polish-completion-handover.md`.

## Status

- **Started:** 2026-05-21 (this session)
- **Current iterate:** C.3 (next)
- **Baseline (campaign start, 2026-05-21):**
  - `main` HEAD: `5c06748` (canon-lint allowlist `.shipwright/planning/adr/**.md`)
  - `shared/tests/`: 2101 passed, 12 skipped, 18 deselected
  - `plugins/shipwright-compliance/tests/`: 351 passed
  - `plugins/shipwright-iterate/tests/`: 237 passed
  - `plugins/shipwright-adopt/tests/`: 278 passed
  - `plugins/shipwright-build/tests/`: 46 passed
  - `plugins/shipwright-changelog/tests/`: 23 passed
  - `plugins/shipwright-test/tests/`: 136 passed
  - `plugins/shipwright-project/tests/`: 43 passed
  - `integration-tests/`: 110 passed
  - **No tolerated baseline failures.**

## Iterates

### B.2 — SBOM polish

- **Status:** merged
- **Branch:** `iterate/b2-sbom-polish` (deleted)
- **PR:** #57
- **Squash commit:** `47ab03d`
- **Predicted ADR:** ADR-056 (filed at `.shipwright/planning/adr/056-sbom-undeclared-triage.md`)
- **External review findings:** 12 (1 HIGH / 9 MED / 2 LOW) — all addressed; full disposition table in ADR-056.
- **External code-review findings:** 3 (2 MED accepted-and-fixed: malformed-manifest guard + error surfacing; 1 LOW rejected-with-reason: test fixture path counts).
- **Test deltas:** compliance 351 → 372 (+21); shared 2101 maintained (canon-lint allowlist gained `.shipwright/planning/campaigns/**.md` to clear regression introduced by #56).
- **Deviations from handover:**
  - Folded a chore-style canon-lint allowlist fix into the same commit (handover treated `5c06748` as baseline 2101; the campaign-state file from #56 had reintroduced one failure on the migration linter). In-scope per handover step-5 footnote.
  - `sbom_generator.py` crossed the 300-LOC guideline (now 339 LOC); test file at 343 LOC. Producer + helpers still cohesive; split into `sbom_triage.py` deferred to a future iterate if C.2 / future adds more producers.

### B.3 — test-evidence layer column + per-layer FAIL triage

- **Status:** merged
- **Branch:** `iterate/b3-test-evidence-layer-and-triage` (deleted)
- **PR:** #58
- **Squash commit:** `ccb2b98`
- **Predicted ADR:** ADR-057 (filed at `.shipwright/planning/adr/057-test-evidence-layer-and-triage.md`)
- **External review findings:** 18 (2 HIGH / 11 MED / 5 LOW) — all addressed inline; disposition table in ADR-057.
- **External code-review findings:** 4 (3 accepted-and-fixed: sanitize newlines + matching test rewrite + missing CLI flag tests; 1 truncated/rejected-with-reason).
- **Test deltas:** compliance 372 → 397 (+25); shared 2107 → 2116 (+9).
- **Deviations from handover:**
  - Extended `record_event.py` schema beyond the plan's wording: added `--<layer>-failed N` CLI flags AND non-negative-int validation AND `passed > total` rejection. All driven by the external review's HIGH findings (skipped-test false positive + input validation); in-scope per the handover audience principle ("loud only where relevant").
  - test_evidence.py crossed the 300-LOC guideline (~640 LOC). Producer + helpers still cohesive; split into a sibling `test_evidence_triage.py` deferred pending C.2's third producer landing (when a shared triage-producer base makes sense).
  - test_test_evidence.py crossed 600 LOC. Same deferral — split per-class file if it grows further.

### B.4 — RTM deep-link rendering + Coverage Summary rewrite

- **Status:** merged
- **Branch:** `iterate/b4-rtm-deep-link-and-coverage` (deleted)
- **PR:** #59
- **Squash commit:** `48024b1`
- **Predicted ADR:** ADR-058 (filed at `.shipwright/planning/adr/058-rtm-triage-deep-link-and-coverage.md`)
- **External review findings:** 15 (1 HIGH datetime determinism + 9 MED + 5 LOW) — all addressed; full disposition in ADR-058.
- **External code-review findings:** 6 (4 MED accepted-and-fixed: out-of-order events handling, spec/AC realignment around warn-emit, sort-order test strengthening, +00:00 suffix test; 1 HIGH rejected-with-reason — false-positive about non-work events; 1 truncated).
- **Test deltas:** compliance 397 → 410 (+13); shared 2116 maintained.
- **Deviations from handover:**
  - Determinism fix expanded scope: `_reference_now` anchors stale math to latest event timestamp (was wall-clock). Strictly necessary per Gemini-H1; would have caused diff churn on every regeneration otherwise.
  - Did not implement suite-level (`suiteId`) cross-link — B.3's emit_test_failure_triage doesn't populate it yet. Documented as deferred in ADR-058.

### C.1 — FR-gate at iterate-finalize

- **Status:** merged
- **Branch:** `iterate/c1-fr-gate-finalize` (deleted)
- **PR:** #60
- **Squash commit:** `388fa55`
- **Predicted ADR:** ADR-059 (filed at `.shipwright/planning/adr/059-fr-gate-at-finalize.md`)
- **External review findings:** 15 (0 HIGH + 7 MED + 8 LOW). All addressed inline; disposition table in ADR-059.
- **External code-review findings:** 5 (3 MED + 1 LOW accepted-and-fixed — stricter `none_reason` rules in spec, pair-integrity rule, integration test strengthening; 2 MED rejected-with-reason — strict-data-on-disk and non-dict bypass design choices).
- **Test deltas:** shared 2116 → 2141 (+25); compliance 410 → 411 (+1).
- **Deviations from handover:**
  - Validation broader than handover description: `_is_valid_none_reason` enforces ≤280 chars + no control chars + no newlines, beyond the "non-empty trimmed string" baseline. Driven by external review (OpenAI-M5).
  - Pair-integrity rule (change_type's presence requires valid none_reason even with FRs) added per Gemini code-review-M1; strict-data-on-disk semantics.

### C.2 — ADR-bloat + Architecture-drift + CLAUDE.md-bloat detector

- **Status:** merged
- **Branch:** `iterate/c2-architecture-and-adr-drift-detector` (deleted)
- **PR:** #61
- **Squash commit:** `9008cf4`
- **Predicted ADR:** ADR-060 (filed at `.shipwright/planning/adr/060-c2-doc-hygiene-detectors.md`)
- **External review findings:** 18 (1 HIGH SHA-injection defense + 9 MED + 8 LOW). All addressed inline; disposition table in ADR-060.
- **External code-review findings:** 5 (1 HIGH corrupt-drop surfacing + 3 MED accepted-and-fixed: F7 evidence full list, F7 regex variants test, F4 top-5 ordering test; 1 truncated/confirmed-correct).
- **Test deltas:** compliance 411 → 428 (+17); shared 2141 maintained.
- **Deviations from handover:**
  - Tests landed in `test_audit_groups_c_f.py` (existing per-group test file) rather than `test_audit_detector.py` (which is the skeleton-test file). Cleaner per-group separation matches the existing pattern (test_audit_group_a5/b/e).
  - Group F gained F4-F7 as detective-only additions alongside the existing F1-F3 preventive-rerun checks. Required updating `test_group_f_emits_finding_per_check` baseline (3 → 7 findings).

### C.3 — Plugin-cache-sync check

- **Status:** not started
- **Branch:** _pending_
- **PR:** _pending_
- **Squash commit:** _pending_
- **Predicted ADR:** ADR-061
- **External review findings:** _pending_
- **External code-review findings:** _pending_
- **Test deltas:** _pending_
- **Deviations from handover:** _pending_

## Final marketplace sync

- **Run:** not yet
- **13 plugins synced (expected):** _pending_
- **Cache symbol verification:** _pending_

## Notes

(append any cross-iterate observations here — e.g. "the SBOM
generator's `_emit_findings_to_triage` already existed, scope was
narrower than expected" etc.)
