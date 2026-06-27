---
canon_generated: true
run_id: "iterate-2026-06-27-compliance-control-grade"
phase: "iterate"
reason: "ensure-current pre-merge refresh"
timestamp: "2026-06-27T21:14:40.530729+00:00"
---

# Session Handoff

> Auto-generated 2026-06-27 21:14:40 UTC

## Session Info

- **Session ID**: 61dd0280-20fb-4933-93d7-7ea41e1a40f6
- **Timestamp**: 2026-06-27 21:14:40 UTC
- **Reason**: ensure-current pre-merge refresh

## Last Iterate

- **Run ID**: iterate-2026-06-27-compliance-control-grade
- **Date**: 2026-06-27T21:15:06.788108Z
- **Type**: feature
- **Complexity**: medium
- **Branch**: iterate/compliance-control-grade
- **ADR**: iterate-2026-06-27-compliance-control-grade
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-06-27-compliance-control-grade.md

## Current Iterate Progress

- **Branch**: iterate/compliance-control-grade
- **Spec**: .shipwright/planning/iterate/2026-06-27-compliance-control-grade.md
- **External Review Marker**: missing

### Mandatory replay on Resume

Before dispatching to the handoff's Remaining phase, run these if missing:
- Finalization (F0–F11) after all mandatory phases pass

## Legacy build state

- **Phase**: design
- **Current Split**: 01-adopted
- **Current Section**: adopted-baseline

- **Splits**: 0/1 complete
- **Sections**: 0/1 complete

## Git State

- **Branch**: iterate/compliance-control-grade
- **Last Commit**: 2462726d Merge remote-tracking branch 'origin/main' into iterate/compliance-control-grade
- **Uncommitted Changes**: Yes

## Config Files to Read

- `shipwright_run_config.json` — exists
- `shipwright_project_config.json` — exists
- `shipwright_plan_config.json` — exists
- `shipwright_build_config.json` — exists
- `shipwright_security_config.json` — exists
- `shipwright_compliance_config.json` — exists

## Last Events

| Event | Type | Source | Date |
|-------|------|--------|------|
| evt-e5afeb65 | work_completed | iterate (CodeQL security hardening: tailor the query suite via codeql-config.yml; root-fix genuine findings (file modes to 0o600, two ReDoS regexes, a loop-capture bug, a rollback-CLI else-guard); remove 13 dead module globals.) | 2026-06-27 |
| evt-2dbacb5b | work_completed | iterate (Control Grade scorer (lib/control_grade.py, in Anlehnung an OpenSSF Scorecard) + Control Verdict block atop the dashboard (AR-01); latest-full-suite resolver kills the 0/0 headline in dashboard + test-evidence (AR-02); inline consistency-audit summary replaces the dead gitignored audit-report.md link (AR-03).) | 2026-06-27 |
| evt-cda28075 | work_completed | iterate (Add shared/tests/test_trivyignore_register.py enforcing that every .trivyignore.yaml accepted-risk entry is scoped (paths|purls) + time-bounded (expired_at) + justified (statement); register optional (absent passes). Self-tested (rejects sloppy, accepts well-formed).) | 2026-06-22 |
| evt-76c38e29 | work_completed | iterate (Add _resolve_trivy_ignorefile + wire --ignorefile <target>/.trivyignore.yaml into _run_trivy (oss_backend.py) so Trivy SCA findings can be accepted via a scoped, time-bounded repo-root register; add .trivyignore.yaml accepting CVE-2026-54285 (perf package-lock, expired_at 2026-12-22) + 4 unit tests.) | 2026-06-22 |
| evt-670808ea | work_completed | iterate (Bump cryptography 48.0.0->49.0.0 (shipwright-plan/uv.lock) and ws 8.20.1->8.21.0 + 7.5.10->7.5.11 (shipwright-test/scripts/perf/package-lock.json) to clear 3 HIGH dependency CVEs from the 2026-06-22 scheduled security scan.) | 2026-06-22 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 211
- **Last iterate**: change — CodeQL security hardening: tailor the query suite via codeql-config.yml; root-fix genuine findings (file modes to 0o600, two ReDoS regexes, a loop-capture bug, a rollback-CLI else-guard); remove 13 dead module globals. (2026-06-27)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
