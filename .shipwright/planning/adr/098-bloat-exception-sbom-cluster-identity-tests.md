# ADR-098: Bloat exception — `test_sbom_generator.py` raised to 815-LOC

- **Status:** accepted
- **Date:** 2026-06-05
- **Re-Review-Date:** 2026-09-05 _(check whether the SBOM cluster tests
  should be split into their own module with shared conftest fixtures,
  or the exception can be retired)_
- **Incident Reference:** sub-iterate A of campaign
  `2026-06-05-track-triage-jsonl`
  (`iterate-2026-06-05-sbom-cluster-stable-identity`). The SBOM cluster
  dedup-key became signature-only (stable id under membership drift); the
  new identity semantics needed regression coverage that pushed the
  already-grandfathered test file past its 787 baseline.

## Context

`test_sbom_generator.py` is the cohesive test suite for the compliance
SBOM producer (markdown generation, per-workspace + cluster triage emit,
auto-resolve, payload shaping). Sub-iterate A reversed the
membership-encoding cluster identity (external-review OpenAI #2/#3) to a
signature-only id. Net **+28 LOC** (787 → 815):

- **inverted** `test_cluster_membership_grows_*` — was "grows → old-dismiss
  + new-emit", now asserts the id is **invariant** under growth and pins the
  by-design body-staleness (`Workspaces (2)` stays).
- **added** `test_cluster_membership_shrinks_within_range_keeps_stable_id`
  — the 3→2 case (both N≥2), distinct from the existing 2→1 boundary-cross.
- **added** `test_cluster_dedup_key_independent_of_membership` — a compact
  contract pin (equal across member sets, distinct across manifest types).

Source was kept **under** baseline (`sbom_generator.py` 578 ≤ 581) by
trimming the dedup-key docstring (detail lives in the campaign A spec).

## Ousterhout Argument

The cluster behaviour is a **deep module**: a narrow producer interface
(`emit_undeclared_triage` → `{appended, dismissed, clusters}`) over
substantial dedup/auto-resolve/payload logic. The tests share the
`TestEmitUndeclaredTriageClusters` fixtures (`_seed_npm`, `_seed_python`,
`_read_sbom_items`). The new scenarios exercise the *same* interface; they
belong with their siblings. Splitting them out to dodge +28 LOC would
duplicate the fixtures and scatter one producer's cluster tests across two
files — exposing wiring the shared fixtures exist to hide.

## YAGNI Check

Every added line is needed **today**: grow- and shrink-stability are the
core behaviour change of sub-iterate A (the prerequisite that lets campaign
C track a non-churning log); the contract pin documents the new
`_cluster_dedup_key` signature. No speculative scope — body-amend fidelity
is explicitly **deferred** (filed as trg-9403a648), not pre-tested here.

## Chesterton-Fence Check

The file is large because the SBOM producer has many cohesive behaviours
(generation, per-workspace + cluster emit, auto-resolve, manifest-type
homogeneity), each with `_seed_*` fixtures centralising workspace seeding.
git history shows the suite grew behaviour-by-behaviour under that
structure. The fence stands for a reason; extending it by 28 LOC for a
semantics change to an existing behaviour is consistent with it.

## Decision

Raise `plugins/shipwright-compliance/tests/test_sbom_generator.py` to **815**
(`state: exception`, `adr: ADR-098`) in `shipwright_bloat_baseline.json`,
in the same commit. Retire when the SBOM cluster tests are split into a
dedicated module sharing conftest fixtures (tracked at the Re-Review-Date).
`sbom_generator.py` stays grandfathered at 581 (kept under via docstring
trim).
