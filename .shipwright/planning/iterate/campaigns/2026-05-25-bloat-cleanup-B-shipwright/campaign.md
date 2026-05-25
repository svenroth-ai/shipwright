---
campaign: 2026-05-25-bloat-cleanup-B-shipwright
branch_strategy: stacked
created: 2026-05-25T20:21:15.422913+00:00
---

# Campaign: 2026-05-25-bloat-cleanup-B-shipwright

## Intent

Cleanup of the God-Module + SKILL.md inventory in the Shipwright monorepo (Track B of the cross-repo bloat cleanup plan). Splits 7 SKILL.md files and 6 large Python modules (data_collector, github_triage, phase_quality, dev_server, orchestrator, contracts) into Kern + references and package + collectors patterns. Each split commit MUST also update shipwright_bloat_baseline.json per the cleanup-invariant. Phase-D acceptance: zero state=grandfathered entries for Shipwright code.

## Sub-Iterates

| ID | Slug | Title | Status |
|---|---|---|---|
| B1.iterate | iterate-skill | Split iterate SKILL.md (1709 LOC) | pending |
| B1.build | build-skill | Split build SKILL.md (1162 LOC) | pending |
| B1.test | test-skill | Split test SKILL.md (986 LOC) | pending |
| B1.adopt | adopt-skill | Split adopt SKILL.md (848 LOC) | pending |
| B1.design | design-skill | Split design SKILL.md (695 LOC) | pending |
| B1.project | project-skill | Split project SKILL.md (612 LOC) | pending |
| B1.plan | plan-skill | Split plan SKILL.md (581 LOC) | pending |
| B8 | contracts | shared/contracts/{compliance,iterate}.py + adopt-bridge + test-boundary refactor | pending |
| B2 | data-collector | Split data_collector.py (1559 LOC) into collectors/ | pending |
| B6 | github-triage | Split github_triage.py (929 LOC) into producer/consumer/state | pending |
| B3 | phase-quality | Split phase_quality.py (1108 LOC) + add Compliance Dashboard bloat column | pending |
| B4 | dev-server | Split dev_server.py (997 LOC) into spawn/health/multiservice | pending |
| B5 | orchestrator | Split orchestrator.py (983 LOC) into phases/ + router | pending |
