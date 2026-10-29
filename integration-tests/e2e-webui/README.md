# Real end-to-end run through the WebUI (operator-started, not a CI gate)

Proves that a Brief package turns into a working **skill-backed app** (a plugin whose skill starts a served HTML board
plus a Python backend over JSON files; the chat is the Claude app itself) with a **real agent**, driven the way
a person drives the WebUI, and leaves a screenshot report. It costs tokens and wall-clock time and a model run
varies, so CI never runs it. CI only checks what needs no model (the package validates, the dry harness passes,
this project's structure rules hold: `integration-tests/test_e2e_webui_project.py`).

The app it builds is the social engagement board in `../fixtures/social-engagement-board/` (profile
`skill-companion-app`, `ux_shape: classic`, `ui_host: served-board`; its `visual-guidelines.md` declares the brand
tokens as `--color-bg: #f6f7f9` lines, so the board gets the Untitled UI kit look with the package's own colours). The
answer key is `../fixtures/social-engagement-board-expected-result.md`. It sits next to the package, not inside it, so
it is not part of the package hash and is not handed to the building agent. It is not hidden from it either: with
`bypassPermissions` the agent can reach this repository through `SHIPWRIGHT_MONOREPO_PATH` and could read the file. The
older chat-first package `../fixtures/social-engagement/` is no longer used by this run; it stays only for the
chat-first design tests (`test_chat_first_design.py`, the design plugin's `test_chat_first_package.py`) and goes with them.

**Every item of the answer key is a hard check except S03.** What checks what:

| Items | Evaluated by |
|---|---|
| H01-H04, H12, H13, S05, S06 | the project files (`src/progress.ts`, `src/project-checks.ts`); H13 is the check no tool did: a screen that does not carry the design kit (kit.css inline or at least two kit component classes, plus a token block in `:root`) is still the mockup copy and fails |
| H05-H11, S07 | the companion's JSON API (`src/board-api.ts`), against the package's documented routes in `brief.md`; there are no chat commands |
| S01, S02, S04 | the served board in a browser (`src/board-dom.ts`): no chat input or panel, one tab per platform with status badges, and every colour and font-size token of `visual-guidelines.md` present on the board |
| S08 | the gates the spec answered, classified by meaning (`src/gates.ts`; the veto words are read in the question and the option), plus the escalation list. Gates and escalations are written to `gates.jsonl` in the run folder as they happen, so a resumed run judges the whole run |
| S03 | the Test phase's screenshot check (metric recorded; compared by eye) |

The API checks need a fresh data folder. The Test phase has already used the throw-away `.dev-data` of port 3911, so
the spec renames it aside before it clicks the preview button (the report says so); a folder that still holds threads
fails H06. If a Test-phase companion is still listening on 127.0.0.1:3911 (for example after a hard kill, or another
skill-companion project's dev server), the preview can attach to it and serve stale state: stop it before the run, the
port is fixed by the profile.

## Two fixtures

`SHIPWRIGHT_E2E_FIXTURE` picks the app the run builds; unset means `social-engagement-board` (above). An unknown name is
refused. `social-engagement-real` (`../fixtures/social-engagement-real/`, key `../fixtures/social-engagement-real-expected-result.md`)
is shaped like the real `social-engagement` skill: a master-detail board (thread list left, one thread right with summary,
draft and a Copy reply button, feedback, status), the svenroth.ai tokens including Inter and Geist Mono, a status filter
with skipped and expired, and the keywords as sources (Syften filters, LinkedIn queries), not a board tab. The hits come
through an exchangeable `fetch_items()` adapter in `backend/sources/`; without a token it replays the recorded
Syften- and Apify-shaped answers in `seed/recorded/`, so a build and its tests need no network and no key.

The checks that differ run in their variant form (`src/variant.ts`): S02 reads the platform switcher with counts, the
status filter, a badge per list row, the thread beside the list and Copy reply (`src/board-dom-real.ts`); S04 also compares
the font families; S05 allows a service name only under `backend/sources/` and needs `fetch_items` and nine recorded items,
three per platform (`src/project-checks-adapter.ts`); H06-H11 plus H14 (feedback) run against the variant's API
(`src/board-api-real.ts`). **S09 (soft)**: with `SHIPWRIGHT_E2E_SKILL_TRIGGER=1` a headless `claude -p` session loads the built
plugin and gets "open the social engagement board" with only the Skill tool allowed; the verdict is whether a skill was
called (`src/skill-trigger.ts`). It costs one short model call and is skipped otherwise. The variant has not run against a
live agent yet; its first run also shows whether Design carries the brand fonts.

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
| `SHIPWRIGHT_E2E_RESUME_RUN` | Optional. Continue a stopped run: the `run-<id>` folder directly under the workdir. See "Resume" below. |
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
through the expert project wizard (profile `skill-companion-app`), copies the package to `<project>/brief/`, starts
"New pipeline" from the task board, follows the phases, approves the design review and launches next phases the
way a user does, waits for completion, opens the board through the project preview button, runs the API, board and file checks, and
puts each approved mockup beside its built screen. The report records the git commit the plugins were loaded from.

It ends on completion, failure, a wall-clock budget overrun, or an **idle abort**: 20 minutes without a new phase
state, project file change or terminal output change (typically a prompt it cannot answer). It fires on no progress
whether or not a prompt is found; the inbox check only adds detail to the report. It then takes a screenshot and writes
the report up to that point. `SHIPWRIGHT_E2E_MAX_MINUTES` is a real limit for the whole run, builds included.

## Resume

A run that stopped (idle abort, budget, crash) leaves its `run-<id>` folder. Set `SHIPWRIGHT_E2E_RESUME_RUN` to that
folder to continue instead of paying 70-80 minutes again. The harness writes `run-manifest.json` (fixture, package hash,
profile, plugin commit) into every new run folder and refuses to resume unless all four match the current checkout, the
folder is a real `run-<id>` directory directly under the workdir (no link), it has `project/` and `home/`, the earlier run
has not yet finished all its checks (a pipeline that is already `complete` is still resumable after a crash in the
preview or the checks; a run that wrote its final report is not), and the project's `brief/` is this package. A resumed run reuses the temp HOME, the project and an
already-started pipeline (New pipeline is not clicked again), starts a fresh WebUI instance and a fresh budget, and runs
every check again. A resumed run records its idle, budget or crash escalations (`gates.jsonl` keeps them across parts), so S08 fails on such a run: resume is a way to continue and diagnose, and a run that needed a resume cannot end "all hard items hold" (fail-closed by design). S08 is judged on the earlier part as loaded when the resumed run starts plus the gates of the resumed part held in memory, never on a re-read of the file. Before resuming, make sure the earlier run's processes are dead: the WebUI stack and the companion on the preview port (127.0.0.1:3911); there is no liveness check. The report names the folder and the steps reused. How the WebUI picks up the continued task is
verified only by a real run (E8).

## Before the first run of this app class

Two WebUI facts this harness relies on and cannot test without the WebUI: the project wizard must show
`stack-profile-card-skill-companion-app`, and the preview button must start a profile with `deploy: null` from its
`dev_server` block (127.0.0.1:3911). If either is missing the run stalls or H05 fails; fix it in the `shipwright-webui`
repo. The Playwright unit specs (`npm run test:unit`, including a stub companion and a real browser) run only when you
start them; CI runs only the Python structure and fixture tests (`test_e2e_webui_project.py`, `test_e2e_board_fixture.py`).

## Output

`<workdir>/e2e-report/<timestamp>/report.md` plus the images (rendered from `report-template.md`: steps in order
with a screenshot each, hard/soft checklist result, durations, gates answered, escalations, model and spend when
available). The folder is not committed. A failed run still writes the report.

## Notes

- The app preview is the project's preview button, not the WebUI's `/preview` (a file viewer).
- The hard API checks use the companion API documented in the fixture's `brief.md` and talk to loopback only; the screenshots click through the board.
- A defect found in the WebUI is fixed through the `shipwright-webui` repo's own iterate, not here.
- Test ids used (`wizard-modal`, `stack-profile-card-*`, `create-menu-item-new-pipeline`, `new-issue-*`,
  `design-gate-approve*`, `continue-pipeline-launch-btn`, `preview-button`, `stack-profile-card-skill-companion-app`) were read from the WebUI checkout when
  this was written; re-check them when the WebUI changes.
