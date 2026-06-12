# Iterate Spec: phase-hook lifecycle + event-log integrity (WP1)

- **run_id:** `iterate-2026-06-10-phase-hook-lifecycle`
- **campaign:** `2026-06-10-audit-2-manual` · sub-iterate **a2-1**
- **intent:** change / bug-fix (load-bearing pipeline correctness)
- **complexity:** medium (locked)
- **risk flags:** `cross_component` (hooks/*.py — diff-driven, F11 recompute),
  `touches_io_boundary` (events.jsonl producer/consumer + `*_config.json` reads),
  `touches_auth` (keyword FP; enforces mandatory review — done anyway)
- **source spec:** `Spec/audits/2026-06-10-deep-audit.md` WP1 (F1, F14, F15)

## Problem (3 confirmed findings)

- **F1 (HIGH).** `main()` of `phase_session_start.py`, `phase_session_stop.py`,
  `phase_user_prompt_validate.py` reads `SHIPWRIGHT_PROJECT_ROOT` /
  `SHIPWRIGHT_SESSION_ID` from **process env vars that no launcher sets**
  (ADR-092/097: hook processes don't inherit them). The launch card is a bare
  `claude --session-id … '/<phase>'` with no env exports; `capture_session_id`
  emits `PROJECT_ROOT` only as `additionalContext` text + writes `SESSION_ID` to
  `CLAUDE_ENV_FILE`, neither of which reaches a sibling hook's `os.environ`. So
  every phase-session hook `return 0`s immediately → the v2 claim/validate/
  complete lifecycle, the fail-closed launch validation, and `plan_next_phase`
  all silently no-op. `/shipwright-run` degrades to disconnected standalone
  sessions with a permanently-wedged run config.

- **F14 (MED).** `record_event.main()` runs the `phase_completed` dedup scan
  (`has_phase_event`) and the `--deduplicate-by-commit` check (`has_commit`)
  **before** `append_event` acquires `_FileLock`. Two concurrent phase-Stop
  firings both pass `has_phase_event()` before the first append lands →
  permanent duplicate `phase_completed`; compliance change-history / RTM
  double-count. `triage.append_triage_item_idempotent` fixed this exact class
  (scan+append in one critical section, "HIGH-1 external review").

- **F15 (MED).** `phase_session_stop` emits event types `phase_failed` and
  `stale_stop_rejected` that `record_event`'s `--type` argparse `choices`
  reject → exit 2, output discarded by the unchecked subprocess call → failure
  events never land in `shipwright_events.jsonl`, the authoritative audit log.

## Spec Impact

**NONE** — pure framework correctness fix; no FR added/modified/removed.
Classified as `change_type: tooling` at F5b (event log + hook plumbing).

## Fix Direction

1. **F1** — new `shared/scripts/lib/hook_session.py`:
   `read_hook_payload(stream)` (tolerant stdin JSON → dict),
   `resolve_session_id(payload)` (payload `session_id` → env fallback → None),
   `resolve_project_root_from_payload(payload)` (env `SHIPWRIGHT_PROJECT_ROOT` if
   a real Shipwright project → payload `cwd` if a project → `resolve_project_root()`
   fallback, ValueError→None). Rewrite each hook's `main()` to use it. Correct the
   now-false docstrings ("Runs AFTER capture_session_id.py so it can read …env").
2. **F15** — add `phase_failed`, `stale_stop_rejected` to `record_event`'s
   `--type` choices; `build_event` handles both like `phase_completed`
   (`phase` + optional `detail`). They are NOT phase-deduped (only
   `phase_completed` is).
3. **F14** — add `append_event_idempotent(project_root, event, *,
   deduplicate_by_commit=False)`: resolve path + lock once, **scan existing
   events and append under the same `_FileLock`**. `main()` keeps its cheap
   lock-free pre-checks (preserves output shape + gate ordering) but routes the
   write through the idempotent appender, which re-checks under the lock and
   returns a skip indicator when it loses the race. `append_event` signature is
   unchanged (widely imported).

## Acceptance Criteria (from sub-iterate spec)

- [ ] AC1 — A subprocess-level test drives each hook `main()` with a realistic
  Claude Code stdin payload (NO env vars) and asserts the claim/validate/complete
  path engages (integration coverage; current suite bypasses `main()`).
- [ ] AC2 — No duplicate `phase_completed` under concurrent append (test).
- [ ] AC3 — `phase_failed` / `stale_stop_rejected` land in events.jsonl (test).
- [ ] AC4 — Full F0 suite green; no new bloat crossing.

## Confidence Calibration
- **Boundaries touched:** (a) Claude-Code hook **stdin payload** →
  `(project_root, session_id)` (producer = Claude Code harness, consumer = 3
  phase hooks); (b) `shipwright_events.jsonl` append (producer = record_event,
  consumers = compliance change-history / RTM / verifiers / dashboard); (c)
  `record_event` `--type` CLI contract (producer = phase_session_stop, consumer
  = argparse + build_event).
- **Empirical probes run:**
  - *Probe 1 (F1 main-path):* drive `phase_session_start.main()` with a stdin
    payload and **no env vars** → lifecycle engages (claim + PIPELINE-CONTEXT).
    **Finding:** works; on pre-fix code main() returned 0 (no env) → the test is
    non-vacuous.
  - *Probe 2 (F1 degrade):* payload `cwd` not a project AND cwd not a project →
    standalone exit 0, no crash. **Finding:** graceful (no finding).
  - *Probe 3 (F14 atomicity):* inject a competing duplicate the instant the lock
    is entered → in-lock scan must skip. **Finding:** skips (pre-fix scan-before-
    lock would double-append). Plus 8-way concurrent subprocess record → exactly
    1 event.
  - *Probe 4 (F15 round-trip / consumer-compat):* the new `phase_failed` /
    `stale_stop_rejected` types now **newly appear** in events.jsonl — does any
    consumer choke? Searched all readers: `validate_event_log` has no type
    allowlist (only `{v,id,ts,type}` required); every counter uses a **positive**
    `type == "phase_completed"` filter, so a failed phase is correctly NOT
    counted as completed; no JSON schema enumerates a closed type set. **Finding:
    none — area exhausted** (asymptote signal; full shared suite 3348 green).
- **Test Completeness Ledger:** see `iterate_latest.test_completeness` in
  `shipwright_test_results.json` (F5). 17 behaviors enumerated; 16 `tested`, 1
  `untestable: covered-by-existing-test` (downstream consumer-compat — positive
  type filters, pinned by the existing consumer suites); 0 untested-testable.
  `category:"integration"` behavior present (full start→stop→record_event chain
  via `main()` + 8-way concurrent dedup) for the `cross_component` flag.
- **Confidence-pattern check:** **Depth** — asymptote reached (Probe 4 found
  nothing). **Breadth** — every diff behavior is in the ledger (3 hooks' main(),
  the helper's 4 functions, F14 idempotent append + lock-position, F15 two types
  + end-to-end). **Composition** — the cross_component integration test proves
  hook-stdin-resolution + phase_task_lifecycle + record_event compose end-to-end
  (the exact gap: the prior suite only exercised `run()`, never `main()`).
