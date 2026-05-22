# Requirements Traceability Matrix

Generated: 2026-05-22T13:10:04Z

## Requirements Coverage

| Requirement | Title | Priority | Verified By | Tests | Last Verified | Status |
|-------------|-------|----------|-------------|-------|---------------|--------|
| [FR-01.01](../../.shipwright/planning/01-adopted/spec.md#fr-0101) | Orchestrate the full Shipwright SDLC pipeline — drives proje... | Must | evt-e3d2949e, evt-b0b9c422, evt-ca7b7d64, evt-7620210f +1 | 225/225 → 0/0 | 2026-05-21 (iter) | FAIL |
| [FR-01.02](../../.shipwright/planning/01-adopted/spec.md#fr-0102) | Decompose project requirements (IREB) into well-scoped plann... | Must | evt-e3d2949e, evt-b0b9c422, evt-ca7b7d64, evt-7620210f +1 | 225/225 → 140/140 | 2026-05-16 (iter) | FAIL |
| [FR-01.03](../../.shipwright/planning/01-adopted/spec.md#fr-0103) | AI-assisted deep planning with research, optional interview,... | Must | evt-e3d2949e, evt-ca7b7d64 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.04](../../.shipwright/planning/01-adopted/spec.md#fr-0104) | Generate UI mockups from IREB specs as standalone HTML scree... | Should | evt-e3d2949e, evt-ca7b7d64 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.05](../../.shipwright/planning/01-adopted/spec.md#fr-0105) | Implement code from /shipwright-plan sections with TDD (red-... | Must | evt-e3d2949e, evt-ca7b7d64 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.06](../../.shipwright/planning/01-adopted/spec.md#fr-0106) | Run unit tests, E2E tests (Playwright), smoke tests, and sec... | Must | evt-e3d2949e, evt-ca7b7d64, evt-c4ae8ef7 | 225/225 → 19/19 | 2026-05-03 (iter) | COVERED |
| [FR-01.07](../../.shipwright/planning/01-adopted/spec.md#fr-0107) | Security scanning chain (Aikido + Semgrep + Trivy + Gitleaks... | Must | evt-e3d2949e, evt-ca7b7d64 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.08](../../.shipwright/planning/01-adopted/spec.md#fr-0108) | Deploy to configured targets with smoke testing and rollback... | Should | evt-e3d2949e, evt-ca7b7d64 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.09](../../.shipwright/planning/01-adopted/spec.md#fr-0109) | Parse Conventional Commits from git history, generate Keep-a... | Must | evt-e3d2949e, evt-ca7b7d64, evt-530b0980 | 225/225 → 19/19 | 2026-05-03 (iter) | COVERED |
| [FR-01.10](../../.shipwright/planning/01-adopted/spec.md#fr-0110) | Generate audit-ready compliance documentation (RTM, test evi... | Must | evt-e3d2949e, evt-ca7b7d64, evt-30338dac, evt-a3888caf +1 | 225/225 → 140/140 | 2026-05-16 (iter) | FAIL |
| [FR-01.11](../../.shipwright/planning/01-adopted/spec.md#fr-0111) | Complexity-adaptive SDLC for ongoing changes — auto-detects ... | Must | evt-e3d2949e, evt-6c637864, evt-baaf4b0e, evt-ca7b7d64 +12 | 225/225 → 140/140 | 2026-05-16 (iter) | FAIL |
| [FR-01.12](../../.shipwright/planning/01-adopted/spec.md#fr-0112) | Local browser preview — start dev server for the target proj... | May | evt-e3d2949e, evt-ca7b7d64 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.13](../../.shipwright/planning/01-adopted/spec.md#fr-0113) | Onboard an existing (brownfield) repository into the Shipwri... | Must | evt-e3d2949e, evt-273bbb54, evt-b0b9c422, evt-aab7ddbd +5 | 225/225 → 304/304 | 2026-05-16 (iter) | FAIL |
| [FR-01.14](../../.shipwright/planning/01-adopted/spec.md#fr-0114) | Pre-backlog triage buffer — findings from local hooks/scans/... | Must | evt-3f488ddc, evt-32f2f1f4, evt-84dbdf5e, evt-e14e5f26 +3 | 1642/1649 → 122/122 | 2026-05-20 (iter) | FAIL |

## Verification Timeline

| Event | Source | Type | FRs | Tests | Commit | Date |
|-------|--------|------|-----|-------|--------|------|
| post-adoption framework cleanup (Sub-1A through 1D) | iterate | change | FR-01.01, FR-01.02, FR-01.03 +10 | 225/225 | 3db485b | 2026-05-02 |
| shipwright-adopt durable fixes (Sub-2A drift detection, 2B test-fixture filter, 2C compliance_bridge sys.path) | iterate | change | FR-01.13 | 233/233 | cffe191 | 2026-05-02 |
| fix hook_installer Shape A -> B | iterate | bug | FR-01.11 | 5/5 | 1ddf9ae | 2026-05-03 |
| suggest_iterate hook quoted-path + Shape A/B upgrade-in-place | iterate | bug | FR-01.13, FR-01.02, FR-01.01 | 249/249 | b24f804 | 2026-05-03 |
| iterate: adopt scaffolds .env.local with profile + framework keys (ADR-021) | iterate | feature | FR-01.13 | 47/47 | 9953008 | 2026-05-03 |
| iterate fix: parse_env_file inline-comment stripping + lib copy sync | iterate | fix | FR-01.11 | 53/53 | 1a9c7f4 | 2026-05-03 |
| hooks.json quoting (deferred from ADR-020) | iterate | bug | FR-01.01, FR-01.02, FR-01.03 +10 | 13/13 | 6ca369d | 2026-05-03 |
| changelog MSYS path-mangling linter | iterate | bug | FR-01.09 | 19/19 | a13fd64 | 2026-05-03 |
| test plugin: boundary coverage report (campaign iterate-skill-hardening Sub-Iterate D, ADR-027) | iterate | feature | FR-01.06 | 19/19 | 216f8b3 | 2026-05-03 |
| iterate: review-driven hardening (ADR-028 / campaign iterate-skill-hardening Sub-Iterate E) | iterate | bug | FR-01.11 | 1539/1539 | 5415ed6 | 2026-05-04 |
| F runner contract mandates reviews (ADR-029) | iterate | feature | FR-01.11 | 188/188 | f6a14fc | 2026-05-04 |
| plugin-owned suggest_iterate hook (ADR-030); retired hook_installer + 7 SKILL.md stanzas + A6 verifier | iterate | bug | FR-01.11, FR-01.13, FR-01.02 +1 | 1691/1716 | a05ff22 | 2026-05-05 |
| post-F7 housekeeping + AC-13 P5 fix (active install path) for plugin-hook-registration | iterate | bug | FR-01.11 | 12/12 | afb3b63 | 2026-05-05 |
| FR-table parser accepts 5-col adopt format + drift protection | iterate | bug | FR-01.10, FR-01.13 | 1594/1628 | 656f96f | 2026-05-05 |
| adopt writes shipwright_iterate_config.json with documented opt-out schema | iterate | bug | FR-01.13, FR-01.11 | 241/241 | f4f7229 | 2026-05-05 |
| verifier accepts drop-dir entries + dashboard short-SHAs | iterate | bug | FR-01.11 | 32/32 | f1f0447 | 2026-05-05 |
| loader deep-merges per-project shipwright_iterate_config.json + cascade helper | iterate | bug | FR-01.11 | 34/34 | 49eca25 | 2026-05-05 |
| post-migration canon cleanup — 9 tests green | iterate | bug |  | 1270/1270 | 7383c18 | 2026-05-06 |
| hooks-consistency parser handles quoted commands — 27/27 green | iterate | bug | FR-01.11 | 1297/1297 | c5e6cb3 | 2026-05-06 |
| F0.5 End-to-End Verification Gate | iterate | feature | FR-01.11 | 1548/1548 | 88f3398 | 2026-05-06 |
| F0.5 empirical-test backfill | iterate | change | FR-01.11 | 1575/1575 | 0df63f2 | 2026-05-06 |
| evt-623a29ad | iterate | change |  | — | 686e7cc | 2026-05-07 |
| evt-f66286bf | iterate | change |  | — | 99fc87b | 2026-05-07 |
| known_issues scanner requires comment context; remove dead save_session_config — 16/16 green | iterate | bug |  | 16/16 | f8d44da | 2026-05-09 |
| Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI | iterate | feature | FR-01.14 | 1642/1649 | 6ba7df1 | 2026-05-11 |
| Triage Inbox Iterate 1a: storage API + aggregator + 2 producers + scaffolder + promote CLI (rebased onto post-test-hygiene main; ADR renumbered 045→046) | iterate | feature | FR-01.14 | 1642/1649 | f638908 | 2026-05-11 |
| Triage Inbox Iterate 2: 4 additional producers (security + performance + F0.5 + drift) wired into append_triage_item_idempotent. CI producer DEFERRED. ADR-047. | iterate | feature | FR-01.14 | 40/40 | aab9bd7 | 2026-05-14 |
| RTM data collection: parse 6-column adopt FR tables + resolve shipwright_events.jsonl via git-common-dir for worktree finalization; fixes false 'Traceability coverage 0%' on adopted projects | iterate | bug | FR-01.10 | 312/312 | ea24bf4 | 2026-05-15 |
| events.jsonl worktree-awareness: F7/verifier/dashboard resolve the log via git-common-dir; leak-guard exempts it; dashboard embeds run_id | iterate | bug | FR-01.11 | 2519/2526 | 34a7987 | 2026-05-16 |
| fix adopt external-review config defaults | iterate | bug | FR-01.13 | 304/304 | 3f5777d | 2026-05-16 |
| triage detector dedup + auto-resolve | iterate | bug | FR-01.14 | 1776/1783 | 931e6b5 | 2026-05-16 |
| spec-impact classification gate: enforce ADD/MODIFY/REMOVE/NONE on every feature/change iterate (F7 record_event + F11 verifier gates, Group D5 audit, Removed Requirements convention) | iterate | feature | FR-01.11, FR-01.10, FR-01.02 | 140/140 | c16d711 | 2026-05-16 |
| triage detector dedup + auto-resolve (rebased onto #31) | iterate | bug | FR-01.14 | 1776/1783 | cd957a0 | 2026-05-16 |
| fix 17 launch-blocker test failures (Windows python3 stub + 6 smaller groups) | iterate | bug |  | 3507/3507 | 21cef22 | 2026-05-18 |
| escape pipe and newline in markdown table cells | iterate | bug |  | 23/23 | 9dd6c8b | 2026-05-20 |
| Artifact-based GitHub security producer for Triage Inbox | iterate | feature | FR-01.14 | 122/122 | 6f5dd5f | 2026-05-20 |
| Artifact-based GitHub security producer for Triage Inbox (+ spec.md FR-01.14 update) | iterate | feature | FR-01.14 | 122/122 | 861c0fd | 2026-05-20 |
| VERIFICATION: with affected-frs — should pass | iterate | feature | FR-01.01 | — | 376c870 | 2026-05-21 |
| VERIFICATION: bug+change-type — should pass | iterate | bug |  | — | 376c870 | 2026-05-21 |
| empirical-verification follow-ups: triage_add CLI + Full Suite Runs synthesis + path-canon ALLOWLIST | iterate | change |  | 2621/2621 | d8f3c05 | 2026-05-21 |
| deterministic render timestamps from max(event.ts) | iterate | bug |  | 34/34 | d325fd6 | 2026-05-21 |
| Extended g2_stoplist with 13 cross-cutting monorepo scopes; backfilled ADR-054..061 stubs in decision_log.md; regenerated RTM/test-evidence/dashboard | iterate | Clear 5 compliance triage bloat items (G2 stoplist + G3 ADR stubs + 3x artifact-stale) from artifact-polish/empirical-verification campaigns |  | — | c3057ff | 2026-05-22 |
| Re-aggregated triage_inbox.md; refreshed sbom.md, dashboard.md, test-evidence.md, traceability-matrix.md, change-history.md, session_handoff.md, build_dashboard.md | iterate | Re-aggregate triage inbox to surface SBOM bug cluster (trg-8bc99ae4) and commit regen artifacts |  | — | 69f1498 | 2026-05-22 |
| Re-aggregated triage_inbox.md; refreshed sbom.md, dashboard.md, test-evidence.md, traceability-matrix.md, change-history.md, session_handoff.md, build_dashboard.md | iterate | Re-aggregate triage inbox to surface SBOM bug cluster (trg-8bc99ae4) and commit regen artifacts |  | — | 69f1498 | 2026-05-22 |
| mirror_findings_to_triage now scoped to groups_run; --only E no longer dismisses A/B/C/D items | iterate | Fix partial-run audit incorrectly dismissing out-of-scope compliance triage items |  | — | 09fedde | 2026-05-22 |

## Coverage Summary

| Metric | Value |
|--------|-------|
| Total splits built | 0 |
| Build sections | 0 |
| Iterate changes | 45 |
| Requirements total | 14 |
| Requirements verified | 14/14 |
| Must-have verified | 11/11 |
| Total review findings | 0 |
| Unresolved findings | 0 |

### FRs with stale verification (> 14 days)

- [FR-01.03](../../.shipwright/planning/01-adopted/spec.md) — last verified 18d ago by `evt-ca7b7d64` (2026-05-03)
- [FR-01.04](../../.shipwright/planning/01-adopted/spec.md) — last verified 18d ago by `evt-ca7b7d64` (2026-05-03)
- [FR-01.05](../../.shipwright/planning/01-adopted/spec.md) — last verified 18d ago by `evt-ca7b7d64` (2026-05-03)
- [FR-01.07](../../.shipwright/planning/01-adopted/spec.md) — last verified 18d ago by `evt-ca7b7d64` (2026-05-03)
- [FR-01.08](../../.shipwright/planning/01-adopted/spec.md) — last verified 18d ago by `evt-ca7b7d64` (2026-05-03)
- [FR-01.09](../../.shipwright/planning/01-adopted/spec.md) — last verified 18d ago by `evt-530b0980` (2026-05-03)
- [FR-01.12](../../.shipwright/planning/01-adopted/spec.md) — last verified 18d ago by `evt-ca7b7d64` (2026-05-03)
- [FR-01.06](../../.shipwright/planning/01-adopted/spec.md) — last verified 17d ago by `evt-c4ae8ef7` (2026-05-03)

