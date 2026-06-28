# Iterate: check_security_scan / check_rtm_coverage PreToolUse hooks — fail-open + robust invocation

- **Run ID:** iterate-2026-06-28-security-scan-hook-failopen
- **Intent:** CHANGE (modify existing hook behavior)
- **Complexity:** medium (self-escalated from classifier `small`)
- **Risk flags:** `cross_component` (hooks.json + `hooks/*.py` — diff-recomputed by F11 `check_integration_coverage`), `touches_io_boundary` (hooks.json)
- **Spec Impact:** MODIFY (hook robustness; no functional gate-decision change)

## Problem (root cause)

The compliance plugin registers **two** PreToolUse `Bash` hooks
(`check_rtm_coverage.py`, `check_security_scan.py`) in
`plugins/shipwright-compliance/hooks/hooks.json`, invoked via
`uv run "<...>.py"` **without `--no-project`**. Because the compliance plugin
declares a real dependency (`pyyaml`), every such `uv run` performs
project/environment resolution + sync on **every Bash tool call**. On Windows,
with two of these firing per Bash call and concurrent `uv` invocations
contending on the uv cache / venv lock, this intermittently fails. A failed
`uv run` surfaces to Claude Code as a hook execution error (the observed
"No stderr output") and — because `uv` can exit non-zero (incl. `2`, which
Claude Code treats as a PreToolUse **block**) — **fail-CLOSES**, blocking the
unrelated Bash call (git add, test runs, file reads). The matcher is `Bash`, so
it blocks **all** Bash calls, not just deploy/commit. Retries clear it →
flakiness, not deterministic policy. Observed in
`iterate-2026-06-27-codeql-security-hardening`.

The hook **logic** is already correctly scoped (early-return 0 unless the
command is a deploy / `git commit`) and already fails open on a stdin parse
error. The fragility is the **invocation layer** (`uv run` env-resolution) plus
an un-guarded crash path in the hook body.

## Fix (three coherent layers — maps to proposals a / b / c)

1. **Invocation robustness (root cause — proposal a's intent).** Change both
   compliance PreToolUse `Bash` hook commands to `uv run --no-project "<...>.py"`.
   These hooks use only stdlib + the pure-stdlib `lib.project_root`, so
   `--no-project` is safe and skips the per-call project sync. Established
   precedent: the iterate plugin already invokes `suggest_iterate.py` with
   `uv run --no-project`. The gate's real work is already command-scoped, so the
   common no-op path becomes both cheap **and** robust.

2. **Process-level fail-open with logged warning (proposal b).** New shared
   helper `plugins/shipwright-compliance/scripts/lib/hook_failopen.py` provides
   `run_failopen(hook_name, main_fn)`: run the hook's `main()`; on ANY
   unexpected `Exception`, append a one-line diagnostic to the **gitignored**
   `.shipwright/agent_docs/runtime/hook_errors.log` (best-effort; logging never
   re-raises) and return `0` (ALLOW). A crashing check must never hard-block
   work. The deliberate soft-block (`return 2`) is the function's normal return
   value, not an exception, so it passes through unchanged. Both hooks route
   their entrypoint through `run_failopen(...)`.

3. **Remediation / override-aware path (proposal c).** Already present
   (`additionalContext` "Continue anyway" → `compliance_overrides.log`). Kept
   intact and pinned by an assertion. No new build.

## Integration coverage (cross_component — non-dodgeable F11 gate)

`integration-tests/test_compliance_enforcement.py` gains a
`category:"integration"` class proving the pieces **compose**:
- **Invocation contract:** parse the compliance `hooks.json`; assert both
  PreToolUse Bash hook commands carry `--no-project` and the file is valid JSON
  (the io-boundary round-trip probe too).
- **Fail-open composition:** run each hook script **end-to-end as a subprocess**
  with a payload that forces a genuine internal crash
  (`{"tool_input": "not-a-dict"}` → `AttributeError` in the un-guarded body) and
  assert exit `0` + a `hook_errors.log` entry — proving the runtime guard
  composes with the real script, not just the unit-level helper.

## Confidence Calibration
- **Boundaries touched:** `plugins/shipwright-compliance/hooks/hooks.json`
  (Claude-Code hook config / io-boundary), the two PreToolUse hook scripts,
  new `lib/hook_failopen.py`, runtime log `.shipwright/agent_docs/runtime/hook_errors.log`.
- **Empirical probes run:** (1) `uv run --no-project` precedent confirmed in
  iterate's `suggest_iterate.py`; (2) `lib.project_root` import chain verified
  pure-stdlib (no pyyaml) → `--no-project` cannot break root resolution;
  (3) confirmed `{"tool_input": "<str>"}` is a real un-guarded crash path
  (`str.get` → AttributeError) usable to exercise fail-open; (4) hooks.json
  re-parsed as JSON after edit (round-trip).
- **Test Completeness Ledger:** see F5 `iterate_latest.test_completeness`; every
  behavior below → `tested`.
- **Confidence-pattern check:** asymptote — fail-open guard unit-tested with a
  raising `main_fn` AND exercised through the real subprocess; coverage — both
  hooks, both layers (invocation contract + runtime guard), plus the preserved
  exit-2 block path (regression). Integration composition — the
  `category:"integration"` test wires hooks.json contract + subprocess fail-open.

## Behaviors (→ tests)
- B1 `run_failopen` returns 0 + logs when `main_fn` raises → unit.
- B2 `run_failopen` passes through 0 and 2 unchanged when `main_fn` returns → unit.
- B3 `log_hook_error` writes to gitignored `runtime/hook_errors.log`, never raises → unit.
- B4 `check_security_scan` fails open (exit 0 + log) on `{"tool_input": "<str>"}` → subprocess.
- B5 `check_rtm_coverage` fails open (exit 0 + log) on `{"tool_input": "<str>"}` → subprocess.
- B6 Deliberate blocks still exit 2 (regression: existing suites) → subprocess.
- B7 compliance hooks.json: both PreToolUse Bash commands carry `--no-project`,
  file is valid JSON → integration.
- B8 Override/additionalContext path preserved on block → existing assertions.
