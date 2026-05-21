# Test Evidence Report

Generated: 2026-05-21T19:07:21Z

## Summary

| Metric | Value |
|--------|-------|
| Total test checkpoints | 39 |
| Total unit tests (latest) | 0/0 |
| New tests from iterations | +42 |

## Test Progression

| # | Event | Source | Layer | New Tests | Suite Total | Result | Date |
|---|-------|--------|-------|-----------|-------------|--------|------|
| 1 | VERIFICATION: bug+change-type — should pass | iterate | — | +0 | — | — | 2026-05-21 |
| 2 | VERIFICATION: with affected-frs — should pass | iterate | — | +0 | — | — | 2026-05-21 |
| 3 | Artifact-based GitHub security producer for Triage Inbox (+ spec.md FR-01.14 update) | iterate | mixed | +0 | 122/122 | PASS | 2026-05-20 |
| 4 | Artifact-based GitHub security producer for Triage Inbox | iterate | mixed | +0 | 122/122 | PASS | 2026-05-20 |
| 5 | escape pipe and newline in markdown table cells | iterate | unit | +23 | 23/23 | PASS | 2026-05-20 |
| 6 | fix 17 launch-blocker test failures (Windows python3 stub + 6 smaller groups) | iterate | mixed | +0 | 3507/3507 | PASS | 2026-05-18 |
| 7 | triage detector dedup + auto-resolve (rebased onto #31) | iterate | mixed | +0 | 1776/1783 | FAIL | 2026-05-16 |
| 8 | spec-impact classification gate: enforce ADD/MODIFY/REMOVE/NONE on every feature/change iterate (F7 record_event + F11 verifier gates, Group D5 audit, Removed Requirements convention) | iterate | unit | +0 | 140/140 | PASS | 2026-05-16 |
| 9 | triage detector dedup + auto-resolve | iterate | mixed | +0 | 1776/1783 | FAIL | 2026-05-16 |
| 10 | fix adopt external-review config defaults | iterate | mixed | +0 | 304/304 | PASS | 2026-05-16 |
| 11 | events.jsonl worktree-awareness: F7/verifier/dashboard resolve the log via git-common-dir; leak-guard exempts it; dashboard embeds run_id | iterate | mixed | +0 | 2519/2526 | FAIL | 2026-05-16 |
| 12 | RTM data collection: parse 6-column adopt FR tables + resolve shipwright_events.jsonl via git-common-dir for worktree finalization; fixes false 'Traceability coverage 0%' on adopted projects | iterate | mixed | +0 | 312/312 | PASS | 2026-05-15 |
| 13 | Triage Inbox Iterate 2: 4 additional producers (security + performance + F0.5 + drift) wired into append_triage_item_idempotent. CI producer DEFERRED. ADR-047. | iterate | mixed | +0 | 40/40 | PASS | 2026-05-14 |
| 14 | Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI (rebased onto post-test-hygiene main; ADR renumbered 045→046) | iterate | unit | +0 | 1642/1649 | FAIL | 2026-05-11 |
| 15 | Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI | iterate | unit | +0 | 1642/1649 | FAIL | 2026-05-11 |
| 16 | known_issues scanner requires comment context; remove dead save_session_config — 16/16 green | iterate | unit | +0 | 16/16 | PASS | 2026-05-09 |
| 17 | evt-f66286bf | iterate | — | +0 | — | — | 2026-05-07 |
| 18 | evt-623a29ad | iterate | — | +0 | — | — | 2026-05-07 |
| 19 | F0.5 empirical-test backfill | iterate | unit | +0 | 1575/1575 | PASS | 2026-05-06 |
| 20 | F0.5 End-to-End Verification Gate | iterate | unit | +0 | 1548/1548 | PASS | 2026-05-06 |
| 21 | hooks-consistency parser handles quoted commands — 27/27 green | iterate | unit | +0 | 1297/1297 | PASS | 2026-05-06 |
| 22 | post-migration canon cleanup — 9 tests green | iterate | unit | +0 | 1270/1270 | PASS | 2026-05-06 |
| 23 | loader deep-merges per-project shipwright_iterate_config.json + cascade helper | iterate | unit | +0 | 34/34 | PASS | 2026-05-05 |
| 24 | verifier accepts drop-dir entries + dashboard short-SHAs | iterate | unit | +0 | 32/32 | PASS | 2026-05-05 |
| 25 | adopt writes shipwright_iterate_config.json with documented opt-out schema | iterate | unit | +0 | 241/241 | PASS | 2026-05-05 |
| 26 | FR-table parser accepts 5-col adopt format + drift protection | iterate | unit | +0 | 1594/1628 | FAIL | 2026-05-05 |
| 27 | post-F7 housekeeping + AC-13 P5 fix (active install path) for plugin-hook-registration | iterate | unit | +0 | 12/12 | PASS | 2026-05-05 |
| 28 | plugin-owned suggest_iterate hook (ADR-030); retired hook_installer + 7 SKILL.md stanzas + A6 verifier | iterate | unit | +0 | 1691/1716 | FAIL | 2026-05-05 |
| 29 | F runner contract mandates reviews (ADR-029) | iterate | unit | +0 | 188/188 | PASS | 2026-05-04 |
| 30 | iterate: review-driven hardening (ADR-028 / campaign iterate-skill-hardening Sub-Iterate E) | iterate | unit | +0 | 1539/1539 | PASS | 2026-05-04 |
| 31 | test plugin: boundary coverage report (campaign iterate-skill-hardening Sub-Iterate D, ADR-027) | iterate | unit | +19 | 19/19 | PASS | 2026-05-03 |
| 32 | changelog MSYS path-mangling linter | iterate | unit | +0 | 19/19 | PASS | 2026-05-03 |
| 33 | hooks.json quoting (deferred from ADR-020) | iterate | unit | +0 | 13/13 | PASS | 2026-05-03 |
| 34 | iterate fix: parse_env_file inline-comment stripping + lib copy sync | iterate | unit | +0 | 53/53 | PASS | 2026-05-03 |
| 35 | iterate: adopt scaffolds .env.local with profile + framework keys (ADR-021) | iterate | unit | +0 | 47/47 | PASS | 2026-05-03 |
| 36 | suggest_iterate hook quoted-path + Shape A/B upgrade-in-place | iterate | unit | +0 | 249/249 | PASS | 2026-05-03 |
| 37 | fix hook_installer Shape A -> B | iterate | unit | +0 | 5/5 | PASS | 2026-05-03 |
| 38 | shipwright-adopt durable fixes (Sub-2A drift detection, 2B test-fixture filter, 2C compliance_bridge sys.path) | iterate | unit | +0 | 233/233 | PASS | 2026-05-02 |
| 39 | post-adoption framework cleanup (Sub-1A through 1D) | iterate | unit | +0 | 225/225 | PASS | 2026-05-02 |

