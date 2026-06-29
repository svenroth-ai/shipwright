# Iterate Spec — Compliance producers: exempt ≠ deficit

- **Run ID:** iterate-2026-06-29-compliance-exempt-not-deficit
- **Intent:** CHANGE (framework-internal compliance tooling)
- **Complexity:** medium
- **Spec Impact:** NONE (no consuming-project FR governs compliance dashboard/audit rendering; `change_type=compliance`)
- **Risk flags:** none (recomputed from diff at F11)

## Problem

Compliance **producers** flag legitimately-exempt items as deficits → inflated WARNs /
alarm-fatigue. Same root flaw the BP-1 traceability-credit already fixed for the
"traced to an FR" metric: a denominator that includes items that were never a deficit.
Surfaced on the shipwright-webui A99 dashboard; the **logic is monorepo** (compliance
plugin collectors), so fixing it here fixes both repos once the compliance plugin is
re-run against each.

## Findings & fixes

### F1 — Bloat over-limit grandfathered count rendered as WARN
- **Symptom:** `| Bloat over-limit | 127 | WARN | 127 file(s) past limit AND not
  ADR-justified |` (monorepo) / `| 80 | WARN |` (webui). The count is just the
  grandfathered set — `measured > limit(300)` for `state != exception`. Grandfathering
  IS the acceptance; the baseline only holds `grandfathered`/`exception` entries, so a
  genuinely *new* crossing is never even in this count (Group H detective owns those).
- **Fix:** downgrade the over-limit row to **INFO** (label it `(grandfathered)`, empty
  Why-warn cell). Keep the **ratchet-delta** row as the WARN — it is the real signal
  (regression past the accepted ceiling). Producer math (`collect_bloat_summary`) is
  **unchanged**; only the render badge/label changes.
- **File:** `plugins/shipwright-compliance/scripts/lib/_bloat_dashboard_rows.py`
  (both `bloat_rows_events_mode` + `bloat_rows_legacy_mode`).
- Control-Grade maintainability dimension already keys off `ratchet_delta` — no change.

### F2 — "Iterate tests passing" counts test-exempt changes
- **Symptom:** `| Iterate tests passing | 142/225 | WARN | 83 iterate(s) without tests |`
  (monorepo) / `90/179 | WARN | 89 |` (webui). The denominator is every
  `source=="iterate"` event, including behavior-preserving no-FR changes
  (docs/tooling/compliance/infra + `none_reason`) that are **legitimately test-free**.
  (Synthetic `backfill*/​*-retro/​*-merge-retro` sources are already excluded by the
  exact `source=="iterate"` filter.)
- **Fix:** mirror the BP-1 traced-credit — exclude **satisfied-no-FR** changes
  (`fr_classification.is_satisfied_no_fr`) from BOTH numerator and denominator. The
  residual (FR-linked / behavior-affecting work with no recorded tests) stays a WARN —
  that is honest signal, not alarm-fatigue. New SSOT helper co-located with
  `_is_traced` so "traced" and "testable" can't drift.
- **Files:** `plugins/shipwright-compliance/scripts/lib/_traceability.py` (new
  `iterate_test_coverage`), `plugins/shipwright-compliance/scripts/lib/compliance_report.py`
  (consume it).
- Empirical reclassification: monorepo 83→16 flagged (67 exempt); webui 89→46 flagged
  (43 exempt). `test-evidence.md` has no "without tests" metric — no change there.

### F3 — Audit "Suggested:" remediation on PASSING/SKIPPED checks
- **Symptom:** ✅C2/C3/C4 and ⏭C1/A5.6/D1/D4/G2 all emit a `_Suggested:_
  /shipwright-iterate … reconcile` line → false action on a non-problem. SKILL.md §3
  already documents the intent: "for each **failing** finding".
- **Fix:** gate the suggestion line on `f.status == "fail"` in the markdown render
  (single chokepoint). JSON payload keeps the field + `status` so programmatic
  consumers can still gate themselves.
- **File:** `plugins/shipwright-compliance/scripts/audit/audit_report.py`
  (`_render_findings_block`).

### F4 — audit-report.md not refreshed by routine regen → silently stale
- **Symptom:** `update_compliance --phase iterate` (the finalize path) regenerates
  rtm/test-evidence/change-history/sbom/dashboard but NOT audit-report.md (only
  `/shipwright-compliance` → `run_audit.py` writes it). On disk it can show
  month-old findings (possibly already resolved).
