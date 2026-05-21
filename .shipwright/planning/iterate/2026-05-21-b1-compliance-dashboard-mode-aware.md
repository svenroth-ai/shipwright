# Iterate Spec: b1-compliance-dashboard-mode-aware

- **Run ID:** iterate-2026-05-21-b1-compliance-dashboard-mode-aware
- **Type:** feature
- **Complexity:** small
- **Status:** draft

## Goal

Iterate B.1 from the artifact-polish plan: turn the Compliance Dashboard
from a generic "1/7 WARN" surface into a mode-aware, signal-first
indicator board.

Three changes:

1. **Mode-aware indicators** — adopted projects render
   `Pipeline phases completed: n/a (adopted)` instead of the misleading
   `1/7 WARN`; the `Work events (build)` and `All sections reviewed`
   rows are hidden entirely (structurally N/A for adopted, not "not run
   yet").
2. **Why-warn column** — every quality-indicator table gains a 4th
   column carrying a one-line diagnostic pointer on WARN rows so the
   operator knows where to look. Empty for PASS / INFO / n/a.
3. **Triage open indicator** — new row counting open items in
   `.shipwright/triage.jsonl`. Signal severity (`critical/high/medium/
   low`) prominent; info-severity shown in parentheses
   (`"3 open (1 info)"`), consistent with the inbox's signal-first
   render decided in B0 ADR-054 D6.

## Plan-correction (empirically observed)

The artifact-polish plan said "lese `run_config.scope` (adopt vs
greenfield)". That's wrong — `scope` carries values like `"library"` /
`"full_app"`, orthogonal to adoption status. The real signal is the
presence of `run_config.adoption` (with `adopted_at`,
`commit_at_adoption`, ...). This iterate uses the empirically correct
check.

## Acceptance Criteria

- [ ] **AC-1** When `run_config.adoption` is set, the `Pipeline phases
  completed` row renders `| Pipeline phases completed | n/a (adopted) |
  INFO |  |` — no fake-WARN.

- [ ] **AC-2** When `run_config.adoption` is set, the `Work events
  (build)` and `All sections reviewed` rows are absent from the
  rendered dashboard.

- [ ] **AC-3** When `run_config.adoption` is unset (greenfield), all
  three rows (Pipeline phases, Work events build, All sections
  reviewed) render with real progress numbers and PASS/WARN status as
  today.

- [ ] **AC-4** Every quality-indicator table starts with the header
  `| Metric | Value | Status | Why warn? |` and separator
  `|--------|-------|--------|-----------|`.

- [ ] **AC-5** WARN rows have a non-empty Why-warn cell with a
  pointer to the relevant artifact (e.g. `"see test-evidence.md"`,
  `"see sbom.md"`). PASS / INFO / n/a rows have an empty cell.

- [ ] **AC-6** A new `Triage open` row appears in every event-based
  dashboard. With no open items: `| Triage open | 0 open | PASS |  |`.
  With signal items only: `| Triage open | N open | WARN | N
  actionable item(s) — see ../agent_docs/triage_inbox.md |`. With
  info-only items: `| Triage open | 0 open (M info) | PASS |  |`. With
  both: `| Triage open | N open (M info) | WARN | ... |`.

- [ ] **AC-7** Dismissed and promoted items don't contribute to the
  count.

## Out of scope

- Layer column for tests (B.3).
- "FRs without tests" / "FRs with stale verification" Coverage Summary
  in RTM (B.4).
- Mode-aware behaviour for the legacy `_quality_indicators_legacy`
  path — only the event-based path is touched. Legacy is the
  pre-event-log path; adopted projects always have events.
- Restructuring `compliance_report.py` (now 386 lines, over the
  300-line guideline). Sensible follow-up split: `lib/quality_indicators.py`
  + `lib/dashboard_sections.py`. Tracked but not in this iterate.

## Implementation notes

- Mode detection lives in `_is_adopted(run_config)` — checks for a
  truthy `adoption` dict.
- Triage open counts come from a new `_triage_open_counts(project_root)`
  helper that reads `shared/scripts/triage.py::read_all_items` and
  partitions by `info` vs everything else. Tolerant of missing /
  corrupt file (returns `(0, 0)`).
- Why-warn column uses inline per-indicator pointers — no dynamic
  reflection; intentional simplicity. The dashboard is a launchpad,
  not a triage tool (the Triage Inbox is, post-B0).

## Verification

- `uv run --extra dev pytest plugins/shipwright-compliance/tests/test_compliance_report.py -v`
  — 22 passed (was 9; +13 new B.1 tests).
- Full compliance suite (`plugins/shipwright-compliance/tests/`):
  348 passed.
- Full shared suite (`shared/tests/`): 2101 passed.
