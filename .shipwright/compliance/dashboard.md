# Compliance Dashboard

Generated: 2026-08-07T23:17:47.920155+00:00
Source-State: run=iterate-2026-08-07-windows-ci-perf
Consistency-audit: last run 2026-07-28 (10 days earlier) — FAIL
Profile: python-plugin-monorepo
Scope: library

## ✅ Control Verdict

> **Controlled, minor gaps. Primarily capped by change reconciliation.**

### Control Grade: **B** (88/100) — Controlled, minor gaps.

| | Dimension | Signal | Anchor |
|---|-----------|--------|--------|
| ✅ | Requirement traceability | 18/20 FRs covered; 494/494 changes traced (FR-linked or classified no-FR) | requirement-to-work traceability (ISO/IEC/IEEE 29148) |
| ✅ | Test health | latest full suite 15200/15200 (2026-08-07) | automated tests pass (OpenSSF Scorecard) |
| ✅ | Change traceability | 494/494 changes linked to a commit, ADR or test run | change provenance (SLSA) |
| ⚠️ | Change reconciliation | 13/20 behavior-touched FRs not re-verified | re-verify changed requirements (ISO/IEC/IEEE 12207) |
| ✅ | Security | 0 open high/critical | no open high/critical vulns (NIST SSDF) |
| ✅ | Size / maintainability discipline | ratchet delta -120 lines (net growth) | no unchecked code-size growth (ISO/IEC 25010) |
| ✅ | Dependency hygiene | 0 unresolved / 11 licenses; 0 copyleft | dependency license & risk (OWASP) |

> 📊 **Test-Health · diff-coverage (Control-Grade input · target ≥80%):** not measured this session — per-PR signal; see the CI "Diff coverage" artifact.

Verified from: `shipwright_events.jsonl (494 events, 2026-05-02 → 2026-08-07)`

_Grade = importance-weighted average over the measurable dimensions (n/a excluded from the denominator), modeled on OpenSSF Scorecard. Age is neutral; only unreconciled change and net growth are control failures. Each Anchor names the open standard the dimension follows — see the guide's Control-Grade dimensions table._

## 🛡️ CI Security (fail-closed gate)

Latest scan: **2026-08-07** · source `security.yml#31225751724` · critical-gate **✅ PASS**

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |

Prompt-injection findings: **1**

**Accepted risks** (`shipwright_accepted_risks.yaml` register):

| ID | Target | Expires | Status | Recorded under |
|----|--------|---------|--------|----------------|
| ar-2026-06-22-otel-baggage-dev-only | trivy-ignore | 2026-12-22 | active | iterate-2026-06-22-trivy-risk-accept |
| ar-2026-07-03-dependabot-cooldown-inert-config | semgrep-rule-exclusion | 2027-01-03 | active | ADR-271 |
| ar-2026-07-03-gh-owned-mutable-action-tags | semgrep-policy-toggle | 2027-01-03 | active | ADR-271 |
| ar-2026-07-28-brace-expansion-dev-only | trivy-ignore | 2027-01-28 | active | iterate-2026-07-28-security-pyasn1-bump-brace-accept |

**Inline suppressions** (`# nosemgrep`, anti-ratchet baseline):

| Rule | Sites | Baseline | Recorded under |
|------|-------|----------|----------------|
| `python.lang.compatibility.python36.python36-compatibility-Popen1` | 2 | 2 | iterate-2026-08-05-inline-suppression-ratchet |
| `python.lang.compatibility.python36.python36-compatibility-Popen2` | 2 | 2 | iterate-2026-08-05-inline-suppression-ratchet |
| `python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected` | 6 | 6 | iterate-2026-08-05-inline-suppression-ratchet |
| `python.lang.security.audit.non-literal-import.non-literal-import` | 9 | 9 | iterate-2026-08-05-inline-suppression-ratchet |
| `python.lang.security.audit.subprocess-shell-true.subprocess-shell-true` | 1 | 1 | iterate-2026-08-05-inline-suppression-ratchet |

_Inline suppressions are deliberately **not** tracked in the accepted-risk register: an offline reconciler would have to mirror the scanner's own suppression semantics and would drift, and a re-review date does not fit a permanent false positive at a fixed source site. The control is the anti-ratchet above — the count cannot grow without a recorded decision. This is visibility, **not** per-site review: unlike a register entry, no site here carries an owner or a re-review date._

_Ingested from CI `findings.json` (public-safe: severity counts + gate verdict only — no finding detail). The local `.shipwright/securityreports/` is intentionally **not** used (stale/FP-laden). Open high/critical feed the Control Grade's Security dimension._

## Quality Indicators

| Metric | Value | Status | Why warn? |
|--------|-------|--------|-----------|
| Pipeline phases completed | n/a (adopted) | INFO |  |
| Work events (iterate) | 494 changes | INFO |  |
| Recent changes traced to an FR | 8/30 (27%) | INFO | feature vs. maintenance mix — informational, does not affect the Control Grade |
| All unit tests passing | 15200/15200 | PASS | +1 change(s) since last full suite |
| Architecture decisions | 328 ADRs | INFO |  |
| Iterate tests passing | 68/120 testable changes tested | WARN | 52 testable change(s) without tests — see test-evidence.md |
| Dependencies | 11 packages | INFO |  |
| Copyleft risk | 0 | PASS |  |
| Triage open | 35 open | WARN | 35 actionable item(s) — see ../agent_docs/triage_inbox.md |
| Bloat over-limit (grandfathered) | 152 | INFO |  |
| Bloat in allowlist | 200 entries | INFO |  |
| Bloat ratchet delta | -120 lines | PASS |  |

## Project Velocity

- Iterate: 494 changes (2026-05-02 → 2026-08-07)
- Last activity: 2026-08-07

## External LLM Review Evidence

| Split | Status | Provider | Findings | Self-review fallback | Reason |
|-------|--------|----------|----------|----------------------|--------|
| 01-adopted | missing | — | 0 | no | — |
| adr | missing | — | 0 | no | — |
| campaigns | missing | — | 0 | no | — |

## 🔎 Consistency Audit

**Last run 2026-07-28 (10 days earlier): FAIL** · 59 checks — 47 pass, 2 fail, 10 skip.

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

