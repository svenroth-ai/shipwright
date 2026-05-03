# Iterate Spec: suggest_iterate hook installer — quoted path + --no-project + Shape-A→B upgrade-in-place

- **Run ID:** iterate-2026-05-03-suggest-iterate-quoted-path
- **Type:** bug
- **Complexity:** medium (manual override — repo-wide pattern propagation, integration with concurrent ADR-019 work)
- **Status:** draft

## Context

Builds directly on ADR-019 (Sven, 2026-05-02) which switched the
suggest_iterate hook installer from Shape A (bare `{type, command}`,
rejected by Claude Code) to Shape B (matcher-group
`{hooks: [{type, command}]}`). ADR-019 fixed the *carrier shape* but
left the *command literal* unquoted and missing `--no-project`, which
is a separate failure mode against any target project on a path
containing spaces.

## Goal

Stop the suggest_iterate UserPromptSubmit hook from blocking every
prompt on adopted projects whose path contains spaces (OneDrive-synced
folders, "Program Files", Windows usernames with spaces). Wrap the
path embedded in the installed hook command in double quotes, add
`--no-project` so a corrupt project `.venv` cannot stall uv on
resolution, and teach the installer to **upgrade** any of the known
legacy entries in place (rewrite to canonical Shape B carrier +
canonical command) so already-adopted projects get fixed by re-running
`/shipwright-adopt` rather than requiring manual settings.json edits.

## Bug detail

After ADR-019, `plugins/shipwright-adopt/scripts/lib/hook_installer.py`
emits the canonical Shape B entry but with the unquoted command:

```
uv run ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/suggest_iterate.py
```

Claude Code expands `${CLAUDE_PLUGIN_ROOT}` and runs the result through
a shell. On a project at `C:\Users\SvenRoth\dinovo GmbH\AI Backup -
Documents\03 Development\shipwright` the expansion contains spaces and
the shell splits the path. uv reports `Failed to spawn:
C:\Users\…\dinovo, exit 2`. Per Claude Code's hook contract, a non-zero
exit on `UserPromptSubmit` blocks the user prompt — symptom is "Claude
is dead, no error visible." The same broken snippet is also documented
at `plugins/shipwright-project/skills/project/SKILL.md` Step 4.5 and
`plugins/shipwright-run/skills/run/SKILL.md` Step 4.5.

## Acceptance Criteria

- [ ] **AC-1 — Installer emits canonical command.** Running
  `install_suggest_iterate_hook(<path>)` against a fresh project writes
  a Shape B entry whose inner `sub.command` literal equals exactly:
  `uv run --no-project "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/suggest_iterate.py"`.
- [ ] **AC-2 — Idempotent upgrade of legacy entries (Shape B carrier).**
  Running the installer against a project whose `.claude/settings.json`
  has a Shape B row with any of the six known legacy command literals
  upgrades that row's `sub.command` to canonical, returns
  `{"installed": False, "already_present": True, "upgraded": True, ...}`,
  and does not append a duplicate.
- [ ] **AC-3 — Idempotent upgrade across Shape A → Shape B.** Running
  the installer against a project whose `.claude/settings.json` has a
  Shape A row (bare `{type, command}` carrier, which Claude Code
  rejects per ADR-019) with EITHER a legacy or canonical command
  literal REPLACES that entire row with a fresh canonical Shape B
  entry, returns `upgraded: True`, and does not append a duplicate.
  Both the carrier shape AND the command literal must be fixed, or
  the next user prompt remains blocked.
- [ ] **AC-4 — True no-op when canonical.** Running the installer
  against a project that already has a Shape B row with the canonical
  command returns `{"installed": False, "already_present": True,
  "upgraded": False, ...}` and does not pointlessly rewrite the file.
