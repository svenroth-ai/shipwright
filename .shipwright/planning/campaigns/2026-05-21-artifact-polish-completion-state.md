# Campaign State — Artifact-Polish Completion (B.2 → C.3)

> Running log. The session executing this campaign updates this file
> after each iterate's merge so a future session can resume on
> context-loss. See the handover prompt at
> `.shipwright/planning/campaigns/2026-05-21-artifact-polish-completion-handover.md`.

## Status

- **Started:** 2026-05-21 (this session)
- **Current iterate:** B.3 (next)
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

- **Status:** not started
- **Branch:** _pending_
- **PR:** _pending_
- **Squash commit:** _pending_
- **Predicted ADR:** ADR-057
- **External review findings:** _pending_
- **External code-review findings:** _pending_
- **Test deltas:** _pending_
- **Deviations from handover:** _pending_

### B.4 — RTM deep-link rendering + Coverage Summary rewrite

- **Status:** not started
- **Branch:** _pending_
- **PR:** _pending_
- **Squash commit:** _pending_
- **Predicted ADR:** ADR-058
- **External review findings:** _pending_
- **External code-review findings:** _pending_
- **Test deltas:** _pending_
- **Deviations from handover:** _pending_

### C.1 — FR-gate at iterate-finalize

- **Status:** not started
- **Branch:** _pending_
- **PR:** _pending_
- **Squash commit:** _pending_
- **Predicted ADR:** ADR-059
- **External review findings:** _pending_
- **External code-review findings:** _pending_
- **Test deltas:** _pending_
- **Deviations from handover:** _pending_

### C.2 — ADR-bloat + Architecture-drift + CLAUDE.md-bloat detector

- **Status:** not started
- **Branch:** _pending_
- **PR:** _pending_
- **Squash commit:** _pending_
- **Predicted ADR:** ADR-060
- **External review findings:** _pending_
- **External code-review findings:** _pending_
- **Test deltas:** _pending_
- **Deviations from handover:** _pending_

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
