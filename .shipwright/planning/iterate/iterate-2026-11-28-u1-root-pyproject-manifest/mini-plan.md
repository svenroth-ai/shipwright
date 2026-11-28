# Mini-plan: U1 — root pyproject.toml and uv.lock as release manifests (D111)

## Goal
A release writes its version into the root `pyproject.toml` (`[project].version`) and the project's own
package in `uv.lock`, through the existing manifest sync (`sync_release_manifests.py`, Step 5.4 write and
Step 6 `--verify-commit`). v0.37.0 bumped 29 manifest slots and left both at 0.36.0 (FINDINGS D111).

## Approach
- New `shared/scripts/lib/manifest_sync_toml.py` with formats `pyproject_toml` and `uv_lock`.
  - Read: `tomllib`. pyproject: `[project].version` must be a string (absent / dynamic -> `missing_version_field`).
    uv.lock: the root package is the single `[[package]]` whose `source` is `{virtual = "."}` or `{editable = "."}`
    (none -> new status `missing_root_package`; two -> `ambiguous_manifest_structure`).
  - Write: line edit scoped to the target table (header line to the next header line); exactly one
    `version = "<current>"` line must match there (else `ambiguous_manifest_structure`). The k-th `[[package]]`
    header is the k-th entry of the parsed package array. The edited text is parsed again and must equal the
    original document with only that value changed, else nothing is written. Always surgical (`reformatted: false`).
- `manifest_sync_core.py`: add both to `SUPPORTED_FORMATS`, dispatch read/render to the new module.
  `describe_version_state` and `--verify-commit` work unchanged (single-field compare).
- Declare `pyproject.toml` / `uv.lock` in this repo's `shipwright_changelog_config.json`; roster test pins it.
- Docs: `references/manifest-sync.md` (frozen: approved delta in `approved_deltas.json`, source D111).

## Tests
- shared/scripts/tests/test_manifest_sync_toml.py: real root files copied -> only the version line changes
  (byte diff); other-table versions, lock top-level `version`, dependency entries untouched; CRLF, quotes,
  comments survive; named refusals; unplaceable version line refused.
- plugins/shipwright-changelog/tests/test_release_sync_five_formats.py: `release_sync.sync` on a scratch
  git project with all five formats runs the real tool, moves every slot, then `--verify-commit` passes.

## Alternative approach considered
Regex replace of `version = "<current>"` anywhere in the file; or rewriting the whole file with a TOML writer
(tomli-w / tomlkit dependency).

## Risks
New parser code in `shared/` ships to consumers. A table-scoped edit must not hit a version of another table.
