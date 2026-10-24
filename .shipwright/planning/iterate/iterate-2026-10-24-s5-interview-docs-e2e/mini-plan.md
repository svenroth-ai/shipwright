# Mini-plan: S5 interview, docs, py guard, end-to-end (stack-profile-resolver)

Goal: finish the stack-profile campaign. Make a custom stack profile reachable from the project interview, document it, enforce the resolver contract in *.py, and prove it end to end.

Changes
1. Project interview step 7: candidates from `resolve_profile.py list --json`, user may name a custom one, no match keeps generic. write-project-config.py gets --project-root at both SKILL call sites; early in_progress sentinel call skips the profile check; a missing shared tree degrades to a warning.
2. test_runner hint names the real `testing.<key>.command` per layer.
3. Docs: new docs/stack-profiles.md, guide ch.5/4.2/App.B, hooks-and-pipeline reconcile (dev_server row, E.14 effective profile, interview paragraph), CLAUDE.md "never hand-composed" sentence names .shipwright/profiles/.
4. Prose nits from S2/S3/S4 hand-offs (preview, runner notes, design-flavors, oss-scanners, adopt step-e relay + exit codes).
5. New shared/tests/test_stack_profile_py_guard.py (AST: no hand-built profile path outside resolver; no swallowed resolver ValueError), shared index reader used by both guards.
6. integration-tests/test_stack_profile_resolution_e2e.py: tmp project + git worktree, scenarios: source=project everywhere; schema_version too new fails all loaders (discovery warns separately); user-level; bundled-name shadow.

Test strategy: pytest per root; subprocess entry points in the integration test.
Risks: passing --project-root at the SKILL call sites moves the written shipwright_project_config.json to the project root (where readers expect it).
