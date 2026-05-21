# Iterate Spec: B.4 — RTM ↔ Triage deep-link + Coverage Summary rewrite

- **Run ID:** iterate-2026-05-21-b4-rtm-deep-link-and-coverage
- **Type:** feature
- **Complexity:** small
- **Status:** draft

## Goal

Close the artifact-polish plan's Iterate B.4 by closing the loop on
ADR-054 D5 (RTM↔Triage cross-link contract): the RTM generator now
*consumes* the `frId` field that B0 made producer-side, and renders
`FAIL → [trg-XXX](../agent_docs/triage_inbox.md#trg-XXX)` deep-links
on every FR row with an open triage card. Plus rewrite the thin
metrics-only Coverage Summary into three operator-actionable
subsections.

## Acceptance Criteria

- [ ] **AC-1** New helper `_open_triage_by_fr(project_root)` returns
  `{fr_id: [open triage items]}` keyed by `frId`. Only items with
  `status == "triage"` (promoted / dismissed stay terminal). Lazy-
  imports the triage API so the RTM generator still works in
  minimal envs.

- [ ] **AC-2** The `## Requirements Coverage` table's Status cell
  carries `FAIL → [trg-XXX](../agent_docs/triage_inbox.md#trg-XXX)`
  for every FR whose ID matches one or more open triage items'
  `frId`.

- [ ] **AC-3** Multiple open triage items for the same FR render as
  comma-separated deep-links, sorted by item ID for deterministic
  diffs.

- [ ] **AC-4** The deep-link **overrides** the previous events-derived
  status (including `COVERED` and `COVERED (baseline)`): an open
  triage item is positive evidence the operator hasn't accepted the
  current verification state, regardless of what the unit tests
  report.

- [ ] **AC-5** Triage items with `frId == None` (or no `frId` field
  at all) are silently ignored — they belong to producers that don't
  carry FR context (Phase-Quality, SBOM, drift findings).

- [ ] **AC-6** Promoted / dismissed / snoozed triage items don't
  render deep-links — only `status == "triage"` participates.

- [ ] **AC-7** The Coverage Summary section keeps the thin metrics
  table at the top, then renders three new subsections:
  - `### FRs without tests` — FRs with no `work_completed` events.
  - `### FRs with stale verification (> 14 days)` — FRs whose latest
    event is older than `_STALE_VERIFICATION_DAYS` days, sorted
    oldest-first.
  - `### FRs with open triage items` — FRs with at least one open
    triage card, each row rendering `FAIL → [trg-XXX](...)` links.

- [ ] **AC-8** Each subsection is OMITTED entirely when its set is
  empty (audience principle: quiet output when nothing's wrong).

- [ ] **AC-9** Stale-verification timestamp parsing tolerates ISO
  strings with both `+00:00` and `Z` suffixes. Malformed timestamps
  skip the row AND emit a `warnings.warn` so operators see the
  data-quality issue in test output / CI logs (code-review-M3 fix —
  silent skip alone hides corrupt event streams).

## Out of scope

- **Suite-level cross-link** (`suiteId` field consumption) — kept
  open for a later iterate when test-evidence producers consistently
  populate suiteId. B.4 reads only `frId`, which B.3's
  `emit_test_failure_triage` does not yet set (it sets `eventId`
  instead). When a future iterate adds per-FR test-evidence triage,
  the existing `_open_triage_by_fr` consumer reads it for free.

- **`eventId` consumption** — the RTM doesn't render eventId
  cross-links (B.3's eventId field links a triage card back to its
  originating test_run event, which is a separate navigation
  direction).

- **Stale-window configuration** — fixed at 14 days per the plan.
  Configurable threshold deferred until an operator complains.

- **Section Traceability deep-links** — only the requirements-coverage
  table consumes `frId`. The section-traceability table is
  greenfield-only (it operates on per-section data) and out of scope.

## Implementation Notes

- `_open_triage_by_fr` mirrors B.1's `_count_triage_status` lazy-
  import pattern: wraps the read in `try/except ImportError` so
  the RTM keeps generating in a minimal CI env without
  `shared/scripts/` on `sys.path`.

- The Status-cell override happens AFTER the events-based status is
  computed — this keeps the existing test coverage stable (unit-test
  paths produce the same baseline status; the open-triage suffix is
  a thin overlay).

- `_frs_with_stale_verification` uses `datetime.now(timezone.utc)`
  and ISO-8601 parsing. The fallback path swallows `ValueError`
  silently — a corrupt timestamp in one event won't crash the whole
  RTM render.

- `_render_fail_triage_links` sorts items by ID for deterministic
  output. The aggregator already emits `<a id="trg-XXX">` anchors
  above every card (B0 acceptance criteria), so `#trg-XXX` resolves
  in VS Code preview + GitHub blob + the WebUI.

## Verification

- `uv run --extra dev pytest plugins/shipwright-compliance/tests/test_rtm_generator.py
  -v` — 24 tests (14 baseline + 10 new: 5 deep-link, 5 Coverage
  Summary rewrite).

- Full compliance suite: 407 passed (baseline 397 + 10 new).

- Full shared suite: 2116 maintained (no shared changes in B.4).
