# Grill-trace evidence record + completeness gate (P4.2)

## Context

REQ3.09 Phase 4 item (2) — `/shipwright-project`'s IREB grilling method
(`shared/requirement-elicitation.md` §8/§9) is a prompt-only guarantee: an
interviewer *should* answer all seven dimensions and record a fit
criterion, but nothing checks that it happened. The design at
`.shipwright/planning/campaigns/2026-07-24-req3-grill-trace-enforcement-DESIGN.md`
opens with a dogfooded failure mode — three real interviews, zero
structured evidence written. This sub-iterate implements that design's
four closed-vocabulary STOP conditions and a live-write producer, on top
of P4.1's `CONTEXT.md` glossary (`context_md_format.read_terms()`).

## Decision

Write `shared/scripts/tools/write_grill_trace.py` (producer) +
`shared/scripts/tools/grill_trace_format.py` (shared data model/reader) so
one JSON grill-trace record per elicited requirement lands at
`{planning_dir}/grill-traces/<requirement_key>.json` **during** the
interview (`interview-protocol.md`), not batched after. Write
`shared/scripts/tools/verify_grill_trace_completeness.py` — a
`verify_iterate_finalization.py`-shaped `check_*`/`run_all_checks` gate —
enforcing exactly DESIGN.md's four STOPs (`blank_dimension`,
`greenfield_assumed`, `undefined_term`, `outcome_without_fit_criterion`),
plus two separately-named, non-closed-vocabulary structural guards added
during review (`grill_trace_coverage`, `fr_trace_coverage`) and two small
consistency checks (`glossary_source_available`, `glossary_delta_declared`).
Wire the gate into `/shipwright-project`'s Step 8 as a blocking item (SKILL.md
+ `step-8-completion.md`). `plugins/shipwright-adopt/**` untouched.

## Consequences

A project that ran `/shipwright-project`'s interview after this ships
cannot reach Step 8 completion with a missing, blank, silently-assumed
(project surface), undefined-term, or fit-criterion-less requirement trace,
nor with a live FR row that has no matching trace at all. A project whose
interview predates this gate sees a genuine, non-false red at Step 8 (no
grandfather path, by design) and must write traces retroactively. The gate
never judges prose quality (honesty guard, `shared/grill-trace-format.md`
§3) — completeness only, proven by a required test that a well-formed but
low-quality trace still passes the full `run_all_checks()` gate.

## Rationale

Mirroring `verify_iterate_finalization.py`'s established `check_*` /
`CheckResult` / `run_all_checks` shape keeps this gate legible to anyone who
has read that verifier; reusing P4.1's `context_md_format.read_terms()`
(rather than forking a second `CONTEXT.md` parser) keeps the two producers'
consumers aligned by construction. `terms_used` is declared by the
interviewer, never scanned from `requirement_text`, because free-text term
extraction is itself a judgment call the honesty guard forbids the gate
from making.

## Rejected alternatives

Scanning `requirement_text` for undefined terms instead of a declared list
(reintroduces a judgment call, rejected — honesty guard). A per-FR-id join
at interview time (impossible — FR ids don't exist until spec generation,
Step 6; the `fr_trace_coverage` slug join runs at gate-time instead, see
findings below). Wiring `adopt`/`iterate` surfaces in the same sub-iterate
(out of scope, `trg-1aa5a8ab` owns onboarding).

## External-Plan-Review-Findings

Two rounds: round 1 against the original mini-plan (four STOPs, no
FR-join); round 2 against the revised mini-plan (after round 1's
`fr_trace_coverage` addition landed).

### Round 1

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | GLM+OpenAI | high | `grill_trace_coverage` alone cannot see a PARTIALLY recorded interview (some requirements traced, one silently skipped) | accepted-and-fixed — added `fr_trace_coverage` (`grill_trace_fr_coverage.py`), a `Name`-slug join running once spec.md exists |
| 2 | GLM/OpenAI | medium | `requirement_key` becomes a filename component with no slug validation — filesystem-boundary risk | accepted-and-fixed — `grill_trace_format._REQUIREMENT_KEY_RE` (`^[a-z0-9]+(-[a-z0-9]+)*$`) rejected at `parse_trace()` |
| 3 | GLM/OpenAI | medium | Missing `CONTEXT.md` could silently degrade the undefined-term check to "nothing to check" | rejected-with-reason — already fail-strict by construction (a declared term then has only `shared/glossary.md` to resolve against); documented explicitly in `shared/grill-trace-format.md` §4 |
| 4 | GLM/OpenAI | low | Reject vs. upsert on a duplicate `requirement_key` write | rejected-with-reason — idempotent upsert kept, matches P4.1's `write_context_term.py` precedent (a requirement revisited later in the same interview just updates its trace) |
| 5 | GLM/OpenAI | medium | `terms_used` declared-not-scanned is bypassable (empty list defeats the undefined-term STOP) | rejected-with-reason — deliberate, DESIGN.md-mandated honesty-guard limit, not a bug; documented in §3 |
| 6 | GLM/OpenAI | low | Gate blocks completion for projects whose interview predates the gate, with no grandfather path | rejected-with-reason — intentional by design; transitional note added to `step-8-completion.md` |

