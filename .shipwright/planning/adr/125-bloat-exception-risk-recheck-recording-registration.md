# ADR-125: Bloat exception — `shared/scripts/tools/verifiers/iterate_checks.py` raised to 1089-LOC

<!-- Grants a bloat-baseline exception for the two-line growth caused by
     iterate-2026-08-05-risk-recheck-recording-integrity. Referenced from
     shipwright_bloat_baseline.json (state="exception", adr="ADR-125").
     Does NOT supersede ADR-093: that ADR already carries the Ousterhout
     argument this one reuses; ADR-125 only records the incremental bump. -->

- **Status:** accepted
- **Date:** 2026-08-05
- **Re-Review-Date:** 2026-08-31 _(co-scheduled with ADR-093's own re-review —
  the same reviewer evaluating whether `verifiers/iterate/` can finally split
  should fold this bump into that same decision)_
- **Incident Reference:** iterate-2026-08-05-risk-recheck-recording-integrity —
  registering the new F11 verifier `check_risk_recheck_recorded` (recording-
  integrity gate for the campaign sub-iterate-runner's Step 3.4) requires one
  new import line and one new call in `run_all_checks`.

## Context

`shared/scripts/tools/verifiers/iterate_checks.py` was already an ADR-093
exception at `current: 1093`. It has since shrunk to 1087 through unrelated
maintenance, but the anti-ratchet gate compares only against the CURRENT
baseline value, not the historical high-water mark ADR-093 already accepted.
This iterate's two-line addition (`from .risk_recheck_recording import
check_risk_recheck_recorded` + one `run_all_checks` call) brings the file to
1089 — still 4 lines BELOW the ceiling ADR-093 already justified, but above
the current baseline entry, which mechanically requires its own exception.

## Ousterhout Argument

Unchanged from ADR-093, restated because it applies verbatim: this module is a
**deep module** — the public interface (`run_all_checks(project_root, run_id,
commit)`) stays exactly as narrow as before, while the cohesive family of F11
finalization invariants it enforces gained one more fail-closed member. The
new check's own logic, schema validation, and path-safety hardening live
entirely in the new sibling module `risk_recheck_recording.py`; this file's
growth is exactly the import + the one-line registration ADR-093 already
anticipated as the recurring, accepted pattern ("`run_all_checks` grew by
exactly one entry") for this specific registry.

## YAGNI Check

The two added lines have no speculative content: one import (used exactly
once, by the new registration call) and one function call (the check itself,
already covered by its own test suite). Nothing here is scope carried "for
later."

## Chesterton-Fence Check

The fence — `iterate_checks.py` as the single registry every F11 check is
wired through — was established and re-affirmed by ADR-093 for the identical
reason: splitting it would either fragment `run_all_checks`'s single ordered
call site or expose per-check internals that should stay encapsulated. No new
fence is being erected or removed here; this ADR only records that the
existing one still holds.

## Decision

Raise `shared/scripts/tools/verifiers/iterate_checks.py`'s baseline `current`
to **1089**. No new split is warranted for a 2-line registration — the
Re-Review-Date is shared with ADR-093's, which already tracks the larger
question of whether the `verifiers/iterate/` package should be split into a
sub-package (at which point this and ADR-093's exceptions would both retire
together).

## Consequences

Any future PR touching this file is now measured against 1089, not 1087. The
next check registered here will need its own (or a renewed) exception unless
the ADR-093/ADR-125 re-review has landed the package split by then.

## Rejected alternatives

- **Shrink the file by 2 lines elsewhere to stay net-neutral:** considered
  first (the preferred remediation). Rejected because the only trimmable
  content nearby is either load-bearing documentation or would read as
  gaming the line count rather than a genuine improvement — the project's own
  stated position is that "long + coherent" is not bloat, and shaving an
  unrelated comment purely to dodge this counter is the kind of rationalization
  the anti-ratchet exists to refuse.
- **Split `iterate_checks.py` now:** deferred to the ADR-093/ADR-125 shared
  re-review date; splitting a 1089-line deep module for a 2-line registration
  is disproportionate churn for this iterate's actual scope.

---

## External Sources Acknowledged

This template's YAGNI Check + Chesterton-Fence Check headings are adapted
from the same sources ADR-093 cites (obra/superpowers `writing-plans`, MIT ©
Jesse Vincent; addyosmani/agent-skills `code-simplification`, MIT © Addy
Osmani).
