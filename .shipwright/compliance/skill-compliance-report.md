# Skill Compliance Report

_Regenerated 2026-05-09T06:15:34+00:00 from last 10 run(s)._

| Phase | Run | Audited | Source | PASS | FAIL | WARN | SKIP |
|---|---|---|---|---:|---:|---:|---:|
| iterate | `unknown` | 2026-05-09T06:15:34+00:00 | iterate | 8 | 3 | 1 | 8 |
| adopt | `unknown` | 2026-05-09T06:15:34+00:00 | orchestrator | 9 | 1 | 0 | 2 |
| test | `unknown` | 2026-05-09T06:15:34+00:00 | orchestrator | 2 | 1 | 0 | 4 |
| compliance | `unknown` | 2026-05-09T06:15:34+00:00 | orchestrator | 2 | 1 | 1 | 3 |
| changelog | `unknown` | 2026-05-09T06:15:34+00:00 | orchestrator | 4 | 0 | 0 | 3 |
| build | `unknown` | 2026-05-09T06:15:34+00:00 | orchestrator | 3 | 3 | 0 | 6 |
| security | `unknown` | 2026-05-09T06:15:34+00:00 | orchestrator | 1 | 2 | 1 | 3 |
| deploy | `unknown` | 2026-05-09T06:15:34+00:00 | orchestrator | 2 | 2 | 0 | 2 |
| project | `unknown` | 2026-05-09T06:15:34+00:00 | orchestrator | 9 | 3 | 1 | 0 |
| design | `unknown` | 2026-05-09T06:15:34+00:00 | orchestrator | 2 | 3 | 1 | 1 |

## iterate — unknown (2026-05-09T06:15:34+00:00)

### canon
- **C1** — FAIL: no phase_completed event for phase=iterate
- **C2** — PASS: 'iterate' found in build_dashboard.md
- **C3** — PASS: mtime age 0s
- **C4** — PASS: 9 ADR(s) referencing 'iterate'
- **C5** — FAIL: [Unreleased]/Added sub-section missing

### workflow
- **W2** — SKIP: complexity=trivial — external review not required
- **W3** — FAIL: test-evidence.md mtime stale (164942s > 86400s)

### infrastructure
- **I1** — SKIP: no phase_completed event for phase=iterate — freshness not verifiable yet
- **I2** — SKIP: no phase_started event for phase=iterate — freshness not verifiable yet
- **I3** — SKIP: no phase_started event for phase=iterate — freshness not verifiable yet
- **I4** — SKIP _(tier-2)_: sbom.md newer than every dependency manifest — no regen needed

### traceability
- **T1** — PASS: all 13 FR(s) present in RTM
- **T2** — PASS _(tier-2)_: no orphan rows (13 RTM FR(s) all backed by specs)

### quality
- **Q1** — PASS _(tier-2)_: ADR-040: Context=764, Decision=639, Consequences=502

### spec
- **S2** — SKIP: complexity=trivial — iterate spec not required below medium
- **S3** — SKIP _(tier-2)_: complexity=trivial — mini-plan not required below medium
- **S4** — PASS _(tier-2)_: no FR ids removed in last 10 spec commits
- **S5** — WARN _(tier-2)_: 4 missing both: .shipwright/planning/01-adopted/spec.md::FR-01.11, .shipwright/planning/01-adopted/spec.md::FR-01.13, .shipwright/planning/01-adopted/spec.md::FR-01.02 (+1)
- **S9** — SKIP _(tier-2)_: category=bug — S9 only runs for features
- **S10** — PASS _(tier-2)_: new top-level dir(s) ['CHANGELOG-unreleased.d'] present but CLAUDE.md was touched recently

## adopt — unknown (2026-05-09T06:15:34+00:00)

### canon
- **C1** — FAIL: no phase_completed event for phase=adopt
- **C2** — PASS: 'adopt' found in build_dashboard.md
- **C3** — PASS: mtime age 0s
- **C4** — PASS: 10 ADR(s) referencing 'adopt'
- **C5** — SKIP: not applicable for phase=adopt

### workflow
- **A1** — PASS: 5 required configs present and valid
- **A2** — PASS: FR found in .shipwright/planning/01-adopted/spec.md
- **A3** — PASS: adoption ADR found
- **A4** — PASS _(tier-2)_: 18 retroactive ADR(s) with substantive Context
- **A5** — PASS _(tier-2)_: review completed and recorded
- **A7** — PASS: exactly 1 'adopted' event
- **A8** — SKIP _(tier-2)_: no Playwright crawl output — baseline suite skipped by design

## test — unknown (2026-05-09T06:15:34+00:00)

### canon
- **C1** — FAIL: no phase_completed event for phase=test
- **C2** — PASS: 'test' found in build_dashboard.md
- **C3** — PASS: mtime age 0s
- **C4** — SKIP: not applicable for phase=test
- **C5** — SKIP: not applicable for phase=test

### workflow
- **W4** — SKIP: coverage.total missing or non-numeric — coverage unverifiable

### infrastructure
- **I2** — SKIP: no phase_started event for phase=test — freshness not verifiable yet

