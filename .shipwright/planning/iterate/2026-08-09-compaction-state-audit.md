# Iterate Spec: compaction-state-audit

- **Run ID:** iterate-2026-08-09-compaction-state-audit
- **Type:** bug
- **Complexity:** medium (overridden from Stage-1 `small`)
- **Status:** implemented

## Complexity override

Stage 1 (`classify_complexity.py`) returned `small` with a `touches_auth`
risk flag from the message keyword `session`. Repo Scout correction: this
is a message-keyword false positive — the change touches conversation/run
*session* files (`session_handoff.md`, `reviews.json`), not user-facing
authentication, and no file under `src/lib/supabase/`, `**/auth/**`, or
`middleware.ts` is touched. `touches_auth` is dropped.

Overridden to `medium` on positive evidence (`SKILL.md` §E requires
positive evidence, never absence of it, to buy medium): the fix spans
multiple governing reference docs of the `/shipwright-iterate` skill itself
(`iteration-planning.md`, `iteration-reviews.md`, `path-a-feature.md`,
`SKILL.md` §B1) plus a shared library consumed by every plugin that calls
`generate_session_handoff.py` (`shared/scripts/lib/handoff_iterate.py`),
and the task explicitly mandates a mid-phase-kill acceptance test as its
own verification step. That is genuine cross-file framework scope, not a
one-file small fix.

## Goal

Close three specific gaps where an iterate run's in-flight state has no
disk representation and can be destroyed by mid-run context-window
auto-compaction (observed 2026-08-07, 2 of 2 autonomous runs compacted,
one during external review).

## Step 1 self-verification (mandatory per task instructions)

The originating task listed six suspected gaps and required each be
re-derived against current code before planning. Full findings (with
file:line citations) are in the session transcript; summary disposition:

| # | Claim | Verdict | Disposition |
|---|---|---|---|
| 1 | Interview answers never on disk | CORRECTED | True only at `small` (no spec file exists below `medium`); at `medium+` already captured into the iterate spec's Goal/AC/Out-of-Scope (`path-a-feature.md:32,35,48`). **Out of scope, deferred (not superseded)** — the mini-plan fix (item 2) only reaches `small` when the Mini-Plan Protocol actually triggers, which per `iteration-planning.md:145` is **FEATURE + small/medium** only; CHANGE + small and BUG + small never reach a Mini-Plan step at all (this run is BUG + medium, so it never exercises that case). Those two combinations still have zero on-disk planning artifact after this fix. Widening the trigger table is a separate Mini-Plan Protocol design decision, declined here on the scope-ratchet guard (flagged by Internal Plan Review, finding #6). |
| 2 | Mini-plan at `small` is session-only | VERIFIED TRUE | **In scope.** `iteration-planning.md:158-163` explicitly: "Small: Inline in session only (no file)". No compensating artifact anywhere. |
| 3 | Architecture-review reconciliation is conversational | FALSE — already solved | **Dropped from scope.** `SKILL.md:13` and `iteration-planning.md:394-411` already write verdicts/findings/reconciliation into the iterate spec's `## Architecture Review` section + the ADR, before Build. |
| 4 | Review findings lost between reviewer-return and `record_review_pass.py` | VERIFIED TRUE | **In scope.** `record_review_pass.py` only ever reads a payload file the agent must already have written (`record_review_pass.py:351-352`); nothing mandates that write happen immediately. Review subagents have `Read, Grep, Glob` only (no Write, no Bash) so they structurally cannot self-persist — the fix has to be an explicit, testable ordering mandate on the orchestrator. |
| 5 | Handoff decision is unrecorded heuristic | CORRECTED | The *trigger* is a heuristic (`iteration-reviews.md:579-584`, no code computes it), but a written schema and an automatic per-turn Stop-hook regeneration already exist (`generate_handoff_on_stop.py`, `handoff_iterate.py::render_iterate_progress`) independent of the heuristic firing. **Narrowed, folded into item 6** — the real gap is that the auto-snapshot only surfaces two markers, not the fuller `reviews.json` state; fixing item 6 fixes this too, since both read from the same function. |
| 6 | B1 resume checks only two markers | VERIFIED TRUE | **In scope.** `SKILL.md:61` literally checks only the external-review marker and an ADR `Self-Review:` block. `reviews.json` (`shared/scripts/lib/review_record_schema.py`) already carries per-type status for all 7 review types on disk but neither B1's prose nor `render_iterate_progress()` reads it. |

