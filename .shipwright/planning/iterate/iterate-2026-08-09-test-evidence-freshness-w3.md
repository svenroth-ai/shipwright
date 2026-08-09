# Iterate Spec: test-evidence freshness

## Intent and decision

- **Run ID:** `iterate-2026-08-09-test-evidence-freshness-w3`
- **Intent:** bug fix
- **Complexity:** medium (shared verifier plus compliance evidence contract)
- **Spec impact:** none — this corrects internal evidence validation.
- **Decision:** Test Evidence is per-iterate evidence. Its existing
  `Source-State: run=` banner is written after finalization records that run's
  `work_completed` event, so it is the authoritative freshness predicate.
- **Alternative rejected:** file mtime. Checkouts and unchanged renders change
  timestamps without changing the evidence state.

## Acceptance criteria

1. W3 traces its evidence to the latest iterate `work_completed` event.
2. W3 compares the report's `Source-State` run identity to that event, not mtime.
3. An old mtime with a current source-state passes; an old source-state fails.
4. A missing or unresolvable source-state fails with the F5b recovery action.
5. The independent `work_completed` requirement remains mandatory.
6. I2 is recorded as a narrowly scoped follow-up: it is phase-start based and
   cannot use W3's per-iterate source-state predicate without changing its contract.

## Affected boundaries

| Producer | Consumer | Format | Test |
| --- | --- | --- | --- |
| `finalize_iterate.py` / Test Evidence generator | W3 verifier | `Source-State: run=<run-id>` | `shared/tests/test_workflow_checks.py` |

## Mini-plan

1. Reuse `source_state.parse_banner_line` in the W3 verifier.
2. Resolve the latest matching iterate event's declared run ID, including its
   historical `adr_id` spelling.
3. Fail closed for missing/mismatched source state; preserve missing-event checks.
4. Add fresh, stale, old-mtime-current, and missing-source-state regression tests.