- **Fix:** **staleness marker** (not full refresh — the detective audit is heavy and
  can fail mid-iterate). New stdlib-only helper stamps an idempotent, HTML-comment-
  delimited banner into the (gitignored) audit-report.md during routine regens
  (`phase != "compliance"`, dashboard regenerated, file present). `run_audit.py` fully
  overwrites the file, so a fresh audit naturally clears the banner.
- **Files:** new `plugins/shipwright-compliance/scripts/lib/audit_freshness.py`,
  `plugins/shipwright-compliance/scripts/tools/update_compliance.py` (call it).

### Clean (no change): SBOM (AR-04), RTM (age-neutral + Reconciled), change-history.

## Test plan (TDD)
- `test_collectors_dashboard.py` — update over-limit render asserts WARN/PASS→INFO;
  add ratchet-delta-still-WARN assertion (Test-Update-Klausel: rendering rule changed).
- `test_traceability.py` — new `TestIterateTestCoverage`: exempt excluded, FR-linked
  /behavior-affecting without tests still counted, empty input.
- `test_compliance_report.py` — iterate-tests row excludes exempt; residual WARN.
- `test_audit_report.py` — pass/skip findings emit NO Suggested line; fail still does.
- new `test_audit_freshness.py` — stamps when stale, idempotent replace, noop when
  absent, run_audit overwrite clears it.

## Confidence Calibration
- **Boundaries touched:** compliance dashboard.md render (Quality-Indicators
  rows), audit-report.md markdown render + file I/O (staleness banner),
  `update_compliance.py` JSON output. No FR/spec/runtime-prompt boundary; no
  hook/migration/auth. Risk flags recomputed at F11 from the diff.
- **Empirical probes run (end-to-end, both repos, fixed plugin):**
  - Monorepo audit: Suggested lines 1, FAIL findings 1 (gated correctly; was ~9
    on passing C1–C4/A5.6/D1/D4/G2).
  - Monorepo dashboard: `Bloat over-limit (grandfathered) | 127 | INFO` (was
    WARN); `Iterate tests passing | 35/40 testable changes tested | WARN`
    (was `142/225 | 83 without tests`); 185 exempt, 5 residual all
    behavior-affecting + FR-linked (honest).
  - Webui audit: Suggested 4 = FAIL 4. Webui dashboard:
    `Bloat over-limit (grandfathered) | 80 | INFO`, ratchet `-541 | PASS`;
    `Iterate tests passing | 70/112 testable | WARN | 42` (was `90/179 | 89`).
  - Staleness banner stamped on both (`--phase iterate`); skipped on
    `--phase compliance`; cleared by a fresh `run_audit` overwrite. Banner is
    keyed only to the audit's own `Generated:` ts → byte-stable: a repeat regen
    on the tracked webui report is a verified no-op (`stamped:False, unchanged`),
    so it never churns a tracked file (code-review MEDIUM, fixed + re-verified).
- **Test Completeness Ledger:**
  | Behavior | Disposition | Evidence |
  |---|---|---|
  | Bloat over-limit renders INFO not WARN (events + legacy) | tested | test_collectors_dashboard.py (3 render asserts updated) |
  | Ratchet delta stays the WARN-bearing signal | tested | test_collectors_dashboard.py::test_legacy_mode_over_limit_is_info_not_warn |
  | `iterate_test_coverage` excludes satisfied-no-FR; keeps FR-linked/behavior-affecting | tested | test_traceability.py::TestIterateTestCoverage (8 cases) |
  | Dashboard iterate-tests row uses testable denominator + wording | tested | test_dashboard_iterate_row.py (2 cases) |
  | Audit `_Suggested:_` only on status==fail | tested | test_audit_report.py::test_suggested_cmd_only_renders_for_failures |
  | Staleness marker: stamp / idempotent-churn-free / noop-absent / overwrite-clears | tested | test_audit_freshness.py (4 cases) |
  | update_compliance wires marker: stamps on iterate, skips on compliance | tested | test_update_compliance_phases.py (2 cases) |
  | End-to-end render against real monorepo + webui data | tested (manual probe) | logged above; not a unit test (requires the two repos' live event logs) |
  - 0 testable-but-untested behaviors.
- **Confidence-pattern check:** depth — the SSOT (`is_satisfied_no_fr`) is shared
  with `count_traced` so "traced" and "testable" can't drift; render badge/label
  asserted at both unit and dashboard level. Breadth — all four producers covered
  (dashboard rows ×2, audit suggestion, staleness) plus the CLI wiring. No
  `cross_component` machinery touched (no integration-composition behavior
  required). 868/868 compliance tests green.
