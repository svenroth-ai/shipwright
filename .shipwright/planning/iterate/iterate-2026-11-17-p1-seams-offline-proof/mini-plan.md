# Mini-plan: P1 seams and offline proof (changelog pilot)

## Goal
Let an offline test drive the real release scripts (`setup-changelog.py`, `create_github_release.py`, `condense_release_notes.py`, `refresh_compliance_docs.py --verify-commit --release-audit`) with no GitHub and no model, while every default path stays identical.

## Changes
1. New `shared/scripts/release_seams.py` (stdlib only, top level like `repo_identity.py`, ADR-045): the only reader of `SHIPWRIGHT_TEST_GH_ARGV_PREFIX` (JSON argv prefix replacing `gh`) and `SHIPWRIGHT_TEST_CONDENSE_FIXTURE_MODEL` (`ok` | `bad-shape`). Inert when unset/empty; malformed = `SeamError`.
2. `create_github_release.py` and `setup-changelog.py` build every `gh` argv through `release_seams.gh_command(...)`.
3. `condense_release_notes.condense` returns fixture text (`via: fixture`) when the fixture seam is set, before any key lookup.
4. Publish guard: fixture text carries a marker sentence; `create_release` refuses a notes file with the marker unless the gh seam is set (before any gh call).
5. Offline proof: no code seam needed for the release audit; a test builds a scratch project from `minimal_valid_project`, runs `--stage`, commits, then `--verify-commit --release-audit` with `UV_OFFLINE=1`, dead proxy and no keys (skips when uv has no cached pyyaml).
6. Docs: seam table in `docs/hooks-and-pipeline.md` (changelog section).

## Tests (L1)
`shared/tests/test_release_seams.py` (default argv unchanged, prefix applied, malformed refused, one-place scan, documented, fixture/ guard, a real stub process), `plugins/shipwright-changelog/tests/test_setup_changelog_gh_seam.py`, `shared/tests/test_release_offline_proof.py`.

## Not done (scope)
No behaviour change (operator decisions of brief 3a are P8). `audit_compliance_lifecycle.py`'s `gh pr view` is merge scope, not on the release path.

## Alternative approach considered
A `.cmd`/shim `gh` on PATH: rejected because on Windows `gh` is spawned as `["gh", ...]`, which cannot run a batch file.
