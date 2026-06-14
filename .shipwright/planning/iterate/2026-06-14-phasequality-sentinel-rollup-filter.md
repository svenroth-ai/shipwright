# Iterate Spec — phase-quality rollups exclude sentinel-run snapshots

- **run_id:** `iterate-2026-06-14-phasequality-sentinel-rollup-filter`
- **Type:** change (MODIFY phase-quality rollup/surfacing semantics)
- **Complexity:** medium (cross-cutting observability machinery: 4 rollup
  consumers + a shared loader; drives the autonomous-loop trigger surface;
  needs careful unit + end-to-end coverage). NOT `cross_component` (changed
  files are `lib/phase_quality/*.py`, none match `CROSS_COMPONENT_FILE_PATTERNS`
  — no `**/hooks/*.py`, no merge/churn machinery). NOT `touches_io_boundary`
  by the path-based detector (no `*_config.json` / `*_state.json` / `hooks.json`
  in the diff), though the code is a finding-JSON producer/consumer boundary.
- **Lineage:** sibling of `iterate-2026-05-31-phasequality-dashboard-skip`
  (which added `_skip_unengaged_fails`) and `iterate-2026-05-31-phasequality-
  triage-bundle` (which added the `unresolvable_run_id_skip` S2/S3 guard). Both
  suppress degenerate findings **at audit/write time**; this iterate extends the
  same canon to the **rollup/read time** so pre-fix and degenerate snapshots
  stop driving false surfacing.

## Problem (what actually triggered this run)

The autonomous loop fired on `iterate:S2` — "no `.shipwright/planning/iterate/*.md`
file contains run_id=unknown (complexity=medium)". Investigation (probe +
git-archaeology) shows this is a **stale, degenerate-context false-positive**:

1. The surfaced finding lives in `.shipwright/compliance/skill-compliance/
   iterate-unknown-unknown.json`, `audited_at = 2026-05-31T07:41:15Z`,
   `run_id="unknown"`, `session_id="unknown"`.
2. The S2 root-cause guard `unresolvable_run_id_skip` landed the **same day at
   12:05Z** (commit 527fc4b7) — ~4.5h *after* that snapshot was written. So the
   snapshot froze the pre-guard FAIL.
3. A fresh audit with current code yields **zero** Tier-1 FAILs (probe-confirmed):
   S2 SKIPs (run_id guard) and the unengaged adopt/deploy C1s are rewritten to
   SKIP by `_skip_unengaged_fails`.
4. The snapshots are gitignored, local-only, `GC_AGE_DAYS=90`, and no fresh
   *non-sentinel* audit has superseded them in the main tree (iterates audit
   inside worktrees). So the rollup **consumers** keep re-rendering the 14-day-old
   sentinel snapshot and re-driving autonomous remediation.

A `run_id="unknown"` snapshot only ever arises when the audit ran with **no
resolvable run/session context at all** (`resolve_run_id` returns
`session_id or "unknown"`; the sentinel needs an empty session AND no run-config
run_id AND no `run_started` event AND no loop vars). By the project's own canon
those checks are "not applicable in this audit context" — yet the rollup readers
ignore that.

## Goal

Phase-quality **rollups** (the read/surface layer) must exclude degenerate
sentinel-run (`run_id ∈ {"", "unknown"}`) snapshots, mirroring the audit-time
guards. This stops stale/degenerate audits from:
- driving the autonomous loop via the triage backlog (`collect_in_scope_fails`),
- emitting the SessionStart "open Tier-1 FAIL(s)" injection (via the digest),
- rendering false red rows on the dashboard / report.

Raw introspection (`load_findings`) and GC (`gc_old_findings`) stay unchanged —
the per-run JSONs remain on disk and enumerable; only the actionable VIEWS
exclude them.

## Approach

Single shared filter, applied at every `load_findings` rollup consumer:

1. `_constants.py`: add `RUN_ID_SENTINELS = frozenset({"", "unknown"})` +
   `is_sentinel_run(run_id)` (case-insensitive, stripped). Cross-reference the
   parallel `_iterate_run_id._RUN_ID_SENTINELS`.
