# Architecture Brief: codex-plugin-execution-reliability R0 — envelope delivery

## The problem

Codex CLI sessions can call tools before a Shipwright iterate's own worktree
setup has actually run — there is no signal today that blocks a tool call
until the run's own precondition (an isolated worktree existing) is
satisfied. Claude-side sessions have the same gap: no runtime today denies a
tool call before that precondition holds, for either runtime. This shows up
as sessions that can proceed past a phase they should not yet be in.

## What already exists here

- Claude-side `hooks.json` files (12 plugins) register `PreToolUse` for two
  narrow purposes (Bash command validation in one plugin, a compliance check
  in another) — neither covers this precondition.
- Codex CLI 0.155.0 supports a `PreToolUse` hook event that can deny a tool
  call outright, and a `UserPromptSubmit` event that fires once per prompt
  with the real session/turn identity already resolved.
- `shipwright-webui`'s Codex-Light path already composes and sends the first
  prompt text programmatically before a Codex session starts responding.

## What would newly, permanently exist

A small, versioned on-disk record format: something mints it once a
precondition is confirmed, and a `PreToolUse`-class hook consumes it before
allowing the gated tool call, denying if the record is absent, stale, or
already consumed. It would be written and read by up to three launch
surfaces (terminal, `shipwright-webui`, potentially a native desktop app) and
would need to keep working correctly as those surfaces evolve.

## Options on the table

- **A:** Mint the record via a pre-launch helper/file, written before the
  target session starts, keyed by working directory and looked up by the
  session once it starts.
- **B:** Mint the record reactively, inside the target runtime's own
  first-prompt-received hook, once real session/turn identity already
  exists; deliver the precondition signal as part of the session's first
  prompt text rather than as a separate pre-existing file.
- **C:** Do nothing new — rely on documentation/operator discipline that
  tool calls should not happen before worktree setup, with no technical
  enforcement.

## Constraints that are not negotiable

- Windows is a supported development platform for this monorepo (path
  normalization, shell quoting).
- Whatever is built must not require changes to Claude Code's own hook
  runtime, since this repo does not control that runtime.
