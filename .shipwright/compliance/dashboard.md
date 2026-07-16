# Compliance Dashboard

Generated: 2026-07-16T18:39:51.338541+00:00
Profile: python-plugin-monorepo
Scope: library

## ✅ Control Verdict

> **Under full control. Primarily capped by change reconciliation.**

### Control Grade: **A** (94/100) — Under full control.

| | Dimension | Signal | Anchor |
|---|-----------|--------|--------|
| ✅ | Requirement traceability | 14/15 FRs covered; 315/315 changes traced (FR-linked or classified no-FR) | requirement-to-work traceability (ISO/IEC/IEEE 29148) |
| ✅ | Test health | latest full suite 5936/5936 (2026-07-16) | automated tests pass (OpenSSF Scorecard) |
| ✅ | Change traceability | 315/315 changes linked to a commit, ADR or test run | change provenance (SLSA) |
| ⚠️ | Change reconciliation | 2/7 behavior-touched FRs not re-verified | re-verify changed requirements (ISO/IEC/IEEE 12207) |
| ✅ | Security | 0 open high/critical | no open high/critical vulns (NIST SSDF) |
| ✅ | Size / maintainability discipline | ratchet delta -93 lines (net growth) | no unchecked code-size growth (ISO/IEC 25010) |
| ✅ | Dependency hygiene | 0 unresolved / 11 licenses; 0 copyleft | dependency license & risk (OWASP) |

> 📊 **Test-Health · diff-coverage (Control-Grade input · target ≥80%):** not measured this session — per-PR signal; see the CI "Diff coverage" artifact.

Verified from: `shipwright_events.jsonl (315 events, 2026-05-02 → 2026-07-16)`

_Grade = importance-weighted average over the measurable dimensions (n/a excluded from the denominator), modeled on OpenSSF Scorecard. Age is neutral; only unreconciled change and net growth are control failures. Each Anchor names the open standard the dimension follows — see the guide's Control-Grade dimensions table._

## 🛡️ CI Security (fail-closed gate)

Latest scan: **2026-07-16** · source `security.yml#29521734707` · critical-gate **✅ PASS**

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 0 |
| Medium | 2 |
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
| Work events (iterate) | 315 changes | INFO |  |
| Recent changes traced to an FR | 3/30 (10%) | INFO | feature vs. maintenance mix — informational, does not affect the Control Grade |
| All unit tests passing | 5936/5936 | PASS |  |
| Architecture decisions | 327 ADRs | INFO |  |
| Iterate tests passing | 46/56 testable changes tested | WARN | 10 testable change(s) without tests — see test-evidence.md |
| Dependencies | 11 packages | INFO |  |
| Copyleft risk | 0 | PASS |  |
| Triage open | 12 open | WARN | 12 actionable item(s) — see ../agent_docs/triage_inbox.md |
| Bloat over-limit (grandfathered) | 124 | INFO |  |
| Bloat in allowlist | 155 entries | INFO |  |
| Bloat ratchet delta | -93 lines | PASS |  |

## Project Velocity

- Iterate: 315 changes (2026-05-02 → 2026-07-16)
- Last activity: 2026-07-16

## External LLM Review Evidence

| Split | Status | Provider | Findings | Self-review fallback | Reason |
|-------|--------|----------|----------|----------------------|--------|
| 01-adopted | missing | — | 0 | no | — |
| adr | missing | — | 0 | no | — |
| campaigns | missing | — | 0 | no | — |

## 🔎 Consistency Audit

Detective audit (2026-06-14): **FAIL — drift found** · 51 checks — 38 pass, 1 fail, 12 skip.

_Inlined from `audit-report.json` (a gitignored transient — no external link, so this stays visible on the public repo)._

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

