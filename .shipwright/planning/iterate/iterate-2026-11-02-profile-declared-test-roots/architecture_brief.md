# Architecture Brief: profile-declared test folders

## The problem
Shipwright links tests to requirements by scanning a fixed list of top-level folders (tests, test, __tests__, e2e, integration-tests, src, app, packages). A project built from the vite-hono stack profile keeps its tests below server/ and client/ (server/tests, client/src, client/e2e), so nothing is scanned and every requirement reads as untested; the merge gate then asks for tests that already exist. Today the only remedy is a hand-written `traceability.test_roots` list in shipwright_compliance_config.json. A warning that names that setting already exists (PR #980).

## What already exists here
- `traceability.test_roots` in shipwright_compliance_config.json: an explicit list of folders or fixed-depth globs; when present it replaces the defaults.
- Stack profiles (shared/profiles/*.json, resolved project > user > bundled) already describe a stack's layout, services, test commands and folder structure; the run config names the profile.
- A shared profile resolver and loader glue that other phases (dev server, test runner, performance check) use.
- The merge gate rebuilds the requirement-to-test index from throwaway archives of the base and head commits with the same collector.

## What would newly, permanently exist
Nothing new runs or writes. A new optional key in the profile schema and one value in vite-hono.json, read by the existing test-root resolution. It must be kept consistent with the compliance config key of the same name.

## Options on the table
- **A:** The stack profile declares its test folders; the collector reads them when the project's compliance config does not set its own.
- **B:** Widen the collector's default discovery to find test folders at any depth for every project.
- **C:** Do nothing beyond the warning; document the compliance config setting in the vite-hono guide.
- **D:** The scaffolding step for a new project writes the compliance config setting at creation time.

## Constraints that are not negotiable
- A project's own `traceability.test_roots` must keep full control (existing behaviour).
- A missing, broken or placeholder (generic, detecting) profile must never crash a regeneration.