### Round 2 (revised mini-plan, after `fr_trace_coverage` landed)

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 7 | OpenAI | high | Coverage guards (`grill_trace_coverage`/`fr_trace_coverage`) make the gate enforce six blocking conditions, conflicting with "implement the design's four STOP conditions verbatim" | rejected-with-reason — the four closed-vocabulary STOPs remain exactly four; the coverage guards are separately named/documented (`shared/grill-trace-format.md` §5) as structural presence checks, not part of the closed vocabulary, satisfying rather than conflicting with the AC |
| 8 | OpenAI (high) / GLM (medium) | high/medium | `fr_trace_coverage`'s slug join has no producer-side identity contract: FR-name collisions and orphan traces are both undetected | accepted-with-reason (documented limitation, not built around) — `shared/grill-trace-format.md` §5 "Known limitation"; follow-up filed as triage card `trg-da67adbd` |
| 9 | OpenAI | high | `terms_used` omission still bypasses the undefined-term STOP (same class as round-1 #5) | rejected-with-reason — same honesty-guard rationale as #5; narrowed (not eliminated) by new `glossary_delta_declared` self-consistency check |
| 10 | OpenAI | medium | Step 8 wiring is prose-level (doc/SKILL.md edits), no code-enforced blocking mechanism identified | accepted-with-reason — pattern-consistent with Step 8's pre-existing verification items 1-6 (also LLM-followed, not scripted); `step-8-completion.md` now states "This BLOCKS phase completion — not advisory" explicitly, matching the convention already used for those items |
| 11 | OpenAI | medium | Missing/malformed `CONTEXT.md` fail-open risk | accepted-and-fixed already at round 1 (#3) plus new `glossary_source_available` check for a missing `shared/glossary.md` specifically |
| 12 | OpenAI | medium | `requirement_key` filename safety | accepted-and-fixed already at round 1 (#2) |
| 13 | OpenAI | medium | Honesty-guard test internally inconsistent (mixed "passes" and "still fails" in one test) | accepted-and-fixed — split into two tests, and the passing one now runs the FULL `run_all_checks()` gate against fully-valid data, not three individually-called check functions |
| 14 | GLM | low | Migration stance for in-flight projects (same class as round-1 #6) | already documented |
| 15 | GLM | low | Whether `fr_trace_coverage` is blocking or advisory should be explicit | accepted-and-fixed — `step-8-completion.md` states both `grill_trace_coverage` and `fr_trace_coverage` are part of the same blocking gate item |

**Verdicts:** round 1 GLM approve / OpenAI revise (findings above address the
revise). Round 2 GLM approve / OpenAI revise (findings above address the
revise; #8 accepted as a documented, triage-tracked limitation rather than
built around, matching this sub-iterate's stated scope).

## External-Code-Review-Findings

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | GLM | high | A malformed grill-trace JSON file crashed the CLI with a raw traceback instead of a reported failure | accepted-and-fixed — `run_all_checks()` wraps `read_trace_dir()`, reporting a red `malformed_trace` `CheckResult` instead |
| 2 | GLM | medium | `terms_used`/`glossary_delta` declared-list honesty guard has a residual bypass (a term sharpened in `glossary_delta` but never listed in `terms_used`) | accepted-and-fixed (partial, by design) — new `check_glossary_delta_declared` catches the self-contradictory half; omitting a term from BOTH lists remains possible, documented as a deliberate honesty-guard limit |
| 3 | GLM | high | A missing `dimensions` key was only caught at gate-read time (`check_blank_dimension`), not at producer write time | accepted-and-fixed — `grill_trace_format._validate_dimensions` now rejects a missing key at `parse_trace()`, i.e. at write time too |
| 4 | GLM | low | `slugify()`'s transliteration behavior (apostrophes/diacritics) was undocumented | accepted-and-fixed — documented in `shared/grill-trace-format.md` §1 |
| 5 | GLM | medium | TOCTOU: `write_trace()` read `path.exists()` before acquiring the file lock, so the returned `created`/`updated` status could race a concurrent re-entrant write | accepted-and-fixed — `existed = path.exists()` moved inside the `file_lock` block |
| 6 | OpenAI | high | `check_greenfield_assumed` trusted the payload-declared `surface` field to SKIP the no-`assumed` rule for any non-`"project"` value — a trace could opt itself out just by writing `"surface": "adopt"` | accepted-and-fixed — this gate only ever evaluates `/shipwright-project`'s traces, so a non-`"project"` surface found here is a data-integrity fault; changed SKIP to FAIL |
| 7 | OpenAI | medium | Missing `shared/glossary.md` silently degraded to an empty term set instead of surfacing as an error | accepted-and-fixed — new `check_glossary_source_available` (`grill_trace_glossary.py`), FAIL when the framework's own glossary file is absent (unlike an absent `CONTEXT.md`, never a legitimate state) |
| 8 | OpenAI | medium | Honesty-guard test used `"assumed:idk"` while claiming to prove "low quality but complete passes" — `assumed` is itself a real STOP condition in project surface, not a prose-quality signal, so the test's premise was internally contradictory | accepted-and-fixed — rewritten with `"n/a:n"` instead, and to call `run_all_checks()` end-to-end |
| 9 | OpenAI | low | Stale mini-plan bullet ("no per-FR-row join... a deliberate scope decision") contradicted the shipped `fr_trace_coverage` code | accepted-and-fixed — mini-plan's §2/limitations sections rewritten to describe the revised, shipped decision |
| 10 | GLM | low | `write_grill_trace.py::main()` had a dead/nonsensical conditional left over from an editing pass | accepted-and-fixed — replaced with clean sequential validation |
| 11 | OpenAI | low | A placeholder assertion (`x.__wrapped__ if False else True`) was left in a test file during an earlier editing pass | accepted-and-fixed — replaced with a real, properly named test |

**Verdict:** both reviewers "revise"; every high/medium finding fixed in
code (not documentation-only), low findings fixed or, where a code fix
would be scope creep beyond this sub-iterate's stated ACs (finding #8 in
the plan-review round-2 table), documented and triage-tracked
(`trg-da67adbd`).

## Stage-1 Spec Review (campaign, P4.2.2 round) — REJECT and fix

The campaign orchestrator's `spec-reviewer` HARD-GATE ran against the
sub-iterate spec after the commit above and **REJECTed on AC2**: the spec's
own wording ("A gate script enforces all four STOP conditions... and is
wired into shipwright-project so it actually blocks completion, **not just
advisory**") and the design's stated mechanism
(`2026-07-24-req3-grill-trace-enforcement-DESIGN.md:37-39` — "a required
output section + a finalization verifier... mirror of iterate's... F11
`check_*` verifiers") were not met by what shipped: the only Step 8 wiring
was prose in `step-8-completion.md`/`SKILL.md` instructing the agent to run
`verify_grill_trace_completeness.py` and decide for itself whether to stop.
`run_project_checks()` — the actual code-level dispatcher this repository
already uses to hard-block Step 8 for C1-C5 via
`phase_validators._run_canon_checks` → `validate_phase()` → `update_step()`
— never called into the gate. **This directly contradicts round 2 finding
#10's "accepted-with-reason" disposition above** — that disposition treated
prose-level wiring as pattern-consistent with Step 8's pre-existing,
also-prose items 1-6; the spec-reviewer's judgment is that the AC's plain
"not just advisory" language cannot be satisfied by a mechanism the
project's own review record already called "prose-level... not scripted",
regardless of that precedent. Finding #10's disposition is superseded by
this round, not retracted from the historical record above.

**Fix (this round):** added `check_grill_trace_completeness()` to
`shared/scripts/tools/verifiers/project_checks.py`, delegating to the
already-built `verify_grill_trace_completeness.run_all_checks()` and
returning its `CheckResult` list unchanged (same names/detail/severity) into
`run_project_checks()`'s own flat list — registered alongside C1-C5, in the
same file, the same way. No new severity classification was introduced: the
delegate's own STOP conditions are already ERROR-severity; `_run_canon_checks`
now turns each into a genuine ask-level, `update-step`-blocking issue for
`/shipwright-project`, exactly as it already does for a missing C1/C4/C5
artifact. `step-8-completion.md` and `SKILL.md` item 7 were reworded from
"this blocks... [implicitly, if you follow it]" to state explicitly that the
gate is code-enforced via the same dispatcher, and that running the CLI in
Step 8 surfaces the same gap earlier rather than being the enforcement
itself. `docs/hooks-and-pipeline.md`'s grill-traces artifact-write row was
corrected to name the actual call chain
(`run_project_checks` → `_validate_project` → `update-step`) instead of
implying the Step 8 prose alone was the block.

**Proof (new tests, not narrative):**
`shared/tests/test_verifiers_project.py::test_run_project_checks_detects_grill_trace_greenfield_assumed`
/ `..._blank_dimension` / `..._passes_with_a_clean_grill_trace` prove the
check participates in `run_project_checks()`'s own result list;
`plugins/shipwright-run/tests/test_phase_validators_project.py::test_grill_trace_stop_blocks_validation_same_path_as_c1_c5`
/ `test_clean_grill_trace_does_not_block_validation` call `validate_phase("project", ...)`
directly — the exact function `update-step --step project` calls — proving
a failing grill-trace produces the same ask-level, `valid=False` block the
existing C5/`phase_history` tests in that file already prove for C1-C5, at
the same integration boundary, not a parallel one.