Net scope: items 2, 4, 6 (5 folds into 6's fix). Items 1 and 3 are
explicitly out of scope — already solved or not worth a dedicated artifact.

## Acceptance Criteria

- [x] AC-1: A FEATURE/CHANGE/BUG iterate at `small` complexity that reaches
      the Mini-Plan step writes `.shipwright/planning/iterate/{date}-{desc}-miniplan.md`
      (not "inline in session only"); a meta-test asserts `iteration-planning.md`'s
      Mini-Plan Protocol persistence rule no longer contains a no-file
      carve-out for `small`. Closed: `iteration-planning.md` + `path-a-feature.md`
      edited; `test_mini_plan_persistence_doc.py` (4/4 passing).
- [x] AC-2: `iteration-reviews.md`'s "Recording each review pass" section
      contains an explicit, testable ordering mandate: the raw reviewer
      reply is written to its payload file as the orchestrator's very next
      action after the subagent/external-review call returns, before any
      other reasoning or the next spawn. A meta-test asserts the mandate
      text is present inside that section's body. Closed: same mandate also
      placed at both actual spawn sites (`SKILL.md` Step 8, `campaign-mode.md`
      3f-bis, per Internal Plan Review finding #8); `test_review_record_immediate_write_rule.py`
      (8/8 passing, parametrized across all three sites) plus a code-level
      `SubagentStop` backstop (see AC-2b below).
- [x] AC-2b (built after Branch A + Architecture Review independently
      converged on the same ask): `write-review-payload-on-stop.py`, a
      `SubagentStop` salvage hook for `spec-reviewer`/`code-reviewer`/`doubt-reviewer`,
      backstops AC-2's prose mandate with a code-level fallback. Closed:
      `plugins/shipwright-build/tests/test_review_payload_on_stop.py`
      (18/18; 131/131 for the full `plugins/shipwright-build` suite,
      confirming no ADR-044 `lib` collision). Hardened post-Stage-2 per the
      internal `code-reviewer` (malformed-`reviews.json` fail-open) and the
      external code-review cascade (salvage-write fail-open) — see "External
      Code Review" below. F11's `check_integration_coverage` then correctly
      flagged this exact hook + `hooks.json` change as `cross_component`
      (touches `hooks.json` + a script under `hooks/`) and required a
      real-scenario composition test, which no prior test in this diff was —
      `test_review_payload_on_stop.py` imports the script's functions
      directly, it never exercises `hooks.json`'s own `command` strings.
      Closed: `test_review_payload_hook_wiring_integration.py` (2/2) — parses
      `hooks.json`, resolves `${CLAUDE_PLUGIN_ROOT}`, and drives each of the
      three wired commands as a real subprocess against a fixture transcript,
      confirming the JSON config and the script actually compose end-to-end.
- [x] AC-3a (primary, authoritative): `SKILL.md` §B1's replay-check reads
      `.shipwright/planning/iterate/{run_id}/reviews.json` directly (via
      `lib.review_record_core.read_record` + `pending_types`), independent
      of whether `session_handoff.md` was ever regenerated for this run —
      closing the actual killed-mid-phase gap (Internal Plan Review finding
      #1: the tracked handoff a killed run never wrote is not a reliable
      signal). Gated on `self` reaching a terminal status first (External
      Plan Review, openai finding #1) so a freshly-`init`'d all-pending
      record never false-triggers. Closed: `test_skill_b1_reviews_json_check.py`
      (4/4, doc-presence) + `test_compaction_state_audit_acceptance.py::test_ac3a_record_review_pass_show_reports_interrupted_cascade`
      (behavioral, drives the real `record_review_pass.py show` CLI B1
      actually runs).
- [x] AC-3b (secondary, best-effort): `render_iterate_progress()`
      (`shared/scripts/lib/handoff_iterate.py`) also surfaces still-pending
      review types (worded as state, not a command) for the live, per-turn
      Stop-hook snapshot, using the same SSoT helpers — not a hand-rolled
      reader. Distinguishes "not started" / "not due yet" / "interrupted" /
      "complete" / "unreadable" (Internal Plan Review finding #5). Closed:
      7 tests in `shared/tests/test_review_cascade_handoff.py`
      (`test_review_cascade_*`) — split into its own file rather than
      appended to the already-grandfathered `test_generate_session_handoff.py`
      (see mini-plan's file-list note on the bloat-baseline ratchet hit).
      The 7th (`test_review_cascade_silent_when_complexity_unresolvable`)
      closes a gap the external code-review cascade caught post-Stage-2 —
      see "External Code Review" below.
- [x] AC-4 (acceptance test, mandated by the originating task): drove the
      real `generate_handoff_on_stop.py` entrypoint end-to-end against a
      fixture `reviews.json` (self+spec completed, code/doubt/external_code
      pending) and confirmed the pending types are named in the file it
      actually writes; separately confirmed B1's `reviews.json`-direct-read
      path (AC-3a) names the same set from the same fixture, via the real
      `record_review_pass.py show` CLI subprocess. A literal same-session
      kill-and-restart is not possible from within the session performing
      the fix — see Self-Review below for what this substitute does and
      does not prove. Closed: `shared/tests/test_compaction_state_audit_acceptance.py`
      (3/3 passing) — two independent cold subprocesses per test, no shared
      in-memory state, reading only fixture files.

## Spec Impact

- **Classification:** modify
- **MODIFY:** FR-01.11 (`/shipwright-iterate`) — append ACs covering: (a)
  the mini-plan is persisted at every complexity tier that runs the
  protocol, not only medium+; (b) a review pass's findings are durable the
  instant the reviewer returns, before any other action; (c) resuming an
  interrupted run is judged against the full per-review-type record, not
  two markers.
- **ADD:** none
- **REMOVE:** none

## Out of Scope

- Giving review subagents (`spec-reviewer`, `code-reviewer`, `doubt-reviewer`,
  `opus-plan-reviewer`) Write/Bash tool access so they could self-persist
  findings directly. That changes their security/capability surface
  (currently deliberately Read/Grep/Glob-only) and is a separate,
  larger architectural decision, not a bug fix.
- Item 1 (small-complexity interview capture) and item 3 (architecture-review
  reconciliation) — verified out of scope above.
- Detecting/enforcing the ADR `Self-Review:` block via code (still prose-only
  in B1) — not part of this run's verified gaps; B1's existing prose already
  covers it and nothing in the self-verification found it broken.
- Any change to `PreCompact` hook behavior — the task explicitly rules this
  out ("PreCompact can only block or observe — it cannot shape the summary").

## Design Notes

n/a — no UI surface.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| Agent (Write tool, mini-plan step, all complexity tiers now) | `spec_checks.py` S3 (WARN-tier presence check, `small`+`feature` now included); `iteration-planning.md`'s `review.py --plan-file` | Markdown |
| `record_review_pass.py record --payload-file` | `reviews.json` — read by B1's replay-check (direct read, primary), `render_iterate_progress` (best-effort live-session convenience), F11 `check_review_record` | JSON |
| `handoff_iterate.render_iterate_progress` | `session_handoff.md` runtime copy (Stop hook only — informational, not authoritative for a cold resume) | Markdown |

Correction from the original draft: `finalize_iterate.py` (F5b) does not
glob mini-plan files at all (verified — no reference exists); the earlier
hedge on this row was wrong, not merely uncertain.

## Confidence Calibration

- **Boundaries touched:** see table above — `reviews.json` read path in
  `handoff_iterate.py`, and the mini-plan file's persistence path.
- **Empirical probes run:**
  - Unit test on `render_iterate_progress()` with a fixture `reviews.json`
    containing a `pending` `code` row → asserts `code` appears in the
    "Mandatory replay on Resume" list.
  - Unit test with all 7 types `completed`/`not_run`/`not_applicable` →
    asserts no review-cascade line is added (no false positive).
  - Meta-test reading `iteration-planning.md`'s Mini-Plan Protocol section →
    asserts no `small`-tier "no file" exemption remains.
  - Meta-test reading `iteration-reviews.md`'s "Recording each review pass"
    section → asserts the immediate-write-ordering mandate text is present.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | `render_iterate_progress` reports `interrupted` + names the pending types when `self` is terminal and others are not | tested | `test_review_cascade_handoff.py::test_review_cascade_interrupted_when_self_terminal_and_others_pending` |
  | 2 | `render_iterate_progress` reports `not due yet` (no false "interrupted") when `self` itself is still pending — even though every other type is also pending on a fresh record | tested | `test_review_cascade_handoff.py::test_review_cascade_not_due_yet_when_self_pending` |
  | 3 | `render_iterate_progress` distinguishes "no record yet" from "record present but unreadable" (malformed JSON) — both add no false interruption but the latter still forces a replay entry | tested | `test_review_cascade_handoff.py::test_review_cascade_not_started_when_reviews_json_absent`, `::test_review_cascade_unreadable_reviews_json_flags_replay` |
  | 4 | `render_iterate_progress` reports `complete` (no replay) when every type is terminal | tested | `test_review_cascade_handoff.py::test_review_cascade_complete_when_self_terminal_and_nothing_pending` |
  | 5 | `render_iterate_progress` resolves `run_id` from a `*-miniplan.md` header when no spec file exists (FEATURE+small) | tested | `test_review_cascade_handoff.py::test_review_cascade_resolves_run_id_from_miniplan_when_no_spec` |
  | 5b | `render_iterate_progress` stays silent (omits the Review Cascade line entirely) when a resolved `run_id` has no `reviews.json` AND complexity is unresolvable, instead of noisily reporting "not started" for a run this section cannot fully identify (external code-review cascade, openai medium finding) | tested | `test_review_cascade_handoff.py::test_review_cascade_silent_when_complexity_unresolvable` |
  | 6 | Mini-Plan Protocol persistence rule requires a file at every complexity tier that runs the protocol, with no `small`-tier no-file carve-out | tested | `test_mini_plan_persistence_doc.py` (4/4) |
  | 7 | `check_s3_iterate_miniplan` WARNs at `small` for `feature`-type runs, still SKIPs at `small` for change/bug | tested | `test_spec_checks_s3_miniplan_gate.py::test_s3_small_feature_warns_then_passes_with_miniplan`, `::test_s3_still_skips_small_change_and_small_bug` |
  | 8 | "Recording each review pass" + both actual spawn sites (SKILL.md Step 8, campaign-mode.md's 3f-bis) carry the immediate-write ordering mandate and the run_id-in-prompt requirement | tested | `test_review_record_immediate_write_rule.py` (8/8, parametrized across all three sites) |
  | 9 | `write-review-payload-on-stop.py` salvages a reviewer's reply only when not already recorded, across fenced/raw JSON and legacy `gates.spec`, never blocks on a malformed `reviews.json` (`AttributeError`/`TypeError`), and never blocks when the salvage write itself raises `OSError` (external code-review cascade, openai medium finding) | tested | `plugins/shipwright-build/tests/test_review_payload_on_stop.py` (18/18; full `plugins/shipwright-build` suite: 131/131) |
  | 10 | B1's replay-check names the direct `reviews.json` read and gates on `self`'s terminal status before treating other pending types as an interruption | tested | `test_skill_b1_reviews_json_check.py` (4/4, doc-presence) |
  | 11 | End-to-end: a fixture `reviews.json` (self+spec completed, rest pending) drives BOTH the real `record_review_pass.py show` CLI and the real `generate_handoff_on_stop.py` Stop-hook subprocess, and both name the same pending set | tested | `test_compaction_state_audit_acceptance.py` (3/3) — the mandated AC-4 acceptance test |
  | 12 | (`category: integration`) `hooks.json`'s three SubagentStop `command` strings, with `${CLAUDE_PLUGIN_ROOT}` resolved and driven as a real subprocess against a fixture transcript, actually launch `write-review-payload-on-stop.py` and salvage into the matching review type — proves the JSON wiring and the script compose, not just that each works in isolation (F11 `check_integration_coverage`: this diff touches `hooks.json` + a script under `hooks/`, the `cross_component` risk flag) | tested | `test_review_payload_hook_wiring_integration.py` (2/2) |

- **Confidence-pattern check:** asymptote — no prior "are you confident?"
  question in this run to re-probe (BUG path skips Interview). Coverage —
  all 13 ledger rows `tested`, 0 untested-testable.

## Architecture Review

- **Brief:** `.shipwright/planning/iterate/iterate-2026-08-09-compaction-state-audit/architecture_brief.md`
- **Verdicts:** deepseek=approve · openai=revise
- **Smallest thing that would do (per reviewers):** deepseek: as proposed (extend existing mini-plan/reviews.json/prose machinery). openai: as proposed, plus a narrowly-scoped `SubagentStop` salvage hook for the reviewer-return gap.
- **Findings:** openai — the immediate-write rule is an ongoing human-discipline obligation, not durability; build the named salvage hook now, reusing this repo's own run-id-resolution approach, writing only when the normal payload hasn't already been recorded. **accepted-and-fixed** — this is the same ask Branch A's openai review made (finding #2 above); converging twice, independently, on the same request is why it was built rather than deferred (see "Code-level backstop" note above). deepseek raised no findings (approve).
- **Reconciliation:** the mini-plan had already logged this exact option as a considered-but-deferred follow-up after Branch A (§ finding #2). A second, independent reviewer pass asking for the same thing — on a brief that withheld the mini-plan's own reasoning, so it isn't an echo — is the strong signal this repo's own external-review protocol treats as decisive. Built it: `write-review-payload-on-stop.py`, using the transcript-inference run-id resolution `write-section-on-stop.py` already proves works in production for this exact hook type (not the heavier `resolve_run_id`/`pointer_run_id` machinery, which solves a different problem — a *Stop* hook needing a *session's* run_id from ambient state, not a *SubagentStop* hook reading a run_id the orchestrator's own prompt already states in plain text).

## Internal Plan Review (opus-plan-reviewer)

- **Ran:** yes
- **Severity:** high
- **Summary:** Root-cause diagnosis and Step-1 verification are sound, but
  the headline fix (B1/handoff surfacing pending reviews) targeted the
  wrong file — the enriched handoff is written to the gitignored runtime
  copy, while B1's documented source is the tracked copy a killed run
  never writes. Fix that plus a section-blind `reviews.json` reader before
  building.
- **Findings:** 11 total (1 high, 8 medium, 2 low) — see disposition table
  below.
- **Known limitations:**
  - `render_iterate_progress()`'s `reviews.json` enrichment cannot resolve
    a `run_id` for CHANGE/BUG at `small` complexity (no spec file, no
    mini-plan — the protocol doesn't trigger there at all). Disclosed, not
    fixed — widening the Mini-Plan Protocol trigger table is a separate,
    larger design decision (declined, scope-ratchet guard).
  - The item-2 ordering mandate (write-immediately-on-return) is enforced
    by agent-followed prose repeated at each spawn site, not by code —
    there is no hook that can observe a subagent's return and force a
    write. This is a structural limit of the review-subagent tool grants
    (Read/Grep/Glob only), not something this iterate can close.
  - The mid-phase-kill acceptance test (AC-4) cannot literally kill and
    restart a Claude Code session from within the session performing the
    fix; it instead drives the real entrypoint (`generate_handoff_on_stop.py`
    and the B1 `reviews.json` read) against a fixture end-to-end, and
    Self-Review states explicitly which half remains unproven.
- **Status:** 9 fixed, 2 declined (both scope-ratchet: widening the
  Mini-Plan trigger table; extending review-subagent tool grants)

| # | Finding | Severity | Disposition |
|---|---|---|---|
| 1 | Enriched handoff lands in the gitignored runtime copy; B1 reads the tracked copy, which a killed-mid-phase run never wrote | high | **fix** — B1's own replay-check now reads `.shipwright/planning/iterate/{run_id}/reviews.json` directly (via `read_record`/`pending_types`), independent of which handoff copy exists. This is the primary/authoritative mechanism; the renderer enrichment becomes a secondary, best-effort live-session convenience. |
| 2 | Hand-rolled `reviews.json` reader is section-blind (misses legacy `gates`-parked `spec` rows) and bypasses `is_safe_run_id` | medium | **fix** — reuse `lib.review_record_core.read_record()` + `pending_types()` (the SSoT), not a hand-rolled dict read. |
| 3 | At `small`, `render_iterate_progress()` cannot resolve `run_id` (no spec file) | medium | **fix (partial) + disclose** — add a fallback: parse `Run ID:` from a `*-miniplan.md` header when no spec exists (closes it for FEATURE+small, which gets a mini-plan after fix #1). CHANGE/BUG+small still has no artifact to parse — disclosed above, not fixed. |
| 4 | "Pending" wording reads as a command even when a type is legitimately not-yet-due (`not_applicable` at this complexity) | medium | **fix** — reworded as descriptive state ("still unanswered in reviews.json"), not an imperative "run this now"; added a mixed-case unit test (self+spec completed, rest pending) asserting no false command. |
| 5 | Missing `reviews.json` treated as a silent no-op — the earliest-kill case looks identical to a healthy run | medium | **fix** — when complexity is resolvable and small+ and no record exists, emit an explicit informational line rather than staying silent. |
| 6 | Item 1 (small interview capture) claimed "superseded" but CHANGE/BUG+small never reach the Mini-Plan step at all — they still have zero planning artifact after this fix | medium | **fix (documentation)** — Step 1 table corrected below: deferred, not superseded, for CHANGE/BUG+small. **decline (widen the trigger)** — scope-ratchet guard: that is a Mini-Plan Protocol redesign, not this bug fix. |
| 7 | `check_s3_iterate_miniplan()` hard-skips below `medium` regardless of type, now stale once FEATURE+small persists | medium | **fix** — extended (cheaply, via the already-existing `_iterate_category` helper) to also WARN at `small` when the run's recorded type is `feature`. |
| 8 | Ordering mandate placed only in `iteration-reviews.md` prose; an agent compacted right after spawning from Step 8 never reaches that section. Ledger row mislabeled "tested" for a doc-presence assertion | medium | **fix, upgraded to code** — one-clause imperative added at both actual spawn sites: `SKILL.md` Step 8 (standalone) and `campaign-mode.md`'s **3f-bis** — not `sub-iterate-runner.md` Step 3.7 as first planned, which only *delegates* the cascade to the orchestrator and never itself calls the `Agent` tool; the orchestrator's own spawn is at 3f-bis (`campaign-mode.md:190-231`). Directly relevant since the originating task's title is "shipwright iterate autonomous" and both observed compactions were autonomous runs. Additionally (per both external review passes converging on the same ask): a `SubagentStop` salvage hook (`write-review-payload-on-stop.py`) now backs this prose with a code-level fallback for the three internally-spawned reviewers — see the "Code-level backstop" note below. Ledger row relabeled "documentation-presence for an agent-discipline rule, not code-enforced" for the prose half; a new behavioral test row covers the hook. |

**Code-level backstop (added after Branch A + Architecture Review, both independently asked for it — see External Plan Review below):** `plugins/shipwright-build/scripts/hooks/write-review-payload-on-stop.py`, wired via `SubagentStop` in `plugins/shipwright-build/hooks/hooks.json` for `spec-reviewer`/`code-reviewer`/`doubt-reviewer`. Fires synchronously when a reviewer subagent stops, independent of the orchestrator's remaining context. No-ops if `reviews.json` already shows the type terminal; otherwise salvages the raw reply from the subagent's own transcript to `{run_id}/{type}_salvaged_raw.json` for a resuming session to feed into `record_review_pass.py record`. Resolves `run_id` from the transcript text (never an env var — `SHIPWRIGHT_RUN_ID` is documented, in this same repo, as unreliable for a Claude-Code-launched hook subprocess); the spawn-prompt mandate above ensures it's always present. Deliberately self-contained, no `shared/scripts/lib` import — `plugins/shipwright-build/scripts/lib` already occupies the `lib` name in that plugin's own pytest process (ADR-044), and importing the shared package under the same name would silently resolve to the wrong one depending on test collection order. 16 tests in `plugins/shipwright-build/tests/test_review_payload_on_stop.py`, full `plugins/shipwright-build` suite (129 tests) re-run green to confirm no collision.
| 9 | AC-4 as planned only calls the inner function against a fixture — proves nothing about the real hook→file→B1 chain | medium | **fix** — drives `generate_handoff_on_stop.py`'s real entrypoint end-to-end against a fixture `reviews.json`, asserting the pending type lands in the file it actually writes. |
| 10 | New tests planned for the wrong root (`shared/scripts/tests/` — existing handoff tests live in `shared/tests/`); import-safety risk in the Stop-hook's swallowed-ImportError path | low | **fix** — tests relocated to `shared/tests/`, added to the run list; new import uses the same relative-then-absolute dual-import pattern as `review_record_schema.py`; one test imports via the hook's actual `sys.path` route. |
| 11 | `docs/hooks-and-pipeline.md` (context-loading matrix) and `docs/guide.md` not in the file list; Affected Boundaries hedge on F5b globbing mini-plans is factually wrong (verified: it doesn't) | low | **fix** — both docs added to the mini-plan's file list; Affected Boundaries table corrected to state fact, not a hedge. |

## External Plan Review (Branch A — deepseek + openai)

- **Verdicts:** deepseek=revise · openai=revise
- **Findings triage:**

| # | Reviewer | Finding | Severity | Disposition |
|---|---|---|---|---|
| 1 | openai | B1's rule as drafted treats *any* pending type as "cascade interrupted," but a freshly-`init`'d record has every type pending before anything is due — this would send a resume into an early, unnecessary Step 8 restart. | high | **fix** — gate the report on `self`'s status being terminal (not pending) before treating any other pending type as meaningful. Self-Review (Step 7) always chronologically precedes the Step 8 cascade, so "self done, something after it still pending" is the correct interrupted-cascade signal; "self itself still pending" means nothing downstream is due yet — stay silent, let the normal linear resume continue. |
| 2 | openai | The immediate-write ordering mandate is prose-only and does not actually guarantee durability against a compaction landing exactly between subagent-return and the write — repeating the instruction improves odds, it doesn't close the gap. Check whether the host has a post-subagent-result callback before treating AC-2 as fully closing it. | medium → **built** | Claude Code's `SubagentStop` hook *does* exist and this exact repo already uses it for an identical durability problem (`plugins/shipwright-plan/hooks/hooks.json` → `write-section-on-stop.py`). Initially deferred here over the `SHIPWRIGHT_RUN_ID`-never-reaches-a-hook-subprocess precedent (`iterate-2026-07-27-c3-phase-history-join*`) — but the Architecture Review pass (below) independently raised the same ask a second time, and the actual precedent's own workaround (infer from the subagent's transcript text, never an env var — confirmed by reading `write-section-on-stop.py` itself, whose `SHIPWRIGHT_PLANNING_DIR` is "normally unset" when it fires) sidesteps that exact failure mode without needing the heavier `resolve_run_id`/`pointer_run_id` machinery. Built as `write-review-payload-on-stop.py` — see "Code-level backstop" note above. AC-2 is still labeled a mitigation for the prose half (an agent can still ignore the write-immediately instruction), but the durability gap itself now has a code-level fallback, not just a repeated instruction. |
| 3 | openai | The mini-plan `run_id` fallback (glob `*-miniplan.md`, substring+mtime match) could pick the wrong run if descriptions overlap or a stale mini-plan lingers. | medium | **disclosed, not fixed** — this is the *identical* heuristic already used, unmodified, for the existing `spec_path` candidate resolution three lines above it in the same function (`handoff_iterate.py:41-46`) — same risk, pre-existing, not introduced by this change. Hardening one call site and not its sibling would be inconsistent single-purpose gold-plating; if this proves a real problem in practice, both call sites should be fixed together in their own iterate. |
| 4 | openai | Verify every Mini-Plan Protocol invocation/creation site is updated, not just the two files named in the mini-plan. | medium | **fix (verification)** — grepped the whole `plugins/shipwright-iterate/` tree for `"Inline in session"` / `"Mini-Plan Protocol"` / `"miniplan"`: only `iteration-planning.md` and `path-a-feature.md` restate the small/medium split; `path-c-bug.md`, `path-b-change.md`, `campaign-mode.md` and `sub-iterate-runner.md` only point at `iteration-planning.md`'s protocol without restating it. The two-file edit is complete; no third site exists. |
| 5 | openai | A malformed/unreadable existing `reviews.json` is materially different from "no record yet" — don't silently conflate them. | medium | **fix** — `render_iterate_progress()` catches `ReviewRecordError` (schema-invalid / unreadable) separately from "file absent," and emits a distinct, concise diagnostic line ("review record could not be read — inspect reviews.json") rather than treating it the same as a healthy not-yet-started run. |
| 6 | openai | AC-4's "B1 direct-read" check only proves the underlying data primitives work, not that a future agent actually follows B1's prose; the doc-presence test has the same ceiling. Keep B1's wording to one canonical command, not "X or Y". | low | **fix** — B1's added clause names exactly one canonical read path (`record_review_pass.py show` piped through `pending_types()`, not "or read the file yourself"), and AC-4/the ledger row names explicitly which half is proven behaviorally vs. which remains a documentation-presence check. |
| 7 | deepseek | If a review is spawned but not yet recorded, `reviews.json` might show no entry at all for that type, understating what's in flight. Suggested a new `--mark-pending` write before each spawn. | medium | **already covered, tightened** — `record_review_pass.py init` (`iteration-reviews.md:457-462`, pre-existing) already materializes **all seven types as `pending` up front**, before any spawn — there is no "no entry at all" state once `init` has run. The actual gap was that the doc only said "early in the run" without pinning a step; tightened to bind it explicitly to Step 7 entry (immediately before the first reviewer spawn), removing the ambiguity rather than adding a new, duplicate mechanism. |
| 8 | deepseek | The immediate-write mandate is prose-only and agents could ignore it; monitor and revisit subagent Write access if it proves insufficient. | low | **disclosed** — same finding as openai #2; folded into the same disclosure + follow-up. No action beyond what #2 already covers. |
| 9 | deepseek | The `run_id` fallback assumes an exact header line match (`- **Run ID:**`); a formatting deviation silently degrades to no enrichment. | low | **accepted as-is** — matches the reviewer's own assessment: graceful degradation, and the primary B1 path (direct `reviews.json` read, not the renderer) doesn't depend on this parse at all. |

- **Built, not deferred:** the `SubagentStop` salvage hook proposed here was
  initially scoped as a follow-up iterate (see finding #2's original
  disposition), but the Architecture Review pass below independently asked
  for the same thing a second time — see the "Code-level backstop" note
  earlier in this section for what shipped. **Remaining follow-up:** the same
  pattern could extend to `shipwright-plan:opus-plan-reviewer` (the Internal
  Plan Review pass) — not built here, since that pass is metadata-only
  (no `--payload-file`, per `iteration-planning.md`) and its findings already
  live in the iterate spec section itself, written directly by the
  orchestrator, not carried in a Task-tool return value the same way.

## External Code Review (Step 8 cascade — deepseek + openai)

- **Verdicts:** deepseek=unavailable (error: `Expecting value: line 313 column 1` —
  provider returned malformed JSON, not a parseable review) · openai=revise
- **Internal cascade context:** `spec-reviewer` PASS, `code-reviewer` completed
  (3 findings, 1 medium fixed — see below), `doubt-reviewer` `not_applicable`
  (Stage 3's conditional trigger — migrations, async/concurrency, cross-plugin
  imports, irreversible ops — does not apply to this diff).
- **Findings triage:**

| # | Reviewer | Finding | Severity | Disposition |
|---|---|---|---|---|
| 1 | openai | `write-review-payload-on-stop.py`'s `out_path.parent.mkdir(...)` / `out_path.write_text(...)` sat outside the fail-open error handling — an `OSError` there (read-only worktree, path collision) would propagate and violate the hook's own "never blocks" guarantee, identical in kind to a finding the internal `code-reviewer` independently raised one line earlier in the same function (`already_recorded()`'s json parsing). | medium | **fix** — wrapped both calls in `try/except OSError`, `_diag()` and return 0, matching every other failure path in the module. New test: `test_never_blocks_when_salvage_write_raises` (forces `Path.mkdir` to raise, asserts `rc == 0`). |
| 2 | openai | The renderer reports "not started" whenever a resolved `run_id` has no `reviews.json`, regardless of whether complexity is resolvable — but the mini-plan's own Work Items section (item 2d) specifically designed this notice to fire only at resolvable small/medium/large complexity and stay silent otherwise ("matching today's degraded behavior"), and the Test Completeness Ledger claimed this was tested when no such test existed. | medium | **fix — genuine implementation/design divergence, not an external hallucination.** Verified directly against the mini-plan text (line 44: "never raised for an unresolvable-complexity case") before accepting: the code had dropped this gate entirely, and the mini-plan-header fallback never even extracted `complexity` (only `run_id`), so a small-tier mini-plan-only run could never resolve it. Added complexity extraction to the mini-plan fallback and gated the "not started" branch on `complexity in ("small","medium","large")`; when unresolvable, the Review Cascade line is omitted entirely rather than rendered as `unknown`. New test: `test_review_cascade_silent_when_complexity_unresolvable`. |
| 3 | openai | `handoff_iterate.py`'s new import (`from lib.review_record_core import ...`) should use the relative-then-absolute `try/except ImportError` fallback pattern `review_record_schema.py` uses for its own sibling import, or it "can fail or resolve the wrong `lib` package" when loaded from a process with another `lib` on `sys.path`. | medium | **rejected-with-reason** — this is the same divergence `spec-reviewer` already surfaced (non-blocking) at Stage 1: the mini-plan's work item 2a *planned* that dual-import pattern, but the shipped code is a plain absolute import. Re-verified independently rather than deferring to that prior note: `review_record_schema.py`'s fallback exists because its sibling `review_verdict` is loaded either as part of the `lib` package or via `importlib.util.spec_from_file_location` (the SubagentStop-hook loading pattern), so it needs to work both ways. `handoff_iterate.py` has no such second loading path — grepped both plugins and shared for any hook or script that loads it via `spec_from_file_location` or invokes it directly; the only two consumers are `generate_session_handoff.py` and this iterate's own tests, both of which already do the `sys.path` setup a normal package import needs. Matches the internal `code-reviewer`'s own independent finding (clean-pass note: "not consumed via `shared_lib_loader`, so the ADR-044/lib-sibling-import blind spot... doesn't apply here"). A planning/implementation mismatch, not a functional bug; no fix applied, disagreement recorded rather than silently ignored. |

- **deepseek unavailable, not skipped:** `degraded: false` at the top level
  (keys valid, `openai` succeeded) but `deepseek`'s own leg returned invalid
  JSON mid-response — recorded as `status: "error"` in the payload, not
  papered over as a clean two-reviewer pass. Single-reviewer coverage here is
  a real gap, not a masked one; not re-run, since openai's findings were
  actionable and this is a documentation/process fix with no user-facing
  runtime risk from a missed second opinion.

## Verification (medium+)

- **Surface:** none
- **Runner command:** n/a
- **Justification:** this change modifies the shipwright-iterate skill's own
  reference documentation and a shared Python helper library with no
  startable web/cli/api surface of its own; verification is via the unit
  tests and meta-tests in the Confidence Calibration table plus the
  mandated mid-phase-kill acceptance test (AC-4), which is a process
  exercise (kill + resume a real iterate session), not a runnable server.
