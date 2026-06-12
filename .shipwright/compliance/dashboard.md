# Compliance Dashboard

Generated: 2026-06-12T08:48:05.654486+00:00
Profile: python-plugin-monorepo
Scope: library

## Quality Indicators

| Metric | Value | Status | Why warn? |
|--------|-------|--------|-----------|
| Pipeline phases completed | n/a (adopted) | INFO |  |
| Work events (iterate) | 145 changes | INFO |  |
| All unit tests passing | 3157/3157 | PASS |  |
| Architecture decisions | 142 ADRs | INFO |  |
| Iterate tests passing | 89/145 iterations tested | WARN | 56 iterate(s) without tests — see test-evidence.md |
| Dependencies | 8 packages | INFO |  |
| Copyleft risk | 0 | PASS |  |
| Triage open | 14 open | WARN | 14 actionable item(s) — see ../agent_docs/triage_inbox.md |
| Bloat over-limit | 123 | WARN | 123 file(s) past limit AND not ADR-justified — see shipwright_bloat_baseline.json |
| Bloat in allowlist | 153 entries | INFO |  |
| Bloat ratchet delta | -150 lines | PASS |  |

## Project Velocity

- Iterate: 145 changes (2026-05-02 → 2026-06-12)
- Last activity: 2026-06-12

## External LLM Review Evidence

| Split | Status | Provider | Findings | Self-review fallback | Reason |
|-------|--------|----------|----------|----------------------|--------|
| 01-adopted | missing | — | 0 | no | — |
| adr | missing | — | 0 | no | — |
| campaigns | missing | — | 0 | no | — |

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

