# Iterate Spec: verifier-drift-remediation

- **Run ID:** iterate-2026-05-23-verifier-drift-remediation
- **Type:** change
- **Complexity:** small (docs + drift-protection test)
- **Status:** draft

## Goal

Close the iterate-skill discipline drift that surfaced when the operator audited
PR #71 + PR #74's iterate flow: F2 was skipped twice (architecture.md not
updated despite `--architecture-impact convention`), F0 leak-guard was skipped
(only F11 was run), TDD RED-first was violated (tests added AFTER
implementation), and F12 Release Prompt was not output.

This iterate (a) backfills the missing architecture.md entries for ALL
historically-missed arch-impact drops (the test surfaced 11, not just my 2),
(b) adds a forward-looking drift-protection test that fails closed on the
next missed update, (c) documents the three discipline lessons in
conventions.md.

## Acceptance Criteria

- [ ] `shared/tests/test_architecture_md_reflects_arch_impact.py` exists,
  written RED before architecture.md updates, then GREEN after.
- [ ] `.shipwright/agent_docs/architecture.md` carries an `## Architecture
  Updates` bullet for every decision-drop with `architecture_impact ∈
  {component, data-flow, convention}` — including the 11 historical drift
  cases the RED test surfaced.
- [ ] `.shipwright/agent_docs/conventions.md` carries three new Learnings:
  TDD RED-first applies to drift-protection tests; F0 leak-guard
  symmetry with F11; `--architecture-impact` flag and architecture.md
  update are structurally coupled.
- [ ] F12 Release Prompt printed at end of run with unreleased changelog
  drop count.
- [ ] F11 verifier returns 0 errors.

## Spec Impact

- **Classification:** `none`
- **NONE justification:** This iterate updates only `.shipwright/agent_docs/`
  (architecture + conventions) and adds a test under `shared/tests/`. No
  FR in `01-adopted/spec.md` describes the iterate-skill's discipline gates
  at AC granularity. FR-01.11 covers `/shipwright-iterate` conceptually;
  tagging it as affected via the F7 FR-gate to satisfy the C.1 rule.

## Out of Scope

- Adding a similar drift-protection test for the `--spec-impact` flag (the
  spec-impact gate is already enforced at F11 by `check_spec_impact_recorded`).
- Rewriting the historical decision-drops for the b/c bloat-cleanup campaign
  iterates — the architecture.md entries this iterate backfilled are based
  on the decision-drop title + decision field, not a full re-read.
- Renaming `architecture_impact: "none"` → omitting the field. That'd be
  a forward-only data shape change; the test filters `none` out already.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `write_decision_drop.py` (`architecture_impact` field) | `test_architecture_md_reflects_arch_impact.py` + `architecture.md` reader (operator + future audits) | JSON drop → markdown |

This iterate adds a consumer (the test) for an existing producer field. No
schema change. Boundary Probe sub-step is N/A (`touches_io_boundary` does not
fire — the JSON drops are framework-internal, not user-edited).

## Self-Review

1. **Correctness.** The test enumerates every `*.json` decision-drop under
   `.shipwright/agent_docs/decision-drops/`, filters for `architecture_impact
   ∈ {component, data-flow, convention}` (excludes the default `none`), and
   substring-greps each `run_id` against `architecture.md`. RED phase
   surfaced 11 real drift cases; GREEN phase after backfill. The 2 sanity
   asserts (drops are discovered at all, drift list is empty) cover both
   axes — discovery and completeness.

2. **Tests.** 1 test file, 2 cases. Goes RED → GREEN cleanly: 11 missing
   entries on first run, 0 missing after backfill. The
   `test_arch_impact_drops_found_at_all` sanity check guards against the
   main-repo-resolution misfire that would silently no-op the main
   assertion.

3. **Conventions.** Test file follows the `shared/tests/test_*.py` pattern
   used by 50+ existing tests. Architecture.md entries follow the existing
   `**run-id** (date): description` format used by all post-ADR-NNN
   iterates. Conventions.md learnings appended to the existing `## Learnings`
   section in the same bullet style.

4. **No regressions.** Architecture.md additions are append-only — existing
   prose untouched. Conventions.md additions are append-only. The new test
   doesn't load any production code; it just reads markdown + JSON files.
   No risk to existing tests (verified via 70/70 still green in
   `test_verify_iterate_finalization.py`).

5. **Documentation.** ADR (decision-drop) + changelog drop + iterate spec
   (this file) + conventions.md Learnings + architecture.md entries — full
   chain. The conventions.md learning EXPLICITLY names the prior drift
   (PR #71 + PR #74 missed the architecture.md update) so future iterates
   can search for the pattern.

6. **Architectural impact.** Convention (`--architecture-impact convention`).
   The change makes the F2 "update + flag" coupling structurally enforced
   instead of advisory. Adds a new test convention.

7. **Affected Boundaries.** New consumer for an existing producer field; no
   schema change. Documented in the Affected Boundaries section above.

## Verification

- **Surface:** `cli`
- **Runner command:** `uv run --with pytest pytest shared/tests/test_architecture_md_reflects_arch_impact.py -v`
- **Evidence:** 2/2 green after architecture.md backfill (RED → GREEN cycle
  confirmed pre-edit by surfacing 11 missing entries).
