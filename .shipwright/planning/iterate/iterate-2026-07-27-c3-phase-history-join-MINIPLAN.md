# Mini-Plan: C3 joins the marker against phase_history

Run ID: iterate-2026-07-27-c3-phase-history-join

## Chosen approach — marker.phase + phase_history, no caller run id

1. **`check_c3_session_handoff_fresh_after_phase(project_root, phase)`** — the
   `run_id` parameter is REMOVED, not defaulted. The join is
   marker → `phase_history[phase]`, both read from disk. This deletes defects 2
   and 3 at the root: a check that never consults the caller's run id cannot be
   broken by two callers resolving it differently.
2. **Verdict table** as in the spec. Order of evaluation:
   applicability (`C3_CANON_PHASES`) → read handoff → marker present →
   completion record present → `marker.phase == phase`, then either the run-id
   join (consulting the note's anchor only where the completion carries one)
   or, for another phase's note, the two phases' wall clocks against each other.

   *An earlier draft routed this through `PIPELINE_PHASES`. It never did, and
   item 3 below is why — the registry is not imported anywhere in the chain.*
3. **Supersession is decided by TIME, not by `PIPELINE_PHASES`** (revised after
   external plan review — see the disposition table below). New
   `lib/phase_history.py` owns `latest_completion(project_root, phase, *, run_id="")`
   — the keyword narrows to the completion recorded under ONE run — plus the two
   single-clock readers `entry_anchor` and `entry_wall_time`, each returning a
   `RecordedTime | None`.
   **`PIPELINE_PHASES` is not touched at all** — the move proposed in the first
   draft is dropped, so this diff no longer edits a registry with two copies.

   *Three corrections from the pre-PR cascade, all of which changed the code:*

   - **Two clocks, two readers, no fallback between them.** The marker's
     `timestamp` is `latest_event_dt`, an EVENT time, not a write time, and a
     completion's wall-clock `at` is structurally later than the marker that
     closed it — comparing the two accused every phase re-run of skipping its C3
     step. `append_phase_history` now stamps `event_at` from the same function;
     `entry_anchor` reads that key ALONE and `entry_wall_time` reads `at`/`date`
     alone. A single anchor-preferring-with-fallback reader (`entry_time`) was
     written, consumed by nothing, and DELETED — its existence invited the very
     cross-clock comparison it was meant to survive.
   - **The cross-phase branch uses neither the marker nor the anchor.** It orders
     this phase's completion against the OWNER's completion for the run the note
     names. Ordering by the anchor there read the two as simultaneous whenever
     `record_event`'s dedup denied the later phase a fresh event, and reported it
     as superseded by the earlier one — a silent SKIP.
   - **`RecordedTime`, not a bare datetime.** A bare `YYYY-MM-DD` pins a day, not
     an instant; reading it as midnight lost every same-day comparison in the
     direction that hides a skipped step. The span is carried and anything it
     cannot settle is a stated WARN.

   **`iterate` DOES need a special case** — the claim that it did not was simply
   wrong. It has never written `phase_history`; F5c writes the file-per-run
   ledger. Comparing it "the same way as any other phase" resolves to *no record
   found* → a permanent WARN naming a tool iterate's pipeline abandoned.
   `COMPLETION_PRODUCER` routes each phase to the record it actually keeps, and
   three drift tests make a phase-without-a-producer, or a producer that
   does not exist or will not run, a build failure.
4. **Defect 5 — the marker-less mid-build write.** `generate_session_handoff.py`
   gains `--preserve-canon-marker`: when the target already carries a canon
   marker and no new one is supplied, carry the existing block through instead
   of dropping it. This is narrower than making preservation unconditional,
   which would let a stale marker outlive its run.

   The cascade found the brief named **one** of three such writes. All three now
   pass the flag — build's Step 11, build's **per-section** doc update
   (`section-doc-update.md`, which runs more often), and **iterate's own F11**
   (which runs after F5b stamped the marker, so every iterate was deleting it at
   the very end). Because all eight canon phases read this one file, any of them
   blanked C3 for all eight. `test_canon_marker_write_contract.py` now asserts
   the property over every invocation in `plugins/**/*.md`, so the next reference
   file cannot reopen it.
5. **Defect 4 + 6 — docs.** Delete the false "Run-id provenance" paragraph;
   restate the key; fix the `--strict` example. **The fourth sub-step —
   updating `verify_phase.py --run-id` help — is STRUCK, not skipped:** the help
   attributes the flag to the `phase_history` membership check
   (`check_phase_history_has_run`) and to iterate, never to C3, so nothing in it
   became false when C3 stopped taking a run id. Editing it would be churn, and
   C3's own removal is already asserted by
   `test_c3_handoff_freshness::test_the_check_takes_no_run_id`.
6. **Defect 7 (from the cascade) — the drift guards.**
   `test_the_source_carries_no_mtime_call` inspects
   `sys.modules[check_c3.__module__]` instead of one function; the
   `plugins/shipwright-run/tests/test_phase_validators_project.py:64` fixture
   gets a real canon frontmatter block so "full canon" asserts a passing C3.
7. **Ledger row 29 correction** — #467 claimed the F11 twin was unaffected; it
   was (routed through `_read_handoff`, details now clipped). Record the true
   claim and add the `assert "unreadable" in detail` the twin's test lacked.
   **Done:** the corrected row is appended in
   `iterate-2026-07-27-c3-phase-content-key.md` (the original is left in place —
   a ledger is a record, not a draft), and the assertion is in
   `test_handoff_freshness::test_unreadable_handoff_is_a_warning_not_a_crash`.

## Alternative considered — keep the run key, fix the two resolvers

Make `resolve_run_id` consult `SHIPWRIGHT_RUN_ID`, make `phase_validators` fall
back to `resolve_run_id`, correct the docs. Smaller diff, touches no verdict
logic.

**Rejected** because it fixes only the noise (defects 2/3/4/6) and leaves defect
1 — the silent pass — untouched, which is the one that makes C3 weaker than the
mtime rule it replaced. It also leaves the check depending on a run id that two
callers resolve differently by construction, so the next caller re-opens it.

## External plan review — disposition

`--mode iterate`: **openai = revise**, **gemini = degraded** (truncated, but its
one complete finding is adopted). Both independently hit the same high-severity
hole, from different ends.

| # | Finding | Disposition |
|---|---|---|
| openai R1 (high) | Static `PIPELINE_PHASES` order cannot separate "a later phase legitimately superseded this one" from "a stale later-phase marker plus a re-run of this phase that wrote nothing" — the second silently SKIPs, which is defect 1 again | **Adopted, design changed.** `PIPELINE_PHASES` is dropped from the design entirely. (This cell recorded the disposition AS TAKEN; the mechanism was corrected twice afterwards by the pre-PR cascade — supersession is now decided by ordering the two phases' recorded completions against each other on wall clock, not against the marker. See item 3 above.) |
| openai R2 (high) | The `phase_history` contract is assumed, not stated or validated; malformed / absent / duplicate / non-completed entries risk permanent false WARNs | **Adopted.** One `lib/phase_history.py` centralises extraction; malformed entry, absent run id and unparseable time each get their own stated reason; tests run against writer-produced JSON, not hand-built fixtures only. |
| openai R3 (medium) | Two independently written artifacts → a verifier could observe one before the other and emit a transient WARN | **Adopted as verification.** Confirmed the canon steps write marker → `append_phase_history` → `update-step` (which runs the validators), so history is current at check time; recorded in the spec. "Marker names a run absent from history" keeps its OWN reason rather than being lumped with "older run", so a genuine mid-flight read is legible instead of misattributed. |
| gemini R1 (high) | If C3 runs before the orchestrator flushes the current phase's completion, "same phase, older history id" false-WARNs | **Same as R3** — ordering verified; distinct reason for the absent-from-history case. |

## Alternative considered — marker.phase == phase only, no phase_history

Simplest fix for defect 1. **Rejected** because it cannot distinguish "this
phase never wrote a note" from "a later phase legitimately overwrote it", so
`--phase all` on a finished pipeline warns on every phase but the last — the
false fire #467 correctly refused to ship. What separates those two is **the
clock**: this phase's last recorded completion against the note's own anchor
(openai R1 in the table above is precisely the finding that a static
`PIPELINE_PHASES` order CANNOT separate them). The completion record is what
additionally makes the same-phase case mean "for its own latest run" rather than
"ever".

## Test plan

- Defect-1 regression FIRST (red before green): sticky run id, build wrote the
  marker, test skipped its step → C3(test) WARNs. This test fails on `main` today.
- Verdict table: one test per row, plus `iterate` (whose completions live in the
  F5c ledger, not in `phase_history`).
- `--phase all` on a finished pipeline: earlier phases SKIP-named, the owning
  phase PASSes, none WARN.
- Composition (cross_component): real writer → real `run_canon_checks` → verdict,
  including the sticky-id scenario end-to-end.
- `--preserve-canon-marker`: marker survives a mid-build handoff; absent the
  flag, behaviour is unchanged.
- Registry drift: `C3_CANON_PHASES` ⊆ `COMPLETION_PRODUCER`, every named producer
  resolves to a file AND runs (`--help`), and `C3_CANON_PHASES` ↔ `PLUGIN_TO_PHASE`
  both directions. (The `PIPELINE_PHASES` re-export bullet this replaces was
  moot — the chosen design never consumes that registry.)
- Write-contract drift: every `generate_session_handoff.py` invocation in
  `plugins/**/*.md` passes `--canon-marker` or `--preserve-canon-marker`, and
  every `--canon-marker` names its `--phase`.
- The real writers, in the real canon order (`record_event` → marker →
  completion), driven as subprocesses: marker and completion land on one clock; a
  re-run with no new event still passes; a split that skips the marker write is
  still caught; a later phase re-run does not accuse the earlier one.

## Process change (the lesson from #467)

Run the **spec-reviewer → code-reviewer → doubt-reviewer** cascade BEFORE opening
the PR, not after. On #467 four external rounds across two providers found three
real bugs and missed all six of these, because external review reads the diff and
the subagents read the callers. External review is not a substitute for it.
