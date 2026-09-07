# Iterate Spec: bloat-gate-subagent-marker-isolation

- **Run ID:** iterate-2026-09-07-bloat-gate-subagent-marker-isolation
- **Type:** bug
- **Complexity:** medium
- **Status:** draft

## Goal
Stop `bloat_gate_on_stop.py` from blocking a campaign orchestrator's own Stop
event on a background subagent's still in-flight, uncommitted oversize edit,
when the orchestrator shares its git worktree with a `sub-iterate-runner`
Task it spawned.

## Root Cause

The marker writer (`check_file_size.py`, PostToolUse) and the Stop gate
(`bloat_gate_on_stop.py`) both keyed the per-session marker file
(`bloat_pending.<key>.json`) off the hook stdin payload's `session_id` alone.
Claude Code gives a subagent spawned via the Agent/Task tool the SAME
`session_id` as the session that spawned it — the only field that
distinguishes a subagent's hook invocation from the main/orchestrator
thread's own is `agent_id`, present in the payload only when the hook fires
inside a subagent call. So a background `sub-iterate-runner` sharing the
orchestrator's worktree (`campaign-worktree.md`) also shared its marker
file: the subagent's PostToolUse (growing a tracked file past the 300/400
line ceiling while mid-edit, uncommitted, unbaselined) wrote a `crossing`
entry the orchestrator's own next Stop then read and blocked on — even
though the offending file was never part of the orchestrator's own diff and
the orchestrator had no way to fix a file it was not editing. The block
re-fired on every subsequent Stop because the hook is not timing-sensitive —
it re-evaluates marker state on every Stop, and the marker/TTL do not
distinguish "written by a sibling still running" from "written by me".

Not a worktree-wide-vs-diff problem (the report's framing) — the marker was
already session-scoped correctly; the missing dimension was **agent**, not
session.

Observed 2026-09-07 in campaign-req3-06-mechanics-webui (shipwright-webui
repo), worktree `.worktrees/campaign-req3-06-mechanics-webui`, offending
file `server/src/core/preview-session-manager.test.ts` at 343 lines.

## Acceptance Criteria
- [x] A background subagent's PostToolUse marker entry (payload carries
      `agent_id`) is written to a marker file distinct from the spawning
      session's own (no `agent_id`).
- [x] The orchestrator's own Stop event (no `agent_id`) does not block on a
      sibling subagent's in-flight marker, even when both share
      `session_id` and the same worktree.
- [x] A subagent's OWN Stop-class event (payload carries the SAME
      `agent_id` it wrote the marker under) still finds and can block on its
      own marker — this is isolation, not a silent drop of enforcement.
      **Scope note (flagged independently by architecture review, internal
      plan review, AND external code review — see those sections):**
      `bloat_gate_on_stop.py` is registered on `Stop` only, never
      `SubagentStop`, so in production this hook's own invocation never
      actually carries `agent_id` — this AC is a defensive-correctness
      property of `marker_key`, proven with a direct synthetic-payload call
      to the gate script, NOT a claim that a live `SubagentStop`-triggered
      enforcement path exists today. A subagent's own oversize edit is
      caught (if at all) by its own F0/F11 finalization's independent
      `bloat_baseline.scan()`, not by this hook.
- [x] Existing single-agent (no `agent_id`) behavior is byte-for-byte
      unchanged — all 47 pre-existing bloat-gate tests still pass with no
      edits.
- [x] `docs/hooks-and-pipeline.md`'s `check_file_size.py` row documents the
      new `agent_id` suffix (Rule: hook-behavior change → same-diff doc
      update).

## Spec Impact
- **Classification:** none
- **NONE justification:** internal hook-marker-keying bugfix; no
  user-facing feature/requirement changes, no FR touched. The framework's
  own bloat-gate machinery is infrastructure (`cross_component`), not a
  product FR.

## Out of Scope
- Heartbeating the campaign session lock for long-running subagent Tasks
  (a separate, already-documented gap in `campaign-worktree.md`).
