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
The profile matcher scores by the dependency names a profile declares. The `claude-plugin` profile declares a runtime key `claude-plugin`; `lib/plugin_signal.py` (called from `analyze_codebase.py`, not from `stack_detector.py`, which sits at its bloat ceiling) adds that key when a `.claude-plugin/` folder exists at the root or under `plugins/*/` AND the repository is a Python-only one (`primary_language == python`). `profile_matcher.SIGNAL_KEYS` makes a profile that does NOT declare the key (bundled or a project's own) score against the signature without it, so its score is exactly what it was; the plugin profile ties or beats the generic one, and ties still go project > user > bundled. Markdown-only, TypeScript and mixed repos are not moved (fixtures pin them, with custom project profiles too). The key is hidden from rendered runtime lists and from the spec constraints, but it IS present in the adopt snapshot's `stack.runtime`: the WebUI adopt card iterates that dict, so it will show `claude-plugin: .claude-plugin/`. Accepted as additive; flagged as a WebUI follow-up.

## Copying the profile
The hook rule's `mechanism` path is Shipwright-repo-relative, so a copy in a project's `.shipwright/profiles/` fails the path check in `validate`; the rule note and `docs/stack-profiles.md` say to make that rule prompt-only (or drop the mechanism) in the copy. The hook guards the Bash tool only (not PowerShell) and also refuses an empty heredoc.

## Reviews and dispositions
- Architecture review (external, both approve); external plan review: edge cases accepted (negative depth fixtures, constraint list test).
- External code review (GLM revise): namespacing the key accepted partially (hidden in renderers rather than moved), dedup guard and threshold removal accepted.
- Internal spec review PASS; code review round 1 high (non-Python repos promoted) and round 2 medium (mixed repos) both fixed with fixtures.

## Follow-ups (not done here)
- `folder_structure` of the new profile is the monorepo layout of the generic one; a customer single-plugin layout description is a follow-up.
- Wiring `check_skill_authoring.py` into a phase or CI stays outside this campaign.
- Prompt-only rules are inert until U6 makes reviewers read the rendered rules.

## Process note
The unit was first classified small by the diff re-check (the brief says medium), so the internal plan and architecture arms were skipped; after the orchestrator's review they were run (model opus) and recorded, and the doubt pass was re-recorded from the orchestrator's review. Merge collision: U3b adds FR-01.01 AC21/22 and an INDEX.md row at the same spots; whoever merges second keeps both and regenerates INDEX.md.
