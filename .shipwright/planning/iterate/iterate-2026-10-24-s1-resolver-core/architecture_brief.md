# Architecture Brief: stack-profile resolver core (campaign unit S1)

## The problem

A stack profile is a JSON file shipped inside the installed Shipwright tree, so a profile a user writes there is lost on the next update, and every phase (test, preview, validate-env, design, adopt) builds the bundled path itself. A broken or unknown profile silently turns into another stack's defaults. We want a profile written once, in the project or the home directory, to be found by every phase, and a broken one to fail loudly.

## What already exists here

- Six or more independent fixed-path lookups of `shared/profiles/<name>.json` in Python loaders, plus the same path spelled in about twenty skill-prose snippets.
- `shared/schemas/` holds JSON schemas for other artifacts (none for stack profiles); `jsonschema` is only available in the shared test environment.
- `.shipwright/` is gitignored except a whitelist in a managed template block.

## What would newly, permanently exist

A shared stdlib-only resolver module (lookup project, then user, then bundled; name rules; schema validation), a small CLI over it with list/resolve/validate, a stack-profile schema file, one gitignore negation so project profiles are committable, and a shared pytest fixture that keeps the real home directory out of tests. Later units rewire the loaders onto it; this unit changes no loader.

## Options on the table

- **A:** One resolver module plus CLI plus schema, loaders migrated afterwards (this unit builds only the foundation).
- **B:** Each loader gets its own custom-directory lookup added in place.
- **C:** Only document "put your profile in the plugin folder and re-copy it after updates".
- **D:** Do nothing.

## Constraints that are not negotiable

Plugins own a top-level `lib` package, so the module must live at the top level of `shared/scripts` with a unique name. The importing modules for dev_server must stay free of pathlib arithmetic and platform-gated imports at import time.