- Making `sub-iterate-runner` self-resolve its own oversize touches before
  yielding (the bug report's "Alternative" suggestion) — the marker-key fix
  makes this unnecessary: the runner's own F0/F11 finalization already
  catches its own oversize files (via `bloat_baseline.scan()`, an
  independent full-tree walk — NOT the marker file, which
  `bloat_gate_on_stop.py` never reads for a subagent since it is registered
  on `Stop` only, never `SubagentStop` — internal plan review, 2026-09-07),
  without blocking the orchestrator.
- Renaming `_session_id` to `_marker_key` in the two hook scripts — kept the
  existing name (docstring updated) to minimize diff surface on already
  reviewed/battle-tested files; the actual composite-key logic lives in the
  new `bloat_marker_key.py`.

## Design Notes
n/a — no UI/design surface; pure hook-internals fix.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `check_file_size.py::_write_marker_entry` (via `_session_id`/`marker_key`) | `bloat_gate_on_stop.py::main` (via `_session_id`/`marker_key`) | JSON marker file, `.shipwright/locks/bloat_pending.<key>.json` |

`touches_io_boundary` risk flag: the marker file IS a serialized
producer/consumer boundary between the two hook scripts (both match
`hooks.json`/`**/hooks/*.py` risk-flag paths too, firing `cross_component`).

## Confidence Calibration

- **Boundaries touched:** the `bloat_pending.<key>.json` marker
  producer/consumer boundary above (both hook scripts touched).
- **Empirical probes run:**
  - Ran the real writer against a synthetic subagent payload
    (`session_id` shared, `agent_id` set) and confirmed via filesystem
    inspection that it lands in `bloat_pending.<sid>.<agent_id>.json`, not
    `bloat_pending.<sid>.json` — `test_writer_keys_subagent_marker_separately_from_orchestrator` PASSED.
  - Ran the REAL writer (subagent payload) followed by the REAL gate
    (orchestrator payload, same `session_id`, no `agent_id`) end-to-end —
    the exact repro of the reported bug — and confirmed the gate now
    passes silently — `test_orchestrator_stop_ignores_inflight_subagent_marker`
    PASSED (this is the `category:"integration"` behavior for the
    `cross_component` gate).
  - Confirmed the subagent's OWN Stop-class event (agent_id present) still
    blocks on its own marker — `test_subagent_own_stop_still_sees_its_own_marker`
    PASSED — proving this is isolation, not silent enforcement loss.
  - Ran the full pre-existing 47-test bloat-gate suite unmodified against
    the fix — all 47 PASSED, confirming byte-identical behavior when
    `agent_id` is absent (the ordinary single-agent iterate path).
  - **Live payload capture (2026-09-07, post-review):** the synthetic-payload
    tests above assume `agent_id` is genuinely present on a real subagent's
    PostToolUse hook call — sourced from Claude Code's official hooks
    reference, not yet independently observed. Verified with a real payload:
    temporarily instrumented (with the user's explicit permission) the
    **plugin-cache** copy of `check_file_size.py` — hooks execute from
    `~/.claude/plugins/cache/shipwright/...`, not from this worktree's
    source, a distinction a first attempt at this same probe missed,
    producing a false negative (its "no `agent_id`" reading came from
    exercising the *stale, unpatched* cache copy, which has no
    `marker_key`/`agent_id` logic at all — not from an absent field) — to
    dump the raw stdin payload to a scratch file, then triggered one real
    `general-purpose` subagent `Edit` call. Captured payload confirmed
    `"agent_id": "<subagent-id>", "agent_type": "general-purpose"` genuinely
    present, alongside the same `session_id` as the spawning session — the
    fix's core precondition, independently confirmed. Instrumentation
    reverted immediately after the single capture; cache file diffed clean
    against its pre-probe backup.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | Subagent's marker write is keyed separately from the spawning session's own | tested | `test_writer_keys_subagent_marker_separately_from_orchestrator` PASSED |
  | 2 | Orchestrator's Stop does not block on a sibling subagent's in-flight marker (integration) | tested | `test_orchestrator_stop_ignores_inflight_subagent_marker` PASSED |
  | 3 | Subagent's own Stop-class event still sees/blocks on its own marker | tested | `test_subagent_own_stop_still_sees_its_own_marker` PASSED |
  | 4 | `marker_key` sanitizes filesystem-unsafe `agent_id` characters | tested | `test_marker_key_sanitizes_unsafe_agent_id_characters` PASSED |
  | 5 | `marker_key` with no `agent_id` matches the prior session-only behavior exactly | tested | `test_marker_key_no_agent_id_matches_prior_session_only_behavior` PASSED |
  | 6 | Pre-existing single-agent bloat-gate behavior is unchanged | tested | 47/47 pre-existing tests PASSED unmodified |
  | 7 | Real subagent PostToolUse payloads genuinely carry `agent_id` (not just per official docs) | tested | live payload capture, 2026-09-07 — see Empirical probes run |

- **Confidence-pattern check:** asymptote (depth) — a second "are you
  confident?" pass, post-review, DID surface something: the docs-sourced
  `agent_id` claim had never been independently observed against a real
  payload. Probing it once caught a methodology trap (a first live-probe
  attempt silently exercised the stale plugin-cache hook copy, producing a
  false "field absent" reading) before it could be trusted; a second,
  correctly-scoped probe then confirmed the claim directly (row 7). Coverage
  (breadth) — every ledger row is `tested`, 0 untested-testable; integration
  composition covered per row 2 above.

## Architecture Review
- **Brief:** n/a (this is a mini-plan `--mode iterate` review, not `--mode architecture` — this is a bug fix to existing machinery, not a new-thing-should-this-exist-at-all question).
- **Verdicts:** glm=revise · openai=revise (both medium/low severity, no high — "revise is not a stop", `iteration-planning.md`)
- **Smallest thing that would do (per reviewers):** as proposed, with two hardening fixes (see Findings).
- **Findings:**
  1. (openai, medium; glm, low) Naive char-substitution sanitization of `agent_id` (`[^A-Za-z0-9_-]` → `_`) is lossy and can collide two distinct agent_ids into one key, silently re-pooling the exact bug this fix exists to close. **Accepted and fixed:** replaced with a collision-free `~XX` hex-escape bijection in `bloat_marker_key.py::_encode_agent_component`; added `test_marker_key_encoding_is_collision_free_not_lossy_substitution`.
  2. (glm, medium; openai, medium) AC #3 ("subagent's own Stop-class event still blocks on its own marker") is only tested with a synthetic payload; `bloat_gate_on_stop.py` is registered on `Stop` only, never `SubagentStop`, so in production this script never actually receives `agent_id` — the claim overclaimed a live enforcement path that may not exist. **Accepted and fixed:** documented explicitly in the module docstring and `docs/hooks-and-pipeline.md` that this hook's job is isolation only (stop a sibling's marker from blocking the spawner), NOT subagent self-enforcement — that's delegated to the subagent's own F0/F11 finalization (already true architecturally per `campaign-worktree.md`). AC #3 in this spec is now understood as a defensive-correctness property of the function, not a claim about a live production trigger.
  3. (glm, low) Pre-fix stale markers written under the old shared key keep blocking until TTL (1h) expiry. **Accepted, not fixed:** self-healing within `MARKER_TTL_SECONDS` (3600s); no migration tooling built for a bounded, self-healing rollout characteristic — would be over-engineering.
  4. (openai, low) Module-naming inconsistency in the mini-plan draft (`bloat_baseline.marker_key` vs `bloat_marker_key.py`). **Accepted and fixed:** both names are correct and intentional (`bloat_marker_key.py` defines it, `bloat_baseline.py` re-exports it for the existing `_bb.marker_key` call sites) — clarified in both docstrings.
  5. (glm, low) Whitespace-only `agent_id` collapsing correctly to the absent-agent key. **Verified already correct** (pre-existing `.strip()` truthiness check); added `test_marker_key_whitespace_only_agent_id_treated_as_absent` to make the guarantee explicit rather than incidental.
  6. (openai, medium) A literal `.` inside `session_id` itself is never encoded, so a legacy no-`agent_id` key (e.g. `"a.b"`) is in principle ambiguous with a composite key for session `"a"` + an `agent_id` encoding to `"b"`. **Accepted, not fixed:** real Claude Code `session_id` values are UUIDs (hyphens, no dots) — not reachable in practice — and encoding `session_id` too would change the no-`agent_id` filename shape, breaking the byte-identical-with-prior-behavior guarantee (AC #4) for zero practical benefit. Documented as a residual, accepted risk directly in `bloat_marker_key.py::marker_key`'s docstring.
- **Reconciliation:** No findings were rejected. All medium/low findings addressed via code + doc changes above (no `high` severity finding was raised, so no user discussion pause per `iteration-planning.md` "Handling results (Branch A)").

## Internal Plan Review
- **Ran:** yes
- **Reviewer:** `shipwright-plan:opus-plan-reviewer`
- **Verdict:** low severity, no blockers
- **Findings:**
  7. (low) `_encode_agent_component`'s prior `[:200]`-truncated-after-encoding step undermined its own "collision-free" claim — two distinct long `agent_id` values sharing a 200-char encoded prefix would collapse to the same key. **Accepted and fixed:** removed the cap entirely (unbounded encode; `agent_id` is a short Claude-Code-internal identifier, never attacker-controlled arbitrary-length input); added `test_marker_key_no_collision_past_prior_200_char_truncation_boundary`.
  8. (low) This spec's Out-of-Scope section claimed F0/F11 finalization catches a subagent's own oversize files "under its own marker" — inaccurate; F0/F11's bloat backstop is `bloat_baseline.scan()`, an independent full-tree walk that never touches the marker file (confirmed: `bloat_gate_on_stop.py` is `Stop`-only across all 13 plugins' `hooks.json`, never fires with `agent_id`, so a per-agent marker file is genuinely unread in production — bounded local-disk debris only, since `.shipwright/locks/` is gitignored). **Accepted and fixed:** corrected the Out-of-Scope wording above; no reaper built (low-severity, bounded, gitignored — a follow-up backlog note, not a blocker).
  9. (low) `docs/hooks-and-pipeline.md`'s `Stop`-registered `bloat_gate_on_stop.py` row was left describing pre-fix behavior with no mention of the new isolation semantics, asymmetric with the thoroughly-updated `check_file_size.py` row. **Accepted and fixed:** updated for symmetry.
- **Follow-up (not built, documented only):** a `.shipwright/locks/bloat_pending.*` directory reaper analogous to `event_once.py`'s `_purge_expired_claims`, for per-agent marker files that accumulate as local-disk debris across many subagent invocations in a long-running campaign. Out of scope for this bug fix (bounded, gitignored, no functional impact).

## Doubt Review
- **Ran:** yes
- **Reviewer:** `shipwright-build:doubt-reviewer`
- **Findings:**
  10. (high) The fix's backward-compatibility claim (AC #4, "no `agent_id` -> byte-identical key") rests on an unverified half of a binary: the live payload capture (row 7, Confidence Calibration) proved `agent_id` IS present on a **subagent's** PostToolUse payload, but nothing had yet confirmed it is genuinely **absent** — not just unused — on a plain **top-level** (non-Task) PostToolUse payload. Since `bloat_gate_on_stop.py` structurally never sees `agent_id` (Stop-only, never SubagentStop — finding #2), a wrong assumption here would mean the ordinary orchestrator path gets silently agent_id-suffixed by the writer but never found by the gate — disabling the bloat gate for the primary use case, worse than the bug being fixed, and failing silently (fail-open, no diagnostic). **Accepted and resolved, not a live defect:** already had direct evidence — the SAME live-capture session's very first captured line (my own top-level `Edit` call against the plugin-cache file, made before any subagent ran) has NO `agent_id` key at all in the payload (goes straight from `"permission_mode"` to `"effort"`), unlike the subagent's line which inserts `"agent_id": "...", "agent_type": "general-purpose"` at that exact position. This is a genuine real top-level payload, captured via the identical instrumentation technique, confirming true absence (not empty-string) rather than an assumption from docs alone.
  11. (low) `_encode_agent_component` calls `str.encode("utf-8")` in strict mode; an unpaired surrogate code point in `agent_id` (malformed, not attacker-reachable per the existing accepted-risk framing) would raise inside the per-character loop. **Accepted, not fixed:** both hook scripts' `main()` already fail open on any exception (advisory writer, pass-silently gate) — a crash here degrades to "no marker for this call," never a hard failure; `agent_id` is Claude-Code-internal, not attacker-controlled.
  12. (low, informational) The two hook scripts' `_session_id()` delegating wrappers are exercised only via the new subprocess-based integration tests (correct test shape for a cross-file boundary claim), which per this repo's own known diff-coverage limitation (subprocess execution is invisible to line coverage instrumentation) may register as uncovered by a strict diff-coverage gate despite being behaviorally proven. Pure logic (`marker_key`, `_encode_agent_component`) is separately, directly unit-tested. **Accepted, not fixed:** pre-existing, project-wide, already-known gate characteristic, not specific to this change.
- **Reconciliation:** No findings rejected; the one high finding was resolved with evidence already on hand rather than requiring new work, both lows accepted as documented trade-offs.

## Verification (medium+)
Full `shared/tests/` suite (54/54 targeted + full-suite run) + repo-wide `uvx ruff@0.15.15 check .` — see F0/F5.
