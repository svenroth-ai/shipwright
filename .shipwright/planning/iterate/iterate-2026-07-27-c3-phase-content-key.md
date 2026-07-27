# Iterate: the phase canon asks whether the handoff belongs to this run

- **Run ID:** iterate-2026-07-27-c3-phase-content-key
- **Date:** 2026-07-27
- **Type:** change
- **Complexity:** medium
- **Branch:** iterate/c3-phase-content-key
- **Spec Impact:** MODIFY — FR-01.01 (an (E) criterion folded onto
  `/shipwright-run`, which owns "a phase is never quietly counted as done on
  work that failed its own test" — C3 is one of those checks. Folded per
  `shared/fr-authoring.md` §3 rather than minting a new requirement.)
- **Observed during:** iterate-2026-07-27-name-the-blocker (PR #459), filed as `trg-bd4e75a9`

## Problem

`shared/scripts/tools/verifiers/common.py:382
check_c3_session_handoff_fresh_after_phase` still decides whether
`session_handoff.md` is fresh by comparing filesystem mtime against a 600-second
budget. Its F11 twin moved off mtime onto a content key in
iterate-2026-07-27-name-the-blocker; this one was deliberately left behind
because a content key for it had to be *designed*, not ported: it is
phase-scoped, and its own docstring records that the handoff carries no
per-phase marker.

The defect is the one that iterate already named and acted on twice
(iterate-2026-06-28-drop-timestamp-drift, now the standing comment at
`shared/scripts/hooks/check_drift.py:10-16`): **filesystem mtime is not a
content-staleness signal in a git repo.** Checkout, branch-switch and worktree
creation all reset it, and a run that waits more than ten minutes on CI trips
the budget on schedule rather than on any defect. A warning that fires on
structure is one operators learn to ignore.

It also leaves the documentation stating a contract the code does not meet:
`docs/guide.md:2029` already describes C3 as
`.shipwright/agent_docs/session_handoff.md is fresh (canon-marker frontmatter)`.
The guide was deliberately left alone by the previous iterate rather than edited
down to match the code.

## Scope: seven callers, not six

The brief named six phase verifiers (build, plan, design, test, changelog,
deploy). There is a **seventh** caller the brief did not have:
`shared/scripts/lib/phase_quality/_runners.py:80`, the Stop-hook Phase-Quality
audit, which runs C3 for *every* phase in `PLUGIN_TO_PHASE` — including
`security`, `compliance` and `adopt`. `project_checks.py` is an eighth call site
(the brief's "six" counted the pipeline phases that follow project). Any content
key has to answer for the phases that have no canon-marker producer at all, or
it converts a schedule-driven false fire into a permanent one.

## The design decision, taken on evidence

The brief's lead was correct: the canon frontmatter carries `phase` alongside
`run_id`, and every canon phase already writes it. But the obvious key — *does
the marker name this phase* — is wrong, and the evidence says so before any code
was written:

**`verify_phase.py --phase all` passes one `run_id` to every phase dispatcher
(`dispatch_all`, lines 120-141), and each dispatches its own C3 against the same
single `session_handoff.md`.** The handoff is overwritten, not appended. Under a
phase key, at most one phase — whichever wrote last — could pass, and every
other phase would fail. That is a *new* structural false fire, the exact defect
class being removed.

This is what makes C3 different from its siblings: C1 (events), C2 (dashboard),
C4 (decision log) and C5 (changelog) all read **accumulating** artifacts, so a
per-phase question has a per-phase answer. C3 reads a **single overwritten
file**. The docstring's note that "session_handoff is a single file without
per-phase markers" is that fact, and no marker design changes it.

**Decision: key on the run, report the phase.** C3 passes when the handoff's
canon marker names the run being verified, and fails when it names a different
run or carries no marker. The marker's `phase` is not a pass/fail key; it is
reported, so the operator is told *which* phase last wrote the handoff. This
matches the guide's existing wording (`canon-marker frontmatter`), matches the
F11 twin, and cannot fire on elapsed time.

**Residual limitation, stated rather than papered over.** If phase P skips its
C3 step but a later phase Q in the same run writes the marker, C3 for P passes
on Q's write. Genuine per-phase attribution needs a per-phase artifact; the
handoff cannot carry it. That is a larger change than this defect warrants and
is recorded here as a known bound, not silently absorbed.

**Producer coverage was verified, not assumed.** All eight canon phases already
write the marker: `project`, `design`, `plan`, `build`, `test`, `changelog`,
`deploy` via `generate_session_handoff.py --canon-marker --phase <phase>` in
their finalization references, and `iterate` via
`finalize_iterate.py:353-355`. `security`, `compliance` and `adopt` write none —
those get a NAMED skip, following the existing `C4_PHASES` / `C5_PHASES`
precedent in `phase_quality/_constants.py`, never a silent pass.

**The Stop hook does not clobber the marker.** `generate_handoff_on_stop.py`
writes only `runtime/session_handoff.md` (gitignored, lines 180-186); the
tracked file C3 reads is written exclusively by phase finalizations and
`finalize_iterate`. Confirmed on this repo's own tracked handoff, which carries
`canon_generated: true`, `run_id`, and `phase: "iterate"`.

## Non-goals

- **Giving `security` / `compliance` / `adopt` a canon-marker producer.** That
  is three plugins' finalization steps, and C3 has never applied to them. Named
  skip here; a producer is a separate decision.
- **A per-phase handoff artifact** to close the residual limitation above.
- Changing C3's severity. It stays WARNING — the handoff is advisory.

## Affected Boundaries

| Boundary | Direction | Note |
|---|---|---|
| `session_handoff.md` canon frontmatter | consume | existing shape; second phase-scoped reader |
| `lib.canon_frontmatter.parse_canon_frontmatter` | consume | existing SSoT parser, no change |
| C3 check signature (`max_age_seconds` → `run_id`) | produce | 8 internal call sites |
| `run_canon_checks(phase, project_root)` signature | produce | gains `run_id`; caller is a Stop hook |

## Acceptance Criteria

- **(A) Freshness is judged by content, not by the clock.** The phase-canon C3
  check passes when the handoff's canon marker names the run being verified and
  fails when it names a different run — however long the run took, and whatever
  the file's modification time is. Modification time is no longer consulted
  anywhere in the check.
- **(B) A phase with no canon-marker producer is named, not failed.** The
  phases that never write a canon marker report an explicit skip that says so,
  instead of a permanent warning or a silent pass.
- **(C) The operator is told which phase wrote the handoff.** A passing result
  names the phase recorded in the marker, so a handoff written by a different
  phase of the same run is visible as such rather than indistinguishable from
  one written by the phase being checked.
- **(D) An unanswerable check says so.** A missing handoff, a handoff with no
  canon marker, an unreadable file, or a caller that supplies no run id each
  produce a distinct stated reason. None of them is reported as a pass.
- **(E) Auditing a whole finished run does not manufacture warnings.** Verifying
  every phase of one run against that run's handoff reports the same answer for
  each phase, rather than passing the last phase and warning on all the others.
- **(F) The documented contract and the code agree.** `docs/guide.md`'s
  description of C3 as a canon-marker check is true of the code, and the
  pipeline reference records the check's key.

## Confidence Calibration

- **Boundaries touched:** the four above. None is a new external shape — the
  canon frontmatter is an existing format with an existing SSoT parser and two
  existing readers; this change adds a third reader and one internal signature
  change that reaches a Stop hook.

- **Empirical probes run:**

  | Probe | Finding |
  |---|---|
  | Read `dispatch_all` in `verify_phase.py` | **Changed the design.** One `run_id`, eight dispatchers, one handoff file — a phase key would have failed 7 of 8 phases. The obvious key was wrong. |
  | Grep every `--canon-marker` producer across `plugins/` | All 7 pipeline phases pass `--phase <phase>`; `finalize_iterate` supplies `phase: "iterate"`. Producer coverage is real, not assumed. |
  | Read `generate_handoff_on_stop.py` write paths | Stop hook writes `runtime/` only; the tracked handoff C3 reads is never clobbered by session end. Removed the main false-fire risk of a content key. |
  | `head` this repo's tracked `session_handoff.md` | Carries `canon_generated`, `run_id`, `phase` — the marker exists in practice, on this repo, today. |
  | Grep callers of `check_c3_...` | **Changed the scope.** Seven call sites, not six; `_runners.py` runs it for `security`/`compliance`/`adopt`, which have no producer. |

- **Test Completeness Ledger** — 30 behaviours: 29 `tested`, 1 `untestable` with
  a closed-vocabulary reason code, zero testable-but-untested. Machine-readable
  copy at F5 in `shipwright_test_results.json.iterate_latest.test_completeness`.

  | # | Behaviour | Disposition | Evidence |
  |---|---|---|---|
  | 1 | An old handoff naming this run passes | tested | `test_c3_handoff_freshness::test_an_old_handoff_naming_this_run_passes` |
  | 2 | A brand-new handoff naming another run fails | tested | `…::test_a_brand_new_handoff_naming_another_run_fails` |
  | 3 | Identical content + different mtime → identical verdict | tested | `…::test_the_check_never_consults_mtime` |
  | 4 | No mtime/`max_age_seconds` call survives in the source | tested | `…::test_the_source_carries_no_mtime_call` |
  | 5 | A phase with no canon producer is skipped, by name | tested | `test_c3_applicability::test_a_phase_with_no_canon_producer_is_skipped_not_warned` |
  | 6 | Every canon phase is actually evaluated | tested | `…::test_every_canon_phase_is_actually_evaluated` |
  | 7 | `C3_CANON_PHASES` ↔ `PLUGIN_TO_PHASE`, both directions | tested | `…::test_c3_canon_phases_align_with_plugin_to_phase` |
  | 8 | A pass names the phase that wrote the handoff | tested | `test_c3_handoff_freshness::test_a_passing_result_names_the_writing_phase` |
  | 9 | The known bound: another phase of the same run passes, and says so | tested | `…::test_a_handoff_written_by_another_phase_of_this_run_passes_and_says_so` |
  | 10 | A marker with no phase renders a placeholder | tested | `…::test_a_marker_without_a_phase_renders_a_placeholder` |
  | 11 | A missing handoff is not a pass | tested | `…::test_a_missing_handoff_is_not_a_pass` |
  | 12 | A handoff with no canon marker is not a pass | tested | `…::test_a_handoff_without_a_canon_marker_is_not_a_pass` |
  | 13 | Non-canon frontmatter is not a marker | tested | `…::test_a_non_canon_frontmatter_block_is_not_a_marker` |
  | 14 | A marker with no run id is not a pass | tested | `…::test_a_marker_without_a_run_id_is_not_a_pass` |
  | 15 | A degenerate run id is "cannot evaluate", not a warn | tested | `…::test_a_degenerate_run_id_cannot_evaluate_rather_than_warn` (4 cases) |
  | 16 | An unreadable handoff is not a pass | tested | `…::test_an_unreadable_handoff_is_not_a_pass` |
  | 17 | Inaccessible ≠ missing (the `is_file()` trap) | tested | `…::test_an_inaccessible_handoff_reads_as_unreadable_not_missing` |
  | 18 | `run_id` is keyword-only with no default | tested | `…::test_run_id_is_keyword_only_and_has_no_default` |
  | 19 | A malformed marker cannot dump its contents into a finding | tested | `…::test_a_malformed_marker_does_not_dump_its_contents_into_the_detail` |
  | 20 | Terminal escapes never reach an operator-facing detail | tested | `…::test_terminal_escapes_in_a_marker_never_reach_the_detail` |
  | 21 | A whole-run audit answers uniformly across canon phases | tested | `test_c3_applicability::test_auditing_a_whole_run_gives_every_canon_phase_the_same_answer` |
  | 22 | …and still skips non-producers | tested | `…::test_auditing_a_whole_run_still_skips_non_producer_phases` |
  | 23 | A whole-run audit of a stale handoff warns for every canon phase | tested | `…::test_a_whole_run_audit_of_a_stale_handoff_warns_for_every_canon_phase` |
  | 24 | Real writer → disk → the runner the Stop hook calls: PASS | tested (**integration**) | `test_handoff_freshness_composition::test_the_canon_runner_passes_c3_on_the_real_writers_marker` |
  | 25 | …WARN when the handoff belongs to another run | tested (**integration**) | `…::test_the_canon_runner_warns_when_the_handoff_belongs_to_another_run` |
  | 26 | …SKIP for a phase with no producer | tested (**integration**) | `…::test_the_canon_runner_skips_c3_for_a_phase_with_no_producer` |
  | 27 | A degenerate run id reaches C3 as itself through the runner | tested (**integration**) | `…::test_a_degenerate_run_id_reaches_c3_as_itself` |
  | 28 | The Stop-hook call site supplies the run id | tested | `…::test_the_stop_hook_call_site_supplies_the_run_id` |
  | 29 | The F11 twin is unaffected by the shared-reader refactor | tested | `test_handoff_freshness` (13 tests, unchanged) |
  | 30 | The guide + pipeline reference describe the contract the code now meets | untestable — `requires-manual-visual-judgment` | `docs/guide.md` C3 row, `docs/hooks-and-pipeline.md` "C3 Freshness — a Content Key, Not mtime" |

- **Confidence-pattern check:**
  - *Depth (asymptote).* The check is a pure function over file content — tested
    directly at its own seam, including the mtime-independence assertion that
    pins (A) by construction rather than by timing.
  - *Breadth (coverage).* The axis is *unknown vs clean*: every unanswerable
    input (missing, unmarked, unreadable, no run id, no producer) has its own
    test asserting it is not reported as a pass.
  - *Integration composition.* Required and confirmed — `is_cross_component_change`
    recomputed from this diff returns **True** (`shared/scripts/hooks/*.py`).
    Four `category:"integration"` behaviours (24-27) drive the real writer's
    output through the real Stop-hook canon runner, rather than calling the
    check with hand-aligned values.

## Self-Review

1. **Spec compliance.** Six acceptance criteria, all implemented and evidenced.
   (A) content key + mtime deleted; (B) named skip via `C3_CANON_PHASES`;
   (C) writer phase reported; (D) five distinct unanswerable reasons;
   (E) uniform whole-run answer, asserted separately from applicability;
   (F) guide + pipeline reference now describe the code.
2. **Scope.** 21 files: the check and its 8 call sites, 4 test files, 2 docs,
   the spec/mini-plan, and `triage.jsonl` (background producer appends, carried
   because the file has a `merge=union` driver for exactly this). Three things
   were deliberately kept out and are recorded in Non-goals — most importantly
   giving `security`/`compliance`/`adopt` a canon-marker producer, which is a
   separate decision about three plugins, not a defect in this check.
3. **Error handling.** Every failure path degrades to a *named* reason, never to
   a clean answer: missing, unreadable, no marker, marker without a run id, and
   "cannot evaluate" for a degenerate run id. The `is_file()` → `try/read` change
   exists because the two error paths were collapsing into the wrong one.
4. **Security.** Marker values *and* the supplied run id are stripped of C0/DEL/C1
   control characters and clipped to 120 chars before entering a detail — these
   strings are rendered into terminals by `format_report`, which emits real ANSI
   itself. No new external input, no shell, no filesystem writes.
5. **Test quality.** 58 tests across four files, each asserting an outcome and
   named for the failure it prevents. The two pre-existing tests that pinned the
   mtime contract were **rewritten to the new contract, not deleted** — they
   pinned a real behaviour, just the previous one. Two drift guards were added
   deliberately: a source-level assertion that no mtime call survives, and a
   two-direction registry test against `PLUGIN_TO_PHASE`.
6. **Naming.** `C3_CANON_PHASES` says which phases it covers; `_Handoff` carries
   `problem` / `content` / `marker` as three distinguishable states; `_clip`
   says it bounds. `_C3_NAME` is the only abbreviation and sits beside `_NAME`.
7. **Affected Boundaries.** All four carry a test. The two signature changes are
   the risky ones and both are pinned: `run_id` keyword-only-with-no-default is
   asserted by reflection, and the Stop-hook call site is pinned by a source
   drift guard because `run_canon_checks` keeps a defaulted `run_id` for
   backwards compatibility — which would otherwise let the argument be dropped
   silently and turn every C3 into "cannot evaluate".

## Reflection

**The brief's lead was right about the material and wrong about the key, and
finding that out cost one file read.** It pointed at the canon frontmatter's
`phase` field, which is indeed the only per-phase fact the handoff carries. The
obvious move was to key on it. Reading `verify_phase.dispatch_all` first showed
why that fails: one `run_id`, eight dispatchers, one overwritten file — a phase
key would have passed the last phase and warned on the other seven, reproducing
the very defect class inside the fix for it. That is the same shape as the
previous iterate's empty-ruleset probe, and the same lesson: *the module's stated
principle does not audit its own code.* The difference is that here the
contradiction was available by reading, before anything was written.

**The brief undercounted the callers, and the missing one was the one that
mattered.** It named six phase verifiers; there are eight call sites, and the
eighth — the Stop-hook phase-quality canon runner — invokes C3 for *every* phase
in `PLUGIN_TO_PHASE`, including three that write no canon marker at all. A
content key without an applicability set would have converted a warning that
fired too often into one that fired always, for `security`, `compliance` and
`adopt`. Counting the callers with a grep rather than trusting the brief's
number is what surfaced it.

**Deleting the parameter mattered more than changing the logic.** `run_id` is
keyword-only with no default specifically because gemini's plan-review finding
was right: with eight call sites, a default would let a missed one compare
against `""` and warn forever. `max_age_seconds` is deleted rather than
defaulted for the mirror reason — a surviving parameter is an invitation to
re-enable the clock. The synthesis (interpreter-enforced at the signature, but an
explicitly-empty value still yields a *stated* "cannot evaluate") is better than
either reviewer's version alone.

**Three external review rounds, three real defects, none of which a unit test
would have caught.** The plan round rejected the naive signature; the first code
round found ANSI/OSC escapes reaching operator-facing output through `_clip`,
which normalizes whitespace but not control bytes; the second found
`Path.is_file()` swallowing `OSError` and reporting a locked handoff as a missing
one — collapsing two of the five distinct reasons AC (D) exists to keep apart.
Each was a correctness gap in exactly the "unknown vs clean" axis this check is
about, and each was found by reading the code rather than by running it.

**The change caught itself on the live repo.** Running the real
`verify_phase.py --phase build` against this worktree produced *"handoff was
generated by iterate-2026-07-27-adopt-inherited-baseline, not
iterate-2026-07-27-c3-phase-content-key"* — a true finding, correctly named,
about a genuinely stale handoff. Under the old code the same state reported an
mtime in seconds and passed or failed on how long the run had taken.

**What is still owed.** `security`, `compliance` and `adopt` have no
canon-marker producer, so C3 skips them by name rather than verifying anything.
That is honest, but it is a gap in coverage, not a property of those phases —
giving them a producer is a decision about three plugins' finalization steps and
is recorded as a non-goal rather than smuggled in here. The per-phase
attribution bound (a later phase's write satisfies an earlier phase's C3) is
pinned by a test so it stays deliberate.
