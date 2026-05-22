# Iterate Spec: reconcile-d1-fr-coverage

- **Run ID:** iterate-2026-05-22-reconcile-d1-fr-coverage
- **Type:** change
- **Complexity:** small
- **Status:** draft

## Goal

Close detective-audit finding **D1 (Spec FR coverage in events)** by recording a
single `work_completed` event that covers the 8 FRs whose post-watermark coverage
is currently empty. No source, test, or spec changes — this iterate is a
compliance-bookkeeping reconciliation.

## Acceptance Criteria

- [ ] One `work_completed` event lands in the main repo's
  `shipwright_events.jsonl` with `affected_frs` =
  `[FR-01.03, FR-01.04, FR-01.05, FR-01.06, FR-01.07, FR-01.08, FR-01.09, FR-01.12]`,
  `spec_impact=none`, and a justification that names the watermark mechanism.
- [ ] Re-running `plugins/shipwright-compliance/scripts/audit/group_d.py` against
  the project's event log returns `pass` on D1.
- [ ] The iterate produces an ADR (decision-drop) that explains the watermark
  quirk and links back to this spec.

## Spec Impact

- **Classification:** `none`
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** All 8 FRs (FR-01.03 `/shipwright-plan`,
  FR-01.04 `/shipwright-design`, FR-01.05 `/shipwright-build`,
  FR-01.06 `/shipwright-test`, FR-01.07 `/shipwright-security`,
  FR-01.08 `/shipwright-deploy`, FR-01.09 `/shipwright-changelog`,
  FR-01.12 `/shipwright-preview`) describe live, operational plugin commands —
  the FR table is correct, the AC blocks are correct. The D1 failure is a
  side-effect of `group_d._watermark_ts` invalidating all pre-`2026-05-04T05:43`
  coverage events when iterate `evt-8ee80d97` set `spec_updated` to a
  *sub-iterate spec file* (not the FR-table spec). Since that day, only
  iterates that explicitly worked on iterate / project / compliance / adopt /
  triage / run touched their FRs in `affected_frs`; the foundational
  plugin-command FRs were never re-confirmed. This iterate is the
  reconciliation event — no FR moves, no spec text changes.

## Out of Scope

- Refining the ACs of the 8 FRs from their current state (FR-01.03/04/05/07/08/09/12
  carry only the original adopt-time placeholder; FR-01.06 has the boundary-coverage
  refinement). Concrete ACs per plugin command should be added during normal
  iterate work that actually exercises those plugins.
- Refining `group_d._watermark_ts` to only honor `spec_updated` values that
  resolve to FR-table spec files (`*/01-adopted/spec.md` or any spec with a
  `## Functional Requirements` section). User decision (2026-05-22):
  defer — the watermark has only moved once since project adoption and
  Iterate C.1's FR-gate discipline reduces the chance of accidental re-trip.
  Re-evaluate if D1 re-fails before the next release.
- Backfilling per-FR coverage events for each plugin separately. Operator
  decision: one multi-FR event is honest documentation of the bookkeeping
  state; eight ahistorical per-FR events would be ceremony without
  additional signal.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `shared/scripts/tools/record_event.py` | `plugins/shipwright-compliance/scripts/audit/group_d.py:_check_d1` (and D2/D3/D4/D5) | JSONL |

The producer/consumer pair already exists and is exercised by every iterate
event. This iterate appends one row through the existing producer — no schema
change, no new field, no new consumer. The Boundary Probe trigger
(`touches_io_boundary`) does NOT fire because the JSONL file is not in the
git diff (it's gitignored and appended via `record_event.py`).

## Confidence Calibration

- **Boundaries touched:** Only the existing `record_event.py` →
  `group_d.py` JSONL pair. No new producer/consumer code.
- **Empirical probes run:**
  1. Re-read `group_d._check_d1` + `_watermark_ts` + `_filter_after_watermark`
     to confirm the watermark is set by max `ts` of any event with
     non-empty `spec_updated`. Confirmed.
  2. `python -c "..."` against the live event log to enumerate the watermark
     (`2026-05-04T05:43:25.028009+00:00`, evt-8ee80d97), the 8 uncovered FRs,
     and the post-watermark covered FRs (01/02/10/11/13/14). Confirmed.
  3. Searched `shipwright_events.jsonl` for any other `spec_updated` set —
     count: 1 (evt-8ee80d97 is the only one ever recorded). The watermark
     has not moved since 2026-05-04.
- **Edge cases NOT probed + why acceptable:**
  - F11 verifier on a no-source-change commit: covered by the deterministic
    `verify_iterate_finalization.py` at F11 itself.
  - record_event.py FR-gate behavior with `affected_frs` non-empty: well-tested
    in `shared/scripts/tools/tests/test_record_event.py`; this iterate uses
    the same code path as 60+ historical iterate events.
- **Confidence-pattern check:** No "are you confident?" question has been
  asked or answered in this run.

## Verification (medium+)

- **Surface:** `none`
- **Justification:** Small-complexity compliance-bookkeeping iterate — no
  user-erlebbare surface to exercise. Verification is the D1 re-run
  (see ACs above), which is a deterministic Python audit check, not a
  startable web/cli/api surface.

## Self-Review

1. **Correctness.** D1's `_check_d1` builds the `covered` set from
   `affected_frs` of post-watermark `work_completed` events. After F7, the new
   event lands with `affected_frs = [the 8 FRs]` and `ts > watermark`. The
   `uncovered` list collapses to `[]` and D1 returns `pass`. Goal met.
2. **Tests.** No test code changed — none needed. The audit harness
   (`plugins/shipwright-compliance/tests/test_audit_group_d.py`) already
   exercises `_check_d1` against synthetic event lists; this iterate's
   event-shape is structurally identical to the events those tests cover.
3. **Conventions.** Iterate spec under `.shipwright/planning/iterate/<date>-<slug>.md`,
   dashed-date `run_id`, worktree isolation via B1a — all per skill.
4. **No regressions in audit Group D.** D2 (FR-refs exist in spec): the 8 FRs
   are all in the live FR table — pass. D3 (promised FRs delivered): no
   `new_frs` in this event — n/a. D4 (latest covering event passed tests):
   the event will carry no `tests` block, so D4 skips silently per its own
   docstring. D5 (feature/change iterate links an FR): event links 8 FRs
   AND records `spec_impact=none` with justification — exempt either way.
5. **Documentation.** Iterate spec + ADR (decision-drop) + CHANGELOG drop —
   all planned.
6. **Architectural impact.** None. No `--architecture-impact` flag passed
   to `write_decision_drop.py`.
7. **Affected Boundaries.** Existing `record_event.py` → `group_d.py` JSONL
   pair, no new producer/consumer, no schema change. Documented above.
