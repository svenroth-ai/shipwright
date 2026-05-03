# Requirements Traceability Matrix

Generated: 2026-05-03T18:14:57Z

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

## Coverage Summary

| Metric | Value |
|--------|-------|
| Total splits built | 0 |
| Build sections | 0 |
| Iterate changes | 7 |
| Total review findings | 0 |
| Unresolved findings | 0 |

