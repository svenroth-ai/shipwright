# Mini-Plan: triage-inbox-1a

- **Run ID:** iterate-2026-05-11-triage-inbox-1a
- **Worktree:** `.worktrees/triage-inbox-1a` (branch `iterate/triage-inbox-1a` off `main`)
- **Linked spec:** `2026-05-11-triage-inbox-1a.md`

## Files Touched

### NEW

| Path | AC | Purpose |
|---|---|---|
| `shared/scripts/triage.py` | 1 | Storage API (cross-plugin-importable; outside `lib/` per ADR-045) |
| `shared/scripts/tools/aggregate_triage.py` | 2 | Markdown aggregator CLI |
| `shared/scripts/tools/triage_promote.py` | 7 | Manual promote CLI (non-webui) |
| `shared/scripts/hooks/aggregate_triage_on_stop.py` | 3 | Stop-hook entry point |
| `shared/scripts/tools/scaffold_triage_inbox.py` | 6 | Scaffolder invoked by adopt (testable helper, not inline-in-SKILL) |
| `shared/tests/test_triage_schema.py` | 8 | JSONL schema validator |
| `shared/tests/test_triage_storage.py` | 8 | Round-trip + lock + idempotency |
| `shared/tests/test_triage_aggregator.py` | 8 | Status resolution + markdown |
| `shared/tests/test_triage_mapping.py` | 8 | Pure mapping fns |
| `shared/tests/test_triage_scaffold.py` | 6,8 | Scaffolder writes header + gitignore + skeleton |
| `shared/tests/test_phase_quality_triage_emit.py` | 4,8 | PhaseQuality → triage hook integration |
| `shared/tests/test_compliance_audit_triage_emit.py` | 5,8 | Compliance → triage hook integration |
| `docs/triage-inbox.md` | 9 | 1-pager pattern + flow + paths |

### MODIFIED

| Path | AC | Change |
|---|---|---|
| `shared/scripts/hooks/audit_phase_quality_on_stop.py` | 4 | After audit: for each Tier-1 FAIL (C1/C5/W3), call `append_triage_item(source="phaseQuality", ...)` with 24h dedup |
| `plugins/shipwright-compliance/scripts/audit/audit_detector.py` | 5 | After `AuditReport` build: emit new findings → triage; dismiss disappeared ones |
| `plugins/shipwright-iterate/hooks/hooks.json` | 3 | Add 3rd Stop-hook entry for `aggregate_triage_on_stop.py` |
| `plugins/shipwright-adopt/skills/adopt/SKILL.md` | 6 | Add "Step E.16 — Triage Inbox Scaffold" under Step E — Artifact Generation |
| `docs/guide.md` | 9 | Chapter 4: cross-link to `docs/triage-inbox.md` |
| `docs/hooks-and-pipeline.md` | 9 | Add entry for `aggregate_triage_on_stop` + triage.jsonl in artifact write matrix |

## Build Order (TDD, commit-per-AC)

Each step: red-failing-tests → implement → green → boundary-probe-sub-step → commit.

| # | AC(s) | Foundation? | Notes |
|---|---|---|---|
| 1 | AC-1 + AC-8 (mapping+storage tests) | yes | Pure functions first, then storage API. Boundary Probe lives in test_triage_storage.py. |
| 2 | AC-2 + AC-8 (aggregator test) | depends 1 | Aggregator after storage |
| 3 | AC-3 | depends 2 | Stop-hook registration + hook script. Validate via test_hook_output_schema_compliance.py (existing drift test will auto-pick the new hook). |
| 4 | AC-4 + AC-8 (PQ emit test) | depends 1, 3 | Patch audit_phase_quality_on_stop.py |
| 5 | AC-5 + AC-8 (compliance emit test) | depends 1 | Patch audit_detector.py |
| 6 | AC-6 + AC-8 (scaffold test) | depends 1 | scaffold_triage_inbox.py + adopt SKILL.md Step E.16 |
| 7 | AC-7 | depends 1 | Promote CLI |
| 8 | AC-9 (docs) | depends 1-7 | Final doc pass |

Estimated 6-9 commits total (some ACs combined per step).

## Test Strategy

