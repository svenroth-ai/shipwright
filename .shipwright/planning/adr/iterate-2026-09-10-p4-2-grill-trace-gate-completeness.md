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

## Stage-2 Code Review (campaign, P4.2 round) — one HIGH finding, fixed

The campaign orchestrator's Stage-2 `code-reviewer` approved with one HIGH
finding: `write_grill_trace.py::main()` (lines 84-119) and
`_write_grill_trace_cli.py`'s `build_arg_parser`/`load_payload_file` had no
direct/in-process test coverage — `test_write_grill_trace.py` exercises
`write_trace()` directly but reaches `main()` and the CLI helpers only via
`subprocess.run(...)`, a separate Python process this repo's coverage
instrumentation never observes (no `COVERAGE_PROCESS_START` hook). Identical
gap class to the one P4.1 hit and fixed for `write_context_term.py`.

**Fix:** added `shared/tests/test_write_grill_trace_direct.py` (in-process
`main()` coverage — success path, `--planning-dir` override, `PayloadError`
from a missing `--payload-file`, missing `--project-root`, `GrillTraceError`
from a malformed record, `LockTimeout`) and
`shared/tests/test_write_grill_trace_cli_direct.py` (in-process
`build_arg_parser`/`load_payload_file` coverage — defaults, every flag,
missing/invalid/non-object/non-dict-scalar payload files), mirroring P4.1's
`test_write_context_term_direct.py` / `test_write_context_term_cli_direct.py`
precedent exactly. Result: `write_grill_trace.py` diff coverage 82%→97.9%
(only the `if __name__ == "__main__":` guard remains uncovered, same as the
P4.1 precedent), `_write_grill_trace_cli.py` at 100%; full-diff diff-coverage
gate (`origin/main`→HEAD) now measures 91%, above the 80% CI gate.

## Stage-3 Doubt Review (campaign, P4.2 round) — 2 real findings, fixed

