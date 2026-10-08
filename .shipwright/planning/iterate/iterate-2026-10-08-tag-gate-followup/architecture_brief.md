# Architecture Brief: let the test-tag check see every test an iterate adds or edits

## The problem
The finishing check that demands every added or edited test name the requirement it proves has four blind spots: tests written
as a table of cases (`it.each(table)('title', ...)`) are not seen at all; a change that also adds a folder to the project's
"leave out of the scan" list can hide its own new tests; a quote character inside a pattern literal or page markup can make the
check misread where a test body ends, so a real edit passes unnoticed; and removing a skip mark or changing a test's case list is
treated as no edit. A fifth gap sits in the check's own integration test, which counts a check that did not run as a pass.

## What would newly, permanently exist
One small lexer module (about 250 lines) in the verifier package, two regex/joiner extensions in the shared tag grammar and
the compliance collector, and a cached "base-side excluded folder names" value inside the regeneration helper. No new
dependency, no new runtime process, no persisted state. Maintainers: whoever changes the test-tag gate.

## Options on the table
- **A:** extend the existing matchers and add a hand-written lexer for regex literals and JSX; digest decorators and the callee.
- **B:** replace the TS handling with a real parser library (tree-sitter or esbuild) and derive declarations and bodies from its tree.
- **C:** leave the blind spots as documented limits; only fix the integration-test skip set.
- **D:** fail the gate whenever a diff changes `traceability.exclude_dirs` or any test-folder setting, instead of scanning with the base set.

## Constraints that are not negotiable
The gate must stay stdlib-only (it runs in every consumer project's finishing step); base and head must be digested by the same code so
a digest change cannot itself flag untouched tests; one pytest root per process.