1. **AC-1 storage tests** — pure function matrices + JSONL round-trip + file-lock contention via `concurrent.futures.ThreadPoolExecutor` + idempotent-mark_status.
2. **AC-2 aggregator tests** — fixture JSONL files (varied statuses, sources, severities) → markdown snapshot comparison (use `pytest --snapshot-update` or inline string).
3. **AC-3 hook test** — leverage existing `shared/tests/test_hook_output_schema_compliance.py` which auto-discovers new hooks; manual sanity check via `python aggregate_triage_on_stop.py < fixture_stop_event.json` should exit 0 and emit valid Stop JSON.
4. **AC-4/AC-5 producer tests** — subprocess-invoke the patched hooks with fixture-input + assert triage.jsonl content. Mock external deps (network, git) as needed.
5. **AC-6 scaffold test** — temporary project root, invoke scaffolder, assert all 3 files present + gitignore line present.
6. **AC-7 promote CLI test** — happy path + error paths (missing id, double-promote, missing task-ref).
7. **Drift protection** — existing `test_hook_output_schema_compliance.py` and `test_silent_skip_ci_discipline.py` will auto-pick the new hook + the new tests. No bypass.

## Alternative Considered (skill protocol — medium+ requires this)

**Alternative A: Put triage helper inside `shared/scripts/lib/triage.py`.**
- Pros: matches user's pre-spec literally; consistent with other lib-namespaced
  helpers like `phase_quality.py`, `events.py`.
- Cons: ADR-045 violation. AC-5 import from `plugins/shipwright-compliance/...`
  triggers the `lib/` namespace collision in test sessions that span both
  `shared/tests/` and `plugins/shipwright-compliance/tests/`. We'd ship a known
  bomb.
- **Rejected.** Path correction documented in spec Deviation Note #1.

**Alternative B: One monolithic test file `test_triage.py`.**
- Pros: simpler discoverability.
- Cons: AC-8 explicitly enumerates 4 test files (schema/storage/aggregator/
  mapping). Splitting matches the AC granularity + makes pytest output
  legible. Also matches existing pattern (`test_phase_quality.py` +
  `test_phase_quality_*.py` for sub-concerns).
- **Rejected.** Stick with 4 files + 3 producer-integration test files (7 test files total).

**Alternative C: camelCase function identifiers AND wire format.**
- Pros: maximum consistency with the user's "camelCase durchgehend"
  directive; avoids the snake_case→camelCase boundary adapter.
- Cons: violates PEP 8; breaks the existing `record_event.py` /
  `phase_quality.py` Python idiom; pyright lint complains; reviewers will
  push back. The wire format constraint is what actually matters for
  webui/leadwright compatibility.
- **Rejected.** Wire-format camelCase only; Python identifiers stay
  snake_case. Documented in Deviation Note #2.

## Risks

| Risk | Mitigation |
|---|---|
| Existing C1/C5/W3 FAILs flood triage.jsonl on first run after AC-4 lands | Dedup window (24h, by `source + detail + commit`) + AC-2 caps render at top-50 |
| audit_detector.py modification breaks compliance plugin tests | Run `uv run --directory <worktree> pytest plugins/shipwright-compliance/tests/ -v` after AC-5; F0 captures regressions |
| Cross-platform file-lock differs on Windows vs POSIX | Mirror `record_event.py:_FileLock` exactly; test_triage_storage's contention test runs on the actual platform (Windows here) |
| ADR-042 Stop-hook schema regression (additionalContext) | `test_hook_output_schema_compliance.py` will catch — that's its sole purpose |
| OneDrive hardlink reappears | Worktree already configured with `UV_LINK_MODE=copy`; document in spec |

## Definition of Done

- [ ] All 9 ACs ticked off via tests + code.
- [ ] `F0` full pytest suite (worktree) green: shared + iterate plugin + compliance plugin.
- [ ] `F0.5` `surface_verification.py --surface cli` exits 0 with `tests_run > 0`.
- [ ] Self-Review block in iterate ADR populated (7 items + Confidence Calibration).
- [ ] Full Code Review run (medium + risk flags + >100 LOC expected) — findings addressed or quarantined-with-justification.
- [ ] External LLM Review marker file present.
- [ ] CHANGELOG-unreleased.d/Added drop file written.
- [ ] ADR-046 (or next number) appended to decision_log.md.
- [ ] PR opened from `iterate/triage-inbox-1a` → `main`.