The campaign orchestrator's fresh-context, adversarial `doubt-reviewer` ran
against the finalized sub-iterate (PR #705) and reported three findings.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | high | `run_all_checks()`'s own stated contract ("a malformed record must report as a red `CheckResult`... never crash the CLI") was met for `read_trace_dir()` but not for `collect_known_terms()` — `context_md_format.read_terms()` raises `ValueError` on a duplicate `## heading`, a state `interview-protocol.md` explicitly sanctions reaching via a post-interview hand-edit of `Relationships`/`Flagged ambiguities`, and the call was unguarded, uncaught in both `run_all_checks()` and the standalone CLI's `main()` | accepted-and-fixed — wrapped in `try`/`except (GrillTraceError, OSError, ValueError)`, mirroring the existing `read_trace_dir()` guard, reporting a new red `malformed_context` `CheckResult` instead of propagating. Fixed at the root layer even though `verifiers/project_checks.py`'s outer `except Exception` already protected the code-level `update-step` path — the standalone CLI convenience invocation (`step-8-completion.md`'s first check) was still exposed |
| 2 | low/medium | `write_trace()` does a full wholesale overwrite of the record on every call (no merge, unlike `write_context_term.py`'s documented `_Avoid_`-preserving upsert referenced in the same doc) — `interview-protocol.md`'s "safe to re-run if a requirement is revisited" wording did not carry the "resend the full record" caveat, inviting the same false expectation the `CONTEXT.md` producer's actual merging behavior would create | accepted-and-fixed — one clarifying sentence added to `interview-protocol.md`'s grill-trace section, explicit about the asymmetry with the `CONTEXT.md` producer directly above it |
| 3 | — | FR-Name/`requirement_key` slug-join identity gap | no action — already documented as a known, accepted limitation in `shared/grill-trace-format.md` §1/§5 with triage card `trg-da67adbd` already scoped |

**Proof (new tests, not narrative):**
`shared/tests/test_verify_grill_trace_completeness_integration.py::test_run_all_checks_reports_a_malformed_context_md_instead_of_crashing`
confirmed red (raised `ValueError`, uncaught) against the pre-fix code before
the fix landed, green after; `..._integration.py::test_cli_exits_non_zero_cleanly_on_a_malformed_context_md_instead_of_a_traceback`
proves the standalone `uv run verify_grill_trace_completeness.py` invocation
exits 1 cleanly (`"Traceback" not in stderr`) instead of printing a raw
traceback.

## Round 4 — PR #705 Tier-3 automated review (`openai/gpt-5.6-luna`) — fix

The required Tier-3 PR reviewer posted a fresh BLOCK verdict on the
finalized commit, with one blocking finding and one Comments-level item.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | high (blocking) | `check_fr_trace_coverage()`'s failure branch returned a `CheckResult` with no explicit `severity`, so it defaulted to `Severity.ERROR` — the same hard-blocking severity as the four closed-vocabulary STOPs, even though the module's own docstring says it is not one of them. Because the `Name`-cell-slug ↔ `requirement_key` join (already documented as a known limitation, §5 "Known limitation", `trg-da67adbd`) has no stable identity contract, a rename, a punctuation/Unicode difference, or a slug collision can produce a false "missing coverage" — which, at ERROR severity, hard-blocks Step 8 for a project that did the elicitation work correctly. | accepted-and-fixed — `check_fr_trace_coverage()`'s failure `CheckResult` now sets `severity=Severity.WARNING.value` explicitly. Reviewer offered two fixes: a real producer-side identity contract (bigger, out of scope) vs. removing the heuristic from the blocking path until that contract exists (pragmatic). Took the pragmatic one — the check keeps running and stays visible (still catches a genuinely skipped/partial interview), it just no longer hard-blocks on its own. `grill_trace_coverage` (structural presence, not a fragile cross-artifact join) and the four real STOPs are unchanged — still ERROR. |
| 2 | low (Comments) | `verify_grill_trace_completeness.py`'s standalone CLI had subprocess-level coverage for the malformed-`CONTEXT.md` crash-avoidance path only (`test_cli_exits_non_zero_cleanly_on_a_malformed_context_md_instead_of_a_traceback`), not for the documented ordinary exit-code contract itself ("Exit code 0 = all green... Exit code 1 = one or more hard failures") | accepted-and-fixed — new `test_cli_exit_code_contract_red_tree_exits_1_green_tree_exits_0` (a red tree via `subprocess.run` on the real CLI, and a green tree, same fixture shapes as the existing `run_all_checks`-level tests) |

**"Sensitive skill documents... maintainer must manually confirm before
merge" bullet:** re-checked against the existing test suite rather than
building a new integration test. The full documented producer-to-Step-8
flow is already proven end-to-end across two existing test files together:
`shared/tests/test_write_grill_trace.py` / `test_write_grill_trace_direct.py`
prove `write_grill_trace.py`'s `write_trace()` writes exactly the JSON
shape `GrillTrace`/`parse_trace()` reads (the producer's own contract);
`plugins/shipwright-run/tests/test_phase_validators_project.py::test_grill_trace_stop_blocks_validation_same_path_as_c1_c5`
/ `test_clean_grill_trace_does_not_block_validation` feed that same shape
into `validate_phase("project", ...)` — the exact function `update-step
--step project` calls — and prove it genuinely blocks/passes at the real
Step-8 boundary, not a parallel mechanism. No new test added for this
bullet; the concern resolves once the severity fix above lands, consistent
with this campaign's P4.1 precedent.

**Fix commit:** severity downgrade in `shared/scripts/tools/grill_trace_fr_coverage.py`;
new tests in `shared/tests/test_grill_trace_fr_coverage.py`,
`shared/tests/test_verify_grill_trace_completeness_integration.py`, and
`plugins/shipwright-run/tests/test_phase_validators_project.py`; doc update
in `shared/grill-trace-format.md` §5.

## Round 5 — PR #705 Tier-3 review, second pass — doc-drift fix (P4.2, this round)

The required Tier-3 PR reviewer posted another fresh BLOCK verdict. This time
the finding was purely prose: Round 4's severity fix
(`check_fr_trace_coverage()` → `Severity.WARNING`) was correct and left
untouched, but `plugins/shipwright-project/skills/project/references/step-8-completion.md`'s
own item-7 prose was never updated to match — it still described a
non-zero exit (including the `fr_trace_coverage` case) as uniformly
blocking ("**This BLOCKS phase completion... not advisory**", "Do not
attempt to mark the project phase complete while this gate is red"),
contradicting the code it describes.

**Fix (documentation only, no severity/logic change):** reworded
`step-8-completion.md` item 7 to split the gate's checks into two
explicit severity buckets — **ERROR** (`grill_trace_coverage`, the four
closed-vocabulary STOPs, `glossary_source_available`,
`glossary_delta_declared`, `malformed_trace`, `malformed_context`; these
genuinely block `update-step`) and **WARNING** (`fr_trace_coverage` alone;
visible in every report, routed to an `inform`-level note, does not block).
Checked `SKILL.md` (lines ~225-239, the same sensitive-path bundle the
reviewer cited): it never names `fr_trace_coverage` at all and its
blocking-conditions list only enumerates the four STOPs plus
`grill_trace_coverage`, so no stale wording was present there — no edit
needed. Verified `shared/grill-trace-format.md` §5 (updated in Round 4)
is already accurate and consistent with the corrected `step-8-completion.md`
wording — no duplicate edit made. No test asserts on this doc's prose (only
`test_skill_references_link.py`, which checks the reference link resolves,
not its content) — none added for a pure prose fix, per the sub-iterate's
own instruction.

**Verification:** `uvx ruff@0.15.15 check .` clean; `shared/tests` (10329
passed, 32 skipped, 0 failed), `plugins/shipwright-project/tests` (64
passed), `plugins/shipwright-run/tests` (564 passed) all green; F11
(`verify_iterate_finalization.py`) and `scripts/verify_local.py` run before
push.
