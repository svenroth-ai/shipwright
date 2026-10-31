# Mini-plan: P1 affected_acs on every work_completed event

Goal (WHAT): an iterate that changes runtime code says, per acceptance criterion, whether it changed, implemented or checked-and-left-unchanged it (one line why), or states a catalog gap with the nearest FR.
Reason (WHY): a rebuild of the application from the catalog must not lose promises; 11 of 17 behaviour-adding PRs left no AC behind.

Changes:
1. `shared/scripts/lib/affected_acs_gate.py`: pure rule - runtime path classification (plugins/**, shared/** minus tests and docs), presence-only declaration test, requires_declaration (feature/change/bug + runtime path).
2. `shared/scripts/tools/verifiers/affected_acs_check.py`: F11 claim check `check_affected_acs_declared`, registered in the claims registry (iterate_checks.py is at its cap). Fails only on absence; never reads content. SKIPs when blind.
3. `shared/scripts/tools/affected_acs_replay.py`: read-only replay over the last N recorded iterate events.
4. Docs: F5b.md (field shape + example extras), hooks-and-pipeline.md claim-checks table.
5. Tests: shared/tests/test_affected_acs_gate.py.

Not changed: the F5b write path (no new write-time gate), no event schema file exists (extras merge freely).
