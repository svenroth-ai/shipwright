# Compliance Dashboard

Generated: 2026-08-04T07:03:48.888864+00:00
Source-State: run=iterate-2026-08-04-p1-15-events-context
Consistency-audit: last run 2026-07-28 (7 days earlier) — FAIL
Profile: python-plugin-monorepo
Scope: library

## ❌ Control Verdict

> **Out of control — AI changes you can't verify. Capped: security failing (3 open high/critical).**

### Control Grade: **F** (49/100) — Out of control — AI changes you can't verify.

| | Dimension | Signal | Anchor |
|---|-----------|--------|--------|
| ✅ | Requirement traceability | 18/19 FRs covered; 450/450 changes traced (FR-linked or classified no-FR) | requirement-to-work traceability (ISO/IEC/IEEE 29148) |
| ✅ | Test health | latest full suite 13680/13710 (2026-08-03) | automated tests pass (OpenSSF Scorecard) |
| ✅ | Change traceability | 450/450 changes linked to a commit, ADR or test run | change provenance (SLSA) |
| ⚠️ | Change reconciliation | 13/19 behavior-touched FRs not re-verified | re-verify changed requirements (ISO/IEC/IEEE 12207) |
| ⚠️ | Security | 3 open high/critical | no open high/critical vulns (NIST SSDF) |
| ✅ | Size / maintainability discipline | ratchet delta -67 lines (net growth) | no unchecked code-size growth (ISO/IEC 25010) |
| ✅ | Dependency hygiene | 0 unresolved / 11 licenses; 0 copyleft | dependency license & risk (OWASP) |

> 📊 **Test-Health · diff-coverage (Control-Grade input · target ≥80%):** not measured this session — per-PR signal; see the CI "Diff coverage" artifact.

Verified from: `shipwright_events.jsonl (450 events, 2026-05-02 → 2026-08-04)`

_Grade = importance-weighted average over the measurable dimensions (n/a excluded from the denominator), modeled on OpenSSF Scorecard. Age is neutral; only unreconciled change and net growth are control failures. Each Anchor names the open standard the dimension follows — see the guide's Control-Grade dimensions table._

## 🛡️ CI Security (fail-closed gate)

Latest scan: **2026-08-04** · source `security.yml#30881608080` · critical-gate **✅ PASS**

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 3 |
| Medium | 2 |
| Low | 0 |

Prompt-injection findings: **1**

**Accepted risks** (`shipwright_accepted_risks.yaml` register):

| ID | Target | Expires | Status | Recorded under |
|----|--------|---------|--------|----------------|
| ar-2026-06-22-otel-baggage-dev-only | trivy-ignore | 2026-12-22 | active | iterate-2026-06-22-trivy-risk-accept |
| ar-2026-07-03-dependabot-cooldown-inert-config | semgrep-rule-exclusion | 2027-01-03 | active | ADR-271 |
| ar-2026-07-03-gh-owned-mutable-action-tags | semgrep-policy-toggle | 2027-01-03 | active | ADR-271 |
| ar-2026-07-28-brace-expansion-dev-only | trivy-ignore | 2027-01-28 | active | iterate-2026-07-28-security-pyasn1-bump-brace-accept |

_Ingested from CI `findings.json` (public-safe: severity counts + gate verdict only — no finding detail). The local `.shipwright/securityreports/` is intentionally **not** used (stale/FP-laden). Open high/critical feed the Control Grade's Security dimension._

## Quality Indicators

| Metric | Value | Status | Why warn? |
|--------|-------|--------|-----------|
| Pipeline phases completed | n/a (adopted) | INFO |  |
| Work events (iterate) | 450 changes | INFO |  |
| Recent changes traced to an FR | 6/30 (20%) | INFO | feature vs. maintenance mix — informational, does not affect the Control Grade |
| All unit tests passing | 13680/13710 | WARN | 30/13710 not green in last full suite — see test-evidence.md; +2 change(s) since last full suite |
| Architecture decisions | 328 ADRs | INFO |  |
| Iterate tests passing | 63/111 testable changes tested | WARN | 48 testable change(s) without tests — see test-evidence.md |
| Dependencies | 11 packages | INFO |  |
| Copyleft risk | 0 | PASS |  |
| Triage open | 40 open | WARN | 40 actionable item(s) — see ../agent_docs/triage_inbox.md |
| Bloat over-limit (grandfathered) | 126 | INFO |  |
| Bloat in allowlist | 171 entries | INFO |  |
| Bloat ratchet delta | -67 lines | PASS |  |

## Project Velocity

- Iterate: 450 changes (2026-05-02 → 2026-08-04)
- Last activity: 2026-08-04

## External LLM Review Evidence

| Split | Status | Provider | Findings | Self-review fallback | Reason |
|-------|--------|----------|----------|----------------------|--------|
| 01-adopted | missing | — | 0 | no | — |
| adr | missing | — | 0 | no | — |
| campaigns | missing | — | 0 | no | — |

## 🔎 Consistency Audit

**Last run 2026-07-28 (7 days earlier): FAIL** · 59 checks — 47 pass, 2 fail, 10 skip.

_On demand by design: the audit has no schedule and no CI trigger, so it never runs on its own, so this date is how far back the last cross-check reaches — anything that drifted after it is unmeasured._

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

