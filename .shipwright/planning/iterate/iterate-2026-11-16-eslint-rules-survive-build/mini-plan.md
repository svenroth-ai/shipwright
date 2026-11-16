# Mini-plan: architecture-rule lint fragments survive the build phase

Run: iterate-2026-11-16-eslint-rules-survive-build. Campaign context: follow-up of campaign profile-architecture-rules, unit U3b (PR #1066).

1. `shared/scripts/eslint_architecture_rules.py` (lib): load the eslint-lint rules of a resolved profile, render each marked fragment exactly like the template does, `inspect()` an eslint.config.* (ok / missing / stale / unpaired per rule; no-config; legacy .eslintrc*), `apply()` (append missing fragments as last elements of the exported array, found with the comment/string-aware lexer; refuse anything that is not plainly an array or defineConfig([...]) literal; write only if the re-inspection of the result is clean; stale fragments replaced only with an explicit flag).
2. `shared/scripts/tools/check_eslint_architecture_rules.py` (CLI): `--project-root`, `--profile`, `--apply`, `--replace-stale`, `--json`; exit 0 ok / not applicable, 1 findings, 2 profile unresolved, 3 cannot edit safely.
3. Build verifier: `verifiers/build_checks.py` gains `check_eslint_architecture_rules` in `run_build_checks` (ERROR when a fragment is missing; WARNING for adopted projects; skipped when the profile has no eslint rule). The existing phase validator (Stop hook / verify_phase) runs it with no hook change.
4. Build SKILL Step 12 completion: one sentence naming the repair command. Project step 7 prose: replace "repeat steps 2 and 3 ..." with a pointer to the tool.
5. Docs: hooks-and-pipeline.md (build verifier), building-skills-plugins-agents.md known limit, stack-profiles.md, spec.md AC36/AC37, new ADR via decision-drop.
6. Tests (shared/tests): real fixtures (create-next-app style config without markers -> finding; with markers -> ok; apply idempotent; CJS; unparseable; stale; unpaired; no config; legacy eslintrc), template drift against rendering, verifier integration, docs pins. Default tier, no npm.

Alternative approach: prose only (a build skill line "repeat steps 2 and 3") or a check inside the test plugin's lint step. The test plugin has no lint step, and the phase verifier already runs at every build completion.
