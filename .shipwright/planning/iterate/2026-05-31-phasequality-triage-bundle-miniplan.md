# Mini-Plan — phase-quality triage bundling

Implements the iterate spec `2026-05-31-phasequality-triage-bundle.md`.
Producer-side scope (inbox fix). Dashboard consistency is a separate follow-up iterate.

## Approach (chosen)

Three layers, all in the **producer path** (not the runners), to bound blast
radius to the triage-emission contract.

1. **Layer 1 — phase-applicability gate.** New `phase_is_engaged(phase, cfg,
   events)`: engaged iff a `phase_completed`/`work_completed[source=phase]`
   event exists, OR (`status==complete` AND `phase==iterate`), OR
   (`status!=complete` AND phase in `completed_steps`/`current_step`). Stale
   `current_step` on a complete project does NOT re-admit a phase.
2. **Layer 2 — run_id guard.** `check_s2_iterate_spec` / `check_s3_iterate_miniplan`
   return SKIP when `run_id` is a sentinel (`""`/`"unknown"`/`None`) or has no
   *exact* `iterate_history` entry — instead of tail-falling-back to the
   most-recent entry's complexity and emitting an unsatisfiable FAIL.
3. **Layer 3 — backlog action-unit.** Replace per-FAIL emit with one rolling
   `phaseQuality:backlog:<sig>` item built from `load_findings` (latest finding
   per phase → Tier-1 FAILs → filtered by Layer 1). Signature = sha256[:12] of
   sorted `phase:code`. Dismiss stale-sig backlog items + append fresh; auto-
   dismiss all when the in-scope FAIL set is empty.

## Files

1. NEW `shared/scripts/lib/phase_quality/_triage_bundle.py` (≤300 LOC) —
   `phase_is_engaged`, `collect_in_scope_fails`, `emit_phase_quality_backlog`.
2. EDIT `shared/scripts/hooks/audit_phase_quality_on_stop.py` — delegate to the
   new module; delete `_emit_tier1_fails_to_triage` (shrinks hook < 300 LOC).
3. EDIT `shared/scripts/lib/phase_quality/__init__.py` — export new symbols.
4. EDIT `shared/scripts/tools/verifiers/spec_checks.py` — Layer 2 guard.
5. REWRITE `shared/tests/test_phase_quality_triage_emit.py` — backlog contract.
6. NEW/EXTEND tests — engagement matrix, S2/S3 skip, bundle dismiss/refresh/resolve.
7. EDIT `docs/hooks-and-pipeline.md` — backlog action-unit shape.

## Alternative considered (rejected for this iterate)

Gate at the **runner** level so non-engaged phases render as SKIP on the
dashboard too. Rejected here because it widens blast radius into `_runners` +
`test_audit_phase_quality` and changes dashboard semantics — split into a
dedicated follow-up iterate (operator-approved two-iterate plan).

## Risk

Low–medium. Single new module behind a stable triage API + one localized
verifier guard. Existing dashboard/aggregate behavior unchanged. Best-effort
(Stop hook always exits 0). The producer test rewrite is contract evolution,
not test-weakening.
