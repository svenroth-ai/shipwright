# Mini-plan U4: bundled claude-plugin profile

1. `shared/profiles/claude-plugin.json`: copy of the generic Python data (runtime python, testing, linting, dev_server null, deploy null, folder layout, env vars) + `claude-plugin` runtime key (adopt signal) + six rule objects (one hook mechanism registered in shipwright-iterate hooks.json; skill-limits rule prompt-only (mechanisable) with a "report only" note).
2. Rewrite the description of `python-plugin-monorepo` as the generic Python profile (no rename).
3. Adopt: `stack_detector.py` emits runtime `claude-plugin` + signal `has-claude-plugin-dir` for `.claude-plugin/` at root or `plugins/*/`; the signal key is skipped in the spec constraints list. CI/CodeQL registries get the new name (same template, `[python]`). Skill prose: counts and one list line only, no commands.
4. Project skill: no edit; selection by name works through the resolver (test).
5. Tests: profile test (valid, Python data equal, mechanism paths exist and are registered, registries); adopt matcher fixtures (plugin repo, plugins/* layout, plain Python keeps generic); project name check; pinned-rules and profile-list tests updated.
6. Docs: `docs/stack-profiles.md` section, `docs/guide.md` tables. ACs AC30-32 under FR-01.01.
