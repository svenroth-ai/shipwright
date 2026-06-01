---
canon_generated: true
run_id: "iterate-2026-06-01-refresh-claudemd-lint-gate"
phase: "iterate"
reason: "Trivial doc refresh: documented CI ruff lint gate in CLAUDE.md"
timestamp: "2026-06-01T06:07:15.577426+00:00"
---

# Session Handoff

> Auto-generated 2026-06-01 06:07:15 UTC

## Session Info

- **Session ID**: f5abacda-c0df-452c-a647-ee215ae3f97b
- **Timestamp**: 2026-06-01 06:07:15 UTC
- **Reason**: Trivial doc refresh: documented CI ruff lint gate in CLAUDE.md

## Last Iterate

- **Run ID**: iterate-2026-06-01-refresh-claudemd-lint-gate
- **Date**: 2026-06-01T06:06:53.293418Z
- **Type**: change
- **Complexity**: trivial
- **Branch**: iterate/refresh-claudemd-lint-gate
- **ADR**: iterate-2026-06-01-refresh-claudemd-lint-gate_001
- **Tests passed**: True
- **Spec**: none (trivial doc refresh)

## Current Iterate Progress

- **Branch**: iterate/refresh-claudemd-lint-gate
- **External Review Marker**: completed (external_review_state.json @ 2026-05-31T15:51:40)

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

- **Branch**: iterate/refresh-claudemd-lint-gate
- **Last Commit**: 4292ab05 Merge pull request #131 from svenroth-ai/fix/prompt-scan-diff-skip
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
| evt-f762bc17 | work_completed | iterate (Document the gating ruff CI lint step in CLAUDE.md Development section.) | 2026-06-01 |
| evt-ea7f2302 | work_completed | iterate (plugin-sync Stop-hook triage item written to durable main-repo log (worktree-aware)) | 2026-06-01 |
| evt-1da91106 | work_completed | iterate (CI gate-coverage guard + workflow hardening (test-dir coverage, loose-gate allowlist, security fail-closed)) | 2026-05-31 |
| evt-4cb02049 | work_completed | iterate (Gate CI Python lint on a curated bug-focused ruff ruleset (pyflakes F + high-signal E/W); remove the || true + continue-on-error neutering; provision ruff via pinned uvx; rename job to Python (lint + test).) | 2026-05-31 |
| evt-0b680aca | work_completed | iterate (Wire shared/ test suites (shared/tests, shared/scripts/tests, shared/scripts/tools/tests) into ci.yml as blocking per-dir invocations; fix 2 non-hermetic validate_env tests via a dir conftest; make the born-red arch-md sibling skip when gitignored decision-drops are absent.) | 2026-05-31 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 86
- **Last iterate**: change — Document the gating ruff CI lint step in CLAUDE.md Development section. (2026-06-01)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-088: shared/contracts/* — cross-plugin contract surface introduced for compliance + iterate
- **Date:** 2026-05-26
- **Section:** Iterate B8 (Campaign B bloat cleanup) — change: introduce contract package
- **Run-ID:** sub_iterate-20260525-211635-B8
- **Context:** Two callsites used to reach across plugin boundaries via fragile mechanisms: plugins/shipwright-adopt/scripts/lib/compliance_bridge.py spawned update_compliance.py as a subprocess + walked ancestor directories; plugins/shipwright-test/
