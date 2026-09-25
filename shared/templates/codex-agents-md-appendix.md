<!-- shipwright:codex-agents-md-appendix -->
## Codex operating policy

This project is managed by Shipwright (`/shipwright-iterate`). When Codex CLI
drives an iterate session, a `UserPromptSubmit` hook mints an activation
record on the session's first prompt if it matches the iterate skill's
envelope; a `PreToolUse` hook then denies any first tool call that isn't the
mandatory worktree-setup step, forcing an armed session through the correct
setup before anything else runs — Codex has no native skill/hook wiring of
its own, so Shipwright enforces this mechanically instead. Do not use
`xhigh` or `max` reasoning unless concrete risk, complexity, or a failed
review justifies it.

- Use one isolated worktree and branch per iterate; never push the default
  branch directly.
- Preserve unrelated and unexplained changes. Do not rewrite, discard, or
  absorb them silently.
- Reviews through the project's configured OpenRouter route are authorized.
- Do not commit mutable derived snapshots (e.g. a root
  `shipwright_test_results.json`). Preserve the required test ledger and
  surface evidence through the iterate skill's own contract.
- Delivery is complete only when `deliver_pr.py` reports `DELIVERED`.
