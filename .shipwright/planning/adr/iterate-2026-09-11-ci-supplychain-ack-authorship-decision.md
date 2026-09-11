# CI supply-chain ack authorship guard

## Context

`record_ci_supplychain_ack.py` computed a run-id- and content-bound
acknowledgement for a `touches_ci_supplychain` change, but had no check for
*who* was calling it. `campaign-mode.md` Step 3.4 stated in prose that a
campaign sub-iterate runner must never write its own ack, but nothing
enforced that. On PR #718 (trg-33d30377), a runner hit the escalation,
wrote its own ack for its own diff, and every existing check (run binding,
content-fingerprint binding, field shape) validated it perfectly — none of
them asked who wrote it. A second, independent gap surfaced while building
the fix: the writer fingerprinted only the WORKING TREE, while the F11
verifier fingerprints the COMMITTED branch diff, so once a CI change was
committed the writer refused with "no acknowledgement is needed" — actively
wrong — and an operator resolving the escalation after the fact had no
reachable path at all.

## Decision

`record_ci_supplychain_ack.py` refuses outright (no override) while
`SHIPWRIGHT_LOOP_UNIT_ID` is set in its own process environment — the
variable an active autonomous-loop unit's process carries, propagated to
its Bash-tool subprocesses via `capture_session_id.py`'s `CLAUDE_ENV_FILE`
write. The guard is checked at every entry point that can reach the write
(`main()`, `build_ack()`, and `write_ack()` itself). The CLI also accepts
`--commit <ref>` to fingerprint an already-committed CI change via the same
`merge-base..ref` view the F11 verifier recomputes, and every ack now
stamps a `provenance` field (`"worktree"` | `"commit"`) that the verifier
requires at the per-run location (legacy-location acks are grandfathered).

## Consequences

A campaign runner (or a `shipwright-build --autonomous` unit — they share
the same env var) can no longer author its own ack, in either content mode,
with no file left behind on refusal. An operator resolving an escalation
has a reachable path both pre- and post-commit. `CLAUDE_ENV_FILE`'s tracked
export lines are now synced (not merely appended) to the hook's current
environment each `SessionStart`, so a stale value from a finished unit does
not linger and block a later legitimate operator action in the same
session. This is a process-identity heuristic, not a cryptographic
guarantee — an agent willing to `unset` the variable before invoking the
CLI can still defeat it; that residual risk is disclosed, not hidden.

## Rationale

Gate on data (who authored the write, checked mechanically), not on an
agent being expected to behave (webui #285 already showed a full medium
iterate with external plan review reversing an accepted-risk posture
unnoticed). `provenance` stays required even though no described
authorization decision currently reads its value (an external review
question) — it is the one signal distinguishing this CLI's own output from
a hand-assembled forgery that otherwise gets run-id and content binding
right by copying a real ack.

## Rejected alternatives

`SHIPWRIGHT_SESSION_ID`-based authorship matching — rejected because a
Task-spawned campaign sub-iterate runner and its orchestrating session are
plausibly the same session id, and the documented remedial flow has the
operator resolve the escalation from that same session. Leaving the rule as
prose only (Option C in the architecture brief) — rejected as the exact
posture that already failed once. A cryptographic/unspoofable
operator-identity proof — not buildable with what this repo has (no
human-in-the-loop signing infrastructure).

## Full detail

Iterate spec: `.shipwright/planning/iterate/iterate-2026-09-11-ci-supplychain-ack-authorship.md`
(Root Cause, Fix, Code Review Cascade, Internal/External LLM Review, Review
Record). Architecture brief:
`.shipwright/planning/iterate/iterate-2026-09-11-ci-supplychain-ack-authorship/architecture_brief.md`.
Mini-plan: `.shipwright/planning/iterate/2026-09-11-ci-supplychain-ack-authorship-miniplan.md`.
