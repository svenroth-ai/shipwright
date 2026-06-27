# Compliance Dashboard

Generated: 2026-06-27T21:14:40.530729+00:00
Profile: python-plugin-monorepo
Scope: library

## ✅ Control Verdict

> **Controlled, minor gaps. Primarily capped by requirement traceability.**

### Control Grade: **B** (88/100) — Controlled, minor gaps.

| | Dimension | Signal | Anchor |
|---|-----------|--------|--------|
| ⚠️ | Requirement traceability | 14/14 FRs covered; 35/211 changes FR-tagged | DO-178C §11.9 / IEC 62304 / ALM RTM |
| ✅ | Test health | latest full suite 3473/3473 (2026-06-14) | coverage gating (SonarQube 'Sonar Way') |
| ✅ | Change traceability | 211/211 changes linked to a commit, ADR or test run | SLSA provenance / OpenSSF Code-Review |
| n/a | Change reconciliation | not measurable — needs per-change behavior-impact (BP-2) | ALM suspect-links + DO-178C/ISO 26262 re-verification |
| n/a | Security | no trustworthy local scan (see CI security gate) | NIST SSDF (SP 800-218) / OWASP / OpenSSF |
| ✅ | Size / maintainability discipline | ratchet delta -40 lines (net growth) | ISO 25010 maintainability / SonarQube |
| ✅ | Dependency hygiene | 0 unresolved / 8 licenses; 0 copyleft | OWASP A06:2021 / OpenSSF Scorecard |

Verified from: `shipwright_events.jsonl (211 events, 2026-05-02 → 2026-06-27)`

_Grade = importance-weighted average over the measurable dimensions (n/a excluded from the denominator), in Anlehnung an OpenSSF Scorecard. Age is neutral; only unreconciled change and net growth are control failures._

## Quality Indicators

| Metric | Value | Status | Why warn? |
|--------|-------|--------|-----------|
| Pipeline phases completed | n/a (adopted) | INFO |  |
| Work events (iterate) | 211 changes | INFO |  |
| All unit tests passing | 3473/3473 | PASS | +19 change(s) since last full suite |
| Architecture decisions | 235 ADRs | INFO |  |
| Iterate tests passing | 132/211 iterations tested | WARN | 79 iterate(s) without tests — see test-evidence.md |
| Dependencies | 8 packages | INFO |  |
| Copyleft risk | 0 | PASS |  |
| Triage open | 1 open | WARN | 1 actionable item(s) — see ../agent_docs/triage_inbox.md |
| Bloat over-limit | 128 | WARN | 128 file(s) past limit AND not ADR-justified — see shipwright_bloat_baseline.json |
| Bloat in allowlist | 158 entries | INFO |  |
| Bloat ratchet delta | -40 lines | PASS |  |

## Project Velocity

- Iterate: 211 changes (2026-05-02 → 2026-06-27)
- Last activity: 2026-06-27

## External LLM Review Evidence

| Split | Status | Provider | Findings | Self-review fallback | Reason |
|-------|--------|----------|----------|----------------------|--------|
| 01-adopted | missing | — | 0 | no | — |
| adr | missing | — | 0 | no | — |
| campaigns | missing | — | 0 | no | — |

## 🔎 Consistency Audit

_Detective cross-artifact audit not run this session — run `/shipwright-compliance` to refresh._

## Compliance Artifacts

| Document | Path | Description |
|----------|------|-------------|
| Event Log | [shipwright_events.jsonl](../../shipwright_events.jsonl) | Unified append-only event log |
| Traceability Matrix | [traceability-matrix.md](./traceability-matrix.md) | Requirements → Work Events → Tests |
| Test Evidence | [test-evidence.md](./test-evidence.md) | Test progression timeline |
| Commit Change Log | [change-history.md](./change-history.md) | Conventional Commits by type |
| Decision Log | [decision_log.md](../agent_docs/decision_log.md) | Architecture decisions (ADRs) |
| SBOM | [sbom.md](./sbom.md) | Open-source dependencies + licenses |
| Activity Dashboard | [build_dashboard.md](../agent_docs/build_dashboard.md) | Per-event change history + pipeline status |
| Changelog | [CHANGELOG.md](../../CHANGELOG.md) | Release notes |

