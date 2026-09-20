# gpt-5.6-sol adversarial review — iterate-2026-09-20-r0-resolve-1a-envelope-delivery

Run via `codex exec -m gpt-5.6-sol --sandbox read-only`, reviewing the R0
iterate spec's first-draft `## Decision` section (file-based envelope
design), at the operator's explicit request — additive to, not a
replacement for, the standard external-review cascade (which uses the
identity-locked `gpt-5.6-terra`, not `sol`).

## Verdict: REJECT

## Findings

1. **Blocker: the pre-session binding is impossible as written.** The helper
   runs before Codex starts, yet the draft claimed a file scoped to
   `cwd + session identity`. That session identity does not exist yet. The
   design must do one of three things: leave an unbound cwd record (claimable
   by the wrong concurrent/manual/Claude session), pass a nonce through
   prompt/env/argv to the exact child (a runtime-specific wrapper), or add an
   atomic `SessionStart`/`UserPromptSubmit` binding protocol. None was
   specified. M3's own contract forbids lookup by "latest cwd/session" and
   requires an exact token.
2. **Blocker: the cross-runtime argument contradicts runtime neutrality.**
   The draft proposed registering the consumer hook in both Claude's and
   Codex's `hooks.json`, then argued Claude can't false-arm because it
   doesn't load Codex's hooks — which stops being true the moment Claude has
   its own registered copy of the same consumer logic.
3. **Blocker: Resolution A was not falsified independently; it was replaced
   with Resolution B's explicit envelope.** The draft's answer also missed
   the case of manual activity resuming the *original* session while an
   activation remains live/unconsumed (same session, different intent
   mid-stream) — not just "a different session."
4. **Blocker: hook trust was bypassed, not confirmed.** The sub-iterate's own
   AC explicitly requires trust confirmation via `codex /hooks`. The
   successful denial used `--dangerously-bypass-hook-trust` instead — proves
   denial semantics under bypass, not that a normally trusted bundled hook
   fires.
5. **Several "live-proven" claims were not actually established:** a trusted
   (non-bypassed) hook denying anything; `collaboration.spawn_agent` actually
   being *denied* (only observed); the prelaunch-file-to-exact-session
   binding; Claude using the same state safely; Desktop discovering/consuming
   the state; the full deny-then-consume-on-correct-call state machine.
6. **The tool-alias conclusion (draft probe 3) was wrong.** Official docs
   state `spawn_agent` also matches matcher `"Agent"` — the draft's claim
   that a Claude-shaped `Agent` matcher "will silently never match" the
   subagent-spawn case is false. (Verified independently post-review via a
   second, more targeted docs fetch — confirmed correct.)
7. **The confidence ledger laundered missing tests.** Rows citing
   `covered-by-existing-test` pointed at architectural reasoning, not a named
   pre-existing test — a misuse of that closed-vocabulary reason_code.
8. **Two scope holes:** the envelope file is plainly a producer/consumer
   boundary, but `Affected Boundaries` said `n/a`; and Codex documents that
   *hosted tools* (e.g. `WebSearch`) bypass `PreToolUse` entirely with an
   explicit caveat ("a useful guardrail, not a complete enforcement
   boundary") — not acknowledged in the draft's framing of what AC1a can
   actually guarantee. (Verified independently post-review — confirmed
   correct.)

## Disposition

All eight points accepted. Findings 1–4 and 8 drove a redesign (envelope
minted reactively inside `UserPromptSubmit`, once a real `session_id`/
`turn_id` exists — not as a free-standing pre-session file); finding 4 became
the explicit blocking-finding-for-R2 recorded in `## Acceptance Criteria`;
findings 6–8 corrected the probe write-up directly. See the revised
`## Decision`, `## Affected Boundaries`, and `## Live Feasibility Probes` in
the iterate spec.
