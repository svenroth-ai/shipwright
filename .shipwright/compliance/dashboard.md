# Compliance Dashboard

Generated: 2026-06-30T21:50:52.825435+00:00
Profile: python-plugin-monorepo
Scope: library

## ✅ Control Verdict

> **Controlled, minor gaps. Capped: traceability declining (FR-tag 10% vs 18% all-time, last 30).**

### Control Grade: **B** (89/100) — Controlled, minor gaps.

| | Dimension | Signal | Anchor |
|---|-----------|--------|--------|
| ⚠️ | Requirement traceability | 14/14 FRs covered; 234/234 changes traced (FR-linked or classified no-FR); FR-tag rate 10% vs 18% all-time — declining | requirement-to-work traceability (ISO/IEC/IEEE 29148) |
| ✅ | Test health | latest full suite 3633/3633 (2026-06-30) | automated tests pass (OpenSSF Scorecard) |
| ✅ | Change traceability | 234/234 changes linked to a commit, ADR or test run | change provenance (SLSA) |
| ✅ | Change reconciliation | 0/4 behavior-touched FRs not re-verified | re-verify changed requirements (ISO/IEC/IEEE 12207) |
| ✅ | Security | 0 open high/critical | no open high/critical vulns (NIST SSDF) |
| ✅ | Size / maintainability discipline | ratchet delta -9 lines (net growth) | no unchecked code-size growth (ISO/IEC 25010) |
| ✅ | Dependency hygiene | 0 unresolved / 7 licenses; 0 copyleft | dependency license & risk (OWASP) |

Verified from: `shipwright_events.jsonl (234 events, 2026-05-02 → 2026-06-30)`

_Grade = importance-weighted average over the measurable dimensions (n/a excluded from the denominator), modeled on OpenSSF Scorecard. Age is neutral; only unreconciled change and net growth are control failures. Each Anchor names the open standard the dimension follows — see the guide's Control-Grade dimensions table._

## 🛡️ CI Security (fail-closed gate)

Latest scan: **2026-06-29** · source `security.yml#28366536467` · critical-gate **✅ PASS**

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |

Prompt-injection findings: **1**

**Accepted risks** (`.trivyignore.yaml` register):

| CVE / ID | Expires | Status |
|----------|---------|--------|
| CVE-2026-54285 | 2026-12-22 | active |

_Ingested from CI `findings.json` (public-safe: severity counts + gate verdict only — no finding detail). The local `.shipwright/securityreports/` is intentionally **not** used (stale/FP-laden). Open high/critical feed the Control Grade's Security dimension._

## Quality Indicators

| Metric | Value | Status | Why warn? |
|--------|-------|--------|-----------|
| Pipeline phases completed | n/a (adopted) | INFO |  |
| Work events (iterate) | 234 changes | INFO |  |
| Recent changes traced to an FR | 3/30 (10%) | WARN | FR-tagging dropped to 10% (last 30) vs 18% all-time — recent changes classified no-FR; see the Control Verdict traceability dimension |
| All unit tests passing | 3633/3633 | PASS |  |
| Architecture decisions | 235 ADRs | INFO |  |
| Iterate tests passing | 37/42 testable changes tested | WARN | 5 testable change(s) without tests — see test-evidence.md |
| Dependencies | 7 packages | INFO |  |
| Copyleft risk | 0 | PASS |  |
| Triage open | 6 open | WARN | 6 actionable item(s) — see ../agent_docs/triage_inbox.md |
| Bloat over-limit (grandfathered) | 127 | INFO |  |
| Bloat in allowlist | 158 entries | INFO |  |
| Bloat ratchet delta | -9 lines | PASS |  |

## Project Velocity

- Iterate: 234 changes (2026-05-02 → 2026-06-30)
- Last activity: 2026-06-30

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

