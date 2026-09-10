# ADR: Grandfather promote_required_layers.py + its test files as a bloat exception

## Context

Both `shared/scripts/tools/promote_required_layers.py` (556 lines before this
iterate) and `shared/scripts/tools/tests/test_promote_required_layers.py`
(927 lines before this iterate) were already several times over the 300-line
source/test limit before P3.4c touched them, and neither had a
`shipwright_bloat_baseline.json` entry — an existing baseline-coverage gap,
not new debt this iterate created.

P3.4c's anchor-promotion fallback (bounded first-parent ancestor walk + a
per-FR staleness guard) is additive functionality on the SAME tool and its
SAME test suite. Splitting either file now would be a structural refactor
unrelated to P3.4c's actual scope (anchoring Layers-promotion to the newest
verified ancestor), and mid-flight would invalidate the code-review and
doubt-review cascades running against the diff.

`shared/tests/test_promotion_evidence_staleness.py` is a genuinely NEW file
this iterate created (the staleness guard's own unit tests), which also
crossed 300 lines during the doubt-review round of fixes (a HIGH finding
needing several new regression tests, on top of the two rounds of fixes
already pinned there). Unlike the other two files, this is new debt, not
grandfathered pre-existing debt — but it is a single cohesive unit (every
test in it exercises the same three closely-related functions in
`promotion_evidence_staleness.py`), and splitting it for its own sake, mid
doubt-review-cascade, carries the same out-of-scope-churn objection as
splitting the other two.

## Decision

Grandfather all three files into `shipwright_bloat_baseline.json` with
`state="exception"` at their current sizes, referencing this ADR. A future
iterate that meaningfully extends any of them again is free to revisit
whether a split is warranted then.

## Consequences

All three files stay exempt from the anti-ratchet gate at their current
size; growing any of them further in a FUTURE iterate re-trips the gate and
must be justified fresh, not silently absorbed into this exception. Growth
within THIS SAME iterate (the doubt-review round's own fixes, landing
before this ADR's baseline entries are first written) is the normal shape
of "baseline refresh is the last step," not a fresh trip.

## Rejected alternatives

Splitting `promote_required_layers.py` or its test file now — rejected as
out-of-scope churn for a bugfix-and-hardening pass already through two
external review rounds (external code review, external plan review); would
need its own iterate to do responsibly (extracting the CLI/argparse shell
from the promotion-planning core, and splitting the test file's fixtures
into a shared conftest).
