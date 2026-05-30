# ADR-093: Bloat exception — test-completeness-gate verifier + test growth

<!-- Grants a bloat-baseline exception for the two files grown by
     iterate-2026-05-30-test-completeness-gate. Referenced from
     shipwright_bloat_baseline.json (state="exception", adr="ADR-093").
     Does NOT supersede ADR-092: that ADR still owns the other four files
     it grew. ADR-093 raises the ceiling only for the two entries below. -->

- **Status:** accepted
- **Date:** 2026-05-31
- **Re-Review-Date:** 2026-08-31 _(3 months out — co-scheduled with ADR-092's
  re-review; the reviewer evaluates the `verifiers/iterate/` package split that
  would let the events-family AND the completeness gate split along one seam,
  and whether the two suites can shed redundant cases)_
- **Incident Reference:** iterate-2026-05-30-test-completeness-gate — adding the
  fail-closed **Test Completeness Ledger** gate (`check_test_completeness_ledger`
  + the closed `UNTESTABLE_REASON_CODES` vocabulary) to the F11 finalization
  verifier, plus the 18 test cases that pin its fail-closed branches.

## Context

The iterate replaces the Confidence-Calibration "Edge cases NOT probed + why
acceptable" escape hatch with a machine-enforced ledger: every behavior a diff
introduces is `tested` (evidence) or `untestable` (closed-vocab `reason_code`),
and a fail-closed F11 check STOPs the run on any testable-but-untested gap. The
check and its vocabulary live in the verifier module; its branches are pinned by
new tests. Two files — both ALREADY ADR-092 exceptions — grew past their
`current` baselines:

| Path | baseline → new | Δ | kind |
|---|---|---|---|
| `shared/scripts/tools/verifiers/iterate_checks.py` | 881 → 1093 | +212 | production (new gate + vocab) |
| `shared/tests/test_verify_iterate_finalization.py` | 1196 → 1465 | +269 | test coverage (18 cases) |

The iterate ALSO touched the grandfathered `test_skill_phase_matrix.py` (no
ADR). Rather than grow it, the new matrix-drift tests were split into a sibling
file `test_skill_completeness_matrix.py` and the in-place edit kept net-zero —
remediation #1/#2 (preferred), so that file needs **no** exception. The new
`test_untestable_vocab_doc_sync.py`, `test_skill_completeness_matrix.py`, and
`test_test_completeness_*` cases live within the existing files or new
sub-300-LOC files (not crossings).

## Ousterhout Argument

`iterate_checks.py` is a **deep module**: its public interface is narrow —
`run_all_checks(project_root, run_id, commit)` + `run_cross_artifact_checks(...)`
— behind which sits the cohesive family of F11 finalization invariants
(events-has-commit, ADR present, changelog drop, spec-impact, surface
verification, and now test-completeness). The completeness gate is ONE more
fail-closed member of that family; `run_all_checks` grew by exactly one entry.
Splitting a single check into its own module would (a) expose the closed
`UNTESTABLE_REASON_CODES` vocabulary and the block-parsing internals that are
intentionally encapsulated, and (b) leave a residual ratchet anyway (the import
+ the `run_all_checks` call line), so the split must be holistic, not piecemeal.
The interface stayed narrow; the body grew because the contract it enforces grew.

`test_verify_iterate_finalization.py` is not a module — the deep-module test
doesn't apply. Its size tracks the **surface under test**: the gate added a new
fail-closed contract with ~10 distinct branches (missing file, malformed JSON,
non-object JSON, missing block, bad status, escape-hatch disposition, bad
reason_code, missing evidence, untested_testable missing/positive/bool,
n/a-forbidden-at-medium, enumeration gap, run_all_checks wiring). Each case pins
one branch. The growth is new coverage, not duplication.

## YAGNI Check

- `iterate_checks.py` +212: the gate IS the feature this iterate delivers —
  making "did you empirically test everything testable?" self-answering so the
  operator stops policing it manually at merge. Not speculative; it ships now and
  is the user's explicit requirement.
- Test growth +269: every case maps to a fail-closed branch the gate added. The
  three review-driven cases (n/a-forbidden-at-medium, bool-as-int rejection,
  non-object-JSON robustness) each closed a concrete hole found in code review —
  removing any would leave a bypass unverified. None is "might need next quarter".

## Chesterton-Fence Check

Both files are pre-existing ADR-092 exceptions; their large size predates this
iterate (Campaign B test-evidence work + per-iterate F11-verifier accretion).
ADR-092's own Re-Review note already anticipated a `verifiers/iterate/` package
split. This iterate deliberately ADDS to the same cohesive module rather than
pre-empting that refactor mid-feature — the fence (single-source the F11 contract
+ its co-located evidence) stands for a documented reason. Git history shows the
verifier grows by deliberate, test-pinned accretion. The 2026-08-31 re-review is
the backstop and now has a second reason (events + completeness) to action the
split.

## Decision

Bump `current` to the measured values above (1093 / 1465); set each of the two
entries' `state="exception"`, `adr="ADR-093"`. ADR-092 retains ownership of the
other four files it grew and remains the historical record for the
events-worktree-commit incident. Retirement plan: at the co-scheduled
2026-08-31 re-review, evaluate splitting `iterate_checks.py` into a
`verifiers/iterate/` package (events / spec-impact / surface / completeness
families), which would let both suites split along the same seam.

## Consequences

Anyone editing these two files now operates against the raised limits; the
anti-ratchet gate passes because `measured == current`. The Group H detective
audit records the exception (adr-linked to ADR-093). If the exception outlives
the Re-Review-Date without a split, the files keep accreting against an
ever-higher ceiling — the re-review is the backstop. The grandfathered
`test_skill_phase_matrix.py` was deliberately NOT grown (split instead),
demonstrating the preferred remediation alongside this exception.

## Rejected alternatives

- **Reuse ADR-092 for the bump.** ADR-092 is scoped to the
  events-worktree-commit incident; re-pointing its `current` numbers for
  unrelated completeness-gate growth misattributes the exception and breaks the
  audit trail (this was the code-review HIGH finding). A dedicated ADR keeps the
  ledger honest.
- **Split `iterate_checks.py` into `verifiers/iterate/` now.** This iterate was
  scoped as a contained medium feature; a package split mid-feature balloons it
  into a refactor. Even a partial extraction leaves a residual ratchet (import +
  orchestrator line), so the split must be holistic. Deferred to the re-review
  with the concrete seam noted.
- **Trim the tests to fit.** Deleting cases to dodge the gate is the exact
  rationalization the anti-ratchet block refuses ("tests don't count — they
  count"). Each added case verifies a fail-closed branch; deleting them would
  ship the gate under-verified — the opposite of this iterate's whole point.

---

## External Sources Acknowledged

YAGNI Check + Chesterton-Fence Check headings adapted from obra/superpowers
`writing-plans` (MIT © Jesse Vincent) and addyosmani/agent-skills
`code-simplification` (MIT © Addy Osmani). The Incident-Reference field follows
the per-decision incident-reference pattern from multica-ai/multica `CLAUDE.md`
(Apache-2.0 modified-with-hosting-restriction — pattern reusable, text not).
