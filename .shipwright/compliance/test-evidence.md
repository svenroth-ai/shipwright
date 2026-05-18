# Test Evidence Report

Generated: 2026-05-18T19:48:16Z

## Summary

| Metric | Value |
|--------|-------|
| Total test checkpoints | 34 |
| Total unit tests (latest) | 3507/3507 |
| New tests from iterations | +19 |

## Test Progression

| # | Event | Source | New Tests | Suite Total | Result | Date |
|---|-------|--------|-----------|-------------|--------|------|
| 1 | fix 17 launch-blocker test failures (Windows python3 stub + 6 smaller groups) | iterate | +0 | 3507/3507 | PASS | 2026-05-18 |
| 2 | triage detector dedup + auto-resolve (rebased onto #31) | iterate | +0 | 1776/1783 | FAIL | 2026-05-16 |
| 3 | spec-impact classification gate: enforce ADD/MODIFY/REMOVE/NONE on every feature/change iterate (F7 record_event + F11 verifier gates, Group D5 audit, Removed Requirements convention) | iterate | +0 | 140/140 | PASS | 2026-05-16 |
| 4 | triage detector dedup + auto-resolve | iterate | +0 | 1776/1783 | FAIL | 2026-05-16 |
| 5 | fix adopt external-review config defaults | iterate | +0 | 304/304 | PASS | 2026-05-16 |
| 6 | events.jsonl worktree-awareness: F7/verifier/dashboard resolve the log via git-common-dir; leak-guard exempts it; dashboard embeds run_id | iterate | +0 | 2519/2526 | FAIL | 2026-05-16 |
| 7 | RTM data collection: parse 6-column adopt FR tables + resolve shipwright_events.jsonl via git-common-dir for worktree finalization; fixes false 'Traceability coverage 0%' on adopted projects | iterate | +0 | 312/312 | PASS | 2026-05-15 |
| 8 | Triage Inbox Iterate 2: 4 additional producers (security + performance + F0.5 + drift) wired into append_triage_item_idempotent. CI producer DEFERRED. ADR-047. | iterate | +0 | 40/40 | PASS | 2026-05-14 |
| 9 | Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI (rebased onto post-test-hygiene main; ADR renumbered 045→046) | iterate | +0 | 1642/1649 | FAIL | 2026-05-11 |
| 10 | Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI | iterate | +0 | 1642/1649 | FAIL | 2026-05-11 |
| 11 | known_issues scanner requires comment context; remove dead save_session_config — 16/16 green | iterate | +0 | 16/16 | PASS | 2026-05-09 |
| 12 | evt-f66286bf | iterate | +0 | — | — | 2026-05-07 |
| 13 | evt-623a29ad | iterate | +0 | — | — | 2026-05-07 |
| 14 | F0.5 empirical-test backfill | iterate | +0 | 1575/1575 | PASS | 2026-05-06 |
| 15 | F0.5 End-to-End Verification Gate | iterate | +0 | 1548/1548 | PASS | 2026-05-06 |
| 16 | hooks-consistency parser handles quoted commands — 27/27 green | iterate | +0 | 1297/1297 | PASS | 2026-05-06 |
| 17 | post-migration canon cleanup — 9 tests green | iterate | +0 | 1270/1270 | PASS | 2026-05-06 |
| 18 | loader deep-merges per-project shipwright_iterate_config.json + cascade helper | iterate | +0 | 34/34 | PASS | 2026-05-05 |
| 19 | verifier accepts drop-dir entries + dashboard short-SHAs | iterate | +0 | 32/32 | PASS | 2026-05-05 |
| 20 | adopt writes shipwright_iterate_config.json with documented opt-out schema | iterate | +0 | 241/241 | PASS | 2026-05-05 |
| 21 | FR-table parser accepts 5-col adopt format + drift protection | iterate | +0 | 1594/1628 | FAIL | 2026-05-05 |
| 22 | post-F7 housekeeping + AC-13 P5 fix (active install path) for plugin-hook-registration | iterate | +0 | 12/12 | PASS | 2026-05-05 |
| 23 | plugin-owned suggest_iterate hook (ADR-030); retired hook_installer + 7 SKILL.md stanzas + A6 verifier | iterate | +0 | 1691/1716 | FAIL | 2026-05-05 |
| 24 | F runner contract mandates reviews (ADR-029) | iterate | +0 | 188/188 | PASS | 2026-05-04 |
| 25 | iterate: review-driven hardening (ADR-028 / campaign iterate-skill-hardening Sub-Iterate E) | iterate | +0 | 1539/1539 | PASS | 2026-05-04 |
| 26 | test plugin: boundary coverage report (campaign iterate-skill-hardening Sub-Iterate D, ADR-027) | iterate | +19 | 19/19 | PASS | 2026-05-03 |
| 27 | changelog MSYS path-mangling linter | iterate | +0 | 19/19 | PASS | 2026-05-03 |
| 28 | hooks.json quoting (deferred from ADR-020) | iterate | +0 | 13/13 | PASS | 2026-05-03 |
| 29 | iterate fix: parse_env_file inline-comment stripping + lib copy sync | iterate | +0 | 53/53 | PASS | 2026-05-03 |
| 30 | iterate: adopt scaffolds .env.local with profile + framework keys (ADR-021) | iterate | +0 | 47/47 | PASS | 2026-05-03 |
| 31 | suggest_iterate hook quoted-path + Shape A/B upgrade-in-place | iterate | +0 | 249/249 | PASS | 2026-05-03 |
| 32 | fix hook_installer Shape A -> B | iterate | +0 | 5/5 | PASS | 2026-05-03 |
| 33 | shipwright-adopt durable fixes (Sub-2A drift detection, 2B test-fixture filter, 2C compliance_bridge sys.path) | iterate | +0 | 233/233 | PASS | 2026-05-02 |
| 34 | post-adoption framework cleanup (Sub-1A through 1D) | iterate | +0 | 225/225 | PASS | 2026-05-02 |

