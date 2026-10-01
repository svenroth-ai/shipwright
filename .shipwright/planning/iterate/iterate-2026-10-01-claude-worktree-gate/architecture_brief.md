# Architecture Brief: claude-worktree-gate

## The problem

Every `/shipwright-iterate` run is supposed to start by creating its own separate working copy (a git worktree) and do all its work there. On Claude Code that rule exists only as written instructions in the skill. With the newest models, sessions regularly skip it and start editing the main checkout directly, which mixes the change into whatever else is open on main and breaks the later isolation checks. The Codex side already has a mechanical enforcement; the Claude side has none.

## What already exists here

- Written instruction in the iterate skill (step "Worktree Isolation") — no enforcement.
- A leak check at the start and end of finalization that detects, after the fact, that the main tree was touched.
- `setup_iterate_worktree.py`, which creates the worktree and writes a per-session pointer file naming it.
- A Codex-only pair of hooks: one records "this session was started as an iterate", the other denies the session's first tool call unless it is the worktree setup command.
- A general Bash safety hook (`validate_command.sh`) that blocks dangerous shell commands.

## What would newly, permanently exist

A pair of Claude Code hook registrations (one script) in the iterate plugin that records "this session started an iterate" and, until the session is working in a worktree, refuses file edits to the main checkout and shell commands that are not clearly read-only. It runs on every edit/shell/skill tool call of every session in a Shipwright project (a no-op unless armed). The iterate plugin's maintainers keep its command allowlist correct as the skill's pre-setup steps change.

## Options on the table

- **A:** A Claude-side hook that arms on the iterate skill/command and checks the real worktree state on every mutating call, denying until the worktree exists.
- **B:** The same arming, but only a one-time check on the first tool call after arming (a direct copy of the Codex design).
- **C:** Strengthen the written instructions and rely on the existing after-the-fact leak check at finalization.
- **D:** Do nothing.

## Constraints that are not negotiable

- Hooks in a plugin must be registered in the plugin's own `hooks.json` (project-level hook installs are not supported for plugin-root paths).
- A broken or confused hook must never trap a session: the worktree setup command itself has to remain runnable at all times.
