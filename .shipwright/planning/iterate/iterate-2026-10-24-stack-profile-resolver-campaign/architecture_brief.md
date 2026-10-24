# Architecture Brief: custom stack profiles that survive updates

## The problem

A stack profile (a JSON file describing a project's test commands, dev servers, env vars, folder layout) is read only from the installed Shipwright plugin tree. An update replaces that tree, so a user who wrote their own profile loses it, and nothing in a project can name a profile that is not bundled. Several loaders also quietly substitute other behaviour when a profile is unreadable or unknown (hardcoded npm test commands, "skipped" env validation).

## What already exists here

- Three bundled profile JSON files plus a deploy-profile subsystem with its own schema and validator.
- `shipwright_run_config.json.profile` stores only a name (free string).
- Roughly five Python loaders and ~15 skill-prose sites each build the path to the bundled directory themselves.
- Adopt scores the repo's stack against every bundled profile and falls back to the name `generic` (not a file).

## What would newly, permanently exist

A lookup of profiles in three places (project directory, user home directory, bundled), a JSON schema for stack profiles, and a small command-line tool that reports which file won. Shipwright maintainers keep the schema and its version in step with what loaders read; users keep their own profile files.

## Options on the table

- **A:** One shared resolver module and CLI; every loader and prose site goes through it; custom profiles validated against a new schema at load.
- **B:** Only a user-level directory; no project level, no schema.
- **C:** Copy bundled profiles into each project at scaffolding time and let the project own its copy.
- **D:** Do nothing; document that custom profiles must be re-added after each update.

## Constraints that are not negotiable

A named profile that cannot be loaded must never lead to a different profile's behaviour or a silent pass. Bundled behaviour for existing projects must not change.
