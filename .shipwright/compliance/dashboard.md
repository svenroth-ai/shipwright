# Compliance Dashboard

Generated: 2026-07-11T02:20:22.384564+00:00
Profile: python-plugin-monorepo
Scope: library

## ✅ Control Verdict

> **Under full control.**

### Control Grade: **A** (100/100) — Under full control.

| | Dimension | Signal | Anchor |
|---|-----------|--------|--------|
| ✅ | Requirement traceability | 14/14 FRs covered; 292/292 changes traced (FR-linked or classified no-FR) | requirement-to-work traceability (ISO/IEC/IEEE 29148) |
| ✅ | Test health | latest full suite 4749/4749 (2026-07-10) | automated tests pass (OpenSSF Scorecard) |
| ✅ | Change traceability | 292/292 changes linked to a commit, ADR or test run | change provenance (SLSA) |
| ✅ | Change reconciliation | 0/5 behavior-touched FRs not re-verified | re-verify changed requirements (ISO/IEC/IEEE 12207) |
| ✅ | Security | 0 open high/critical | no open high/critical vulns (NIST SSDF) |
| ✅ | Size / maintainability discipline | ratchet delta -87 lines (net growth) | no unchecked code-size growth (ISO/IEC 25010) |
| ✅ | Dependency hygiene | 0 unresolved / 11 licenses; 0 copyleft | dependency license & risk (OWASP) |

> 📊 **Test-Health · diff-coverage (Control-Grade input · target ≥80%):** not measured this session — per-PR signal; see the CI "Diff coverage" artifact.

Verified from: `shipwright_events.jsonl (292 events, 2026-05-02 → 2026-07-11)`

_Grade = importance-weighted average over the measurable dimensions (n/a excluded from the denominator), modeled on OpenSSF Scorecard. Age is neutral; only unreconciled change and net growth are control failures. Each Anchor names the open standard the dimension follows — see the guide's Control-Grade dimensions table._

## 🛡️ CI Security (fail-closed gate)

Latest scan: **2026-07-11** · source `security.yml#29135368686` · critical-gate **✅ PASS**

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
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
| Work events (iterate) | 292 changes | INFO |  |
| Recent changes traced to an FR | 0/30 (0%) | INFO | feature vs. maintenance mix — informational, does not affect the Control Grade |
| All unit tests passing | 4749/4749 | PASS | +4 change(s) since last full suite |
| Architecture decisions | 309 ADRs | INFO |  |
| Iterate tests passing | 45/53 testable changes tested | WARN | 8 testable change(s) without tests — see test-evidence.md |
| Dependencies | 11 packages | INFO |  |
| Copyleft risk | 0 | PASS |  |
| Triage open | 6 open | WARN | 6 actionable item(s) — see ../agent_docs/triage_inbox.md |
| Bloat over-limit (grandfathered) | 127 | INFO |  |
| Bloat in allowlist | 158 entries | INFO |  |
| Bloat ratchet delta | -87 lines | PASS |  |

## Project Velocity

- Iterate: 292 changes (2026-05-02 → 2026-07-11)
- Last activity: 2026-07-11

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

