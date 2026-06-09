# B2 — Phase-aware SessionStart dispatcher

- **Type:** change (topology refactor)
- **Complexity:** medium
- **Depends on:** B0
- **Supersedes:** `proposed-sessionstart-dedup-guard.md` (the interim
  once-per-event dedup). If the interim shipped first, B2 removes that
  guard code and replaces it with the real topology fix.

## Goal

Collapse the SessionStart fan-out — `capture_session_id.py` (×12, the
source of the visible Phase-Quality spam), `check_artifact_drift.py`
(×12), `session_start_using_shipwright.py` (×12), `phase_session_start.py`
(×9) — into **one** SessionStart dispatcher owned by `shipwright-iterate`,
removed from the other 11 plugins.

## Acceptance Criteria

- [ ] **AC-1 (single injection).** SessionStart context contains the
      Phase-Quality block, the "Using Shipwright" bootstrap, and each
      drift notice **once** (today: 9–12×).
- [ ] **AC-2 (env capture preserved).** `SHIPWRIGHT_SESSION_ID`,
      `PROJECT_ROOT`, autonomous-loop vars, and the `CLAUDE_ENV_FILE`
      write are still emitted (these were per-process; the dispatcher
      emits them once authoritatively).
- [ ] **AC-3 (no active-plugin signal needed).** SessionStart injections
      are byte-identical across plugins, so the dispatcher just emits the
      canonical set once — no phase resolution required for the
      *injection* content (resolver only needed if phase-specific
      bootstrap is later added).
- [ ] **AC-4 (11 plugins de-registered).** Shared SessionStart hooks
      removed from the other 11 `hooks.json`. iterate-only SessionStart
      hooks (`import_github_findings.py`) stay.
- [ ] **AC-5 (consumer back-compat).** Older cached installs keep working.
- [ ] **AC-6 (opt-out lever intact).** `SHIPWRIGHT_PHASE_QUALITY_MODE=
      audit_only` still suppresses the Phase-Quality injection.

## Tests

- One SessionStart event → exactly one of each injected block.
- Env vars + CLAUDE_ENV_FILE still written.
- `audit_only` suppresses Phase-Quality block.
- Regression: the 11×-duplication asserted absent.

## Out of scope

- Stop side (B1), Prompt (B3), PostTool (B4).
