# Iterate: Compliance-artifact usability (test-evidence + traceability-matrix)

- **Run ID:** iterate-2026-06-30-compliance-artifact-usability
- **Intent:** CHANGE (modify rendering of two compliance artifacts)
- **Complexity:** medium
- **Spec Impact:** MODIFY (FR-01.10 — audit-ready compliance documentation)

## Problem

The `test-evidence.md` and `traceability-matrix.md` audit artifacts are hard to
navigate: the `iterate`/`(iter)` source tokens are plain text, the Verification
Timeline is oldest-first, FRs in the timeline aren't clickable, commits aren't
linked, and the Event column shows only the raw technical `description`. A user
also asked whether the unit-only "Full Suite Runs" table is a bug.

## Data reality (measured, see investigation)

Events carry **no** per-iteration spec path (`run_id`: 0/226, `spec_updated`:
2/226; `adr_id` mostly has no file). Backfilling a spec link from name+date
matches only ~8% safely — most iterates were trivial/small and never authored a
spec. So the durable, **complete** per-event trace target is the Verification
Timeline anchor (`#evt-…`, present for every event, resolves in both repos), and
the commit (GitHub). The unit-only Full Suite Runs table is a known limitation,
not a bug: it is synthesized from `work_completed` events (single unit count);
the 4-layer breakdown needs `test_run` events, which neither repo records.

## Acceptance Criteria

- **AC-1** Test Progression `Source` links canonical-id iterate events to their
  Verification Timeline row (`traceability-matrix.md#evt-…`); non-canonical ids
  stay plain text.
- **AC-2** Requirements Coverage `Last tested` links the `(iter)` token to the
  latest-tested event's timeline anchor (`#evt-…`); build / non-canonical → plain.
- **AC-3** Each Requirements Coverage row carries an in-document anchor
  `<a id="rtm-fr-…">` placed AFTER the requirement link (row prefix unchanged).
- **AC-4** Verification Timeline is sorted **descending** (newest first),
  deterministically (stable; malformed timestamps sort last).
- **AC-5** Verification Timeline `FRs` link each declared FR to its
  `#rtm-fr-…` coverage-row anchor; FRs not in the requirements set stay plain.
- **AC-6** Verification Timeline `Commit` links to the commit on GitHub when a
  repo URL is resolvable from the project's `origin` remote; empty commit or no
  URL → plain short SHA / `—`.
- **AC-7** Event display name prefers an authored `summary` (new optional
  `WorkEvent` field), else a lightly-cleaned `description` (strips a leading
  `iterate:` / `iterate fix:` prefix), else the id. Applied in Test Progression,
  Verification Timeline, and Code Review Evidence.
- **AC-8** `record_event.py` accepts `--summary`; the iterate F5b reference
  instructs authoring a one-line plain `summary` (forward-only; passed through
  `finalize_iterate.py --event-extras-json`).
- **AC-9** The **synthesized** Full Suite Runs table carries an honest note that
  the non-unit columns are `—` because no `test_run` events are recorded (not
  because those layers were skipped). The real `test_run` path is unchanged.

## Affected Boundaries

- Event wire format (`shipwright_events.jsonl`) — **additive** optional field
  `summary` (producer: `record_event.py` / `finalize_iterate.py` passthrough;
  consumer: `WorkEvent.from_dict`). Round-trip test required.
- `ComplianceData.repo_url` (new, populated by `collect_all` from git remote,
  fail-soft "").

## Confidence Calibration
- **Boundaries touched:** event wire format (additive optional `summary`); repo-URL
  resolution from the project's `origin` git remote (read-only subprocess, fail-soft).
- **Empirical probes run:**
  - Real-data smoke render against the live monorepo event log: 71 Verification
    Timeline commit cells link to `github.com/svenroth-ai/shipwright/commit/<sha>`,
    40 FR-link occurrences, timeline newest-first, every Test Progression `Source`
    and Requirements-Coverage `(iter)` token linked, per-FR `<a id="rtm-fr-…">`
    anchors present after the requirement link. → all render correct.
  - `resolve_repo_url(worktree)` → `https://github.com/svenroth-ai/shipwright`
    (https `.git`-stripped); SSH form `git@github.com:o/r.git` → `https://github.com/o/r`;
    non-repo dir → `""`. → boundary verified both directions.
  - `summary` round-trip: `WorkEvent.from_dict({"summary": …})` → `we.summary` →
    Event column renders it; absent → falls back to cleaned `description`. → verified.
- **Test Completeness Ledger:** `tested` for every behavior (0 untested-testable):
  - AC-1 Source cross-file link → `TestProgressionSourceLink` (2 cases).
  - AC-2 `(iter)` link / AC-3 anchor → `TestCoverageLinks` (3 cases).
  - AC-4 descending + malformed-ts-last → `TestTimelineDescending` (2).
  - AC-5 FR links (declared / unknown) → `TestTimelineFrLinks` (2).
  - AC-6 commit link + repo-url resolution → `TestCommitLink` (7, incl. real-git probes).
  - AC-7 summary preference + cleanup + round-trip → `TestEventDisplayName` (5).
  - AC-9 synthesized-table note present / absent on real path → `TestFullSuiteNote` (2).
  - Drift pins → `test_event_id_re_matches_rtm_render_pattern`, `test_fr_anchor_id_shape`.
  - Regression guard: full compliance suite (893) + contract/enforcement (15) green.
  - AC-8 F5b doc instruction documents `summary` → `test_f5b_reference_documents_summary_field`.
- **Confidence-pattern check:** depth — empirically probed the two new boundaries
  (git-remote resolution, event round-trip) rather than asserting confidence;
  breadth — 25 new unit tests across all 8 ACs + real-data render. No
  `cross_component` machinery touched (diff hits no `CROSS_COMPONENT_FILE_PATTERNS`),
  so no integration-composition row is required.

## Out of scope (answered, not built)

- A real per-iteration `spec.md` deep-link (data doesn't support it; ~8% safe).
- A `test_run` producer with the 4-layer breakdown (medium–large; deferred).
- Backfilling `summary` for historical events (forward-only by design).
