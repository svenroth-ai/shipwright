# Test Evidence Report

Generated: 2026-05-21T19:08:17.472175+00:00

## Summary

| Metric | Value |
|--------|-------|
| Total test checkpoints | 40 |
| Total unit tests (latest) | 2621/2621 |
| New tests from iterations | +42 |

## Test Progression

| # | Event | Source | Layer | New Tests | Suite Total | Result | Date |
|---|-------|--------|-------|-----------|-------------|--------|------|
| 1 | empirical-verification follow-ups: triage_add CLI + Full Suite Runs synthesis + path-canon ALLOWLIST | iterate | unit | +0 | 2621/2621 | PASS | 2026-05-21 |
| 2 | VERIFICATION: bug+change-type — should pass | iterate | — | +0 | — | — | 2026-05-21 |
| 3 | VERIFICATION: with affected-frs — should pass | iterate | — | +0 | — | — | 2026-05-21 |
| 4 | Artifact-based GitHub security producer for Triage Inbox (+ spec.md FR-01.14 update) | iterate | mixed | +0 | 122/122 | PASS | 2026-05-20 |
| 5 | Artifact-based GitHub security producer for Triage Inbox | iterate | mixed | +0 | 122/122 | PASS | 2026-05-20 |
| 6 | escape pipe and newline in markdown table cells | iterate | unit | +23 | 23/23 | PASS | 2026-05-20 |
| 7 | fix 17 launch-blocker test failures (Windows python3 stub + 6 smaller groups) | iterate | mixed | +0 | 3507/3507 | PASS | 2026-05-18 |
| 8 | triage detector dedup + auto-resolve (rebased onto #31) | iterate | mixed | +0 | 1776/1783 | FAIL | 2026-05-16 |
| 9 | spec-impact classification gate: enforce ADD/MODIFY/REMOVE/NONE on every feature/change iterate (F7 record_event + F11 verifier gates, Group D5 audit, Removed Requirements convention) | iterate | unit | +0 | 140/140 | PASS | 2026-05-16 |
| 10 | triage detector dedup + auto-resolve | iterate | mixed | +0 | 1776/1783 | FAIL | 2026-05-16 |
| 11 | fix adopt external-review config defaults | iterate | mixed | +0 | 304/304 | PASS | 2026-05-16 |
| 12 | events.jsonl worktree-awareness: F7/verifier/dashboard resolve the log via git-common-dir; leak-guard exempts it; dashboard embeds run_id | iterate | mixed | +0 | 2519/2526 | FAIL | 2026-05-16 |
| 13 | RTM data collection: parse 6-column adopt FR tables + resolve shipwright_events.jsonl via git-common-dir for worktree finalization; fixes false 'Traceability coverage 0%' on adopted projects | iterate | mixed | +0 | 312/312 | PASS | 2026-05-15 |
| 14 | Triage Inbox Iterate 2: 4 additional producers (security + performance + F0.5 + drift) wired into append_triage_item_idempotent. CI producer DEFERRED. ADR-047. | iterate | mixed | +0 | 40/40 | PASS | 2026-05-14 |
| 15 | Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI (rebased onto post-test-hygiene main; ADR renumbered 045→046) | iterate | unit | +0 | 1642/1649 | FAIL | 2026-05-11 |
| 16 | Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI | iterate | unit | +0 | 1642/1649 | FAIL | 2026-05-11 |
| 17 | known_issues scanner requires comment context; remove dead save_session_config — 16/16 green | iterate | unit | +0 | 16/16 | PASS | 2026-05-09 |
| 18 | evt-f66286bf | iterate | — | +0 | — | — | 2026-05-07 |
| 19 | evt-623a29ad | iterate | — | +0 | — | — | 2026-05-07 |
| 20 | F0.5 empirical-test backfill | iterate | unit | +0 | 1575/1575 | PASS | 2026-05-06 |
| 21 | F0.5 End-to-End Verification Gate | iterate | unit | +0 | 1548/1548 | PASS | 2026-05-06 |
| 22 | hooks-consistency parser handles quoted commands — 27/27 green | iterate | unit | +0 | 1297/1297 | PASS | 2026-05-06 |
| 23 | post-migration canon cleanup — 9 tests green | iterate | unit | +0 | 1270/1270 | PASS | 2026-05-06 |
| 24 | loader deep-merges per-project shipwright_iterate_config.json + cascade helper | iterate | unit | +0 | 34/34 | PASS | 2026-05-05 |
| 25 | verifier accepts drop-dir entries + dashboard short-SHAs | iterate | unit | +0 | 32/32 | PASS | 2026-05-05 |
| 26 | adopt writes shipwright_iterate_config.json with documented opt-out schema | iterate | unit | +0 | 241/241 | PASS | 2026-05-05 |
| 27 | FR-table parser accepts 5-col adopt format + drift protection | iterate | unit | +0 | 1594/1628 | FAIL | 2026-05-05 |
| 28 | post-F7 housekeeping + AC-13 P5 fix (active install path) for plugin-hook-registration | iterate | unit | +0 | 12/12 | PASS | 2026-05-05 |
| 29 | plugin-owned suggest_iterate hook (ADR-030); retired hook_installer + 7 SKILL.md stanzas + A6 verifier | iterate | unit | +0 | 1691/1716 | FAIL | 2026-05-05 |
| 30 | F runner contract mandates reviews (ADR-029) | iterate | unit | +0 | 188/188 | PASS | 2026-05-04 |
| 31 | iterate: review-driven hardening (ADR-028 / campaign iterate-skill-hardening Sub-Iterate E) | iterate | unit | +0 | 1539/1539 | PASS | 2026-05-04 |
| 32 | test plugin: boundary coverage report (campaign iterate-skill-hardening Sub-Iterate D, ADR-027) | iterate | unit | +19 | 19/19 | PASS | 2026-05-03 |
| 33 | changelog MSYS path-mangling linter | iterate | unit | +0 | 19/19 | PASS | 2026-05-03 |
| 34 | hooks.json quoting (deferred from ADR-020) | iterate | unit | +0 | 13/13 | PASS | 2026-05-03 |
| 35 | iterate fix: parse_env_file inline-comment stripping + lib copy sync | iterate | unit | +0 | 53/53 | PASS | 2026-05-03 |
| 36 | iterate: adopt scaffolds .env.local with profile + framework keys (ADR-021) | iterate | unit | +0 | 47/47 | PASS | 2026-05-03 |
| 37 | suggest_iterate hook quoted-path + Shape A/B upgrade-in-place | iterate | unit | +0 | 249/249 | PASS | 2026-05-03 |
| 38 | fix hook_installer Shape A -> B | iterate | unit | +0 | 5/5 | PASS | 2026-05-03 |
| 39 | shipwright-adopt durable fixes (Sub-2A drift detection, 2B test-fixture filter, 2C compliance_bridge sys.path) | iterate | unit | +0 | 233/233 | PASS | 2026-05-02 |
| 40 | post-adoption framework cleanup (Sub-1A through 1D) | iterate | unit | +0 | 225/225 | PASS | 2026-05-02 |

## Full Suite Runs

| Run | Trigger | Unit | Integration | pgTAP | E2E | Smoke | Date |
|-----|---------|------|-------------|-------|-----|-------|------|
| 1 | iterate | 13/13 | — | — | — | — | 2026-05-03 |
| 2 | iterate | 19/19 | — | — | — | — | 2026-05-03 |
| 3 | iterate | 19/19 | — | — | — | — | 2026-05-03 |
| 4 | iterate | 1539/1539 | — | — | — | — | 2026-05-04 |
| 5 | iterate | 188/188 | — | — | — | — | 2026-05-04 |
| 6 | iterate | 1691/1716 | — | — | — | — | 2026-05-05 |
| 7 | iterate | 12/12 | — | — | — | — | 2026-05-05 |
| 8 | iterate | 1594/1628 | — | — | — | — | 2026-05-05 |
| 9 | iterate | 241/241 | — | — | — | — | 2026-05-05 |
| 10 | iterate | 32/32 | — | — | — | — | 2026-05-05 |
| 11 | iterate | 34/34 | — | — | — | — | 2026-05-05 |
| 12 | iterate | 1270/1270 | — | — | — | — | 2026-05-06 |
| 13 | iterate | 1297/1297 | — | — | — | — | 2026-05-06 |
| 14 | iterate | 1548/1548 | — | — | — | — | 2026-05-06 |
| 15 | iterate | 1575/1575 | — | — | — | — | 2026-05-06 |
| 16 | iterate | 16/16 | — | — | — | — | 2026-05-09 |
| 17 | iterate | 1642/1649 | — | — | — | — | 2026-05-11 |
| 18 | iterate | 1642/1649 | — | — | — | — | 2026-05-11 |
| 19 | iterate | 40/40 | — | — | — | — | 2026-05-14 |
| 20 | iterate | 312/312 | — | — | — | — | 2026-05-15 |
| 21 | iterate | 2519/2526 | — | — | — | — | 2026-05-16 |
| 22 | iterate | 304/304 | — | — | — | — | 2026-05-16 |
| 23 | iterate | 1776/1783 | — | — | — | — | 2026-05-16 |
| 24 | iterate | 140/140 | — | — | — | — | 2026-05-16 |
| 25 | iterate | 1776/1783 | — | — | — | — | 2026-05-16 |
| 26 | iterate | 3507/3507 | — | — | — | — | 2026-05-18 |
| 27 | iterate | 23/23 | — | — | — | — | 2026-05-20 |
| 28 | iterate | 122/122 | — | — | — | — | 2026-05-20 |
| 29 | iterate | 122/122 | — | — | — | — | 2026-05-20 |
| 30 | iterate | 2621/2621 | — | — | — | — | 2026-05-21 |

