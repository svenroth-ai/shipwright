# Mini-plan U5: shipwright-monorepo project profile

1. `.shipwright/profiles/shipwright-monorepo.json`: copy of bundled `claude-plugin`, new name/description, three added rule objects with honest classes: conftest.py guard = validator (note: only when repo root is rootdir); pre-commit anti-ratchet = hook (note: per-clone install, bypassable, growth only); bloat baseline CI = validator (note: new crossings not blocked).
2. Switch `profile` in the three tracked configs; render the block into `.shipwright/agent_docs/conventions.md` (render tool, no hand edit).
3. Test `shared/tests/test_shipwright_monorepo_profile.py` (AC33 under FR-01.01): three configs resolve source=project; copy-equality on every key but name/description/architecture_rules; all bundled rules contained unchanged; mechanism paths exist and are invoked; resolve CLI validates; `--check` current.
4. Docs: guide sentence made true, stack-profiles.md worked example, architecture.md profile name.
5. Name-keyed code (CI/CodeQL tables) checked: bundled names only, no runtime break; `.github/workflows` already committed.
Risks: re-adopt loses bundled CI/CodeQL defaults (accepted by brief); the copy drifting from claude-plugin (pinned by test).
