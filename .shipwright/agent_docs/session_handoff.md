---
canon_generated: true
run_id: "iterate-2026-06-28-codeql-fixture-noise"
phase: "iterate"
reason: "iterate: CodeQL fixture-noise cleanup"
timestamp: "2026-06-28T06:17:09.227517+00:00"
---

# Session Handoff

> Auto-generated 2026-06-28 06:17:09 UTC

## Session Info

- **Session ID**: a9af39f8-f3c8-445b-a07a-86412ffe4704
- **Timestamp**: 2026-06-28 06:17:09 UTC
- **Reason**: iterate: CodeQL fixture-noise cleanup

## Last Iterate

- **Run ID**: iterate-2026-06-28-security-scan-hook-failopen
- **Date**: 2026-06-27T22:43:35.568860Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/2026-06-28-security-scan-hook-failopen
- **ADR**: iterate-2026-06-28-security-scan-hook-failopen
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-06-28-security-scan-hook-failopen.md

## Current Iterate Progress

- **Branch**: iterate/codeql-fixture-noise
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

- **Branch**: iterate/codeql-fixture-noise
- **Last Commit**: 01059128 fix(compliance): fail-open + robust invocation for PreToolUse Bash gates (#278)
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
| evt-5d34869b | work_completed | iterate (CodeQL fixture-noise cleanup: paths-ignore test fixtures + explicit string-concat refactor) | 2026-06-28 |
| evt-d50b793d | work_completed | iterate (compliance PreToolUse Bash gates: robust uv run --no-project invocation + fail-open guard) | 2026-06-27 |
| evt-e5afeb65 | work_completed | iterate (CodeQL security hardening: tailor the query suite via codeql-config.yml; root-fix genuine findings (file modes to 0o600, two ReDoS regexes, a loop-capture bug, a rollback-CLI else-guard); remove 13 dead module globals.) | 2026-06-27 |
| evt-2dbacb5b | work_completed | iterate (Control Grade scorer (lib/control_grade.py, in Anlehnung an OpenSSF Scorecard) + Control Verdict block atop the dashboard (AR-01); latest-full-suite resolver kills the 0/0 headline in dashboard + test-evidence (AR-02); inline consistency-audit summary replaces the dead gitignored audit-report.md link (AR-03).) | 2026-06-27 |
| evt-cda28075 | work_completed | iterate (Add shared/tests/test_trivyignore_register.py enforcing that every .trivyignore.yaml accepted-risk entry is scoped (paths|purls) + time-bounded (expired_at) + justified (statement); register optional (absent passes). Self-tested (rejects sloppy, accepts well-formed).) | 2026-06-22 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 213
- **Last iterate**: change — CodeQL fixture-noise cleanup: paths-ignore test fixtures + explicit string-concat refactor (2026-06-28)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
