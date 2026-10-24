# Mini-plan: S1 resolver core

Files: new `shared/scripts/profile_resolver.py` (+ `profile_model.py`, `profile_schema_check.py` split to stay under the 300-line limit), `shared/scripts/tools/resolve_profile.py` (CLI), `shared/schemas/stack_profile.schema.json`, gitignore template + repo block (`!/.shipwright/profiles/`), shared pytest fixture `shared/scripts/profile_test_isolation.py` wired into 9 test roots, tests in shared/tests (resolver, CLI, schema vs jsonschema, gitignore in a scratch repo) and one boundary probe per consumer root.

Approach: first FILE wins (project, user, bundled) with no fall-through; reserved sentinels generic/detecting are builtin; names validated lowercase + Windows device names; containment via resolve() + is_relative_to; exact directory-entry spelling check; hand-written schema checker supporting only the keywords the schema file uses (unsupported keyword raises); provenance/shadow warnings returned for loaders to print; CLI exit codes 0/2/3/4 with stdout clean and provenance on stderr; list contract_version 1.

Alternative approach considered: add a custom directory to each loader in place. Rejected because it multiplies six lookups and keeps silent fallbacks.

Tests: ACs (1)-(19) of the brief mapped to tests; CLI tested in-process via main(argv) plus one subprocess smoke; `jsonschema` cross-check in the shared root.

Risks: new gitignore negation propagating to adopted projects (covered by the template drift test and a scratch-repo test); fixture wiring in 9 conftests (boundary probe per root).
