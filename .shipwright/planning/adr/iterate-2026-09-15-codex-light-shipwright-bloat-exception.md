# Bloat exception — completion-oracle verifier and regression-test files

- **Status:** accepted
- **Date:** 2026-09-15
- **Re-Review-Date:** 2026-12-15
- **Incident Reference:** `iterate-2026-09-15-codex-light-shipwright`

## Context

The Codex Light specification requires additive public functions in the existing
`common.py` verifier module, an additive option in `build_checks.py`, and
regression coverage in their established test modules. Those files were already
grandfathered above the normal 300-line limit. The required additions raise
`common.py` to 869 lines, `build_checks.py` to 461 lines,
`test_verifiers_common.py` to 640 lines, and `test_verifiers_build.py` to 400
lines.

## Ousterhout Argument

Each verifier module is a deep module: callers receive a small set of stable
checks while event parsing, compatibility rules, and result shaping remain
encapsulated. The new run-scoped siblings belong next to the legacy C1 check so
they reuse the same event semantics without exposing a new cross-module
protocol. Each paired test module keeps the regression cases close to the
public verifier contract it proves.

## YAGNI Check

The added code is needed now: the WebUI launch path requires a run-scoped
completion signal, existing callers require unchanged fallback behavior, and
the opt-in build rule needs a backwards-compatibility test. No speculative
phase, hook, or delivery behavior was added. Moving only a few helpers would
not reduce the four files below their existing ceilings and would create a new
internal API without a present consumer.

## Chesterton-Fence Check

The current structure groups C1 event interpretation with the legacy verifier
and groups its regression matrix with the same public API. The task explicitly
requires additive siblings rather than changing the legacy function, so the
existing module boundary is load-bearing. The established tests already use
the paired files as their contract home; splitting them during this focused
feature would obscure the required legacy-regression proof.

## Decision

Set the four listed baseline entries to `state: exception` at their measured
current sizes, referencing this ADR pending release numbering. Re-evaluate by
2026-12-15 whether a dedicated verifier-package split can reduce the two
large legacy modules without widening their public surface.

## Consequences

The anti-ratchet gate accepts these exact sizes for this commit but blocks any
future growth unless it is separately justified. The new completion-oracle
file remains a separate, focused CLI and does not add to the existing verifier
modules beyond the required public siblings.

## Rejected alternatives

- Leave the old limits and split immediately — rejected because the task
  explicitly requires the public siblings in these modules, while a safe
  module-boundary redesign exceeds this feature's scope.
- Compress or delete regression tests — rejected because AC1 requires proof
  that the seven legacy C1 callers remain unaffected.
- Move the behavior into `deliver_pr.py` — rejected because that tool mutates
  PR delivery and the specification requires a read-only oracle.

---

## External Sources Acknowledged

This decision applies the repository's bloat-exception template. Its YAGNI
Check and Chesterton-Fence Check headings are adapted from the sources named
in `.shipwright/planning/adr/_template-bloat-exception.md`.
