# ADR-097: Bloat exception — test_audit_group_b.py raised for B7 Rule E

- **Status:** accepted
- **Date:** 2026-06-05
- **Re-Review-Date:** 2026-09-05 _(retire when the Group-B audit suite is split
  per-check — candidate for the B/C bloat-cleanup campaigns; same horizon as
  ADR-095/096.)_
- **Incident Reference:** `iterate-2026-06-05-b7-exclude-nonfunctional` — B7
  Rule E (exclude non-functional Conventional-Commit types) + its regression
  tests pushed `test_audit_group_b.py` past its ADR-095 ceiling (706 → 751).

## Context

Rule E makes B7 exclude non-functional Conventional-Commit types
(`build`/`chore`/`ci`/`docs`/`style`/`test`) by default — repo maintenance with
no RTM footprint — superseding B's narrow-Rule-D decision (which created a
backfill treadmill: every direct `ci`/`docs`/`chore` commit re-opened B7). The
growth is **tests only**:

- `test_audit_group_b.py` 706 → 751 (+45): four new Rule E cases
  (excludes-nonfunctional-by-default, still-flags-functional-`feat`, opt-out via
  `exclude_nonfunctional_types=false`, `conventional_type` parsing) + the
  `rule_b` isolation test updated to set `rule_e=false`.

Source stayed within limits and was NOT baselined upward: `git_log_scan.py`
292 (under the 300 guideline, unbaselined), `audit_detector.py` 402 (under its
ADR-existing 422 ceiling).

## Ousterhout Argument

`test_audit_group_b.py` is the per-group B suite with shared git-init/commit
fixtures; splitting it to shave +45 would scatter the Rule A–E cases that share
those fixtures, exposing per-rule wiring the suite exists to centralise.

## YAGNI Check

Every added line backs Rule E shipped today (the recurrence it kills is live —
`2fa1e9ab` re-appeared mid-backfill). Both the new behaviour AND its opt-out are
asserted; no speculative scope.

## Chesterton-Fence Check

The suite is large because Group B covers many independent checks (B1–B8) under
one fixture set; git history shows growth under that structure (ADR-095 already
raised it for C1's B7 Run-ID tests). Extending it for a real correctness change
is consistent with the fence.

## Decision

Raise `plugins/shipwright-compliance/tests/test_audit_group_b.py` to **751**
(`state: exception`, `adr: ADR-097`, re-pointed from ADR-095 — the controlling
reason for the current measurement).

## Consequences

The file operates against the new limit; further additions stay within it or
bump again with justification. The new logic landed in `git_log_scan.py`
(unbaselined, 292) — no source baseline was raised.

## Rejected alternatives

- **Trim the new tests to dodge the bump** — theatre (ADR-095's standing
  finding); the opt-out + functional-still-flagged cases are exactly the
  coverage that proves Rule E didn't weaken B7.
- **Split the Group-B suite now** — disproportionate mid-fix; belongs to the
  dedicated bloat-cleanup campaigns.

---

## External Sources Acknowledged

YAGNI / Chesterton-Fence headings follow the bloat-exception template, adapted
from obra/superpowers `writing-plans` (MIT © Jesse Vincent) and
addyosmani/agent-skills `code-simplification` (MIT © Addy Osmani).
