# Mini-Plan: fix-launch-blocker-tests

Run ID: iterate-2026-05-18-fix-launch-blocker-tests

## Approach

Five independent root-cause fixes, ordered largest-first. Each group has a
known failing test that flips green; no group depends on another.

### G1 — bash hooks call the Microsoft-Store `python3` stub (9 failures)

`python3` on default Windows 11 resolves to the App-Execution-Alias stub
(`WindowsApps/python3` → prints "Python was not found", exits non-zero).
The 4 shell hooks that parse their JSON payload via `python3 -c` therefore
get an empty `FILE_PATH`/`COMMAND` and exit 0 — silently no-op. This is a
real production bug: `check_secrets.sh` is a security control.

**Fix:** add a `_resolve_python()` helper to each of the 4 hooks — probe
`python3`, `python`, `py` and pick the first that actually executes
(`"$c" -c "import sys"` succeeds; the Store stub fails this). Replace the
hardcoded `python3` invocation with the resolved interpreter. Keep
fail-open (exit 0) when no interpreter resolves — unchanged behavior, and
the resolver finds `python`/`py` on every real install.

Files: `shared/scripts/hooks/check_secrets.sh`,
`shared/scripts/hooks/check_file_size.sh`,
`plugins/shipwright-build/scripts/hooks/validate_command.sh`,
`plugins/shipwright-build/scripts/hooks/check_destructive_migration.sh`.

### G2 — workflow-dormancy tests vs. Go-Live activation (3 failures)

`test_workflow_shape.py::TestDormantTriggers` enforces commented-out
triggers + a `DORMANT` banner. Launch-prep Step 4 activated the workflows
(user-approved Go-Live action — the test's own message says "user
activates them manually at Phase B / Go-Live"). The pre-launch invariant
is now obsolete.

**Fix:** rewrite `TestDormantTriggers` → `TestActiveTriggers`: assert the
`pull_request` / `push` / `schedule` triggers ARE present in `ci.yml`,
`codeql.yml`, `security.yml` and the DORMANT banner is gone. This is the
Test-Update-Klausel — the test codifies the launch-state rule.

### G3 — `parse_tests_run` regex breaks on ANSI color (2 failures)

Per ADR-048 (conventions.md): pytest under `uv run` emits ANSI color even
without a TTY; `\x1b[1m7 passed` has no word boundary before the digit, so
`\b(\d+)\s+passed\b` matches 0. The F0.5 callers were told to pass
`--color=no`, but the parser itself stays fragile and the real-pytest
tests exercise it without that flag.

**Fix:** strip ANSI escapes in `parse_tests_run` before the regex
(`re.sub(r"\x1b\[[0-9;]*m", "", stdout)`). Root-cause fix; `--color=no`
convention stays as belt-and-suspenders.

### G4 — canon detector false-positive on prose (1 failure)

`test_no_legacy_artifact_paths[compliance-migrated]` flags
`conventions.md` lines 42 + 74 because the prose contains the substring
`compliance/`. The detector's text-regex matches legacy artifact paths but
cannot tell a real path from an English sentence.

**Fix:** investigate the detector — harden it so a `compliance/` token
inside running prose (not a path-shaped context) is not flagged, OR add
the doc to the detector's allowlist if prose exclusion is structurally
hard. Decide after reading the detector. No weakening of real-path
detection.

### G5 — deploy missing-token warning omits the variable name (1 failure)

`validate-deploy.py` reports `jelastic_token: false` correctly but its
`warnings` list entry does not contain the literal `JELASTIC_TOKEN`.

**Fix:** make the warning string name the env var. Read the script first
to confirm whether the test or the message drifted.

### G6 — ci.yml cannot find pytest (CI config)

`ci.yml` runs `uv sync && uv run pytest` per plugin. Plugins declare
pytest as an optional `dev` extra (`shipwright-build`) or not at all
(`shipwright-iterate`), so `uv sync` does not install it. Activated CI
would fail immediately.

**Fix:** change the plugin-test + integration-test steps to
`uv run --with pytest --with pytest-mock pytest ...` (the form proven to
work in reproduction).

## Test Strategy

- Per group: run the named failing test(s) → confirm red → fix → confirm green.
- After all groups: full sweep — every plugin suite + `shared/tests/` +
  `integration-tests/` — must be 0 failed.
- G1 extra probe: run `check_secrets.sh` manually on this machine (the
  Store-stub environment) with an AWS-key payload → must exit 2.

## Risk / Notes

- High-sensitivity areas touched: `plugins/*/hooks/`, `shared/`,
  `.github/workflows/`, `shipwright-security/` (per conventions.md). Extra
  self-review care; no new shell `eval`/`exec`, no new dependencies.
- `touches_io_boundary`: hooks parse JSON stdin — Boundary Probe satisfied
  by the existing subprocess round-trip tests.
