# Iterate: C3 asks whether THIS phase left the handover note

- **Run ID:** iterate-2026-07-27-c3-phase-history-join
- **Date:** 2026-07-27
- **Type:** change
- **Complexity:** medium
- **Branch:** iterate/c3-phase-history-join
- **Spec Impact:** MODIFY — FR-01.01
- **Fixes:** regressions shipped by iterate-2026-07-27-c3-phase-content-key (PR #467)

## Problem

PR #467 moved Canon C3 off filesystem mtime onto "does the handoff's canon
marker name the run being verified". The mtime deletion was right. **The key was
wrong, and it shipped six defects.** All six were found by the internal
code-reviewer / doubt-reviewer / spec-reviewer cascade run *after* the merge;
four rounds of external review across two providers had missed every one,
because they read the diff and the subagents read the callers.

### The key is vacuous in one regime and broken in the other

#467 justified keying on the run by observing that `verify_phase --phase all`
hands ONE run id to eight dispatchers reading one overwritten handoff, so a
phase key would pass only the last writer. True — but the run key only avoids
that when every phase shares one id, and **in exactly that case the run key
passes everything**:

`SHIPWRIGHT_RUN_ID` is set with `: "${SHIPWRIGHT_RUN_ID:=…}"` — assign-only-if-
unset — in build (`section-state.md:75`), test (`step-5-report-results.md:59`),
changelog (`SKILL.md:323`) and deploy (`SKILL.md:307`). The idiom is deliberate;
design's step-9 says so in prose. So those four inherit an earlier phase's id.
Then: build writes the marker, **test skips its C3 step entirely**, and C3 for
test compares the shared id, matches, and **passes**. Under the mtime rule that
warned. The "known bound" #467 recorded as a corner case is the **default for
four of the eight canon phases**, and it is a silent pass — the worst direction.

Where ids *are* per-phase, the run key fails the other phases under `--phase all`
just as a phase key would. This repo carries both regimes at once:
`phase_history` shows `project/plan/build/test` sharing `adopt-2026-05-02T183757`
while `changelog` mints `changelog-v0.26.0-20260613`.

### The alternative was named in the docstring #467 deleted

The pre-#467 `common.py` C3 docstring pointed at it verbatim: *"callers that want
stronger checks can use `read_run_config(...).get("phase_history", {}).get(phase,
[])`"*. `phase_history` is an **accumulating per-phase artifact** — exactly what
C1/C2/C4/C5 read, and what #467 asserted did not exist. `check_phase_history_has_run`
already reads it two lines away in the same verifier suite.

### Five more shipped defects

| # | Defect | Effect vs. mtime |
|---|---|---|
| 2 | Stop hook resolves run id via `pq.resolve_run_id`, which never reads `SHIPWRIGHT_RUN_ID` (`_resolution.py:142-188`): run_config `run_id` (orchestrator writes `runId`) → `run_started` (no producer exists) → loop vars → **session UUID**. | permanent WARN, every canon phase, every Stop |
| 3 | `phase_validators._run_canon_checks:63` reads `SHIPWRIGHT_RUN_ID` from a hook-launched subprocess that never inherits the skill's shell export → `""`. | permanent "cannot evaluate" inform |
| 4 | `docs/guide.md:2042` documents `verify_phase.py --phase all` with no `--run-id`; now 8 warnings, and exit 1 under `--strict`. | documented example fails |
| 5 | build `SKILL.md:266-276` Step 11 writes a **marker-less** handoff to the TRACKED path mid-split (`generate_session_handoff.py:563`). | deletes the marker C3 depends on |
| 6 | `docs/hooks-and-pipeline.md:2358-2363` (added by #467) asserts both callers resolve the id the writer stamps and that no id is synthesized. Both false. | doc states the opposite of the code |

Defect 6 is the same AC-(F) failure #467 existed to close, re-committed in the
same change.

## The key, restated

C3 answers **"did THIS phase leave the handover note?"** using the marker's
`phase` field plus the phase's own accumulating completion record — not pipeline
order. Two branches, and they key on **different clocks**, which is the whole of
the correction below:

- **The note names THIS phase.** Compare the note's own anchor against this
  phase's latest completion anchor. Both are EVENT times, stamped from one
  function moments apart, so equality means "this canon block wrote it".
- **The note names ANOTHER phase.** Compare the two phases' WALL clocks against
  each other — this phase's latest completion against the owner's completion
  *for the run the note names*. The note's anchor is deliberately not consulted
  here: `record_event` dedups permanently, so a phase completing a second time
  inherits the owner's anchor and the two read as simultaneous.

| Case | Meaning | Verdict |
|---|---|---|
| marker phase == checked phase, marker run id == latest recorded run id | this phase wrote it, for its own latest completion | **PASS** |
| marker phase == checked phase, run id matches, the completion carries an event anchor, and the note's anchor is older than it | a later step completed without re-writing the note | **WARN** |
| marker phase == checked phase, run id is an *older* entry | the note is from a previous run of this phase | **WARN** |
| marker phase == checked phase, run id absent from the record | note and record disagree about this phase | **WARN** (own reason) |
| marker phase == checked phase, the completion CLAIMS an anchor that cannot be read | a malformed record must not buy the run-id fallback | **WARN** (own reason) |
| marker phase != checked phase, **this phase completed after the OWNER phase did** | this phase ran later and left no note | **WARN** ← defect 1 |
| marker phase != checked phase, **this phase completed before the OWNER phase did** | legitimately superseded; undeterminable from one file | **SKIP**, naming the owner |
| marker phase != checked phase, the owner recorded no completion under the run the note names | the two cannot be attributed to each other | **WARN** (stated) |
| either side's time missing, unparseable, or too coarse to settle the order — INCLUDING two spans that merely overlap | cannot order the two | **WARN** (stated) |
| no marker / no completion record / unreadable / missing | stated reason | **WARN** |

**Revised during the pre-PR cascade — three things this table originally got wrong.**

*The clock.* The marker's `timestamp` is not a write time: it is
`latest_event_dt`, the newest event on disk, chosen so the tracked handoff does
not go dirty on every regeneration. A completion's wall-clock `at` is therefore
never comparable with it — the canon block records the event, writes the marker,
*then* appends, so `at` is unconditionally later. Comparing them accused every
phase re-run of skipping its C3 step (reproduced end-to-end against the real
tools). `append_phase_history` now also stamps `event_at` from that same
function, and C3 compares against that; a correct block leaves the two equal, so
ties are not "later".

*The scope.* The clock is consulted where the completion carries an anchor, and
nowhere else. Gating on a COUNT of completions was the first attempt and was
wrong: `iterate`'s ledger is one file per run id, so its count is pinned at one
forever and a rewritten entry with a skipped marker passed on the bare id.

*The other branch.* When a DIFFERENT phase owns the note, the anchor cannot
decide it at all — the same dedup makes a second completion inherit the owner's
anchor, so the two read as simultaneous and the later phase was reported as
superseded by the earlier one. That branch orders the two phases against each
other on wall clock, which is comparable because one producer writes both.

**Why time, not pipeline order.** External plan review (openai R1, high) showed
a static order cannot separate two real situations: `deploy` writing the note in
this run and legitimately superseding `build`, versus a *stale* `deploy` note
followed by a `build` re-run that wrote nothing. Under phase order both read as
"later phase superseded" → SKIP, and the re-run that skipped its step is missed —
defect 1 again, in a new costume. Ordering the two phases' recorded completions
against each other separates them, and drops the `PIPELINE_PHASES` dependency
entirely.

**Timestamp fields are inconsistent** — and, as the cascade found, were also the
*wrong* fields. Live entries carry `at` (written by **adopt**, which has always
stamped it) or a bare `date` (changelog), both wall clock. `append_phase_history`
itself wrote `date` alone until this iterate; it now stamps `at` as well, and
`event_at` — the one field readable on the marker's clock. `lib/phase_history.py`
exposes the two clocks through SEPARATE readers that never fall back to each
other: `entry_anchor` reads `event_at` alone, `entry_wall_time` reads `at`/`date`
alone. A single anchor-preferring-with-fallback reader existed in an earlier
round; it was deleted because nothing consumed it and its existence invited the
very cross-clock comparison that broke this check twice. Both read a bare
`YYYY-MM-DD` as a DAY rather than as midnight, and report anything they cannot
settle as a stated WARN — the module's unknown-vs-clean rule.

**Ordering is safe in the orchestrated flow** (verified, gemini R1): the canon
steps write the marker, then `append_phase_history`, then `update-step` — which
is what runs the validators. So history is current when C3 reads it.

**The caller's `run_id` stops being an input.** The join is
marker → `phase_history[phase]`, both on disk. That deletes defects 2 and 3 at
the root rather than patching two resolvers: a check that does not consult the
caller's run id cannot be broken by the caller resolving it differently.

## Non-goals

- Reworking `resolve_run_id` or `phase_validators`' env read. Once C3 stops
  taking a run id, their disagreement no longer reaches it. Other consumers of
  those resolvers are out of scope.
- The F11 twin `check_session_handoff_fresh`. It runs at iterate finalization
  where the run id IS authoritative and per-run; it keeps its run key.
- Giving `security`/`compliance`/`adopt` a canon-marker producer (still no
  producer; still a named SKIP).

## Affected Boundaries

| Boundary | Direction | Note |
|---|---|---|
| `session_handoff.md` canon frontmatter (`phase` field) | consume | now load-bearing, not decorative — so an empty `--phase` is refused rather than stamped |
| `session_handoff.md` canon frontmatter (all four values) | produce | rendered unescaped as `key: "…"`; now sanitised in `build_marker`, since a newline in `--reason` could forge `phase`/`timestamp` |
| `shipwright_run_config.json::phase_history[phase]` | consume | new read for C3 |
| `shipwright_run_config.json::phase_history[phase]` entry shape | **produce** | `append_phase_history.py` wrote `{run_id, date}`; it now writes `{run_id, at, event_at?, date}`. BOTH `at` and `event_at` are new — a schema addition to a tracked artifact |
| `append_phase_history.py --entry-json` | **produce** | its canonical-key refusal widens from `{run_id, date}` to `{run_id, at, event_at, date}` — a CLI contract narrowing. No call site in `plugins/**/*.md` passes either new key, so nothing breaks today |
| `append_iterate_entry.py --entry-json` | **produce** | the same narrowing on the sibling tool: `{run_id, date}` → `{run_id, date, event_at}`. It reserves `event_at` without producing it, so no caller can forge the anchor |
| `lib/phase_quality/_runners.py::run_canon_checks` | **produce** | drops its `run_id` parameter. A different signature from C3's own, with its own consumers (`hooks/audit_phase_quality_on_stop.py`, `shared/tests/test_audit_phase_quality.py`); #467 declared it as a boundary when it ADDED the parameter, so removing it is one too |
| `.shipwright/agent_docs/iterates/<run_id>.json` | consume | `iterate`'s completion record; routed by `COMPLETION_PRODUCER` |
| C3 signature (drops `run_id`) | produce | 8 call sites simplify |
| build Step 11 + per-section + iterate F11 handoff writes | produce | must stop clobbering the marker |

`PIPELINE_PHASES` is **not** touched: the design comparing times rather than
pipeline order drops that dependency entirely (see "Why time, not pipeline
order" above). An earlier draft of this table listed it as a consumed boundary;
that was wrong and the code never did it.

## Acceptance Criteria

- **(A) A phase that left no note is caught.** When a phase completes without
  regenerating the handover note, its check reports that — even when it shares a
  run identifier with the phase that did write one. This is the case that
  silently passed after #467 and warned before it.
- **(B) A note from the phase itself, for its own latest run, passes.** No
  dependence on how recently the file was written, and no dependence on the
  caller supplying an identifier.
- **(C) The one genuinely undecidable case is a named skip, not a verdict.**
  Auditing a finished pipeline, where a later phase has legitimately overwritten
  the note, reports that it cannot be determined and says which phase now owns
  the note — instead of warning on every earlier phase or passing them all.
- **(D) An unanswerable check still says which part it could not read.** Missing
  note, unreadable note, no marker, and no recorded completion for that phase are
  four distinct stated reasons; none is reported as a pass.
- **(E) Mid-build handovers stop destroying the marker.** A handover note written
  during a split no longer removes the canon marker an earlier split recorded.
- **(F) Documentation describes the shipped rule.** The pipeline reference and
  the guide state this key, the false provenance paragraph from #467 is gone, and
  the documented `verify_phase` examples work as written.
- **(G) The drift guards actually guard.** The mtime guard covers the module
  rather than one function, and the phase-quality fixture that silently stopped
  exercising C3 exercises it again.

## Confidence Calibration

- **Boundaries touched:** see the Affected Boundaries table above — the canon
  marker (consume + produce), `phase_history` entry shape (produce, two new
  keys), the `--entry-json` CLI contract (produce, narrowed), the iterate ledger
  (consume), C3's signature (produce), and three handoff write sites (produce).

- **Empirical probes run.** Every claim below was executed, not reasoned about:
  - Read this repo's LIVE `phase_history`: `adopt` stamps `at`, `changelog`
    stamps a bare `date`, and **no live entry from any pipeline phase carried
    `at`** before this change. That is HIGH-1's root, confirmed on real data.
  - Read the live iterate ledger: 54 entries, `date` a full ISO instant — so the
    ledger has intra-day precision and the same reader serves it.
  - **Drove the real canon block twice** (`record_event` → marker → producer).
    First run: PASS. Second run: `record_event` reported
    `{"skipped": true, "reason": "duplicate_phase"}`, the marker was rewritten,
    and C3 accused the phase of skipping its step. That reproduced the round-2
    HIGH; the same probe now passes.
  - **Drove changelog → deploy → changelog-without-its-C3-step.** C3 reported
    `superseded: deploy wrote the note after changelog completed` — a silent SKIP,
    factually backwards. That reproduced the round-3 HIGH; the same probe now
    warns correctly. Both probes showed the two phases' `event_at` EQUAL and
    their `at` correctly ordered, which is what the fix keys on.
  - Timed `latest_completion` on the live repo: `build` 0.07 ms, `iterate`
    3.45 ms over 54 ledger files. C3 runs once per phase per Stop.
  - Confirmed `RUN_ID_STRICT` is enforced on ledger writes, so the reader's
    `iterate-*.json` filename gate cannot silently drop a real completion.
  - Confirmed `shipwright_run_config.json` is NOT in `.gitattributes`' union-merge
    set, which is what makes positional "latest" safe.
  - Read a BOM-encoded run config through `latest_completion`: readable.
  - Ran the bloat pre-commit hook against the staged tree at each step.

- **Test Completeness Ledger:** machine-readable block at F5 in
  `shipwright_test_results.json::iterate_latest.test_completeness`. Every
  behaviour this diff introduces is `tested`; there are no `untestable` rows.
  Enumerating it is what surfaced two changes I had made without tests (the
  BOM-hardened read and the lazy marker-timestamp thunk) — both now covered.

- **Confidence-pattern check.**
  - *Asymptote (depth).* Depth here means testing the PRODUCER, not the fixture.
    Three defects in this iterate survived a green suite because a fixture
    modelled a shape no writer emits; `test_completion_writers.py` drives the
    real tools in real canon order, and `_c3_fixtures.history_entries` now stamps
    `at` strictly later than `event_at` so no suite can pass by reading the wrong
    clock.
  - *Coverage (breadth).* One test per verdict-table row; both directions of
    three registry drift guards; an exact-inventory guard over every handoff
    write site in `plugins/**/*.md`; and the false-positive guards for each rule
    that could plausibly over-fire.
  - *Integration composition (`cross_component`).*
    `test_handoff_freshness_composition.py` runs writer → Stop hook → canon
    runner → C3 on disk, including the `--preserve-canon-marker` case where two
    consumers read one marker.
  - *Honest limits — two, and one of them never expires.*
    1. **Transient, seven phases.** The same-phase anchor check is inert until
       each `phase_history` phase completes once after this merges, because only
       new completions carry `event_at`. On the merge target every phase's latest
       entry predates this change, so the clock is consulted for none of them on
       day one. `adopt`'s `config_writer.py` replaces the whole run config with
       anchorless entries, so a re-adopt resets it.
    2. **Permanent, `iterate`.** `append_iterate_entry.py` deliberately stamps no
       `event_at` (the key is reserved so no caller can forge one), so
       `PhaseCompletion.anchor` is None for `iterate` forever and its same-phase
       check passes on a bare run-id match. Safe because its ledger is one FILE
       per run id — a stale marker names a DIFFERENT run, which the run-id branch
       catches — and the only escape is an in-place F5c re-run without a matching
       F5b. Deferred, not forgotten: trg-1346abbd, and the bound is asserted by
       `test_completion_writers.py` so it cannot move silently.

    What ships working on day one, for all eight phases: the cross-phase branch
    (wall clock, which every producer already writes), the run-id join, the
    stated-unknown states, and the three marker-preservation fixes.
