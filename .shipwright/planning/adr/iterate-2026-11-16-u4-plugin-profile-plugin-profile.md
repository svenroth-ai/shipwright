# Bundled claude-plugin profile for Claude Code plugin repositories

Run: iterate-2026-11-16-u4-plugin-profile (campaign profile-architecture-rules, unit U4). No FR is minted; the criteria are AC30-AC32 under FR-01.01.

## Decision
A new bundled stack profile `claude-plugin` carries the generic Python data (Python 3.11+, `uv run pytest`, `uv run ruff check`, no dev server, no deploy, the same folder layout, the same CI and CodeQL defaults) plus six architecture rules for plugin projects. `python-plugin-monorepo` keeps its name and becomes "the generic Python-project profile" in its description only.

## Rules and their honest classes
- code versus prose, generated files next to their source: prompt-only (judgement).
- Anthropic's skill limits: prompt-only (mechanisable). `check_skill_authoring.py` is a report that no phase or CI job runs, so it is not claimed as enforcement.
- scripts run via `uv run`, hook paths via `${CLAUDE_PLUGIN_ROOT}`: prompt-only (mechanisable) with a note (nothing checks them for customer repos).
- no bare `python -` reading stdin: hook, mechanism `plugins/shipwright-iterate/scripts/hooks/bare_python_stdin_guard.py`, registered in that plugin's hooks.json (test parses the registration); it holds only in Claude Code sessions where shipwright-iterate is active.

## Adopt matching
The profile matcher scores by the dependency names a profile declares. The `claude-plugin` profile declares a runtime key `claude-plugin`; `lib/plugin_signal.py` (called from `analyze_codebase.py`, not from `stack_detector.py`, which sits at its bloat ceiling) adds that key when a `.claude-plugin/` folder exists at the root or under `plugins/*/` AND the repository is a Python-only one (`primary_language == python`). A Python-only repo without the folder still scores higher on the generic profile (its key set is a strict subset). Markdown-only, TypeScript and mixed repos are not moved (found by code review round 1 and 2, fixtures pin them). The key is hidden from rendered runtime lists and from the spec constraints.

## Reviews and dispositions
- Architecture review (external, both approve); external plan review: edge cases accepted (negative depth fixtures, constraint list test).
- External code review (GLM revise): namespacing the key accepted partially (hidden in renderers rather than moved), dedup guard and threshold removal accepted.
- Internal spec review PASS; code review round 1 high (non-Python repos promoted) and round 2 medium (mixed repos) both fixed with fixtures.

## Follow-ups (not done here)
- `folder_structure` of the new profile is the monorepo layout of the generic one; a customer single-plugin layout description is a follow-up.
- Wiring `check_skill_authoring.py` into a phase or CI stays outside this campaign.
- Prompt-only rules are inert until U6 makes reviewers read the rendered rules.
