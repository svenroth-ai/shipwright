# Iterate Spec: Quote ${CLAUDE_PLUGIN_ROOT} in plugins/*/hooks/hooks.json

- **Run ID:** iterate-2026-05-03-hooks-json-quoting
- **Type:** bug
- **Complexity:** small (mechanical sweep + 1 regression test; deferred from ADR-020)
- **Status:** draft
- **Parallel iterate:** runs alongside `iterate/adopt-env-local-scaffold`
  (ADR-021, Sven's bug 3 in another session). Disjoint file scopes — no
  conflict expected at merge time.

## Goal

Close the deferred lurking bug from ADR-020. Every plugin's
`hooks/hooks.json` file embeds `uv run ${CLAUDE_PLUGIN_ROOT}/...` (or
`bash ${CLAUDE_PLUGIN_ROOT}/...`) without quoting the path argument.
Same shell word-splitting failure mode as the suggest_iterate hook
installer — but the trigger is different: it fires when the *plugin
install path* contains spaces, which today only happens for users
whose Windows username contains a space.

## Bug detail

Repo-wide grep across `plugins/*/hooks/hooks.json` (12 files) found
~78 unquoted `${CLAUDE_PLUGIN_ROOT}` references inside hook command
strings. Each is shell-executed by Claude Code on the corresponding
hook event (SessionStart, UserPromptSubmit, Stop, PreToolUse, etc.).

For a user with a Windows username like `John Doe`, the cache path is
`C:\Users\John Doe\.claude\plugins\cache\shipwright\<plugin>\<version>\`.
`${CLAUDE_PLUGIN_ROOT}` resolves to that path; the shell splits at the
first space; uv exits non-zero with `Failed to spawn: C:\Users\John,
exit 2`. Per Claude Code's hook contract, non-zero on a blocking hook
event blocks the operation. Effect: no SessionStart hooks fire, no Stop
hooks fire, no PreToolUse validation runs. The Shipwright SDLC pipeline
silently breaks for that user.

This was empirically verified for the SAME failure mode in
ADR-020's TEST 1 (replacing the suggest_iterate path with a path
containing spaces). The trigger here is different (plugin cache path,
not target project path) but the failure mechanism is identical.

## Acceptance Criteria

- [ ] **AC-1 — All hooks.json `command` strings quote
  `${CLAUDE_PLUGIN_ROOT}`.** Repo-wide invariant: every value of the
  shape `"command": "uv run ${CLAUDE_PLUGIN_ROOT}/..."` (or `bash`)
  must wrap the path placeholder in escaped double quotes:
  `"command": "uv run \"${CLAUDE_PLUGIN_ROOT}/...\""`.
- [ ] **AC-2 — JSON validity preserved.** All 12 `plugins/*/hooks/hooks.json`
  files still parse as valid JSON after the sweep.
- [ ] **AC-3 — Regression test.** A new shared test asserts the AC-1
  invariant repo-wide (so future hooks added without quoting get
  caught at test time, not at install time on a user's machine).

## Out of Scope

- `--no-project` flag for between-phase hooks. Unlike the
  suggest_iterate UserPromptSubmit hook (which runs in the *target
  project's* CWD with potentially-corrupt project `.venv`), these
  between-phase hooks are part of the framework's own pipeline and
  expect uv to resolve normally. Adding `--no-project` here would
  prevent uv from finding plugin-local pyproject.toml dependencies.
- Quoting other env var expansions (`${CLAUDE_PROJECT_DIR}`,
  `${SHIPWRIGHT_*}`) — repo grep already showed those are not used in
  shell-executed contexts (see ADR-020 TEST 3).
- Touching any installer-side code; the previous iterate covered that.

## Affected FRs

- **FR-01.01 through FR-01.13** indirectly — every plugin's
  between-phase hooks fall under its FR. But the change is mechanical
  documentation/quoting, no FR semantics change. No new ACs needed
  in spec.md (per the iterate skill's "Spec Update" guidance: this is
  not an FR-level behavior change).

## Test Strategy

- New `shared/tests/test_hooks_json_quoting.py`: walks
  `plugins/*/hooks/hooks.json`, parses each, traverses the structure,
  asserts every `command` string that references `${CLAUDE_PLUGIN_ROOT}`
  has the placeholder wrapped in `\"..\"`. Catches future regressions.
- JSON-parse all 12 files post-sweep (verified during build).
- Cross-reference existing `test_phase_plugin_hooks_consistency.py` —
  it should still pass (it checks hook order/presence, not command
  string format).
