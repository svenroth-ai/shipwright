---
canon_generated: true
run_id: "iterate-2026-06-27-codeql-security-hardening"
phase: "iterate"
reason: "CodeQL security hardening complete; ready for PR."
timestamp: "2026-06-27T21:10:50.533812+00:00"
---

# Session Handoff

> Auto-generated 2026-06-27 21:10:50 UTC

## Session Info

- **Session ID**: 12c9c16a-2f03-47d2-9d1b-612113aa9379
- **Timestamp**: 2026-06-27 21:10:50 UTC
- **Reason**: CodeQL security hardening complete; ready for PR.

## Last Iterate

- **Run ID**: iterate-2026-06-22-trivyignore-policy-check
- **Date**: 2026-06-22T21:47:52.146404Z
- **Type**: change
- **Complexity**: small
- **Branch**: iterate/trivyignore-policy-check
- **ADR**: iterate-2026-06-22-trivyignore-policy-check
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/codeql-security-hardening
- **Spec**: .shipwright/planning/iterate/2026-06-27-codeql-security-hardening.md
- **Complexity**: medium
- **External Review Marker**: missing

### Mandatory replay on Resume

Before dispatching to the handoff's Remaining phase, run these if missing:
- Step 4 — External LLM Review (marker missing/stale)
- Finalization (F0–F11) after all mandatory phases pass

## Legacy build state

- **Phase**: design
- **Current Split**: 01-adopted
- **Current Section**: adopted-baseline

- **Splits**: 0/1 complete
- **Sections**: 0/1 complete

## Git State

- **Branch**: iterate/codeql-security-hardening
- **Last Commit**: 4cfb9d2d docs(images): update command-center board screenshot (#275)
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
| evt-cda28075 | work_completed | iterate (Add shared/tests/test_trivyignore_register.py enforcing that every .trivyignore.yaml accepted-risk entry is scoped (paths|purls) + time-bounded (expired_at) + justified (statement); register optional (absent passes). Self-tested (rejects sloppy, accepts well-formed).) | 2026-06-22 |
| evt-76c38e29 | work_completed | iterate (Add _resolve_trivy_ignorefile + wire --ignorefile <target>/.trivyignore.yaml into _run_trivy (oss_backend.py) so Trivy SCA findings can be accepted via a scoped, time-bounded repo-root register; add .trivyignore.yaml accepting CVE-2026-54285 (perf package-lock, expired_at 2026-12-22) + 4 unit tests.) | 2026-06-22 |
| evt-670808ea | work_completed | iterate (Bump cryptography 48.0.0->49.0.0 (shipwright-plan/uv.lock) and ws 8.20.1->8.21.0 + 7.5.10->7.5.11 (shipwright-test/scripts/perf/package-lock.json) to clear 3 HIGH dependency CVEs from the 2026-06-22 scheduled security scan.) | 2026-06-22 |
| evt-6b111a3b | work_completed | iterate (Add a once-per-(Stop,session) claim_once_for_event guard to aggregate_triage_on_stop so one stop regenerates triage_inbox.md once instead of once-per-plugin; a failed winner releases the claim so a sibling retries.) | 2026-06-20 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 210
- **Last iterate**: change — CodeQL security hardening: tailor the query suite via codeql-config.yml; root-fix genuine findings (file modes to 0o600, two ReDoS regexes, a loop-capture bug, a rollback-CLI else-guard); remove 13 dead module globals. (2026-06-27)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
