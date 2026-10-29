# Iterate: E2E run-12 learnings (harness fixes, Plan initial state, build attribution wording, bare `python -` guard)

Run-ID: iterate-2026-10-29-e2e-run12-learnings
Type: CHANGE · Complexity: medium (hooks.json touched → `cross_component`)
Source: second end-to-end run, report `e2e-report/2026-10-29T13-12-42-805Z-z0padf`, `autorune2e/learnings-run12.md`; plus an operator request about runaway `python -` processes.

## Acceptance criteria
- AC1 (S05): loopback and placeholder URLs (`http://127.0.0.1:{port}`, `http://{DEFAULT_HOST}:{port}`) are not external use; a real host is still flagged.
- AC2 (S06): `total = passed+failed` is accepted as well as `passed+failed+skipped`; a real gap still fails.
- AC3: the report prints the preview origin the run opened.
- AC4: an agent auth failure in the terminal stops the run at once (`auth-failure`).
- AC5 (Plan): the section-writer and batch-task prompt require an `Initial state:` line in every `## Design Reference` block, copied from the mockup.
- AC6 (Build): a failed section-attribution check is repaired by re-recording the same-scope declaration with `--extra` entries; the agent does not ask whether the section is "closed".
- AC7: `sub-iterate-runner` states "always `uv run python`, never a bare `python -`".
- AC8: a PreToolUse Bash hook denies `python -` with no stdin source and any unterminated heredoc feeding an interpreter; well-formed forms pass; fail-open; `SHIPWRIGHT_BARE_PYTHON_GUARD=off` lifts it.

## Spec impact
NONE (framework tooling and prompts; no product requirement changes).

## Root-cause notes
- Item 5: the section-writer only linked the mockup, never its first-load state; the build then saw section ("none selected") vs mockup ("Reddit") and hit its contradiction STOP rule.
- Item 6 (inferred, not reproduced): the attribution check (Step 10b) runs after Step 10 has marked the section complete (and, on a split's last section, archived it and closed the phase), so the agent's "already closed" was literally true. The repair is to re-record the identical declaration plus the missing `--extra` entries (the tool overwrites, it does not merge). A follow-up could move Step 10b before Step 10; not done here.
- Hang mechanism for the `python -` guard: inferred from process start times matching runner commands; not reproduced. Which runtime (Claude Code or Codex) ran those runners is not recorded; plugin hooks do not fire under Codex.

## Not done
Leftover-process check at campaign close (not small).

## Affected Boundaries
- `hooks.json` registration → new Bash hook (stdin JSON in, deny JSON out).
- Section file format: new `Initial state:` bullet inside `## Design Reference`.

## Confidence Calibration
- **Boundaries touched:** PreToolUse hook payload; section-writer output; harness checklist inputs.
- **Empirical probes run:** guard run against both reported command shapes (denied) and closed heredoc / `-c` / piped / `<` forms (allowed); harness unit tests with templated URLs.
- **Test Completeness Ledger:** see F5c entry.
- **Confidence-pattern check:** the integration test runs the hook through its real hooks.json command line.
