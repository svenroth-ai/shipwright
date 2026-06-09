# B4 — Phase-aware PostToolUse(Write|Edit) dispatcher

- **Type:** change (topology refactor)
- **Complexity:** small → medium
- **Depends on:** B0 (and the B1/B2 dispatcher pattern)

## Goal

Collapse `check_file_size.py` (×12) and `mark_plugin_edit.py` (×12) — both
on the `Write|Edit` matcher — into **one** PostToolUse hook owned by
`shipwright-iterate`, removed from the other 11 plugins.

## Acceptance Criteria

- [ ] **AC-1.** One Write/Edit → file-size check runs **once** and
      plugin-edit mark recorded **once** (today 12× each).
- [ ] **AC-2 (universal, not phase-scoped).** Both checks are
      phase-agnostic (file size + plugin-edit tracking apply always), so
      the dispatcher runs them unconditionally — no resolver gating
      needed. (Resolver only relevant if a phase-specific PostToolUse
      check is later folded in.)
- [ ] **AC-3.** De-registered from the other 11 `hooks.json`. build's
      extra PostToolUse hooks (`track_tool_calls.py`,
      `check_destructive_migration.sh`, `check_secrets.sh`) stay in build.
- [ ] **AC-4.** Consumer back-compat preserved.

## Tests

- One Write → one size-check + one edit-mark; de-registration regression;
  large-file FAIL still surfaced once.

## Note

Highest per-action frequency (every Write/Edit) — the 12× duplication is
pure wasted subprocess spawns. Good wall-clock win, low semantic risk.
