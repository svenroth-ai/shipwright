# iterate-2026-09-20-shared-rollout-commit-resolver

Complexity: small (CHANGE — behavior-preserving refactor). No iterate spec file
is required at this tier per the phase matrix; this file stands in as the spec
for review purposes.

## Task

`iterate-2026-09-12-project-gate-rollout-transition`'s `_project_gate_rollout.py`
duplicates ~20 lines of git shallow-check + `rev-list --before` +
committer-epoch-verify logic already proven in `_layer_coverage_rollout.py`
(the `check_binding_completeness` precedent, trg-aedcfe7b/PR #721) -- this is
now a THIRD near-identical copy of the same idea (layer-coverage's own
resolver, the binding-completeness one, and this one), noted by external plan
review (glm, low) on this iterate. Deliberately not factored out here, per the
P3.3 ADR's own established precedent that each gate family gets its own
rollout instant and resolver since each gate ships on a different date -- but
the next gate family that needs this will face a stronger temptation to
finally share it. Scope a shared primitive (commit resolution:
resolve_head_sha/resolve_rollout_commit/shallow-clone guard/epoch
re-verification) that each family's own thin wrapper can call with its own
epoch constant, without forcing a single shared rollout INSTANT across
families. See `_project_gate_rollout.py`'s own module docstring for the
disclosed-cost reasoning.

## What was done

Extracted `shared/scripts/tools/verifiers/_rollout_resolution.py`, exposing
`is_shallow`, `resolve_head_sha`, and `resolve_rollout_commit(project_root,
commit_hash, *, epoch)`. `_project_gate_rollout.py` and
`_layer_coverage_rollout.py` became thin wrappers calling it with their own
`GATE_ROLLOUT_AT_EPOCH`, keeping their own caches and public APIs unchanged.
Added `shared/tests/test_rollout_resolution.py` (real-git tests against a
third, unrelated epoch, proving the primitive is not hardcoded to either
family's instant). Updated one existing test's monkeypatch target to the new
call site. No behavior change — verified via `behavior_snapshot.py`
snapshot/verify (64 pre-existing tests green before and after).
