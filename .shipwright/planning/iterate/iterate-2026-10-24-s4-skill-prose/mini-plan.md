# Mini-plan: S4 skill prose through the resolver

Files: skill/agent/reference markdown in test, preview, project, security, build, run, design, adopt (hand-built `shared/profiles/{profile}.json` paths replaced by `resolve_profile.py resolve --path-only` / `list`, or by passing the profile NAME to `test_runner.py` / `performance_check.py` per D8f); README one sentence; the S2 hand-off sentence "profile problem: stop and show the message" at the dev_server call sites; new tests `shared/tests/test_stack_profile_prose_guard.py` (planted-path red/green, allowlist reverse, zero findings) and `test_stack_profile_prose_commands.py` (each resolver snippet in the edited prose is extracted, filled and run against a tmp fixture).

Approach: prose is runtime code, so the replacement is the CLI the resolver already ships; read-only sites use `--path-only` (empty = built-in defaults), command-running test layers pass NAME + project root so the loader knows the source. Preview becomes a gate on the exit code.

Alternative considered: leave the old paths because S2's `name_over_bundled_path` maps them back to a name. Rejected: custom profiles stay invisible to read-only prose sites and the guard cannot be enforced.

Risks: bloat caps (section-builder.md 485 -> 484, security SKILL.md 434 unchanged; preview SKILL.md grows 9 lines, not baselined). docs/hooks-and-pipeline.md untouched (S5).
