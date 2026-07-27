# Mini-Plan: C3 phase-canon handoff freshness → content key

Run ID: iterate-2026-07-27-c3-phase-content-key

## Chosen approach — co-locate with the F11 twin, key on the run

1. **Move** `check_c3_session_handoff_fresh_after_phase` out of
   `verifiers/common.py` into `verifiers/handoff_freshness.py`, next to
   `check_session_handoff_fresh`. Both now answer "does this handoff belong to
   the run being verified" off the same canon marker, via one shared private
   reader. `common.py` does not import `handoff_freshness`, so no cycle.
2. **New signature:** `(project_root, phase, *, run_id: str)` — keyword-only and
   **no default**, so a missed caller is a `TypeError` at import/call time rather
   than a silent mismatch warning (external review, gemini R1). An empty-but-
   supplied run id stays a stated "cannot evaluate" result, because sentinel runs
   legitimately produce one. `max_age_seconds` is deleted, not defaulted-away —
   leaving it would let a caller re-enable the clock.
3. **Canon-producer set** `C3_CANON_PHASES` = the 8 phases that write a marker.
   A phase outside it returns `Severity.SKIPPED` naming the absence of a
   producer. It lives in `handoff_freshness.py`, **not** in
   `phase_quality/_constants.py` beside `C4_PHASES`/`C5_PHASES` as the reviewer
   suggested: `phase_quality/__init__` imports `_runners`, which imports
   `tools.verifiers.*`, so importing the constant back would close a cycle. The
   alignment the reviewer wanted is enforced by a drift meta-test against
   `PLUGIN_TO_PHASE` instead (both directions).
4. **Thread `run_id`** through the 8 call sites. Seven already have it in scope;
   `run_canon_checks` gains a `run_id` parameter supplied by
   `audit_phase_quality_on_stop.py`, which already holds one and resolves it via
   `phase_quality.resolve_run_id`. A sentinel run id (`""` / `"unknown"`, per the
   existing `is_sentinel_run`) is passed through as "cannot evaluate", never
   synthesized into a value that would false-warn (external review, openai R1).
5. **Rewrite** the two mtime tests in `test_verifiers_common.py` to the new
   contract (rewrite, never delete — they pin a real behaviour, just the old
   one), and add the new suite + composition test.
6. **Docs:** `docs/hooks-and-pipeline.md` C3 row records the key;
   `docs/guide.md:2029` is verified to now be true rather than edited.

7. **A structured marker read**, shared by both checks: one private reader that
   returns a distinguishable state for *missing file*, *unreadable*, *no canon
   marker* (covers malformed YAML and non-canon frontmatter — `parse_canon_
   frontmatter` already requires `canon_generated: true`), *marker without a
   run id*, and *valid marker*. Each maps to its own C3 reason, which is what
   AC (D) asks for (external review, openai R2).
8. **Bounded diagnostics.** Marker values are clipped before entering a result
   detail, so a malformed handoff cannot dump arbitrary content into Stop-hook
   output (external review, openai R6). Exception payloads are reported as the
   exception *type*, matching the F11 twin.

**Why co-locate rather than duplicate:** `handoff_freshness.py`'s own docstring
records the reason the parser was centralised — *"two implementations of one
format drift, and here they would drift on the meaning of 'fresh'."* Keeping a
second marker-reader in `common.py` would rebuild exactly that.

## External plan review — disposition

`external_review.py --mode iterate`: **openai = revise**, **gemini = degraded**
(`finish_reason=length`; the truncation detector shipped in
iterate-2026-07-27-name-the-blocker catching a real one). All six openai findings
and gemini's one complete finding are adopted, as recorded in steps 2, 3, 4, 7, 8
above plus the test plan:

| # | Finding | Disposition |
|---|---|---|
| openai R1 | Stop-hook run-id provenance unspecified | Adopted — step 4; sentinel passthrough + a runner-level test |
| openai R2 | "canon marker" needs a validation contract | Adopted — step 7, structured reader |
| openai R3 | Move changes an import surface; a missed importer fails at load | Adopted — exhaustive symbol + module grep, and a module-load test per verifier entry point |
| openai R4 | `C3_CANON_PHASES` alignment with `PLUGIN_TO_PHASE` | Adopted with a **placement change** — constant stays in `handoff_freshness.py` (cycle, step 3); alignment enforced by a two-direction drift meta-test |
| openai R5 | "every phase gets the same answer" would mask an applicability regression | Adopted — AC (E) test split into two assertions: canon phases evaluate, excluded phases skip |
| openai R6 | Don't echo raw frontmatter into hook output | Adopted — step 8 |
| gemini R1 | `run_id=""` default masks a missed caller | Adopted with a **refinement** — keyword-only and no default (interpreter enforces), while an explicitly-empty value keeps its stated "cannot evaluate" result |
| gemini R2 | A marker may carry `run_id` but no `phase` | Adopted — empty phase renders as `(unnamed)` rather than an empty string |

## Alternative considered — keep it in `common.py`, import the parser

Leave the function where it is and have `common.py` import
`parse_canon_frontmatter` from `lib.canon_frontmatter` (it already imports
`lib.adr_headers`, so the path works). Zero import-site churn: 8 files untouched.

**Rejected because** it puts a second implementation of "is this handoff fresh"
in a second module, which is the drift the prior iterate centralised the parser
to prevent — and the two would drift on *semantics* (run key vs phase key), not
just parsing. The import churn it avoids is mechanical and covered by the type
checker and the suite; the drift it invites is not.

## Alternative rejected earlier (recorded in the spec)

Key on the marker's `phase`. Ruled out by reading `verify_phase.dispatch_all`:
one handoff, eight dispatchers, one `run_id` — it would fail 7 of 8 phases.
