# Mini-Plan: binding-completeness-rollout-transition

- **Run ID:** iterate-2026-09-11-binding-completeness-rollout-transition

## Files to create/modify

1. **NEW** `shared/scripts/tools/verifiers/_layer_coverage_rollout.py` — the
   fixed rollout-instant constant, `resolve_rollout_commit()` (git `rev-list
   -1 --before=<instant> <commit_hash>` against the CALLING project's own
   history), `rollout_manifest()` (archive + collector build at that commit,
   `with_evidence=False`, process-cached), `clear_rollout_cache()`.
2. **EDIT** `shared/scripts/tools/verifiers/_layer_coverage_binding.py` —
   `binding_predates_rollout(rollout, key, head_node)` pure comparator:
   source-agnostic, SUPERSET check (head's `required_layers` ⊇ the rollout
   snapshot's value — not exact-match, so a post-rollout widening keeps
   grace), and title-matched (the rollout snapshot's node title must match
   head's, so a manifest key reused by a repurposed FR does not inherit a
   predecessor's grace). `evaluate_binding_completeness` gains an optional
   `rollout=None` param and downgrades a would-be-HARD gap to advisory (new
   `LayerGap.reason` value `BINDING_INCOMPLETE_TRANSITION`) when the
   comparator says so.
3. **EDIT** `shared/scripts/tools/verifiers/layer_coverage_binding.py` — wire
   `rollout_manifest(project_root, commit_hash)` into `check_binding_completeness`;
   `_binding_result`'s advisory message distinguishes "pre-rollout transition
   grace" from legacy/collision instead of reusing one blanket phrase.
4. **NEW** `shared/tests/test_layer_coverage_rollout.py` — real-git tests for
   `resolve_rollout_commit`/`rollout_manifest` (commits pinned before/after the
   rollout instant via `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE`), plus the
   no-history-before-rollout (greenfield) case.
5. **EDIT** `shared/tests/test_layer_coverage_binding.py` — pure-evaluator
   cases: grace granted (identical required_layers at rollout), grace withheld
   (edited/promoted since rollout, or no rollout snapshot).
6. **EDIT** `shared/tests/test_layer_coverage_binding_wrapper.py` — wire
   `rollout_manifest` mocking into the existing full-path tests (so they stay
   git-free) + one new wrapper-level transition-grace test.
7. **EDIT** `.shipwright/agent_docs/architecture.md` — new Architecture
   Updates bullet (new module + gate-semantics change).
8. **NEW** ADR at `.shipwright/planning/adr/` (F3) — records the design,
   the dry-run, and the deliberate scope boundary (no change to
   `evaluate_cross_layer` / the keystone gate).
9. **Triage** — mint a new follow-up card (mirrors `trg-875104ac`) for
   "extend transition grace to `evaluate_cross_layer`/keystone" as a tracked,
   deliberate deferral; resolve `trg-aedcfe7b` at F12 once merged.

## Work Breakdown

1. Build `_layer_coverage_rollout.py` with the fixed `GATE_ROLLOUT_AT`
   constant + `resolve_rollout_commit` + `rollout_manifest` + cache. Unit
   tests against a real throwaway git repo with pinned commit dates
   straddling the constant, plus the "born after rollout" case.
2. Add `binding_predates_rollout` + wire `rollout` through
   `evaluate_binding_completeness`; pure-evaluator tests (grace / no-grace /
   None-rollout) using the existing hand-built-manifest fixture style — no
   real git needed at this layer.
3. Wire the wrapper (`layer_coverage_binding.py`): call `rollout_manifest`,
   pass through, adjust `_binding_result` messaging. Update/extend the
   existing wrapper tests (mock `rollout_manifest` for the git-free ones,
   add one new wrapper test exercising the real evaluator with a graced gap).
4. Run the full `shared/tests` suite + `uv run scripts/verify_local.py`.
5. Empirical dry-run: against a SYNTHETIC fixture corpus (this repo's own
   manifest is 100% `inferred_legacy` — already covered by the legacy valve,
   so a dry-run against it would be tautological, per the spec's AC6 and
   external plan-review finding glm#5/openai#4). Build a fixture modeling the
   actual motivating population (an `explicit`/promoted-to-`explicit`
   pre-rollout binding, plus a genuinely-new post-rollout control) and record
   the hard-count before/after through the transition-aware evaluator.
6. Architecture doc + ADR + triage follow-up card + resolve `trg-aedcfe7b`.

## Test Strategy

- Pure-evaluator unit tests (no git) for the comparator logic itself.
- Real-git tests for the two new git-touching functions (`resolve_rollout_commit`,
  `rollout_manifest`), reusing the `_git`/`_init`/`_write` helpers already in
  `test_layer_coverage_gate_integration.py`, with one new local `_commit_at`
  helper that sets `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` so commit dates can
  straddle the fixed rollout instant deterministically.
- Wrapper-level test proving the wiring end-to-end (a real graced gap survives
  through `check_binding_completeness`, not just the pure evaluator).
- No E2E/UI surface exists for this change (pure framework verifier logic) —
  `Verification: none`, matching every sibling gate in this family.

## Alternative approach (rejected)

**Global fixed ISO-date cutoff compared against each FR's blame/log date on
its own spec.md row**, instead of a resolved-commit-manifest-snapshot diff.
Rejected: locating the exact line for an FR's `Layers` cell inside a markdown
table and blaming just that line is fragile against reformatting/reordering
that touches the line without changing the cell's *value* (a false
"edited since rollout" reading that denies grace it should grant) — the
`compare_traceability_manifest.py`/ledger work already tried a git-history
approach for an adjacent problem (P3.3's own AC2, reconciling `(E)`-bullet
citations) and hit exactly this class of confound (rejected alternative #4
in the P3.3 ADR: bulk-commit false-universal-drift). The rollout-manifest
snapshot approach compares the *value* the collector already parses
(`required_layers`/`required_layers_source`), reusing the SAME archive+collector
machinery `regenerate_base_head` already trusts for base/head, rather than a
second, less-tested line-oriented git primitive.
