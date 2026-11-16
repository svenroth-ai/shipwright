# Stack Profiles

A **stack profile** is a small JSON file that tells Shipwright how your technology stack
works: which commands run the tests, which services make up the dev server, which
environment variables are needed, which budgets apply. Shipwright ships six
(`supabase-nextjs`, `vite-hono`, `python-plugin-monorepo`, `claude-plugin`, `chat-first-json`, `skill-companion-app`). If none of them fits your
stack, you can write your own and every phase uses it.

Two names are special and are not files: `generic` means "no stack file, use the
built-in defaults", and `detecting` is a placeholder the project phase writes before a
profile has been chosen. You never create them.

## Where profiles live (lookup order)

Shipwright looks for `<name>.json` in three places. **The first file found wins**, and
the search never falls through to a lower place if the winning file is broken.

| Order | Location | Use it for |
|---|---|---|
| 1 | `<your project>/.shipwright/profiles/<name>.json` | A stack description for this project. Commit it. |
| 2 | `~/.shipwright/profiles/<name>.json` | A stack description you reuse across projects on this machine. |
| 3 | the bundled `profiles/` folder of the Shipwright install | The built-in profiles. |

To see what is available and where each one comes from:

```bash
uv run --no-project <shipwright>/shared/scripts/tools/resolve_profile.py list --project-root . --json
uv run --no-project <shipwright>/shared/scripts/tools/resolve_profile.py resolve --project-root . --name my-stack
uv run --no-project <shipwright>/shared/scripts/tools/resolve_profile.py validate --project-root . --name my-stack
```

`resolve` and `validate` exit with `0` (fine), `2` (no profile of that name; the message
lists every place that was searched), `3` (the file is broken or written for a newer
Shipwright) or `4` (the command was used wrongly).

## Commit your project profiles

A project profile is only useful if every checkout sees it: your teammates, CI, and each
iterate worktree under `.worktrees/`. Shipwright's managed `.gitignore` block therefore
leaves `.shipwright/profiles/` tracked (`!/.shipwright/profiles/`). If your project was
set up before this existed, run `uv run <shipwright>/shared/scripts/lib/gitignore_canon.py --project-root .`
once to refresh the block, then `git add .shipwright/profiles/`.

## How to start

1. Pick the bundled profile closest to your stack and copy it into
   `.shipwright/profiles/` (or `~/.shipwright/profiles/`). The bundled files live in the
   Shipwright install; `resolve_profile.py resolve --name vite-hono --path-only` prints
   the path of one.
2. **Rename it, twice**: the file name and the `"name"` field inside must be the same
   (`my-stack.json` with `"name": "my-stack"`). Names are lower case letters, digits and
   dashes, starting with a letter or digit (`^[a-z0-9][a-z0-9-]*$`).
3. **Give every test layer a command.** The built-in node profiles declare
   `testing.unit` and `testing.e2e` without a `command`, because Shipwright fills in its
   own commands for bundled profiles. A copy is a custom profile and gets no such
   defaults, so `/shipwright-test` stops with exit 3 and names the missing key (for
   example `testing.e2e.command`). Add an explicit `"command"` to each layer you keep, or
   delete the layers you do not use.