2. `_aggregates.py`: add `LoadedFinding.is_sentinel` property + a
   `load_actionable_findings(project_root)` = `load_findings(...)` minus
   sentinel-run snapshots (same newest-first ordering).
3. Route the four rollup consumers through `load_actionable_findings`:
   - `_triage_bundle.collect_in_scope_fails` (autonomous-loop driver),
   - `_dashboard_render.rewrite_session_findings_summary` (digest → injection),
   - `_dashboard_render.write_quality_dashboard_file` (dashboard),
   - `_dashboard_render.rewrite_aggregated_report` (report).
4. Export the new symbols via `phase_quality/__init__.py`.

## Acceptance Criteria

- [ ] **AC-1.** `is_sentinel_run(r)` is True iff `str(r or "").strip().lower()`
      ∈ `{"", "unknown"}` — so `None` / missing / whitespace-only / `"UNKNOWN"`
      all count as sentinel; False for real run/session ids. (Belt-and-suspenders:
      `load_findings` already normalises a missing/`null` JSON `run_id` to
      `"unknown"`.) `LoadedFinding.is_sentinel` mirrors it.
- [ ] **AC-2.** `load_actionable_findings(project_root)` returns exactly
      `load_findings(project_root)` with sentinel-run snapshots removed; ordering
      (newest-first) and all other fields preserved.
- [ ] **AC-3.** `collect_in_scope_fails` drops Tier-1 FAILs from sentinel-run
      snapshots. With ONLY a sentinel snapshot carrying a FAIL → returns `[]`;
      a non-sentinel engaged FAIL still surfaces (engagement/Tier-2/error filters
      intact).
- [ ] **AC-4.** `rewrite_session_findings_summary`, `write_quality_dashboard_file`,
      and `rewrite_aggregated_report` omit sentinel-run snapshots; a phase whose
      ONLY snapshot is sentinel renders no row / no "open FAILs".
- [ ] **AC-5 (no over-suppression).** A non-sentinel snapshot for the same phase
      still surfaces its findings across all four consumers — real audits are
      unaffected.
- [ ] **AC-6 (raw + GC untouched).** `load_findings` still returns sentinel
      snapshots; `gc_old_findings` still archives them by mtime. Only the rollup
      views exclude them.
- [ ] **AC-7 (end-to-end).** With a sentinel-only FAIL on disk,
      `emit_phase_quality_backlog` opens 0 backlog items (dismiss/auto-resolve
      path); with a non-sentinel engaged FAIL it appends one.
- [ ] **AC-8 (regression).** Existing `test_audit_phase_quality` /
      `test_phase_quality_triage_emit` / `test_phase_quality_rollout` stay green
      (they use non-sentinel run_ids).
- [ ] **AC-9 (bloat).** Touched files stay within their bloat baseline (extract
      if needed; `_aggregates.py` is near its 300-LOC source budget).
