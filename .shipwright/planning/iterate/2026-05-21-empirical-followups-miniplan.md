# Mini-plan: empirical-followups

- **Run ID:** iterate-2026-05-21-empirical-followups
- **Spec:** `.shipwright/planning/iterate/2026-05-21-empirical-followups.md`
- **Status:** draft (pre-approval)

## Strategy

Sequenced for risk-amortization: smallest blast radius first, biggest after. AC-3 (path-canon ALLOWLIST extension) lands first — it's a 1-3 line config edit that unblocks the baseline test count. AC-1 (new `triage_add.py` CLI) lands next — net-new file, no risk to existing producers. AC-2 (test-evidence synthesis) lands last — modifies existing rendering behavior, biggest review surface, fully gated by the boundary-probe round-trip test.

## Files to change

### AC-3 — Path-canon ALLOWLIST (smallest, lands first)

| File | Action | Reason |
|---|---|---|
| `shared/scripts/lib/artifact_migrations.py` | Edit | Add `.shipwright/agent_docs/triage_inbox.md` to `ALLOWLIST['compliance']` (and to siblings if/when they drift on the same root cause). The triage_inbox.md is a regen artifact: a per-card launchPayload legitimately mentions `plugins/shipwright-compliance/scripts/tools/update_compliance.py`, where `-compliance/` trips the regex `(?<![\w/.\\])compliance/`. The path is structurally legitimate; allowlist is the right fix per the file's existing comments about plugin-prefixed forms. |
| `shared/tests/test_artifact_path_canon.py` | (no edit) | Verifies the test now passes 4/4 without changes to the test itself. |

### AC-1 — `triage_add.py` CLI for manual FR stamping

| File | Action | Reason |
|---|---|---|
| `shared/scripts/tools/triage_add.py` | **Create** | New ~120 LOC CLI. Argparse `--title --severity --kind --detail --fr-id --source --evidence-path --commit --run-id`. Validates `--fr-id` matches `^FR-\d+\.\d+$` (regex). Delegates to `triage.append_triage_item` with all kwargs. Prints `{success, id, frId}` JSON. Returns exit 0 on success, 1 on invalid input. |
| `shared/tests/test_triage_add_cli.py` | **Create** | New ~80 LOC test. Coverage: happy path (valid fr_id → card with frId populated), regex rejection (`--fr-id foo` → exit 1, "invalid_fr_id"), no fr_id (optional, card with frId=null), default severity/kind values, source validation. Round-trip: call CLI → read triage.jsonl → assert frId present + matches input. |

### AC-2 — Full Suite Runs synthesis from work_events

| File | Action | Reason |
|---|---|---|
| `plugins/shipwright-compliance/scripts/lib/test_evidence.py` | Edit | Add new helper `_full_suite_runs_from_work_events(data)` that emits the same `## Full Suite Runs` markdown table from `data.work_events` (when `data.test_runs` is empty AND `data.work_events` has any entry with `tests_total > 0`). Modify `generate()` to call new helper when test_runs is empty. Row shape: `Run | Trigger | Unit | Integration | pgTAP | E2E | Smoke | Date` — Trigger = `work_event.source`, Unit = `tests.passed/tests.total`, Integration / pgTAP / Smoke = `—`, E2E = `—` (e2e_run boolean doesn't carry counts), Date = `timestamp[:10]`. Cap to last 30 work_events (matches the practical scroll cap of the test_run path). |
| `plugins/shipwright-compliance/tests/test_test_evidence.py` | Edit | Add 3-4 new tests: (a) synthesis branch — empty test_runs, populated work_events → Full Suite Runs table present with correct row count + columns; (b) original branch — populated test_runs → original behavior unchanged (existing test should still pass); (c) both populated → test_run path wins (no double-render); (d) round-trip — write fixture, render, parse table rows back, assert column count + ordering. |

## Test strategy

- **TDD red-then-green per AC** — write failing test first, watch it red, implement, watch it green.
- **Boundary probe** mandatory for AC-2: real producer→file-on-disk→consumer round-trip across both the test_run-only branch and the work_event-only branch.
- **AC-3 boundary probe:** the `test_no_legacy_artifact_paths` test IS the producer/consumer round-trip — extending ALLOWLIST and re-running the test confirms the fix.
- **AC-1 boundary probe:** unit test that writes via CLI → reads back via `triage.read_all_items` → asserts frId is present in the resolved view, then runs `update_compliance.py --phase iterate` against the tmp project → asserts the RTM contains the deep-link.

## Alternative considered (rejected)

**Alternative for AC-1:** Extend `record_event.py task_created` to also emit a triage card when `--fr-id` is set. Rejected — record_event.py owns event-log writes; mixing in triage-card emission creates two responsibilities behind one CLI and tightens the event_log ↔ triage coupling. A standalone CLI keeps surfaces orthogonal and lets future producers (security, sbom, test-evidence) opt into FR-stamping without modifying record_event.py.

**Alternative for AC-2:** Wire a real `record_event.py --type test_run` call into the test runner (or into a Stop-hook). Rejected as out-of-scope — the synthesis path delivers the same operator-facing visibility today without requiring a producer-side wiring change across N test invocation points. The synthesis path can be retired later if real test_run events become routine.

## Effort estimate

- AC-3: 15 min (edit + verify)
- AC-1: 45 min (CLI + tests)
- AC-2: 60 min (synthesis + tests + round-trip probe)
- External review: 5 min (kick off, wait for results)
- Self-review + full code review + tests + finalize: 30-45 min

Total: 2.5-3 hours.
