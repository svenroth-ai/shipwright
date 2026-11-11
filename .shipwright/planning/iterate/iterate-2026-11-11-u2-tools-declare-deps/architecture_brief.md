# Architecture Brief: tools declare their own packages

## The problem
Two Shipwright tools (the finalization verifier and the release-notes condenser) rely on packages (jsonschema/pyyaml, openai) that only the monorepo's root project supplies. Started with a plain `uv run <script>` from any other folder (a consumer project, a plugin folder, an empty directory), the condenser answers "openai package not installed" and the verifier's schema-backed checks degrade silently.

## What would newly, permanently exist
Nothing new as a mechanism. This changes machinery that already exists: how two existing scripts get their packages (the hook scripts already carry PEP 723 `# /// script` headers).

## Options on the table
- **A:** Add a PEP 723 inline `# /// script` dependency header to each of the two scripts.
- **B:** Document `uv run --with jsonschema --with openai` (or `uv run --project <root>`) as the required invocation.
- **C:** Make callers (skills, finalize_iterate.py) always pass `--project`/`--with`.
- **D:** Do nothing; the root project already supplies them when run from the repo root.
