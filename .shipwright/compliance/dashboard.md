# Compliance Dashboard

Generated: 2026-05-02T06:56:52Z
Profile: python-plugin-monorepo
Scope: library

## Quality Indicators

| Indicator | Value | Status | Description |
|-----------|-------|--------|-------------|
| All planned splits built | 1 | PASS | Every project split has been implemented |
| All sections completed | 0/1 | WARN | Build sections across all splits |
| All unit tests passing | 0/0 | WARN | Unit tests across all sections |
| Code reviewed | 1/1 sections | PASS | Sections that went through code review |
| Architecture decisions logged | 8 | INFO | ADR entries in decision_log.md |
| Third-party dependencies | 5 | INFO | Open-source packages in use |
| Copyleft license risk | 0 | PASS | Packages with GPL/AGPL/LGPL/MPL licenses |

## External LLM Review Evidence

| Split | Status | Provider | Findings | Self-review fallback | Reason |
|-------|--------|----------|----------|----------------------|--------|
| 01-adopted | missing | — | 0 | no | — |

## Compliance Artifacts

| Document | Path | Description |
|----------|------|-------------|
| Event Log | [shipwright_events.jsonl](../../shipwright_events.jsonl) | Unified append-only event log |
| Traceability Matrix | [traceability-matrix.md](./traceability-matrix.md) | Requirements → Work Events → Tests |
| Test Evidence | [test-evidence.md](./test-evidence.md) | Test progression timeline |
| Commit Change Log | [change-history.md](./change-history.md) | Conventional Commits by type |
| Decision Log | [decision_log.md](../agent_docs/decision_log.md) | Architecture decisions (ADRs) |
| SBOM | [sbom.md](./sbom.md) | Open-source dependencies + licenses |
| Changelog | [CHANGELOG.md](../../CHANGELOG.md) | Release notes |

