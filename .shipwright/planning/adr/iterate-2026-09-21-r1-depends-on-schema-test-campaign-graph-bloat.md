# Bloat exception — `shared/tests/test_campaign_graph.py` raised to 325-LOC

- **Status:** proposed
- **Date:** 2026-09-22
- **Re-Review-Date:** 2026-12-21
- **Incident Reference:** campaign `campaign-dag-scheduler` sub-iterate R1
  (`iterate-2026-09-21-r1-depends-on-schema`); external Tier-3 PR review
  (`openai/gpt-5.6-luna`, `2026-09-22T01:08:31Z`) blocking finding on
  `safe_project_campaign_status`'s validation ordering.

## Context

`test_campaign_graph.py` was written new in this same sub-iterate and sat at
289 lines, under the 300-line limit. The external Tier-3 PR-review gate then
found a real defect its own existing test suite had not caught:
`safe_project_campaign_status` ran `validate_dependency_graph` (structural)
BEFORE `check_frozen_contracts` (per-unit revert), so a non-pending unit's
edited `depends_on` that was ALSO structurally invalid (e.g. an unknown id)
hit the structural check first and degraded the WHOLE campaign projection,
bypassing the per-unit revert the function's own docstring already promised
("a single bad edit must never brick unrelated DAG branches"). Fixing the
ordering in `campaign_graph.py` (reordering two existing calls plus a
docstring correction, no new lines of substance there) needed a new
regression test proving the corrected behavior — a frozen unit's structurally
-invalid edit now reverts to its frozen value instead of degrading the whole
campaign — which pushed this file to 310. The SAME Tier-3 review round also
found `_read_loop_state_units` didn't validate a retained unit's own
`depends_on` field was a list, crashing `check_frozen_contracts` on a
non-list value; a new regression test
(`test_non_list_depends_on_on_retained_unit_does_not_crash`) proving that
input no longer raises pushed this file to 325.

## Ousterhout Argument

The new test (`test_frozen_edit_to_unknown_id_reverts_instead_of_degrading_whole_campaign`)
is a single test method reusing the same `TestSafeProjectCampaignStatus`
fixture helper (`_write`) and `CAMPAIGN_MD`/`_committed()` module-level
fixtures every other test in this class already uses — it is not a new
concern, just one more case of the class this file already exists to cover
(`safe_project_campaign_status`'s degrade-vs-revert contract). Splitting one
test method into a second file for line-count reasons alone would scatter a
single class's related assertions across two files for no readability gain.

## YAGNI Check

The test exists because an independent, external reviewer demonstrated the
prior ordering was reachable with real input (an operator hand-editing a
claimed unit's `depends_on` cell to a typo'd id — exactly the input
`check_frozen_contracts` exists to catch). Nothing here is speculative.

## Chesterton-Fence Check

No prior design decision pins this file at exactly 300 lines — it is the
same brand-new file from earlier in this same sub-iterate whose being under
300 lines was incidental to when each review round ran, not a boundary
anyone deliberately drew.

## Decision

Grant an exception raising `test_campaign_graph.py`'s allowed `current` to
325. Retirement plan: if a future change to `safe_project_campaign_status`'s
validation ordering needs a THIRD interacting-findings regression test
beyond structural/charset/frozen, that is the trigger to reconsider splitting
`TestSafeProjectCampaignStatus` into its own test module — re-review at that
point rather than waiting for the calendar date alone.

## Consequences

No production code's public interface changed from this test addition
itself (the production fix is in `campaign_graph.py`'s existing bloat
exception). The bloat-baseline anti-ratchet now holds this file at 325 as
its ceiling; a future PR that grows it further without its own exception is
correctly blocked.

## Rejected alternatives

- **Skip the regression test and rely on the fix alone.** Rejected: the
  ordering bug survived to an external, live-gate review specifically
  because no existing test exercised "frozen unit + structurally-invalid
  edit" as a combined case; landing the fix without a test re-opens exactly
  that blind spot for the next change to this function.
- **Split `TestSafeProjectCampaignStatus` into its own file now.** Rejected
  as premature: one class, one new test method, ten lines over budget — not
  yet a coherent second concern worth a second file.
