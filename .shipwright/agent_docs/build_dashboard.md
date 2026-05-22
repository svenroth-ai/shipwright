# Project Activity Dashboard
> Updated: 2026-05-22 13:10 UTC | Session: 18bf1094-aa14-43b4-b60e-a1cf98127cbf | Run: iterate-2026-05-22-reconcile-d1-fr-coverage

## Recent Changes (45 iterations)

| Type | Description | Tests | Commit | FRs | Date |
|------|-------------|-------|--------|-----|------|
| Fix partial-run audit incorrectly dismissing out-of-scope compliance triage items | mirror_findings_to_triage now scoped to groups_run; --only E no longer dismisses A/B/C/D items | 0/0 | 09fedde | tooling | 2026-05-22 |
| Re-aggregate triage inbox to surface SBOM bug cluster (trg-8bc99ae4) and commit regen artifacts | Re-aggregated triage_inbox.md; refreshed sbom.md, dashboard.md, test-evidence.md, traceability-matrix.md, change-history.md, session_handoff.md, build_dashboard.md | 0/0 | 69f1498 | compliance | 2026-05-22 |
| Re-aggregate triage inbox to surface SBOM bug cluster (trg-8bc99ae4) and commit regen artifacts | Re-aggregated triage_inbox.md; refreshed sbom.md, dashboard.md, test-evidence.md, traceability-matrix.md, change-history.md, session_handoff.md, build_dashboard.md | 0/0 | 69f1498 | compliance | 2026-05-22 |
| Clear 5 compliance triage bloat items (G2 stoplist + G3 ADR stubs + 3x artifact-stale) from artifact-polish/empirical-verification campaigns | Extended g2_stoplist with 13 cross-cutting monorepo scopes; backfilled ADR-054..061 stubs in decision_log.md; regenerated RTM/test-evidence/dashboard | 0/0 | c3057ff | compliance | 2026-05-22 |
| bug | deterministic render timestamps from max(event.ts) | +34 new, 34/34 | d325fd6 | tooling | 2026-05-21 |
| change | empirical-verification follow-ups: triage_add CLI + Full Suite Runs synthesis + path-canon ALLOWLIST | 2621/2621 | d8f3c05 | tooling | 2026-05-21 |
| bug | VERIFICATION: bug+change-type — should pass | 0/0 | 376c870 | tooling | 2026-05-21 |
| feature | VERIFICATION: with affected-frs — should pass | 0/0 | 376c870 | FR-01.01 | 2026-05-21 |
| feature | Artifact-based GitHub security producer for Triage Inbox (+ spec.md FR-01.14 update) | 122/122 | 861c0fd | FR-01.14 | 2026-05-20 |
| feature | Artifact-based GitHub security producer for Triage Inbox | 122/122 | 6f5dd5f | FR-01.14 | 2026-05-20 |
| bug | escape pipe and newline in markdown table cells | +23 new, 23/23 | 9dd6c8b |  | 2026-05-20 |
| bug | fix 17 launch-blocker test failures (Windows python3 stub + 6 smaller groups) | 3507/3507 | 21cef22 | tooling | 2026-05-18 |
| bug | triage detector dedup + auto-resolve (rebased onto #31) | 1776/1783 | cd957a0 | FR-01.14 | 2026-05-16 |
| feature | spec-impact classification gate: enforce ADD/MODIFY/REMOVE/NONE on every feature/change iterate (F7 record_event + F11 verifier gates, Group D5 audit, Removed Requirements convention) | 140/140 | c16d711 | FR-01.11, FR-01.10, FR-01.02 | 2026-05-16 |
| bug | triage detector dedup + auto-resolve | 1776/1783 | 931e6b5 | FR-01.14 | 2026-05-16 |
| bug | fix adopt external-review config defaults | 304/304 | 3f5777d | FR-01.13 | 2026-05-16 |
| bug | events.jsonl worktree-awareness: F7/verifier/dashboard resolve the log via git-common-dir; leak-guard exempts it; dashboard embeds run_id | 2519/2526 | 34a7987 | FR-01.11 | 2026-05-16 |
| bug | RTM data collection: parse 6-column adopt FR tables + resolve shipwright_events.jsonl via git-common-dir for worktree finalization; fixes false 'Traceability coverage 0%' on adopted projects | 312/312 | ea24bf4 | FR-01.10 | 2026-05-15 |
| feature | Triage Inbox Iterate 2: 4 additional producers (security + performance + F0.5 + drift) wired into append_triage_item_idempotent. CI producer DEFERRED. ADR-047. | 40/40 | aab9bd7 | FR-01.14 | 2026-05-14 |
| feature | Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI (rebased onto post-test-hygiene main; ADR renumbered 045→046) | 1642/1649 | f638908 | FR-01.14 | 2026-05-11 |
| feature | Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI | 1642/1649 | 6ba7df1 | FR-01.14 | 2026-05-11 |
| bug | known_issues scanner requires comment context; remove dead save_session_config — 16/16 green | 16/16 | f8d44da | compliance | 2026-05-09 |
| change | — | 0/0 | 99fc87b | tooling | 2026-05-07 |
| change | — | 0/0 | 686e7cc | tooling | 2026-05-07 |
| change | F0.5 empirical-test backfill | 1575/1575 | 0df63f2 | FR-01.11 | 2026-05-06 |
| feature | F0.5 End-to-End Verification Gate | 1548/1548 | 88f3398 | FR-01.11 | 2026-05-06 |
| bug | hooks-consistency parser handles quoted commands — 27/27 green | 1297/1297 | c5e6cb3 | FR-01.11 | 2026-05-06 |
| bug | post-migration canon cleanup — 9 tests green | 1270/1270 | 7383c18 | tooling | 2026-05-06 |
| bug | loader deep-merges per-project shipwright_iterate_config.json + cascade helper | 34/34 | 49eca25 | FR-01.11 | 2026-05-05 |
| bug | verifier accepts drop-dir entries + dashboard short-SHAs | 32/32 | f1f0447 | FR-01.11 | 2026-05-05 |
| bug | adopt writes shipwright_iterate_config.json with documented opt-out schema | 241/241 | f4f7229 | FR-01.13, FR-01.11 | 2026-05-05 |
| bug | FR-table parser accepts 5-col adopt format + drift protection | 1594/1628 | 656f96f | FR-01.10, FR-01.13 | 2026-05-05 |
| bug | post-F7 housekeeping + AC-13 P5 fix (active install path) for plugin-hook-registration | 12/12 | afb3b63 | FR-01.11 | 2026-05-05 |
| bug | plugin-owned suggest_iterate hook (ADR-030); retired hook_installer + 7 SKILL.md stanzas + A6 verifier | 1691/1716 | a05ff22 | FR-01.11, FR-01.13, FR-01.02 | 2026-05-05 |
| feature | F runner contract mandates reviews (ADR-029) | 188/188 | f6a14fc | FR-01.11 | 2026-05-04 |
| bug | iterate: review-driven hardening (ADR-028 / campaign iterate-skill-hardening Sub-Iterate E) | 1539/1539 | 5415ed6 | FR-01.11 | 2026-05-04 |
| feature | test plugin: boundary coverage report (campaign iterate-skill-hardening Sub-Iterate D, ADR-027) | +19 new, 19/19 | 216f8b3 | FR-01.06 | 2026-05-03 |
| bug | changelog MSYS path-mangling linter | 19/19 | a13fd64 | FR-01.09 | 2026-05-03 |
| bug | hooks.json quoting (deferred from ADR-020) | 13/13 | 6ca369d | FR-01.01, FR-01.02, FR-01.03 | 2026-05-03 |
| fix | iterate fix: parse_env_file inline-comment stripping + lib copy sync | 53/53 | 1a9c7f4 | FR-01.11 | 2026-05-03 |
| feature | iterate: adopt scaffolds .env.local with profile + framework keys (ADR-021) | 47/47 | 9953008 | FR-01.13 | 2026-05-03 |
| bug | suggest_iterate hook quoted-path + Shape A/B upgrade-in-place | 249/249 | b24f804 | FR-01.13, FR-01.02, FR-01.01 | 2026-05-03 |
| bug | fix hook_installer Shape A -> B | 5/5 | 1ddf9ae | FR-01.11 | 2026-05-03 |
| change | shipwright-adopt durable fixes (Sub-2A drift detection, 2B test-fixture filter, 2C compliance_bridge sys.path) | 233/233 | cffe191 | FR-01.13 | 2026-05-02 |
| change | post-adoption framework cleanup (Sub-1A through 1D) | 225/225 | 3db485b | FR-01.01, FR-01.02, FR-01.03 | 2026-05-02 |

## Test Status
Last run: 2026-05-22 | Smoke: not_run | (iterate)

## Pipeline

| Phase | Status | Completed |
|-------|--------|-----------|
| project | — | — |
| design | — | — |
| plan | — | — |
| build | — | — |
| test | — | — |
| changelog | complete | 2026-05-03 |
| compliance | — | — |
| deploy | — | — |
