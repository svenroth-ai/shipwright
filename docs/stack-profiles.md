# Stack Profiles

A **stack profile** is a small JSON file that tells Shipwright how your technology stack
works: which commands run the tests, which services make up the dev server, which
environment variables are needed, which budgets apply. Shipwright ships four
(`supabase-nextjs`, `vite-hono`, `python-plugin-monorepo`, `chat-first-json`). If none of them fits your
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
| 3 | the bundled `profiles/` folder of the Shipwright install | The three built-in profiles. |

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
| `stack` | adopt matching | what adopt compares a repository against |

`schema_version` (optional whole number, 1 when missing) says which profile format the
file was written for. `version` is a free-text note about your own profile and is not
`schema_version`.

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