4. Check it: `resolve_profile.py validate --project-root . --name my-stack`.
5. Choose it: in the `/shipwright-project` interview ("use your own stack description or
   a built-in one"), with `--profile my-stack` for `/shipwright-adopt`, or set `profile`
   in `shipwright_run_config.json`.

## Minimum fields

Only `name` is required. Everything else is optional, and a key Shipwright does not know
is ignored (keys starting with `_` are comments). The ones that change behaviour:

| Key | Read by | Notes |
|---|---|---|
| `testing.unit` / `testing.integration` / `testing.e2e` / `testing.db_tests` | `/shipwright-test` | each with a `command`; `testing.command` is one runner for the unit layer |
| `testing.performance` | performance budgets | a layer you do not declare is skipped |
| `services` / `dev_server` | dev server, preview, browser verify | neither declared: Shipwright falls back to `dev_url` in `shipwright_build_config.json`, then to `npm run dev` |
| `required_env_vars` | `validate_env.py` | |
| `design_system` | `/shipwright-design` | |
| `ux_shape`, `ui_host` | brief-driven runs | optional plain strings (for example `"ux_shape": "chat-first"`; the bundled `chat-first-json` declares both); no loader reads them yet, the value format is defined by the unit that first reads them, and profiles without them work unchanged |
| `rules`, `folder_structure`, `migrations` | project scaffolding | |
| `traceability.test_roots` | `/shipwright-compliance` (test-to-requirement links, merge gate) | list of folders (or fixed-depth globs such as `plugins/*/tests`) that hold the tests; folders that do not exist are skipped. Used only when the project's `shipwright_compliance_config.json` sets no `traceability.test_roots` of its own, which replaces it. Only project and bundled profiles are read for this, never `~/.shipwright/profiles`, so the result is the same on every machine and in the merge gate; the gate also needs `shipwright_run_config.json` (which names the profile) to be committed. A wrong type here (for example a string instead of a list) makes the whole profile invalid for every phase. `vite-hono` declares `server/tests`, `server/src`, `client/src`, `client/tests`, `client/e2e`, `e2e`, `tests`, `integration-tests` |
| `stack` | adopt matching | what adopt compares a repository against |

`schema_version` (optional whole number, 1 when missing) says which profile format the
file was written for. `version` is a free-text note about your own profile and is not
`schema_version`.

## Skill-backed apps (`skill-companion-app`)

A skill-backed app is a Claude **skill, better a plugin**, that runs in the Claude desktop app
or in the terminal. The chat is the Claude app itself, so the app has no chat interface of its
own. Its **companion** is a served HTML board plus a Python backend with a JSON data folder; the
skill is the front door that starts and stops the companion. The bundled `skill-companion-app`
profile models the social-engagement skill and replaces `chat-first-json` for this app class
(`chat-first-json` stays bundled so existing apps keep resolving). The operator end-to-end run
(`integration-tests/e2e-webui/`) builds this app class from the Brief package
`integration-tests/fixtures/social-engagement-board/` and checks its API, board and files.

The bundled profile records four concepts as a **convention**, under the comment key
`_skill_companion` (keys starting with `_` are comments). They are **not** schema keys and no
phase reads them:

| Concept | Values | Meaning |
|---|---|---|
| `host` | `desktop-app`, `terminal` (a list) | where the skill runs |
| `delivery` | `skill` or `plugin` | how the app reaches the user; a plugin can bundle several skills, the manifest and the companion |
| `companion` | `ui`, `backend`, `bind`, `lifecycle` | the served board (`dir`, served by the backend), the Python entry point, the loopback address, and `lifecycle.owner: skill` with when it starts and stops and the health path |
| `data_folder` | `location`, `default`, `override_env`, `contents` | the JSON data lives in a folder the user owns, **outside the plugin install**: a plugin update replaces its own folder, so data inside it would be lost |

**Decision (unit E2, architecture review).** The four concepts were deliberately **not** added
to `stack_profile.schema.json`: nothing reads them, and a typed key with no reader widens the
frozen keyword set for no function. Whoever first adds a reader promotes them to real top-level
keys in that same unit, with the schema entries and the tests, and does not delete the bundled
profile. The working facts the phases do use (`dev_server`, `testing`, `folder_structure`,
`deploy`) are ordinary schema fields.

**Guidance for the companion backend (descriptive, nothing enforces it).** It is a local web
server with a write API, so: bind `127.0.0.1` only; check the `Host` header and require a
on state-changing routes a same-origin `Origin` check plus `application/json` or a per-session token, and no permissive CORS (a web page can otherwise reach a loopback server); keep a pidfile or idle timeout so a backend left behind by a crashed session is found and
stopped; handle "port already in use". Adopt scores a profile by its declared dependencies, and
this profile declares the same ones as `chat-first-json`, so adopt cannot tell them apart and
prefers `chat-first-json` by name: a skill-backed app chooses `skill-companion-app` explicitly.

What each phase does with a plugin-shaped app today (recorded by unit E2 of campaign
`e2e-run-findings`; nothing branches on the four concepts):

| Phase | Behaviour |
|---|---|
| Build / scaffolding | scaffolds the profile's `folder_structure` (plugin manifest, `skills/`, `backend/`, `board/`, tests), not a node project |
| Plan | reads no key specific to this class: nothing changes |
| Test | `testing.unit` is `uv run pytest`, `testing.e2e` is Playwright against the board; unit and e2e layers need a `command`, as for any custom profile |
| Preview / Browser Verify | start only the `dev_server` block (the same backend the skill starts, port 3911, `/api/health`, with a throw-away `--data-dir`; the real companion binds 3901, so a dev run never attaches to it); never the `npm run dev` fallback |
| Deploy | none: `deploy: null`, run config `deploy_target: none`, no CI or CodeQL template; the plugin is installed, not deployed. A plugin-shaped deploy target (marketplace publish) does not exist and is not part of this unit |

A Brief package for this class names `profile: skill-companion-app` and sets `ux_shape: classic` and `ui_host: served-board`
(the brief vocabulary `classic`, `chat-first` is unchanged here; `skill-companion` is the profile's own value). Design composes this class's screens from the Untitled UI kit and the package's tokens and never builds a chat layout; the chat-first layout is retired for this class (an older chat-first package of another profile keeps working; this profile is always composed as a board, and a package of this profile that says `chat-first` is a defect to re-approve as `classic`).

## Plugin projects (`claude-plugin`) and the generic Python profile

`claude-plugin` is the bundled profile for repositories that are Claude Code plugins (or plugin monorepos) whose code is Python. It carries the same Python data as `python-plugin-monorepo` (Python 3.11+, `uv run pytest`, `uv run ruff check`, no dev server, no deploy, the same CI and CodeQL templates) and adds six architecture rules: what goes into scripts and what goes to the AI, Anthropic's skill limits, scripts run through `uv run`, no bare `python -` reading stdin, hook paths through `${CLAUDE_PLUGIN_ROOT}`, generated files next to their source. Only one rule has a mechanism that something invokes (the bare-`python -` hook of the shipwright-iterate plugin, active in Claude Code sessions where that plugin is installed). The skill-limits checker (`check_skill_authoring.py`) is a report today and nothing runs it, so that rule is `prompt-only (mechanisable)` with a note saying so.

**Copying `claude-plugin` into your own `.shipwright/profiles/`:** the rule `no-bare-python-stdin` names a mechanism path that is relative to the Shipwright repository (`plugins/shipwright-iterate/...`), which does not exist in your project, so `validate` reports `rules_valid=false` for the copy. Also, any profile that declares the `claude-plugin` key is a candidate only in a Python repository with the folder and the key never counts toward its score, so a copy adapted to a non-Python stack must drop that key or it will never be matched. Change that rule to `prompt-only (mechanisable)` or `prompt-only (judgement)` (drop its `mechanism`) in the copy. The hook behind it only guards the Claude Code Bash tool in sessions where the shipwright-iterate plugin is installed (not PowerShell), and it also refuses an empty or unterminated heredoc. The Shipwright repository itself is the worked example: `.shipwright/profiles/shipwright-monorepo.json` is a copy of `claude-plugin` that keeps that rule (the path exists there) and adds rules for mechanisms found only in that repository (the root test-root guard, the pre-commit anti-ratchet hook, the bloat Stop gate, the bloat check in CI, the hooks.json quoting test) and one note rule that says which copied notes do not apply there. A test pins that the copy equals the bundled profile on every key except `name`, `description` and `architecture_rules`.

`python-plugin-monorepo` is now described as the generic Python-project profile; its name is historical and is not changed here (about thirty files name it).

**How adopt chooses between them.** `/shipwright-adopt` scores each profile by the dependency names it declares under `stack`. When the repository root is a Python repository (a `pyproject.toml` and no JavaScript dependencies in the root `package.json`) and has a `.claude-plugin/` folder at its root or one level down under `plugins/*/`, the analysis adds a `claude-plugin` entry to the runtime part of the stack signature. That entry never enters a score: every profile, bundled or your own, is scored exactly as before. The plugin profile (which declares the entry) is a candidate only when the signature carries it, and it wins a tie against the generic Python profile; a project profile still wins a tie over a bundled one. So a repository that would have matched `python-plugin-monorepo` now gets `claude-plugin` (and `claude-plugin` joins that repository's list of alternative candidates, which the adopt interview shows), and nothing else moves: a Python repository without the folder keeps the match it had (typically `python-plugin-monorepo`), a markdown-only, TypeScript or mixed plugin (JavaScript dependencies at the root, even only for tooling) keeps the match it had (pick the plugin profile by name there: `/shipwright-project`, or the adopt profile hint), and a repository that matched nothing before (for example a pyproject with no `requires-python` and no known dependencies) stays `generic`. `/shipwright-project` picks the profile by name like any other bundled one (`--profile claude-plugin`).

## What a Shipwright update can change

If a later Shipwright changes the profile format, a file written for the newer format
(`schema_version` too high) or a key of the wrong type stops the phase with exit 3. The
message names the file, what is wrong, which `schema_version` this Shipwright supports,
and which bundled profile to copy as a new starting point. Nothing silently falls back
to another profile or to defaults. Bundled profiles may improve with an update; **your
copies do not follow**, so re-compare them with the bundled original from time to time.

## When a profile has the name of a bundled one

This is allowed (it is how you adjust a built-in profile), and it **replaces** the
bundled file completely, it does not merge. Every phase that uses it prints a prominent
warning ("WARNING: project profile <path> shadows the bundled profile ...") and the result
reports the profile source (`project`, `user` or `bundled`). Two consequences:

* Defaults that exist only for the bundled profile (its standard test commands, its CI
  and CodeQL workflow templates) are **not** applied to your file. A copied bundled
  profile loses the bundled CI/CodeQL templates; `/shipwright-adopt` then reports
  `no CI template for profile ...` and `AUTOMERGE_SETUP.md` lists fewer required checks.
* A repository can therefore change what a phase runs for a bundled name; see the trust
  paragraph below.

## Architecture rules (`architecture_rules`)

A profile can say which architecture rules a project of that stack must keep, and for each rule how it is kept. The key is optional: absent (or `null`) means "not declared", `[]` means "explicitly none". Each rule is one object:

```json
{
  "id": "no-direct-db-client",
  "text": "Only src/lib/db/ creates a database client.",
  "why": "One place to change connection handling.",
  "enforcement": "validator",
  "lint": {"tool": "eslint", "target": "eslint.config.mjs", "block": {"rules": {"no-restricted-imports": "error"}}},
  "note": "Optional extra context."
}
```

- `enforcement` is one of `hook`, `validator`, `test`, `prompt-only (mechanisable)`, `prompt-only (judgement)`, `unimplemented` (the same list as the constitution register).
- A rule carries `lint` **or** `mechanism` (a list of repo-relative paths), never both. `validator` needs one of them; `hook` and `test` need `mechanism`; the other classes carry neither, and `prompt-only (mechanisable)` and `unimplemented` need a `note`. A lint rule is class `validator`; its rendered line says the fragment comes with the scaffold template and is enforced only where the project's linter config carries it (an adopted or older project may not).
- `lint` is `{tool, target, block}`: `tool` is `eslint` or `ruff`, `target` the config file in the project, `block` the config fragment (for `eslint` an object with a non-empty `rules` object). `mechanism` paths are relative to the Shipwright repo for a bundled profile and to the project root for your own profile; they must not be absolute or contain `..`.
- A mechanism only counts as enforcement if something invokes it in the user's project; a checker that exists but is not run is `prompt-only (mechanisable)`.
- The old format, a list of plain sentences, is still accepted until the last bundled profile is converted. Such a sentence is treated as an instruction whose class is not declared; `validate` warns about it, no other command does.

**A wrong rule never invalidates the profile.** `resolve_profile.py validate` prints rule errors and warnings to stderr and lists them as `rule_errors` / `rule_warnings` (and `rules_valid`) with `--json`, but still exits `0` as long as the profile itself is valid: read `rule_errors` or `rules_valid` to gate on them. The bad rule is left out; the others stay usable. For your own profile `validate` also checks that each mechanism path exists under `--project-root` (default `.`, so run it from the project) and stays inside it.

If your own profile has a bundled name and declares no `architecture_rules`, but the bundled one does, the resolver adds a warning next to the usual shadow warning; copy the rules in, or write `"architecture_rules": []` to say you mean none.

**How the rules reach agents.** `render_architecture_rules.py` writes the rules of the project's profile into one marked block of `.shipwright/agent_docs/conventions.md` (`--profile`, else the run config's `profile`). `/shipwright-project` step 7 and `/shipwright-adopt` call it; you can run it yourself after changing the profile. Running it again changes nothing unless the profile changed; text outside the block is never touched. A profile with no rules gets a "none declared" line, and an instruction-only rule says so. If a project's `conventions.md` already has hand-written rules under that heading (older scaffolds), delete them first: the block is placed under the heading and never removes text. `conventions.md` is merged with the union strategy, so if two branches each re-render the block with different content, a merge can keep both bodies; the tool then stops with exit 3 (two blocks) without writing. Delete one block by hand and run it again.

## Discovery versus selection

Where Shipwright only *lists or suggests* profiles (the interview's candidate list,
adopt's matching), a broken candidate is skipped with a warning and the rest continue.
Where a profile was *chosen* (a run-config profile, `--profile`), a broken or unknown
file is an error. Adopt matches on profile metadata (the `stack` block) only, so a
minimal custom profile can score below the threshold and adopt answers `generic`; select
it explicitly (interview or `--profile`).

## Trust

A project profile can carry commands that run: `testing.*.command` is executed through
the shell by `/shipwright-test`, and `services[].command` is started by the dev server;
environment variables are expanded inside those commands. That is the same trust level
as the project's own `package.json` scripts or `conftest.py`, which `/shipwright-test`
already runs, so there is no separate approval step. Commands only run inside a phase you
invoked, and the profile source is printed before they do. Two residual risks are
accepted knowingly:

* commands in `~/.shipwright/profiles/` run in **every** project, including a clone of a
  repository you do not trust;
* environment variables are substituted into those commands, and a hostile repository
  controls some of them.

Do not keep a profile in `~/.shipwright/profiles/` whose commands you would not run
against an untrusted checkout, and read a repository's `.shipwright/profiles/` before
running a phase there, as you would its scripts.

## Reference for tool authors

* Exit codes of the CLI: 0 ok, 2 not found, 3 invalid or too new, 4 usage. Provenance
  (`source=`, `shadows`) goes to stderr; stdout carries only the requested output.
* `adopt`: `generate_adoption_artifacts.py` exits 2 for "snapshot not found" **and** for
  "profile not found" (read stderr, do not branch on the code alone), 3 for an invalid
  profile, 1 for anything else; nothing is written on 2 or 3.
* `resolve_profile.py list --json` carries `contract_version: 1` for tools that read it.
* Test isolation: `SHIPWRIGHT_USER_PROFILES_DIR` overrides the user folder.