## compliance — unknown (2026-05-09T06:15:34+00:00)

### canon
- **C1** — FAIL: no phase_completed event for phase=compliance
- **C2** — PASS: 'compliance' found in build_dashboard.md
- **C3** — PASS: mtime age 0s
- **C4** — SKIP: not applicable for phase=compliance
- **C5** — SKIP: not applicable for phase=compliance

### workflow
- **Cmp1** — WARN _(tier-2)_: 1 completed phase(s) not mentioned: ['plan']
- **Cmp2** — SKIP: .shipwright/compliance/traceability-matrix.md missing or no coverage row

## changelog — unknown (2026-05-09T06:15:34+00:00)

### canon
- **C1** — PASS: found event @ ?
- **C2** — PASS: 'changelog' found in build_dashboard.md
- **C3** — PASS: mtime age 0s
- **C4** — SKIP: not applicable for phase=changelog
- **C5** — SKIP: not applicable for phase=changelog

### workflow
- **W6** — PASS: v0.17.1 present in git

### infrastructure
- **I3** — SKIP: no phase_started event for phase=changelog — freshness not verifiable yet

## build — unknown (2026-05-09T06:15:34+00:00)

### canon
- **C1** — FAIL: no phase_completed event for phase=build
- **C2** — PASS: 'build' found in build_dashboard.md
- **C3** — PASS: mtime age 0s
- **C4** — FAIL: found 0 ADR(s) referencing 'build', need >= 1
- **C5** — FAIL: [Unreleased]/Added sub-section missing

### workflow
- **W1** — SKIP _(tier-2)_: no build work_completed events — TDD order unverifiable

### infrastructure
- **I1** — SKIP: no phase_completed event for phase=build — freshness not verifiable yet
- **I2** — SKIP: no phase_started event for phase=build — freshness not verifiable yet
- **I3** — SKIP: no phase_started event for phase=build — freshness not verifiable yet
- **I4** — SKIP _(tier-2)_: sbom.md newer than every dependency manifest — no regen needed

### quality
- **Q1** — PASS _(tier-2)_: ADR-040: Context=764, Decision=639, Consequences=502
- **Q2** — SKIP: no plan snapshot and no .shipwright/planning/ tree — plan phase has not produced sections yet

## security — unknown (2026-05-09T06:15:34+00:00)

### canon
- **C1** — FAIL: no phase_completed event for phase=security
- **C2** — WARN: no mention of 'security' in build_dashboard.md
- **C3** — PASS: mtime age 0s
- **C4** — SKIP: not applicable for phase=security
- **C5** — SKIP: not applicable for phase=security

### workflow
- **Sec1** — FAIL: .shipwright/compliance/security-scan-report.md missing
- **Sec2** — SKIP: security-scan-report.md missing — Sec1 covers this

## deploy — unknown (2026-05-09T06:15:34+00:00)

### canon
- **C1** — FAIL: no phase_completed event for phase=deploy
- **C2** — PASS: 'deploy' found in build_dashboard.md
- **C3** — PASS: mtime age 0s
- **C4** — SKIP: not applicable for phase=deploy
- **C5** — FAIL: [Unreleased]/Changed sub-section missing

### workflow
- **W7** — SKIP: no smoke test evidence in deploy_config / test_results / events.jsonl

## project — unknown (2026-05-09T06:15:34+00:00)

### canon
- **C1** — FAIL: no phase_completed event for phase=project
- **C2** — PASS: 'project' found in build_dashboard.md
- **C3** — PASS: mtime age 0s
- **C4** — PASS: 2 ADR(s) referencing 'project'
- **C5** — FAIL: [Unreleased]/Added sub-section missing

### traceability
- **T1** — PASS: all 13 FR(s) present in RTM
- **T2** — PASS _(tier-2)_: no orphan rows (13 RTM FR(s) all backed by specs)

### quality
- **Q1** — PASS _(tier-2)_: ADR-040: Context=764, Decision=639, Consequences=502

### spec
- **S1** — FAIL: .shipwright/agent_docs/spec.md missing
- **S5** — WARN _(tier-2)_: 4 missing both: .shipwright/planning/01-adopted/spec.md::FR-01.11, .shipwright/planning/01-adopted/spec.md::FR-01.13, .shipwright/planning/01-adopted/spec.md::FR-01.02 (+1)
- **S6** — PASS: CLAUDE.md present (5757 chars)
- **S7** — PASS _(tier-2)_: Structure block present (22 line(s))
- **S8** — PASS: README.md present (18894 chars)

## design — unknown (2026-05-09T06:15:34+00:00)

### canon
- **C1** — FAIL: no phase_completed event for phase=design
- **C2** — PASS: 'design' found in build_dashboard.md
- **C3** — PASS: mtime age 0s
- **C4** — SKIP: not applicable for phase=design
- **C5** — FAIL: [Unreleased]/Added sub-section missing

### workflow
- **D1** — FAIL: no design artifacts (no mockups/*.html, no screens.md, no user-flow.md)
- **D2** — WARN _(tier-2)_: missing under .shipwright/agent_docs/: ['screens.md', 'user-flow.md']
