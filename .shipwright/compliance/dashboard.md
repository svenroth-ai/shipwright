# Compliance Dashboard

Generated: 2026-07-28T07:58:42.604954+00:00
Source-State: run=iterate-2026-07-27-pr-review-forged-boundary
Consistency-audit: never run
Profile: python-plugin-monorepo
Scope: library

## ✅ Control Verdict

> **Controlled, minor gaps. Primarily capped by change reconciliation.**

### Control Grade: **B** (84/100) — Controlled, minor gaps.

| | Dimension | Signal | Anchor |
|---|-----------|--------|--------|
| ✅ | Requirement traceability | 17/18 FRs covered; 382/382 changes traced (FR-linked or classified no-FR) | requirement-to-work traceability (ISO/IEC/IEEE 29148) |
| ✅ | Test health | latest full suite 4946/4961 (2026-07-23) | automated tests pass (OpenSSF Scorecard) |
| ✅ | Change traceability | 382/382 changes linked to a commit, ADR or test run | change provenance (SLSA) |
| ⚠️ | Change reconciliation | 18/18 behavior-touched FRs not re-verified | re-verify changed requirements (ISO/IEC/IEEE 12207) |
| ✅ | Security | 0 open high/critical | no open high/critical vulns (NIST SSDF) |
| ✅ | Size / maintainability discipline | ratchet delta -88 lines (net growth) | no unchecked code-size growth (ISO/IEC 25010) |
| ✅ | Dependency hygiene | 0 unresolved / 11 licenses; 0 copyleft | dependency license & risk (OWASP) |

> 📊 **Test-Health · diff-coverage (Control-Grade input · target ≥80%):** not measured this session — per-PR signal; see the CI "Diff coverage" artifact.

Verified from: `shipwright_events.jsonl (382 events, 2026-05-02 → 2026-07-28)`

_Grade = importance-weighted average over the measurable dimensions (n/a excluded from the denominator), modeled on OpenSSF Scorecard. Age is neutral; only unreconciled change and net growth are control failures. Each Anchor names the open standard the dimension follows — see the guide's Control-Grade dimensions table._

## 🛡️ CI Security (fail-closed gate)

Latest scan: **2026-07-28** · source `security.yml#30340025168` · critical-gate **✅ PASS**

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 0 |
| Medium | 1 |
| Low | 0 |

Prompt-injection findings: **0**

**Accepted risks** (`shipwright_accepted_risks.yaml` register):

| ID | Target | Expires | Status | Recorded under |
|----|--------|---------|--------|----------------|
| ar-2026-06-22-otel-baggage-dev-only | trivy-ignore | 2026-12-22 | active | iterate-2026-06-22-trivy-risk-accept |
| ar-2026-07-03-dependabot-cooldown-inert-config | semgrep-rule-exclusion | 2027-01-03 | active | ADR-271 |
| ar-2026-07-03-gh-owned-mutable-action-tags | semgrep-policy-toggle | 2027-01-03 | active | ADR-271 |

_Ingested from CI `findings.json` (public-safe: severity counts + gate verdict only — no finding detail). The local `.shipwright/securityreports/` is intentionally **not** used (stale/FP-laden). Open high/critical feed the Control Grade's Security dimension._

## Quality Indicators

| Metric | Value | Status | Why warn? |
|--------|-------|--------|-----------|
| Pipeline phases completed | n/a (adopted) | INFO |  |
| Work events (iterate) | 382 changes | INFO |  |
| Recent changes traced to an FR | 20/30 (67%) | INFO | feature vs. maintenance mix — informational, does not affect the Control Grade |
| All unit tests passing | 4946/4961 | WARN | 15/4961 not green in last full suite — see test-evidence.md; +24 change(s) since last full suite |
| Architecture decisions | 328 ADRs | INFO |  |
| Iterate tests passing | 53/84 testable changes tested | WARN | 31 testable change(s) without tests — see test-evidence.md |
| Dependencies | 11 packages | INFO |  |
| Copyleft risk | 0 | PASS |  |
| Triage open | 21 open | WARN | 21 actionable item(s) — see ../agent_docs/triage_inbox.md |
| Bloat over-limit (grandfathered) | 125 | INFO |  |
| Bloat in allowlist | 159 entries | INFO |  |
| Bloat ratchet delta | -88 lines | PASS |  |

## Project Velocity

- Iterate: 382 changes (2026-05-02 → 2026-07-28)
- Last activity: 2026-07-28

## External LLM Review Evidence

| Split | Status | Provider | Findings | Self-review fallback | Reason |
|-------|--------|----------|----------|----------------------|--------|
| 01-adopted | missing | — | 0 | no | — |
| adr | missing | — | 0 | no | — |
| campaigns | missing | — | 0 | no | — |

## 🔎 Consistency Audit

**Never run — nothing has cross-checked this evidence against the project's actual state.**

_On demand by design: the audit has no schedule and no CI trigger, so it never runs on its own — invoke `/shipwright-compliance` to establish a first reading._

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

