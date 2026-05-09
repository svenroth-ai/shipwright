# Requirements Traceability Matrix

Generated: 2026-05-09T08:03:18Z

## Requirements Coverage

| Requirement | Title | Priority | Verified By | Tests | Last Verified | Status |
|-------------|-------|----------|-------------|-------|---------------|--------|
| [FR-01.01](../../.shipwright/planning/01-adopted/spec.md#fr-0101) | Orchestrate the full Shipwright SDLC pipeline — drives proje... | Must | evt-e3d2949e, evt-b0b9c422, evt-ca7b7d64, evt-7620210f | 225/225 → 1691/1716 | 2026-05-05 (iter) | FAIL |
| [FR-01.02](../../.shipwright/planning/01-adopted/spec.md#fr-0102) | Decompose project requirements (IREB) into well-scoped plann... | Must | evt-e3d2949e, evt-b0b9c422, evt-ca7b7d64, evt-7620210f | 225/225 → 1691/1716 | 2026-05-05 (iter) | FAIL |
| [FR-01.03](../../.shipwright/planning/01-adopted/spec.md#fr-0103) | AI-assisted deep planning with research, optional interview,... | Must | evt-e3d2949e, evt-ca7b7d64 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.04](../../.shipwright/planning/01-adopted/spec.md#fr-0104) | Generate UI mockups from IREB specs as standalone HTML scree... | Should | evt-e3d2949e, evt-ca7b7d64 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.05](../../.shipwright/planning/01-adopted/spec.md#fr-0105) | Implement code from /shipwright-plan sections with TDD (red-... | Must | evt-e3d2949e, evt-ca7b7d64 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.06](../../.shipwright/planning/01-adopted/spec.md#fr-0106) | Run unit tests, E2E tests (Playwright), smoke tests, and sec... | Must | evt-e3d2949e, evt-ca7b7d64 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.07](../../.shipwright/planning/01-adopted/spec.md#fr-0107) | Security scanning chain (Aikido + Semgrep + Trivy + Gitleaks... | Must | evt-e3d2949e, evt-ca7b7d64 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.08](../../.shipwright/planning/01-adopted/spec.md#fr-0108) | Deploy to configured targets with smoke testing and rollback... | Should | evt-e3d2949e, evt-ca7b7d64 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.09](../../.shipwright/planning/01-adopted/spec.md#fr-0109) | Parse Conventional Commits from git history, generate Keep-a... | Must | evt-e3d2949e, evt-ca7b7d64 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.10](../../.shipwright/planning/01-adopted/spec.md#fr-0110) | Generate audit-ready compliance documentation (RTM, test evi... | Must | evt-e3d2949e, evt-ca7b7d64, evt-30338dac | 225/225 → 1594/1628 | 2026-05-05 (iter) | FAIL |
| [FR-01.11](../../.shipwright/planning/01-adopted/spec.md#fr-0111) | Complexity-adaptive SDLC for ongoing changes — auto-detects ... | Must | evt-e3d2949e, evt-ca7b7d64, evt-da156299, evt-7620210f +1 | 225/225 → 12/12 | 2026-05-05 (iter) | FAIL |
| [FR-01.12](../../.shipwright/planning/01-adopted/spec.md#fr-0112) | Local browser preview — start dev server for the target proj... | May | evt-e3d2949e, evt-ca7b7d64 | 225/225 → 13/13 | 2026-05-03 (iter) | COVERED |
| [FR-01.13](../../.shipwright/planning/01-adopted/spec.md#fr-0113) | Onboard an existing (brownfield) repository into the Shipwri... | Must | evt-e3d2949e, evt-273bbb54, evt-b0b9c422, evt-ca7b7d64 +2 | 225/225 → 1594/1628 | 2026-05-05 (iter) | FAIL |

## Verification Timeline

| Event | Source | Type | FRs | Tests | Commit | Date |
|-------|--------|------|-----|-------|--------|------|
| post-adoption framework cleanup (Sub-1A through 1D) | iterate | change | FR-01.01, FR-01.02, FR-01.03 +10 | 225/225 | 3db485b | 2026-05-02 |
| shipwright-adopt durable fixes (Sub-2A drift detection, 2B test-fixture filter, 2C compliance_bridge sys.path) | iterate | change | FR-01.13 | 233/233 | cffe191 | 2026-05-02 |
| fix hook_installer Shape A -> B | iterate | bug |  | 5/5 | 1ddf9ae | 2026-05-03 |
| suggest_iterate hook quoted-path + Shape A/B upgrade-in-place | iterate | bug | FR-01.13, FR-01.02, FR-01.01 | 249/249 | b24f804 | 2026-05-03 |
| iterate: adopt scaffolds .env.local with profile + framework keys (ADR-021) | iterate | feature |  | 47/47 | 9953008 | 2026-05-03 |
| iterate fix: parse_env_file inline-comment stripping + lib copy sync | iterate | fix |  | 53/53 | 1a9c7f4 | 2026-05-03 |
| hooks.json quoting (deferred from ADR-020) | iterate | bug | FR-01.01, FR-01.02, FR-01.03 +10 | 13/13 | 6ca369d | 2026-05-03 |
| changelog MSYS path-mangling linter | iterate | bug |  | 19/19 | a13fd64 | 2026-05-03 |
| test plugin: boundary coverage report (campaign iterate-skill-hardening Sub-Iterate D, ADR-027) | iterate | feature |  | 19/19 | 216f8b3 | 2026-05-03 |
| iterate: review-driven hardening (ADR-028 / campaign iterate-skill-hardening Sub-Iterate E) | iterate | bug |  | 1539/1539 | 5415ed6 | 2026-05-04 |
| F runner contract mandates reviews (ADR-029) | iterate | feature | FR-01.11 | 188/188 | f6a14fc | 2026-05-04 |
| plugin-owned suggest_iterate hook (ADR-030); retired hook_installer + 7 SKILL.md stanzas + A6 verifier | iterate | bug | FR-01.11, FR-01.13, FR-01.02 +1 | 1691/1716 | a05ff22 | 2026-05-05 |
| post-F7 housekeeping + AC-13 P5 fix (active install path) for plugin-hook-registration | iterate | bug | FR-01.11 | 12/12 | afb3b63 | 2026-05-05 |
| FR-table parser accepts 5-col adopt format + drift protection | iterate | bug | FR-01.10, FR-01.13 | 1594/1628 | 656f96f | 2026-05-05 |
| adopt writes shipwright_iterate_config.json with documented opt-out schema | iterate | bug |  | 241/241 | f4f7229 | 2026-05-05 |
| verifier accepts drop-dir entries + dashboard short-SHAs | iterate | bug |  | 32/32 | f1f0447 | 2026-05-05 |
| loader deep-merges per-project shipwright_iterate_config.json + cascade helper | iterate | bug |  | 34/34 | 49eca25 | 2026-05-05 |
| post-migration canon cleanup — 9 tests green | iterate | bug |  | 1270/1270 | 7383c18 | 2026-05-06 |
| hooks-consistency parser handles quoted commands — 27/27 green | iterate | bug |  | 1297/1297 | c5e6cb3 | 2026-05-06 |
| F0.5 End-to-End Verification Gate | iterate | feature |  | 1548/1548 | 88f3398 | 2026-05-06 |
| F0.5 empirical-test backfill | iterate | change |  | 1575/1575 | 0df63f2 | 2026-05-06 |
| evt-623a29ad | iterate | change |  | — | 686e7cc | 2026-05-07 |
| evt-f66286bf | iterate | change |  | — | 99fc87b | 2026-05-07 |
| known_issues scanner requires comment context; remove dead save_session_config — 16/16 green | iterate | bug |  | 16/16 | f8d44da | 2026-05-09 |

## Coverage Summary

| Metric | Value |
|--------|-------|
| Total splits built | 0 |
| Build sections | 0 |
| Iterate changes | 24 |
| Requirements total | 13 |
| Requirements verified | 13/13 |
| Must-have verified | 10/10 |
| Total review findings | 0 |
| Unresolved findings | 0 |

