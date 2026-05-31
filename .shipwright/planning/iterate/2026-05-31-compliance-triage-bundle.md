# Iterate Spec — compliance triage → one rolling backlog action-unit

- **run_id:** `iterate-2026-05-31-compliance-triage-bundle`
- **Type:** change (MODIFY producer emission shape)
- **Complexity:** medium (`touches_io_boundary`: writes `triage.jsonl`; changes a
  contract consumed by the WebUI inbox + RTM; rewrites the producer test)
- **Base:** `main` (independent of #126/#128 — touches a different file,
  `plugins/shipwright-compliance/scripts/audit/audit_detector.py`)
- **Triggering principle:** [[project_triage_launch_surface_redesign]] /
  [[project_phasequality_triage_bundle]] — producers emit action-units, not
  finding-mirrors. This is the operator-approved follow-up that applies the
  phaseQuality treatment to the **second** producer.

## Problem

`audit_detector.mirror_findings_to_triage` emits **one `source=compliance`
triage item per failing Group A-G check** (`dedup_key=check_id`). On the
adopted framework monorepo a full audit produced **11 items** (A5.6, B7, D1,
D5, E1-E5, E?, G2, G3) — the same finding-mirror flood the phaseQuality
producer had. The operator dismissed them manually, but they re-fire on the
next audit because the producer is unchanged.

## Goal

Collapse the per-check mirror into **one rolling `compliance:backlog:<sig>`
action-unit** (mirroring `phaseQuality:backlog`), auto-dismissed when no checks
fail, with a one-shot migration that retires the legacy per-check items.

## Acceptance Criteria

- [ ] **AC-1 (single rolling item).** When ≥1 Group A-G finding has
      `status="fail"`, `mirror_findings_to_triage` emits **exactly one**
      `source="compliance"` item, `dedup_key="compliance:backlog:<sig>"`
      (`sig` = sha256[:12] of the sorted `group/check_id` set). Body lists each
      `group/check_id: name` (+ detail/hint); `launch_payload` = `/shipwright-compliance`
      + context. Severity = the highest among the bundled findings.
- [ ] **AC-2 (idempotent + refresh).** Re-running with the same failing set →
      no new item (open same-sig suppresses, `match_commit=False`,
      `window=None`). When the failing set changes → dismiss open
      `compliance:backlog:*` whose sig ≠ current (`reason="complianceRefreshed"`)
      + append the fresh one.
- [ ] **AC-3 (auto-dismiss on resolve).** When **no** finding fails, every open
      `compliance:backlog:*` item is dismissed (`reason="complianceResolved"`).
      Preserves the existing "auto-dismiss when cleared" guarantee, now for the
      single bundle.
- [ ] **AC-4 (one-shot legacy migration).** On emit, any currently-`triage`
      `source="compliance"` item whose `dedupKey` does NOT start with
      `compliance:backlog:` is dismissed (`reason="supersededByBacklog"`) — a
      per-source-gated, one-shot retirement of the old per-check shape (mirrors
      the github/sbom `schemaMigration` pattern). Items already
      promoted/dismissed stay terminal.
- [ ] **AC-5 (full-coverage safety preserved).** The producer is still only
      *called* by `audit_compliance_on_stop` after a verified full A-G run, so
      a partial/crashed audit never wrongly dismisses (unchanged caller gate).
- [ ] **AC-6 (LOC / no ratchet).** Bundle logic lands in a new module
      `plugins/shipwright-compliance/scripts/audit/triage_bundle.py` (≤300 LOC);
      `audit_detector.py` (grandfathered 422) **shrinks** by delegating — net
      de-ratchet, never a ratchet.
- [ ] **AC-7 (best-effort).** Per-item errors swallowed; returns
      `{"appended", "dismissed"}` (back-compat telemetry shape, plus optional
      `migrated`/`open_fails`).
- [ ] **AC-8 (consumer compat).** `source` stays `compliance`, `kind` stays
      `compliance`; only dedup-key shape + count change. No RTM/detector keys on
      the per-check dedup shape (verify by grep).
- [ ] **AC-9 (docs).** `docs/hooks-and-pipeline.md` compliance-producer rows
      updated to the backlog action-unit shape.

## Explicitly OUT of scope (low-risk boundary)

- **Per-check applicability gate** (making D1/D5/B7 SKIP-when-not-applicable on
  framework/adopted repos). Unlike phaseQuality's clean phase-engagement
  signal, "does this A-G check apply to this repo type" is fuzzy and risks
  hiding real findings. The **bundle alone guarantees ≤1 inbox row**; the
  existing E-group self-heal + auto-dismiss already clears transient staleness.
  A per-check applicability pass is a separate, carefully-designed iterate.
- **Shared bundle helper** for both producers. Two callers ≠ three — keep the
  compliance bundle local (Simplicity First); extract a shared helper only when
  a third producer arrives.
- The 11→1 Stop-hook consolidation (separate architecture iterate).

## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| `mirror_findings_to_triage` → one `compliance:backlog:<sig>` | WebUI inbox + RTM | `.shipwright/triage.jsonl` |

## Confidence Calibration

- **Boundaries touched:** writes `triage.jsonl` (append/status); reads the
  in-memory `AuditReport`.
- **Empirical probes run:**
  - Reproduction probe: the exact 11 flooding findings → `mirror_findings_to_triage`
    → **1** `compliance:backlog` item (severity=high = max). Then empty report
    → auto-dismissed → **0** open. (was 11.)
  - Caller integration: `test_audit_compliance_on_stop` (28) green — the
    full-coverage Stop path drives the new bundle correctly.
  - LOC: `audit_detector.py` 422→**362** (de-ratchet, AC-6); new
    `triage_bundle.py` = 176.
- **Test Completeness Ledger:**
  | Behavior | Status | Evidence |
  |---|---|---|
  | many fails → 1 backlog item, max severity, body lists keys, launch payload (AC-1) | tested | test_compliance_audit_triage_emit::test_many_fails_one_backlog_item + ::test_severity_is_max_of_bundle |
  | pass/skip not emitted | tested | ::test_pass_skip_not_emitted |
  | idempotent across commits + refresh on changed set (AC-2) | tested | ::test_idempotent_across_commits + ::test_refresh_on_changed_set |
  | auto-dismiss when resolved (AC-3) | tested | ::test_auto_dismiss_when_all_resolved + ::test_empty_report_no_op |
  | one-shot legacy per-check retirement (AC-4) | tested | ::test_legacy_per_check_items_retired |
  | promoted/other-source items untouched | tested | ::test_promoted_backlog_stays_terminal + ::test_other_source_items_not_touched |
  | full-coverage caller gate preserved (AC-5) | tested | test_audit_compliance_on_stop.py (28 cases) |
  | end-to-end 11→1→0 on the real flooding set | tested | reproduction probe above |
  | docs (AC-9) | untestable (`covered-by-existing-test`) | doc prose |
  - **0 untested-testable behaviors.**
- **Confidence-pattern check:** asymptote — exercised refresh-on-change, the
  legacy-retirement one-shot, terminal-status preservation, and the resolve→0
  path, not just the happy bundle. Coverage — producer unit tests + caller
  integration + full-suite regression + real-flood reproduction. Residual: the
  per-check *applicability* gate (D1/D5/B7 noise-by-context) is explicitly
  out of scope; the bundle guarantees ≤1 row regardless.
