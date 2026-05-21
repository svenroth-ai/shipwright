# Test Status Overrides

Single source of truth for FAIL-row dismissals from `test-evidence.md` +
`traceability-matrix.md`. The current RTM/test-evidence generators do
not consume this file — they continue to render FAIL based on the
event-log snapshot at commit time. Plan-of-record: Iterate B.4 (RTM
generator refactor) wires this file as the dismiss-aware overlay so
historic-dismissed rows render as `FAIL [dismissed YYYY-MM-DD — historic]`.

Until B.4 lands, this file is the **audit trail** for "we looked at
these FAILs and they are NOT lived bugs". Reviewers (Senior, audit)
should treat any FAIL in RTM/test-evidence that is also listed here as
historic.

Created by Phase 0d of the artifact-polish plan
(`~/.claude/plans/ich-habe-ein-paar-imperative-emerson.md`).

---

## Iterate-row dismissals

Snapshot FAILs at commit time. Each entry below was a `work_completed`
event whose `tests.passed < tests.total`. Later iterates (and current
test suites) confirm the failing-at-commit-time tests are either green
or have been retired.

| event_id | commit | description | tests at commit | dismissed_at | reason |
|---|---|---|---|---|---|
| evt-16154172 | cd957a0 | triage detector dedup + auto-resolve (rebased onto #31) | 1776/1783 (7 fail) | 2026-05-21 | snapshot-only; same fix as evt-e14e5f26; both rebased onto post-test-hygiene main. Later iterates show 122/122 + 2519/2526 + 1985/1985 etc. all green for the triage producer surface. |
| evt-e14e5f26 | 931e6b5 | triage detector dedup + auto-resolve | 1776/1783 (7 fail) | 2026-05-21 | snapshot-only; original of the rebased fix above. |
| evt-{events-worktree-aware} | 34a7987 | events.jsonl worktree-awareness: F7/verifier/dashboard resolve the log via git-common-dir | 2519/2526 (7 fail) | 2026-05-21 | snapshot-only; the new SSoT helper `shared/scripts/lib/events_log.py::resolve_events_path` is covered by `shared/tests/test_events_log_ssot.py` which is green today. |
| evt-{triage-1a-rebased} | f638908 | Triage Inbox Iterate 1a (rebased onto post-test-hygiene main) | 1642/1649 (7 fail) | 2026-05-21 | snapshot-only; same fix as the unrebased commit below; later Triage Iterate 2 + GitHub importer iterates verified storage/aggregator/promote paths green. |
| evt-{triage-1a-original} | 6ba7df1 | Triage Inbox Iterate 1a | 1642/1649 (7 fail) | 2026-05-21 | snapshot-only; original of the rebased fix above. |
| evt-{fr-parser-5col} | 656f96f | FR-table parser accepts 5-col adopt format + drift protection | 1594/1628 (34 fail) | 2026-05-21 | snapshot-only; the RTM data-collection followup (commit ea24bf4) shows 312/312 green for the parser surface; FR table parsing in compliance dashboard is exercised by `test_traceability_checks.py` (green). |
| evt-{plugin-owned-suggest-iterate} | a05ff22 | plugin-owned suggest_iterate hook (ADR-030); retired hook_installer + 7 SKILL.md stanzas + A6 verifier | 1691/1716 (25 fail) | 2026-05-21 | snapshot-only; re-verified 2026-05-21 by running hook-related test set: `test_hooks.py + test_phase_session_hooks.py + test_phase_plugin_hooks_consistency.py + test_hooks_json_wrapper.py + test_hooks_json_quoting.py` → 119/119 PASSING. |

## FR-level dismissals (RTM "FAIL" status that is generator-stale)

Each entry below has FAIL status in `traceability-matrix.md` despite
current iterate test runs being green. Diagnosed root cause: the RTM
generator sets FAIL from an older `work_completed` event whose tests
< total, and does not consult later events whose tests are equal-and-
green. Iterate B.4 (RTM generator refactor + Action-Unit triage link)
addresses this structurally.

| fr_id | title | rtm-shown current tests | last-verified | dismissed_at | reason |
|---|---|---|---|---|---|
| FR-01.01 | Orchestrate the full Shipwright SDLC pipeline | 1691/1716 (25 fail) | 2026-05-05 (iter) | 2026-05-21 | re-verified 2026-05-21 — SKILL.md Step 4.5 ("no install step needed") AC is satisfied; 119/119 hook-related tests passing. The 25-fail snapshot was Iterate plugin-owned-suggest_iterate-hook at commit time; superseded. |
| FR-01.02 | Decompose project requirements (IREB) | 140/140 | 2026-05-16 (iter) | 2026-05-21 | STALE — current tests 140/140 passing per spec-impact gate iterate (evt-3cee5b32 / c16d711). Generator did not pick up the green run because the older FAIL event still anchors the FR status column. |
| FR-01.10 | Generate audit-ready compliance documentation | 140/140 | 2026-05-16 (iter) | 2026-05-21 | STALE — same root cause as FR-01.02; spec-impact gate iterate touched this FR too and its tests are green. |
| FR-01.11 | Complexity-adaptive SDLC for ongoing changes | 140/140 | 2026-05-16 (iter) | 2026-05-21 | STALE — same root cause; events.jsonl worktree-awareness + spec-impact gate iterates both touched FR-01.11 with green tests. |
| FR-01.13 | Onboard an existing (brownfield) repository | 304/304 | 2026-05-16 (iter) | 2026-05-21 | STALE — current 304/304 green per fix-adopt-external-review-config-defaults (evt-38e36ac6 / 3f5777d). |
| FR-01.14 | Pre-backlog triage buffer | 122/122 | 2026-05-20 (iter) | 2026-05-21 | STALE — current 122/122 green per artifact-based GitHub security producer iterate. |

## Pending re-verify (none)

All shipwright FAIL rows have been classified above.

## Out of scope for Phase 0d

- **Coverage gaps** (FRs with `NOT VERIFIED` status in RTM): not stale-FAILs; require new tests or explicit `no-automated-coverage` annotation. Track separately.
- **Generator refactor** (Iterate B.4): consumes this file as overlay so future RTM/test-evidence renders dismissed rows with the `dismissed` annotation.

---

_Last updated: 2026-05-21 by Phase 0d (artifact-polish plan)._
