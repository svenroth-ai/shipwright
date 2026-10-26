# Real end-to-end run through the WebUI (operator-started, not a CI gate)

Proves that a Brief package turns into a working chat-first Shipwright app with a **real agent**, driven the way
a person drives the WebUI, and leaves a screenshot report. It costs tokens and wall-clock time and a model run
varies, so CI never runs it. CI only checks what needs no model (the package validates, the dry harness passes,
this project's structure rules hold: `integration-tests/test_e2e_webui_project.py`).

The app it builds is the social engagement desk in `../fixtures/social-engagement/`. The answer key is
`../fixtures/social-engagement-expected-result.md` (hard items must hold, soft items are compared by eye). It sits
next to the package, not inside it, so it is not part of the package hash and is not handed to the building agent. It is not hidden from it either: with
`bypassPermissions` the agent can reach this repository through `SHIPWRIGHT_MONOREPO_PATH` and could read the file.

## One-time setup

1. WebUI checkout (separate repo `shipwright-webui`): run `npm ci` in its `server/` and `client/`.
2. In this directory: `npm install`, then `npx playwright install chromium`.
3. Local checks that need no model: `npm run typecheck` and `npm run test:unit`.

## Inputs (no defaults)

The spec refuses to start without the first three. Each is read from the process environment first, then from an
env file outside the repo (`KEY=VALUE` lines, `#` comments). The real environment always wins. The file is never
committed; `.env.example` lists the names only. The report records which source supplied each value, never a secret.

| Variable | Meaning |
|---|---|
| `SHIPWRIGHT_E2E_PERMISSION_MODE` | Agent permission mode written into the temp HOME (`permissions.defaultMode`), for example `acceptEdits` or `bypassPermissions`. A mode that still prompts stalls the run: tool-permission prompts are terminal dialogs the WebUI inbox does not see. Your decision, hence no default. |
| `SHIPWRIGHT_E2E_WEBUI_DIR` | Path of the `shipwright-webui` checkout. |
| `SHIPWRIGHT_E2E_MAX_MINUTES` | Overall wall-clock budget in whole minutes. |
| `SHIPWRIGHT_E2E_WORKDIR` | Optional. The temp project, the temp HOME and `e2e-report/` are created under it (use a folder outside the repo). Unset: OS temp directory. |
| `SHIPWRIGHT_E2E_ENV_FILE` | Optional, process environment only. Env file path. Default `../autorune2e/.env` relative to the repo root (no user path is hard-coded). |

Authentication: set `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` in the environment. Otherwise the spec copies
the Claude Code login file from the real `~/.claude` into the temp HOME and deletes the copy when the run ends
(also on failure, abort and interruption). Nothing secret is logged, screenshotted or put in the report; it only
says which source was used. With `ANTHROPIC_API_KEY` the last 20 characters are written to the temp HOME's
`.claude.json` (Claude Code's own key-approval record); the temp HOME is under the workdir and stays after the run,
so delete the run folder when you are done with it. (The spec removes `.claude.json` again when it ends.)

Exposure to know about: while the run lasts, the agent runs with the chosen permission mode and the temp HOME, so it
can read the copied login file (or the auth variables in its environment). Prefer `CLAUDE_CODE_OAUTH_TOKEN`. After a
hard kill (SIGKILL, closed console) no handler runs: the next start scrubs leftovers (login copy and `.claude.json`, only
those older than the run budget plus an hour), or delete `<workdir>/run-*/home/.claude/.credentials.json` yourself.

More things to know:
- A copied login can log you out of Claude Code if the provider rotates refresh tokens while the second copy is in use;
  prefer `CLAUDE_CODE_OAUTH_TOKEN`.
- The agent's transcripts under `<workdir>/run-*/home` persist after the run, and the terminal screenshots in the report
  may show anything the agent prints. Review the report folder before sharing it.
- From a git worktree the default env-file location resolves next to the worktrees folder, not next to your main
  checkout; set `SHIPWRIGHT_E2E_ENV_FILE` to point at the file.

## Run

From this directory, unattended (no interactive shell needed):

```
npm run e2e
```

The spec builds the WebUI, starts a second instance on its own port with the temp HOME (real plugins from this
checkout, permission mode, onboarding and folder trust written; `SHIPWRIGHT_MONOREPO_PATH` points at this
checkout; `SHIPWRIGHT_ACCEPT_FIXTURE_APPROVAL=1` is set for the server and so for the agent), creates the project
through the expert project wizard (profile `chat-first-json`), copies the package to `<project>/brief/`, starts
"New pipeline" from the task board, follows the phases, approves the design review and launches next phases the
way a user does, waits for completion, opens the app through the project preview button and exercises the chat
commands, and puts each approved mockup beside its built screen.

It ends on completion, failure, a wall-clock budget overrun, or an **idle abort**: 20 minutes without a new phase
state, project file change or terminal output change (typically a prompt it cannot answer). It fires on no progress
whether or not a prompt is found; the inbox check only adds detail to the report. It then takes a screenshot and writes
the report up to that point. `SHIPWRIGHT_E2E_MAX_MINUTES` is a real limit for the whole run, builds included.

## Output

`<workdir>/e2e-report/<timestamp>/report.md` plus the images (rendered from `report-template.md`: steps in order
with a screenshot each, hard/soft checklist result, durations, gates answered, escalations, model and spend when
available). The folder is not committed. A failed run still writes the report.

## Notes

- The app preview is the project's preview button, not the WebUI's `/preview` (a file viewer).
- The hard chat checks use the app's documented `POST /api/chat` contract; the screenshots drive the chat box.
- A defect found in the WebUI is fixed through the `shipwright-webui` repo's own iterate, not here.
- Test ids used (`wizard-modal`, `stack-profile-card-*`, `create-menu-item-new-pipeline`, `new-issue-*`,
  `design-gate-approve*`, `continue-pipeline-launch-btn`, `preview-button`) were read from the WebUI checkout when
  this was written; re-check them when the WebUI changes.