- [ ] **AC-5 — Documented snippets match.** The
  `.claude/settings.json` JSON snippets in
  `plugins/shipwright-project/skills/project/SKILL.md` and
  `plugins/shipwright-run/skills/run/SKILL.md` use the matcher-group
  Shape B carrier + canonical command. Anyone copy-pasting from the
  docs gets a snippet that both parses in Claude Code (Shape B) AND
  survives target-project paths containing spaces (quoted +
  `--no-project`).
- [ ] **AC-6 — No regression for clean re-run.** Running adopt twice
  in a row on a project that had no prior settings.json results in
  exactly one Shape B canonical hook entry under `UserPromptSubmit`.

## Out of Scope

- `plugins/*/hooks/hooks.json` between-phase hooks (consumed by Claude
  Code from the *plugin install location* `~/.claude/plugins/cache/...`,
  which only contains spaces when the user's home directory does —
  Windows usernames with spaces). Different blast radius; touch in a
  follow-up iterate if a user reports it on a custom plugin install
  path.
- `${CLAUDE_PROJECT_DIR}` quoting in scripts/hook bodies. The bug
  report mentioned both, but verification shows only
  `${CLAUDE_PLUGIN_ROOT}` is embedded inside the installed command
  string. `CLAUDE_PROJECT_DIR` is consumed inside Python, where shell
  quoting does not apply.

## In-scope sweep (Category B)

A repo-wide sweep wraps every documented `uv run {placeholder}/...`
snippet in double quotes across `plugins/*/skills/`,
`plugins/*/agents/`, and `shared/scripts/` docstrings — same
conceptual fix, same risk class (the LLM agent that renders these
snippets into shell at runtime would otherwise propagate the
unquoted form). Pure text edit; no behavior change on systems
without spaces; teaches the right pattern going forward.

## Affected FRs

- **FR-01.13** (`/shipwright-adopt`): hook installer is part of
  adopt's scaffold contract; ACs cover the canonical install +
  upgrade-in-place behavior across Shape A/B carrier transitions.
- **FR-01.02** (`/shipwright-project`): documents the same hook
  install in the project SKILL.md; AC covers the matching documented
  form.
- **FR-01.01** (`/shipwright-run`): documents the same hook install
  in the run SKILL.md; AC same as FR-01.02.

## Relationship to ADR-019

This iterate **layers** on ADR-019 rather than competing with it.
ADR-019 fixed the carrier shape (Shape A → Shape B), this iterate
fixes the command literal (unquoted → quoted + `--no-project`) AND
generalizes the upgrade-in-place semantics to cover both axes (so
already-adopted projects whose entries still have the old shape OR
the old command get fixed automatically on re-run).

## Test Strategy

- Existing tests from origin/main (Shape B install, idempotency, no
  Shape-A carrier, both legacy aliases) all retained verbatim.
- New parametrized regression in
  `plugins/shipwright-adopt/tests/test_hook_installer.py`:
  - `test_installer_emits_quoted_command_with_no_project` — exact
    equality with canonical literal (AC-1).
  - `test_installer_upgrades_legacy_unquoted_entry_in_place_shape_b`
    — parametrized over 6 legacy command literals carried in Shape B
    (AC-2).
  - `test_installer_upgrades_legacy_shape_a_entry_to_shape_b` —
    parametrized over 6 legacy command literals carried in Shape A,
    asserts both shape conversion AND command rewrite (AC-3).
  - `test_installer_upgrades_shape_a_canonical_command_to_shape_b` —
    edge case from ADR-019: Shape A carrier with canonical command
    still upgrades (AC-3 corner).
  - `test_installer_idempotent_returns_upgraded_false_when_already_canonical`
    — true no-op when correct (AC-4).
- Run full pytest for `plugins/shipwright-adopt/tests/` to confirm
  nothing in adopt regressed.
- Run shared hook tests via the iterate plugin's `.venv`.
- Smoke check: grep verification that the documented snippets and
  every uv-run path placeholder in skills/agents/docstrings now use
  the quoted form.
