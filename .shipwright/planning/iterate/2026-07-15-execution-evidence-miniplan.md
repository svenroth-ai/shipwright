# Mini-plan: TT-EV — Per-test execution-evidence ingestion → manifest status/executed

Run-ID: iterate-2026-07-15-execution-evidence · Campaign:
2026-07-15-test-traceability-layers · change_type=feature · complexity=small.

## Problem

The traceability manifest (TT1) carries a per-test `status`/`executed`, but the
only producer of the normalized evidence index was a hand-authored fixture. A
static `@FR` tag proves nothing (Spec §11 R1, the unclosed G5): a skipped /
never-run / filtered E2E would still mark a required layer covered. "Covered at a
layer" must mean a tagged test that is **enabled AND observed passing** in that
layer's runner evidence.

## Approach (surgical, fail-closed)

1. **Reader** (`collectors/execution_evidence.py`, pure) — parse JUnit XML +
   Playwright JSON + Vitest reporter output into `{path::name → {status,
   executed, runner}}` keyed to the collector's stable ids. Runner-specific raw
   statuses are NORMALIZED into a frozen closed vocab; out-of-vocab is coerced
   fail-closed (`executed→not_run`, `status→quarantined`) — never trusted.
2. **Frozen vocab boundary** — `evidence_index_schema.json` (closed enums,
   `additionalProperties:false`); the reader validates its output before returning
   (fail-closed, mirrors TT1's `_validate_manifest`).
3. **Expiring waiver** — `waiver_state()` + `layer_satisfied()`: a layer that
   genuinely cannot run gets an explicit waiver with full accountability metadata
   (layer/reason/owner/ticket/expires). Honored while valid; expired/incomplete →
   fail-closed False. No self-reported success.
4. **Join** — reuse TT1's existing `_make_link`/`_cov_status` (already recompute
   `coverage[layer]=ok` iff enabled+pass). No fork.
5. **Finalization wiring** — `_execution_evidence_io.refresh_index` discovers raw
   reports under `.shipwright/compliance/evidence/` and emits the index;
   `test_links.generate_file` calls it before `load_evidence`. NON-DESTRUCTIVE:
   no reports ⇒ existing index untouched, absent evidence ⇒ not_run at consumer.
   F5.md documents the drop location.

## Acceptance mapping

- AC1 → reader reproduces the P1 evidence answer-key from the three raw reports;
  skipped tagged test = skipped/not_run.
- AC2 → green-but-skipped required layer = MISSING (regression pinned end-to-end
  raw-report → reader → manifest).
- AC3 → missing evidence file = not_run (never pass); valid waiver honored,
  expired fails.
- AC4 → new RED-before/green-after tests over 3 formats + skipped/missing/waiver +
  vocab coercion; framework suite green.
- AC5 → footprint = compliance collectors + one wiring call + tests; all files
  ≤300 LOC; bloat baseline not ratcheted.

## Non-goals

- The D-layer / cross-layer ENFORCING gates (TT2/TT5) — this iterate ships the
  data + fail-closed primitives they consume, no gate flips here (R3: committed
  artifact is derived/RTM-visibility only).
- Reporter-flag wiring inside `surface_verification.py` (its exact exit-code
  contract is heavily tested) — kept untouched; evidence emission lives at the
  compliance single-Producer layer instead.
