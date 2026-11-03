# Mini-Plan: native surface (run `iterate-2026-11-03-native-surface-f05`)

## Files
1. NEW `shared/scripts/tools/verifiers/_surface_native.py` — `native_check(project_root, commit, ui_paths) -> (roots, problem)`; reads
   `package.json` at the commit via `git show`; native = depends on react-native or expo, and on neither react-dom nor next.
2. EDIT `_surface_evidence.py` — separate report KINDS from result LABELS: `SURFACE_REPORT_KINDS`, `SURFACE_RUNNERS` (labels);
   native adds a root + JS/TS-extension filter; `evidence_problem` takes the native roots.
3. EDIT `surface_check.py` — accept `native`; the UI-needs-web rule becomes "web, or native when every UI path is in a native
   package"; refusal text names `native`; docstring.
4. EDIT `shared/scripts/surface_verification.py` — `VALID_SURFACES` + tests_run parse for native (Jest summary); neutral line count.
5. Docs: F0.5 reference (surface list + staging recipe incl. jest-junit `addFileAttribute`), docs/hooks-and-pipeline.md if it lists
   surfaces, SKILL.md surface mentions if any.
6. NEW `shared/tests/test_surface_native.py` (tagged `FR-01.11/AC07`).

## Work breakdown
1. Tests first (red): native accepted with Jest-json evidence under the package; refused for web file in diff; Python JUnit and
   other-package Jest results rejected; short count fails; JUnit without `file` attr rejected; `cli`/`none` still refused.
2. `_surface_native.py`. 3. evidence filter. 4. surface_check wiring. 5. orchestrator. 6. docs. 7. full surface test files green.

## Test strategy
Real git repos + real `evidence_drop` staging via the existing fixtures; no mocks of the verifier.

## Alternative approach (rejected)
A project-level declaration (config / profile) that flips `web` to accept non-Playwright reports. Rejected because it is a switch
anyone can set for a web project and then skip the browser run; deriving native-ness from the diff's own package cannot be used
that way.
