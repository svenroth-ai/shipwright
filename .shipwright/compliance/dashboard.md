# Compliance Dashboard

Generated: 2026-06-28T12:48:12.844908+00:00
Profile: python-plugin-monorepo
Scope: library

## ✅ Control Verdict

> **Under full control. Primarily capped by security.**

### Control Grade: **A** (90/100) — Under full control.

| | Dimension | Signal | Anchor |
|---|-----------|--------|--------|
| ✅ | Requirement traceability | 14/14 FRs covered; 221/221 changes traced (FR-linked or classified no-FR) | DO-178C §11.9 / IEC 62304 / ALM RTM |
| ✅ | Test health | latest full suite 3853/3853 (2026-06-28) | coverage gating (SonarQube 'Sonar Way') |
| ✅ | Change traceability | 221/221 changes linked to a commit, ADR or test run | SLSA provenance / OpenSSF Code-Review |
| ✅ | Change reconciliation | 0/4 behavior-touched FRs not re-verified | ALM suspect-links + DO-178C/ISO 26262 re-verification |
| ⚠️ | Security | 3 open high/critical | NIST SSDF (SP 800-218) / OWASP / OpenSSF |
| ✅ | Size / maintainability discipline | ratchet delta -167 lines (net growth) | ISO 25010 maintainability / SonarQube |
| ✅ | Dependency hygiene | 0 unresolved / 7 licenses; 0 copyleft | OWASP A06:2021 / OpenSSF Scorecard |

Verified from: `shipwright_events.jsonl (221 events, 2026-05-02 → 2026-06-28)`

_Grade = importance-weighted average over the measurable dimensions (n/a excluded from the denominator), in Anlehnung an OpenSSF Scorecard. Age is neutral; only unreconciled change and net growth are control failures._

## 🛡️ CI Security (fail-closed gate)

Latest scan: **2026-06-22** · source `security.yml#27950188761` · critical-gate **✅ PASS**

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 3 |
| Medium | 1 |
| Low | 0 |

Prompt-injection findings: **0**

**Accepted risks** (`.trivyignore.yaml` register):

| CVE / ID | Expires | Status |
|----------|---------|--------|
| CVE-2026-54285 | 2026-12-22 | active |

_Ingested from CI `findings.json` (public-safe: severity counts + gate verdict only — no finding detail). The local `.shipwright/securityreports/` is intentionally **not** used (stale/FP-laden). Open high/critical feed the Control Grade's Security dimension._

## Quality Indicators

| Metric | Value | Status | Why warn? |
|--------|-------|--------|-----------|
| Pipeline phases completed | n/a (adopted) | INFO |  |
| Work events (iterate) | 221 changes | INFO |  |
| Recent changes traced to an FR | 1/30 (3%) | WARN | FR-tagging dropped to 3% (last 30) vs 18% all-time — recent changes classified no-FR; see the Control Verdict traceability dimension |
| All unit tests passing | 3853/3853 | PASS | +1 change(s) since last full suite |
| Architecture decisions | 235 ADRs | INFO |  |
| Iterate tests passing | 140/221 iterations tested | WARN | 81 iterate(s) without tests — see test-evidence.md |
| Dependencies | 7 packages | INFO |  |
| Copyleft risk | 0 | PASS |  |
| Triage open | 1 open | WARN | 1 actionable item(s) — see ../agent_docs/triage_inbox.md |
| Bloat over-limit | 127 | WARN | 127 file(s) past limit AND not ADR-justified — see shipwright_bloat_baseline.json |
| Bloat in allowlist | 158 entries | INFO |  |
| Bloat ratchet delta | -167 lines | PASS |  |

## Project Velocity

- Iterate: 221 changes (2026-05-02 → 2026-06-28)
- Last activity: 2026-06-28

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

