# Iterate: bloat-gate Stop-hook fan-out dedup

- **Run ID:** `iterate-2026-06-20-bloat-gate-stop-fanout-dedup`
- **Intent:** BUG (Path C) · **Complexity:** medium (risk floor `cross_component`)
- **Spec Impact:** NONE (behavior-preserving bug fix; no FR / `spec.md` change)
- **Risk flags:** `cross_component` (edits `shared/scripts/hooks/bloat_gate_on_stop.py`,
  matches `(^|/)hooks/.+\.py$`) → integration coverage + full test suite + full review

## Problem (observed)

WebUI session `bfd244ca-6f1f-4319-a9b2-a05a416e402e` shows **12 identical
"Stop hook feedback" blocks** from the `SHIPWRIGHT BLOAT GATE`, all stamped
within ~350 ms (`2026-06-20T10:36:09.396Z` … `.753Z`) — i.e. **one Stop event
fanned across the 12 enabled plugins**, one `bloat_gate_on_stop.py` invocation
per plugin.

## Root cause (Iron Law: investigated before any fix)

Claude Code fires every enabled plugin's Stop hooks with no active-plugin
filter, so a hook registered in N plugins runs N× per event. PR #250
(`iterate-2026-06-14-hook-fanout-dedup`) wrapped the redundant work of THREE
Stop/SessionStart hooks in the fail-open `event_once.claim_once_for_event`
guard — `audit_phase_quality_on_stop`, `generate_handoff_on_stop`,
`check_artifact_drift` — but **left `bloat_gate_on_stop.py` unguarded**. The
gate is invisible on the pass path (empty stdout), so the duplication only
surfaces when it actually **blocks**: every invocation that finds offenders
emits the same block. Root cause = a missing dedup guard, not a logic error in
the gate itself.

## Fix (mini-plan)

Add the established once-per-`(Stop, session)` claim to the bloat gate's **block
path only**:

1. Import `claim_once_for_event` from `lib.event_once`.
2. After all no-op/pass guards (no marker → pass, no/malformed baseline → pass,
   no offenders → pass), and immediately before `_emit_block`, claim the event.
   The first invocation to reach a real block wins and emits; the losers emit
   the empty pass. Key: `("stop-bloat", sid)`, reusing the gate's existing
   `sid` (payload `session_id` → `SHIPWRIGHT_SESSION_ID` → `"unknown"`).
3. `sid == "unknown"` → helper returns True without claiming (shared-key
   collision guard) → fail-open over-emit, never a dropped block.

**Why the claim sits on the block path, not at the top:** the PR #250 lesson —
take the claim AFTER the no-op guards so a marker-less / baseline-less /
offender-less invocation never consumes it. A fixed-file re-stop re-measures
under the limit → `not offenders` → passes before ever reaching the claim, so
the guard cannot mask a genuinely-cleared file.

### Alternative considered (rejected)

*Per-stop-event discriminator* (fold the transcript's last-message UUID into the
claim key) would avoid the 30 s TTL re-arm window entirely. Rejected:
(a) it leaks one unbounded `.cache` claim file per stop event (the TTL re-arm
GC only fires for a repeated key); (b) inconsistent with the three hooks PR #250
already guards with the plain `(event, session)` key; (c) the 30 s window is
benign here — the local gate is an advisory nudge and **CI anti-ratchet is the
authoritative gate**; a cleared file passes regardless of the claim, and the
only suppressed case (ignore-the-block + re-stop within 30 s) is exactly the
tight block-loop the TTL is meant to damp. Chose the consistent `(event,
session)` key.

## Affected Boundaries

- `shared/scripts/hooks/bloat_gate_on_stop.py` — Stop hook (Claude-Code hook I/O
  boundary; stdin JSON payload, stdout decision JSON).
- `.shipwright/.cache/stop-bloat-<sid>.claim` — new claim file (gitignored cache).

## Confidence Calibration

- **Boundaries touched:** the bloat-gate Stop hook (stdin/stdout contract) and
  the `.shipwright/.cache` claim file written by `claim_once_for_event`.
- **Empirical probes run:**
  - Session forensics: 12 block messages, single ~350 ms window, exactly =
    12 enabled plugins → confirmed plugin fan-out (not project-level
    double-registration; webui `.claude/settings.json` registers no Stop hook).
  - `is_cross_component_change(["shared/scripts/hooks/bloat_gate_on_stop.py"])`
    → `True` (predicate authoritative; keyword classifier under-called "small").
  - Read all existing `test_bloat_gate_on_stop.py` cases → every one fires the
    gate ONCE per fresh tmp dir → the dedup change cannot regress them.
- **Test Completeness Ledger:**

  | Behavior (this diff) | Disposition | Evidence |
  |---|---|---|
  | N× fan-out with offenders → exactly one block, rest empty | `tested` | `test_bloat_gate_fanout_blocks_once` (unit) + `test_bloat_gate_fanout_blocks_once` (integration, real git, 12 plugins) |
  | Per-session scoping: a second session still blocks | `tested` | `test_bloat_gate_fanout_per_session_independent` |
  | Single firing with offenders still blocks (no regression) | `tested` | existing `test_blocks_on_anti_ratchet` / `test_blocks_on_new_crossing_outside_baseline` (unchanged, green) |
  | No-op invocation (no marker/baseline/offender) never claims | `tested` | `test_bloat_gate_pass_path_does_not_claim` |
  | `sid == "unknown"` → fail-open, still blocks | `tested` | existing `test_session_scoping_unknown_fallback` (unchanged, green) |
  | Block-on-second-genuine-stop after >TTL re-arms | `untestable` | `covered-by-existing-test` (TTL re-arm proven in `event_once` tests; no new TTL logic here) |

  0 untested-testable behaviors.
- **Confidence-pattern check:** *asymptote (depth)* — the gate's block/pass
  logic is unchanged; only an idempotency guard is added on the block edge.
  *coverage (breadth)* — fan-out, per-session, single-fire, pass-path, unknown-sid.
  *integration composition* — `cross_component` requires proof the
  register-everywhere hook + the claim guard COMPOSE under a real multi-plugin
  fan-out: `integration-tests/test_hook_fanout_consolidation.py::
  test_bloat_gate_fanout_blocks_once`, recorded `category:"integration"`.

## Acceptance Criteria

- **AC-1** One Stop event firing the gate N× (same session) with offenders →
  exactly one `decision:block`, the rest empty stdout.
- **AC-2** A different session blocks independently (claim is per-session).
- **AC-3** A single firing with offenders still blocks (no regression).
- **AC-4** Pass-path invocations never create the claim file and never block.
- **AC-5 (integration)** The real hook script driven across a 12-plugin fan-out
  in a git-backed project emits exactly one block.

## Deployment note

Hook source lives in this monorepo; webui runs the cached plugin. After merge,
`bash scripts/update-marketplace.sh` is required for the fix to reach webui's
runtime (standard plugin-cache sync; out of this PR's scope but tracked in F12).
