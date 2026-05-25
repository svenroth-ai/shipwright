# Escape Hatch

When complexity = large, print scope assessment with two options.

See `references/iteration-planning.md` for the full protocol including
handoff file format and failure behavior.

## Summary

The escape hatch is the deliberate exit point for changes that exceed
the iterate skill's adaptive envelope. Rather than try to absorb a
large-scope change into the iterate lifecycle, the agent prints a
scope assessment and hands off to the full pipeline
(`/shipwright-plan` + `/shipwright-build`).

Triggers:

- Complexity classifier returns `large`.
- Mid-flight escalation lands at `large` from any starting point
  (`references/mid-flight-escalation.md`).
- User explicitly requests escape hatch.

The full protocol — including the handoff template, the WIP-checkpoint
rule for dirty trees, and the failure-mode behavior — lives in
`references/iteration-planning.md`.
