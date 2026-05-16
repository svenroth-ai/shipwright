# Iterate Spec: spec-impact-gate

- **Run ID:** iterate-2026-05-16-spec-impact-gate
- **Type:** feature
- **Complexity:** large (force-continue — user-directed normal iterate)
- **Status:** implemented

## Goal

Make every FEATURE/CHANGE iterate explicitly classify its spec impact as
ADD / MODIFY / REMOVE / NONE, enforce it with a hard finalization gate, and
surface historical drift via a compliance detective check. Today the
"Step 2: Spec Update (always)" contract is prose-only and was empirically
violated ~27/28 times — whole subsystems landed with no FR.

## Acceptance Criteria

- [x] AC-1 — `record_event.py` accepts `--spec-impact {add|modify|remove|none}`
  and `--spec-impact-justification`, and writes both onto `work_completed`
  events when present. (`TestSpecImpactField`)
- [x] AC-2 — `record_event.py` exits 1 for a `work_completed` + `source=iterate`
  + `intent in (feature,change)` event with `spec_impact=none` and no
  justification. (`test_spec_impact_none_without_justification_fails`)
- [x] AC-3 — `record_event.py` exits 1 for the same event class when
  `spec_impact != none` (or absent) AND both `affected_frs` and `new_frs`
  are empty. Build events (`source != iterate`) are unaffected.
  (`TestSpecImpactGate`)
- [x] AC-4 — `check_spec_impact_recorded` (in `verifiers/iterate_checks.py`):
  feature/change iterate whose commit touched no `.shipwright/planning/**/spec.md`
  and recorded no `spec_impact=none`+justification → FAIL (ERROR); commit
  touched a spec.md → PASS; bug intent → SKIPPED; git unavailable → SKIPPED.
  (9 `test_spec_impact_*` cases)
- [x] AC-5 — compliance audit Group D gains `D5`: flags `work_completed`
  events with `intent in (feature,change)`, empty `affected_frs` AND `new_frs`,
  and `spec_impact != none`. Severity MEDIUM. (6 `test_d5_*` cases)
- [x] AC-6 — a `## Removed Requirements` section in `spec.md` is excluded
  from FR parsing by both `drift_parsers.parse_fr_table` and
  `data_collector.collect_requirements` — removed FRs do not appear in RTM
  coverage and are not flagged as uncovered. (3+2 exclusion tests)
- [x] AC-7 — `spec-generation.md` documents the `### Removed Requirements`
  convention, including the mandatory literal `status: deprecated`.
- [x] AC-8 — iterate `SKILL.md` Step 2 (Paths A/B/C) restructured into the
  ADD/MODIFY/REMOVE/NONE classification; Phase Matrix row renamed; F7 gains
  `--spec-impact`; iterate-spec template gains `## Spec Impact`; Artifact
  Ownership table updated.
- [x] AC-9 — `docs/hooks-and-pipeline.md` and `docs/guide.md` updated.

## Affected FRs
- FR-01.11 (`/shipwright-iterate`): MODIFY — gains the enforced spec-impact
  classification + the `check_spec_impact_recorded` finalization gate.
- FR-01.10 (`/shipwright-compliance`): MODIFY — audit gains the D5
  inverse-drift check.
- FR-01.02 (`/shipwright-project`): MODIFY — spec generation gains the
  `### Removed Requirements` convention.

## Out of Scope
- Retroactive backfill of FRs for already-landed features (Triage Inbox,
  F0.5 gate, etc.) — the user backfills prose in a separate session.
- A new Status column on the FR table — rejected in favor of the separate
  `## Removed Requirements` section.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `record_event.py:build_event` | `iterate_checks.py:check_spec_impact_recorded`, `group_d.py:_check_d5` | `shipwright_events.jsonl` work_completed event (JSON) |
| iterate Step 2 / `spec-generation.md` | `drift_parsers.py:parse_fr_table`, `data_collector.py:collect_requirements` | `spec.md` FR table + `## Removed Requirements` section (Markdown) |

## Confidence Calibration
- **Boundaries touched:** `work_completed` event JSON (`record_event.py` →
  `iterate_checks.py` / `group_d.py`); `spec.md` FR table + `## Removed
  Requirements` section (`spec-generation.md` → `drift_parsers.parse_fr_table`
  / `data_collector.collect_requirements`).
- **Empirical probes run:**
  - Round-trip: `record_event.py` writes `spec_impact` → re-read via
    `read_events` → asserted (`TestSpecImpactField`). Gate exits 1 with
    nothing written on the fail paths — `read_events(project) == []`
    asserted.
  - FR-parser exclusion fed FR-shaped rows inside `### Removed Requirements`
    (5-col, priority `Must`) — would parse as live FRs without the section
    skip; both parsers confirmed to exclude them, and a live FR table after
    the section's closing heading still parses.
  - Verifier commit-diff probe: real `git init`+commit fixtures with and
    without a planning `spec.md` in the diff → PASS / FAIL respectively.
- **Edge cases NOT probed + why acceptable:** merge-commit diffs in
  `_commit_changed_paths` — iterate commits are never merges (F6 is a
  single normal commit). Non-UTF8 event-log lines — `read_text(errors=
  "ignore")` already covers it and is exercised by existing record_event
  corruption tests.
- **Confidence-pattern check:** the first Removed-Requirements fixtures used
  a non-FR-shaped removed row (priority column = run_id), so the regex
  skipped them for free and the test passed without exercising the section
  logic — caught during RED, fixtures corrected to FR-shaped rows. No
  "are you confident?"→yes→bug pattern after that fix.

## Verification
- **Surface:** cli
- **Runner command:** `uv run pytest shared/tests/ plugins/shipwright-compliance/tests/ -v`
  (record_event + verifier + drift_parsers + Group D5 + data_collector)
- **Evidence path:** pytest log under `.shipwright/runs/iterate-2026-05-16-spec-impact-gate/`
