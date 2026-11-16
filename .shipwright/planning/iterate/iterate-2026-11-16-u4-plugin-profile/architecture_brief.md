# Architecture Brief: bundled claude-plugin profile (U4)

## Campaign context (read this first)
This is unit U4 of a six-unit campaign in this repository, built serially (campaign brief section 3). Merged: U1 (rule object, loader, validation in `shared/scripts/profile_architecture_rules.py`), U2 (`render_architecture_rules.py` writes a profile's rules into each project's `conventions.md`), U3a (first real rule objects, in `supabase-nextjs`). Next: U5 copies this profile into `.shipwright/profiles/shipwright-monorepo.json` and adds repo-only internal rules; U6 makes the code-reviewer read the rendered rules. So consumers of this profile exist as scheduled work in the same campaign; operator decision 4.1 says plugin rules ship to customers in a new bundled profile.

## The problem
Repositories that are Claude Code plugins (Python code, `.claude-plugin/` folders, hooks, skills) get the generic `python-plugin-monorepo` profile from adopt, which carries no architecture rules. The conventions that matter for such repositories (what goes into scripts versus to the AI, Anthropic's skill limits, scripts run via `uv run`, hook paths via `${CLAUDE_PLUGIN_ROOT}`, generated files next to their source) live only in prose in this repo.

## What already exists here
- `python-plugin-monorepo.json` (Python 3.11+, uv, pytest, ruff, folder layout); adopt's Jaccard matcher over stack dependency names gives it to every Python-only repo; CI/CodeQL templates keyed by profile name.
- Rule shape and loader (U1); a check that every bundled mechanism path exists; `check_skill_authoring.py` (a report, run by no phase or CI job); one invoked hook that covers one narrow Python rule (`bare_python_stdin_guard.py`).

## What would newly, permanently exist
- One bundled profile file `claude-plugin.json` carrying the same Python data plus six rule objects (one `hook` with a real, registered mechanism; four prompt-only; the skill-limits rule honestly `prompt-only (mechanisable)`).
- A matching signal: the stack detector adds a `claude-plugin` runtime key when a `.claude-plugin/` folder exists (root or `plugins/*/`); the new profile declares that key so it outscores the generic one; a Python-only repo without the folder still matches the generic profile.
- CI and CodeQL registry entries for the new name (same Python template), tests, docs; the generic profile's description is rewritten, no rename.

## Options on the table
- A (chosen): new bundled profile + data-driven matching signal (a stack key the detector emits).
- B: put the rules into `python-plugin-monorepo` itself (would apply plugin rules to every Python-only repo).
- C: keep the profile only for Shipwright's own repo (`.shipwright/profiles/`), no bundled one (contradicts decision 4.1).
- D: do nothing.

## Constraints that are not negotiable
No new FRs (criteria under FR-01.01). A Python-only repo must keep its current match. A mechanism counts as enforcement only if something invokes it. No rename of `python-plugin-monorepo`.
