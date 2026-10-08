# One runtime-built scenario proves the finalization-claims gates stay independent

Run: `iterate-2026-10-08-u11-integration-scenario` (campaign `2026-10-07-finalization-claims-hardening`, unit U11).

## Context

U1 (test tags), U3 (review record at every complexity), U4 (100-line cascade trigger), U5 (F0.5 surface claim) and U6
(requirement gates) each have unit tests, but nothing showed they stay independent over one run: a second red gate can hide a
missing check in the first.

## Decision

`shared/tests/test_finalization_claims_scenario.py` builds a compliant run in `tmp_path` at run time (trunk, branch, F5c entry,
review record, staged evidence); `_finalization_scenario_records.py` writes the records. Each case breaks exactly one claim and
asserts the owning gate's own diagnostic AND that every other gate is green. Complexity is chosen per case (U4 at small, U5 at
medium, U3 at trivial/small/medium). A converse case breaks every small-scope claim at once; one case runs `run_all_checks` to
prove F11 wires U1/U4/U5. Nothing is committed as a fixture (U1 would refuse an untagged one); `iterate_checks.py` is untouched.

## Rejected

A committed fixture repo (freezes a shape and fights the tag gate); relying on per-gate unit tests (cannot show masking).

## Reviews

- **Architecture review: approve / approve.**
- **Plan review: openai revise, glm approve.** Accepted: the baseline passes at every complexity before any mutation; the F11
  entry point is exercised. Rejected: a U7 case (U7 was cut from the campaign 2026-10-07).
- **External code review: openai revise, glm revise.** Both flagged only the missing U7 (rejected, same reason). Accepted: the
  U4 positive control now asserts every gate is green. Rejected: a medium free-text U3 case (low; U3 trivial/small cover it).

## Self-Review

1. Spec Compliance: pass. 2. Error Handling: pass. 3. Security Basics: pass. 4. Test Quality: pass. 5. Performance Basics: pass
(20 cases, ~25 s). 6. Naming & Structure: pass (211 + 58 lines). 7. Affected Boundaries: pass (the scenario is the round trip).

## External-Code-Review-Findings

| Finding | Disposition |
|---|---|
| U7 absent from the scenario | rejected-with-reason: U7 cut from the campaign |
| U4 positive control asserts only U4 | accepted-and-fixed |
| free-text U3 case not run at medium | rejected-with-reason: low; covered at trivial/small |
