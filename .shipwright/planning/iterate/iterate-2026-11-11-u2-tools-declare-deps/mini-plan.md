# Mini-plan: U2 tools declare their own packages

## Goal
`uv run verify_iterate_finalization.py` and `uv run condense_release_notes.py` get their packages from the script itself, from any working directory.

## Facts verified
- Root pyproject.toml declares openai, jsonschema, pyyaml, so the tools work only when the cwd project is the monorepo root. In any other cwd uv does not supply them.
- verify_iterate_finalization.py imports jsonschema/pyyaml only transitively (verifiers using the compliance evidence readers and ci_gate_scan), which is why the failure is silent degradation rather than a crash.
- The hook scripts already use PEP 723 headers for exactly this (`test_hooks_pep723_isolation.py`).
- finalize_iterate.py:199 launches the compliance plugin's update_compliance.py with `uv run --project <compliance plugin>`; that script is run as `python <script>` (inline metadata is not read for that form), so it stays on `--project`; it is a different script and a different launch form, left as is.

## Changes
1. `# /// script` header in `shared/scripts/tools/verify_iterate_finalization.py` (jsonschema>=4.18, pyyaml>=6.0) and `shared/scripts/tools/condense_release_notes.py` (openai>=2.30.0), same bounds as the root pyproject.
2. New test `shared/tests/test_tools_declare_own_dependencies.py`: static header check; slow real-uv check that the header resolves from an empty directory.
3. One sentence in docs/hooks-and-pipeline.md (release-notes row).
4. The "openai package not installed" fallback and its tests are untouched; release notes stay best-effort.

## Risks
A wrong header shows only in a clean environment: verified with `uv export --script` and `uv run --no-project --script` from an empty directory.
