# Architecture Brief: Python loaders use the stack-profile resolver (campaign unit S2)

## The problem

A resolver now exists that finds a stack profile in the project, the home directory or the installed Shipwright tree. Five Python programs still open the installed file themselves, and when that file is broken or the name is unknown they quietly carry on with another stack's defaults (npm commands for a Python project, no performance budgets, a skipped environment check). A user-written profile is therefore invisible to them, and a typo in the profile name looks like success.

## What already exists here

- The resolver, its schema and its CLI (merged), with a documented import convention.
- Per loader: a fixed bundled path, a `try/except` that turns bad JSON into "no profile", and a hard-coded command table keyed on the profile NAME.
- Existing tests that pin some of the silent behaviour (an unknown profile "skips", a missing file is "no profile").

## What would newly, permanently exist

One small shared glue module the loaders call (read the run config's profile, resolve with a remediation message, print the source line), a new error result shape in the environment scaffolder, a `profile_source` field in each loader's JSON, and name-keyed defaults that apply only to bundled profiles.

## Options on the table

- **A:** Route every loader through the resolver now; unknown, corrupt or too-new profiles fail loudly; reserved names and "no profile" keep a documented behaviour per loader.
- **B:** Leave the loaders as they are and only fix the skill prose.
- **C:** Keep the silent fallbacks but print a warning.
- **D:** Do nothing.

## Constraints that are not negotiable

Each touched file that is already over the size limit must not grow. The dev_server package must stay free of pathlib arithmetic and platform-gated imports at import time. A plugin's own `lib`/`tools` packages must not be shadowed by shared code on the import path. Behaviour for bundled profiles must not change.