- [ ] **AC-10 (docs).** `docs/hooks-and-pipeline.md` phase-quality section notes
      the rollup sentinel-exclusion (mirrors the dashboard-skip iterate's doc AC).

## Out of scope

- Changing the audit WRITE path (`audit_phase_quality_on_stop.py`) or whether a
  sentinel snapshot is written at all — a hook change (`cross_component`) and not
  needed; the read-layer filter fully addresses the surfacing harm.
- A staleness/time-window filter — the discriminating property here is the
  degenerate *run context* (sentinel), not age; real-run FAILs remain real and
  are superseded by the next real audit. Adding an age threshold would be
  arbitrary scope creep.
- Operationally deleting the existing gitignored sentinel snapshots — with this
  fix they become invisible to all rollups on the next regen; the per-run JSONs
  GC out at 90 days.

## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| audit Stop hook writes per-run finding JSON | `load_findings` → `load_actionable_findings` (NEW filter) → 4 rollups | `.shipwright/compliance/skill-compliance/<phase>-<run>-<sess>.json` |
| `load_actionable_findings` | triage backlog action-unit / SessionStart digest / dashboard / report | in-memory `LoadedFinding` list |

## Confidence Calibration

- **Boundaries touched:** reads per-run finding JSON (via `load_findings`);
  feeds the triage backlog (`.shipwright/triage.jsonl` outbox), the
  SessionStart-injection digest (`_findings.md`), and the dashboard/report
  caches. No new file formats; the filter is a pure list reduction.
- **Empirical probes run:**
  - Probe A (fresh-audit reality check) — ran the live repo's runners with
    current code + a resolvable session: `iterate` → **no FAIL** (S2 SKIPs via
    the run_id guard); `adopt`/`deploy` raw-C1 FAILs exist but `engaged=False`
    → rewritten to SKIP by `_skip_unengaged_fails`. Net **zero Tier-1 FAILs** —
    proving the surfaced finding is a stale artifact, not a live bug.
  - Probe B (before/after) — live `collect_in_scope_fails` on the repo's stale
    snapshots returned exactly `[iterate:S2]` (the autonomous trigger). With the
    fix, the sentinel snapshot is excluded → `[]` (unit:
    `test_collect_drops_sentinel_only_fail` + `test_emit_backlog_ignores_sentinel_only`),
    while a non-sentinel engaged FAIL still surfaces
    (`test_collect_keeps_non_sentinel_engaged_fail`).
  - Probe C (blast radius) — `ruff@0.15.15` clean on the touched tree;
    anti-ratchet `--staged` exit 0 (`_triage_bundle.py` held at its 308 baseline);
    phase-quality regression set 140 passed / 2 pre-existing skips; full
    `shared/tests/` suite green (F0).
- **Test Completeness Ledger:**
  | Behavior (AC) | Status | Evidence |
  |---|---|---|
  | `is_sentinel_run` truth table + `LoadedFinding.is_sentinel` (AC-1) | tested | `::test_is_sentinel_run_truth_table` (7 cases) + `::test_loaded_finding_is_sentinel_property` |
  | `load_actionable_findings` filters sentinel, preserves raw + order (AC-2/AC-6) | tested | `::test_load_actionable_filters_sentinel_preserves_raw` + `::test_load_actionable_preserves_newest_first_order` |
  | GC still archives sentinel by mtime (AC-6) | tested | `::test_gc_still_archives_sentinel_by_mtime` |
  | `collect_in_scope_fails` drops sentinel, keeps real, no-mask (AC-3/AC-5) | tested | `::test_collect_drops_sentinel_only_fail` + `::test_collect_keeps_non_sentinel_engaged_fail` + `::test_collect_sentinel_does_not_mask_older_real_fail` |
  | backlog emit ignores sentinel-only, appends for real (AC-7) | tested | `::test_emit_backlog_ignores_sentinel_only` + `::test_emit_backlog_appends_for_non_sentinel` |
  | dashboard/digest/report omit sentinel (AC-4) | tested | `::test_dashboard_omits_sentinel_only_phase` + `::test_session_summary_omits_sentinel_fail` + `::test_report_omits_sentinel_run` |
  | existing renderer/triage suites stay green (AC-8) | tested | `test_audit_phase_quality` + `test_phase_quality_triage_emit` + `test_phase_quality_rollout` (140 passed) |
  | bloat baseline respected (AC-9) | tested | anti-ratchet `--staged` exit 0 |
  | docs note (AC-10) | untestable (`covered-by-existing-test`) | doc prose in `docs/hooks-and-pipeline.md`; behavior covered above |
  - **0 untested-testable behaviors.**
- **Confidence-pattern check:** asymptote — exercised empty / sentinel-only /
  mixed / non-sentinel / sentinel-masking-older-real sets, plus the raw-vs-view
  split and GC, not just the happy path. Coverage — per-consumer unit tests + an
  end-to-end backlog test + full-suite regression. Composition — verified the
  changed files do NOT match `CROSS_COMPONENT_FILE_PATTERNS` (no `**/hooks/*.py`,
  no merge/churn machinery), so `cross_component` does not fire and no mandatory
  `category:"integration"` ledger row is required; an end-to-end backlog test is
  added regardless. Residual: the existing gitignored stale sentinel snapshots in
  the main tree become invisible to all rollups on the next regen (verified by
  the unit tests); they GC out at 90d — no manual deletion needed.
