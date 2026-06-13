# Iterate Spec: unify-simplify-reducibility

- **Run ID:** iterate-2026-06-13-unify-simplify-reducibility
- **Type:** change · **Complexity:** medium (locked) · **Status:** draft
- **Spec source:** follow-up to OS1/P3.2 (PR #238). Unifies the simplify gate with the
  reducibility/bloat catalog (PR #219). User-directed 2026-06-13.

## Goal

One shared vocabulary + cross-wire the two gates' unique capabilities, so the
behavior-preserving simplify path (OS1) and the intelligent bloat/reducibility gate
(`shared/reducibility-catalog.md`) stop duplicating and instead reinforce each other.

## Acceptance Criteria

- [ ] AC1 — `behavior_snapshot.py` relocates to `shared/scripts/tools/behavior_snapshot.py`
  (SSoT, reachable by all reviewers without an inverted plugin→shared dependency). All
  references updated (F-simplify.md, SKILL.md Path B, routing test). No back-compat shim
  (1-day-old tool, all refs controlled); full suite stays green after the move.
- [ ] AC2 (Side 1) — `F-simplify.md` adopts the closed catalog (`D·A·X·C·S·M·P·T` + G1–G6 in
  `shared/reducibility-catalog.md`) as its concrete "what to simplify" vocabulary; the Osmani
  Five Principles remain the dispositional layer.
- [ ] AC3 (Side 2) — `reducibility-catalog.md` + `code-reviewer.md` cite `behavior_snapshot.py`
  as the **mechanical proof** for the "keeps tests green" / G3 clause: on *executable* surfaces
  (local diff review, simplify/apply path) a reduction proven green→green via snapshot/verify
  may block/apply; the **self-contained CI Tier-3 `pr_reviewer`** (no filesystem/exec) keeps its
  conservative numeric-LOC heuristic — explicitly scoped, not weakened.
- [ ] AC4 — Bidirectional integration test (`integration-tests/`): the ONE shared tool proves
  BOTH (a) a simplify edit preserves behavior → green, AND (b) a catalog-style reduction
  (X dead-code delete) preserves behavior → green, while (c) a coverage-destroying reduction →
  rejected. Plus the migrated CLI arms (clean simplify / drift / removed-coverage / red-baseline).
- [ ] AC5 — cross-surface parity gains: catalog cites `behavior_snapshot.py` as G3 proof;
  `F-simplify.md` cites the catalog. **Placement deviation (sound):** these asserts landed in a
  NEW companion `shared/tests/test_simplify_reducibility_unify.py` rather than inside
  `test_reducibility_gate.py` — appending to the latter pushed it past the 300-LOC test guideline,
  so it stays byte-identical to origin/main and the new file carries the unification asserts.
- [ ] AC6 — `docs/guide.md`: note the unified gate (simplify + reducibility share the catalog
  vocabulary + the mechanical proof).

## Spec Impact

- **Classification:** NONE — framework tooling consolidation (relocate + cross-wire docs +
  one new integration test). No user-application FR. FR-gate branch: `change_type = tooling`.

## Out of Scope

- Weakening the CI Tier-3 reviewer's heuristic (it cannot exec; keep numeric threshold).
- Changing the catalog codes D/A/X/C/S/M/P/T or the guardrails G1–G6 themselves.
- A back-compat re-export shim (no external consumers of the 1-day-old tool).
- Touching the OS1 architecture.md entry (append a NEW relocation entry instead).

## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| `shared/scripts/tools/behavior_snapshot.py::write_snapshot` | same `::read_snapshot` | JSON (`.shipwright/runs/<run_id>/behavior_snapshot.json`) — unchanged by the move |

`touches_io_boundary` already covered by the existing round-trip test (moves with the tool).
No `cross_component` machinery (no merge/churn/hook/phase-validator files).

## Confidence Calibration
- **Boundaries touched:** the relocated snapshot store (same producer/consumer pair; the
  round-trip Boundary Probe moved with the tool and still passes).
- **Empirical probes run:**
  - *Relocation safety*: after the `git mv` + ref updates, all affected suites green — shared
    tools unit 10, parity (reducibility 30 + unify 4) 34, iterate plugin 427, integration 7.
    Grep for the old `scripts/lib/behavior_snapshot` path = 0 live *code/runtime-prompt* refs
    (**code-review FINDING**): the OS1 `architecture.md` entry retained the old path by the
    append-log model; this iterate appends a relocation entry that supersedes it (the OS1 entry
    stays as historical provenance). Decision-drops/runs are gitignored history, not live refs.
  - *Bidirectional integration*: the new `integration-tests/test_behavior_snapshot_gate.py`
    proves the ONE shared tool serves both gates — simplify edit → green, X dead-code reduction
    → green, drift → reject, removed-coverage → reject. No finding on the logic.
  - *CI-selection probe* (**FINDING**): the integration test, first marked `@pytest.mark.slow`,
    was silently **deselected** (exit 5) because `integration-tests/` inherits the root
    `addopts = -m 'not slow'` — and CI's integration step inherits it too, so it would never have
    run in CI. Fixed by un-marking (matching the `test_shipwright_run_e2e.py` convention);
    re-ran → 7 passed. (Asymptote: finding → fix → clean re-run.)
- **Test Completeness Ledger:** see F5 `iterate_latest.test_completeness`; AC1–AC6 each `tested`.
- **Confidence-pattern check:** depth — the CI-selection finding was resolved and re-verified
  clean; breadth — 6 ACs covered by named tests across 4 surfaces (tool, catalog, code-reviewer,
  F-simplify) + the integration proof. No `cross_component` machinery touched (relocation of a
  standalone tool is not a merge/churn/hook/phase-validator change).

## Verification (medium+)
- **Surface:** none — framework tooling (relocation + doc cross-wiring + tests). Proven by the
  relocated unit suite + the new bidirectional integration test, green at F0. Justification recorded at F0.5.

## Mini-Plan (build order, TDD)

1. **Relocate** behavior_snapshot.py + unit tests → `shared/scripts/tools/` (+ `tests/`); rewrite
   their import/path setup to the shared pattern (`sys.path` → `shared/`, `from scripts.tools...`).
   Update F-simplify.md / SKILL.md / test_f_simplify_routing.py refs. Run suites green.
2. **Side 2 first** (so the integration test has something to assert): catalog + code-reviewer.md
   cite behavior_snapshot.py as the executable-surface G3 proof (CI prompt scoped out).
3. **Side 1**: F-simplify.md adopts the catalog vocabulary.
4. **Integration test** (integration-tests/) — both sides + migrated CLI arms.
5. **Parity guard** test_reducibility_gate.py extension; **guide.md** doc-follow.

### Alternatives considered
- *Reference-only (no relocation)*: rejected — a shared rubric pointing at a plugin-local tool
  inverts the plugin→shared dependency (MU-PL2) and makes the build reviewer run an iterate-plugin
  script. Relocation to shared is the correct SSoT.
- *Keep slow CLI tests in the plugin*: rejected — consolidating all behavior_snapshot integration
  in `integration-tests/` is cleaner. Note: that dir **inherits** the root `-m 'not slow'` (CI's
  integration step does too), so the arms must stay **unmarked** (not `slow`) to execute — matching
  the `test_shipwright_run_e2e.py` convention.
