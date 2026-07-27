# Iterate — plan-phase gates: reviewer contradiction, section dependencies, coverage

- **Run ID:** `iterate-2026-07-27-plan-phase-gates`
- **Date:** 2026-07-27
- **Intent:** CHANGE
- **Complexity:** medium
- **Spec Impact:** MODIFY — `.shipwright/planning/01-adopted/spec.md` FR-01.03
- **Triage:** `trg-88f721be` (high, P1, `kind: improvement`)
- **Evidence:** `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  → FR-01.03 rows 2, 3, 3b, 4, 5

---

## Problem

The FR-01.03 scenario pass produced a per-plugin work unit for
`shipwright-plan`. Three problems, all of the same shape: **the phase promises
a guarantee that nothing can check.**

1. **Two reviewers, one number.** `external_review.py` runs Gemini and OpenAI
   in parallel and preserves both full texts. Everything downstream —
   `mark-review-state.py` → `external_review_state.json` →
   `plan_compliance.check_w5_external_review_marker` — reduces the pair to one
   `status` and one integer `findings_count`. One reviewer approving while the
   other calls the approach fundamentally wrong is therefore indistinguishable
   from an ordinary finding count. Two independent reviewers exist so that
   disagreement gets noticed; averaging it away makes the second reviewer
   worthless.
2. **Section order cannot be checked.** `section-index.md` promises "numbers
   represent execution order", but `SECTION_MANIFEST` is a flat list of
   `NN-slug` names. Dependencies are **not expressible**, so nothing could
   establish the promise, and a section can be scheduled before what it needs.
   `check_section_id_validity` only checks that the numbering is gap-free —
   which says nothing about order being *correct*.
3. **Four claimed gates that are prose.** `SKILL.md` Step 9 lists "Section
   Quality Gate", "FR Coverage Check" and "Dependency Order" as *verification
   gates*, and Step 6 opens with a review-marker gate. None of the four exists
   in code. `check_fr_orphans_in_plan` checks only the *outward* direction
   (a cited FR must exist); nothing checks that every requirement is covered,
   and nothing checks that a section traces back to a requirement at all — so
   a plan can quietly add work nobody asked for.

## Acceptance Criteria

**AC1 — reviewer verdicts are read, not summarised.** Each external reviewer
ends with a single constrained sentinel line, `SHIPWRIGHT_VERDICT: approve |
revise | reject`. The parser accepts it only when **exactly one line** of the
reply *purports* to be a sentinel line (the token opens the line, whatever
follows) **and** that line is the reply's last non-empty line **and** it is
well-formed. Zero such lines, two or more, an unrecognised word, trailing prose
after it, or a truncated reply all yield `unknown`. A sentinel quoted *inside*
prose is not a line and is ignored. A verdict is never inferred from prose,
headings, or finding severities.

**Tolerated on that line:** surrounding markdown emphasis or code ticks
(`**SHIPWRIGHT_VERDICT:** approve`), a leading list marker or blockquote, case
variation, and padding around the colon. This is deliberate, not laxity: models
bold and quote their closing lines routinely, and rejecting those forms would
manufacture the same false `unknown` that the first two versions of this rule
produced. The line must still contain nothing but the sentinel and one
recognised word — decoration cannot smuggle in prose.

The review output carries both verdicts and both provider statuses alongside
the existing full texts.

**AC2 — contradiction is its own outcome.** When one reviewer approves and the
other rejects, that is recorded as a contradiction — a distinct outcome, not a
finding count. The comparison is a pure function of the two verdicts.

**AC3 — anything that stops the two reviewers being comparable is put to the
person.** The marker carries both verdicts, the derived contradiction, and the
operator's resolution. The plan cannot be declared reviewed while any of these
has no recorded resolution:

- the two reviewers **contradict** each other;
- a verdict **could not be read** — an unreadable verdict is not agreement;
- **only one of the two answered.** Two independent reviewers exist so that
  disagreement gets noticed; with one, it could not have been. Proceeding on
  that single review is a decision, not a default;
- the recorded pair is **not the two reviewers that run**, or is incomplete.

All are cleared the same way, with one flag naming the decision. *Neither*
reviewer answering is the one case that asks for no decision — there are no
sides to take — but it still **blocks**: a `completed` marker where no leg
answered is not a review, and the remedy is to re-run it or record the
appropriate `skipped_*` status with a reason.

**The reader derives this from the verdicts rather than trusting the stored
contradiction block** — a marker whose summary disagrees with its own verdicts
must not walk through a gate.

**AC4 — a section can name what it presupposes.** `SECTION_MANIFEST` accepts
`NN-slug: dep-a, dep-b`. A bare `NN-slug` line keeps parsing exactly as today
(no dependencies) — every existing manifest stays valid.

**AC5 — the numbering is checked against the declarations.** A manifest that
places a prerequisite after the section that needs it fails. Every dependency
must be written as a **complete canonical section id** and must be declared in
the same manifest; an unknown id, a self-dependency, a duplicate section id, a
duplicate dependency token, an *interior* empty token (`01-a, , 02-b`), and an
id that does not match the section grammar all fail. A single **trailing**
comma is punctuation, not a missing dependency, and is tolerated. Diagnostics
name the offending manifest line number.

**AC6 — every requirement lands in at least one section.** Linkage is read
from one explicit machine-readable field — a `Requirements:` line in the
section file — never from a prose scan for `FR-NN.NN`. A live FR in the
split's `spec.md` that no section declares fails the gate.

**AC7 — every section traces back to a requirement.** A section whose
`Requirements:` field is absent or empty, or which names only ids that are not
live FRs of its split, fails the gate.

**AC8 — every section states purpose, ≥2 steps, and how it is tested.** The
accepted headings are a defined closed set, and the section-writer prompt plus
the `section-splitting.md` template emit exactly those headings in the same
diff. A section missing any of the three fails, and the failure names the
missing part and the heading it expected.

**AC9 — the in-session review gate is runnable.** `check-plan-gates.py
--gate review` exits non-zero when the review state is not clear to proceed,
so Step 6's "STOP" is a command, not an instruction.

**AC10 — the new gates run at phase-completion.** All four (AC5–AC8) are part
of `run_plan_checks`, so `_validate_plan` blocks `update-step --step plan
--status complete` on them.

**AC11 — a plan written before this change is flagged, not stranded.** A split
whose sections declare no `Requirements:` field at all pre-dates the field;
AC6/AC7 report it as a `WARNING` naming the migration, `strict_exempt` so
`--strict` cannot mass-false-red it. Adoption is decided **per split, from the
presence of the field** — a section that writes `Requirements:` and leaves it
empty has adopted the format and failed it, which is not the same as a plan
that predates it. Once any section adopts, every section in that split is held
to it. AC8's headings follow the same per-split rule.

A **marker** written before the verdict fields is the analogous case, and the
two readers resolve it differently on purpose: `W5` warns (it audits plans of
any age), while the in-session gate blocks (the marker it reads was written
moments ago, so "completed with no verdicts" means Step 5b ran without
`--verdict`, which would make the whole disagreement check opt-out by
omission). The in-session section gates are likewise strict: a plan being
written today complies.

**AC12 — one authoritative reading of review state.** `check-plan-gates.py
--gate review`, `check_w5_external_review_marker`, and the
`setup-planning-session.py` resume gate all decide via one shared function, so
the three cannot drift into three different definitions of "reviewed".

## Non-goals

- Not changing which providers run, or the review prompt's finding taxonomy.
- Not registering the new checks in the compliance Group C adapter
  (`audit_adapters.REQUIRED_SYMBOLS`). That registry is a curated iterate-12
  subset with a pinned count; the plan **phase validator** is the enforcement
  point for the plan phase. Deliberate boundary, recorded here.
- Not touching `check_fr_orphans_in_plan` — the outward direction already
  works; AC6/AC7 add the two missing directions beside it.

## Affected Boundaries

| Boundary | Producer | Consumer |
|---|---|---|
| `SECTION_MANIFEST` block in `plan.md` | `/shipwright-plan` Step 4 (agent) | `plan_manifest.parse_manifest` → `sections.py`, `check-sections.py`, `plan_checks.py`, `setup-planning-session.py` |
| reviewer feedback text | Gemini / OpenAI | `review_verdict.parse_verdict` |
| `external_review.py` stdout JSON | the CLI | plan SKILL Step 5 (agent), iterate Step 4 |
| `external_review_state.json` | `mark-review-state.py` | `plan_compliance` W5, `setup-planning-session` resume gate, `check-plan-gates.py --gate review` |
| section `.md` files | `section-writer` subagent | `plan_section_quality`, `/shipwright-build` |

Round-trip pairs (written then read back by a different component):
`SECTION_MANIFEST` and `external_review_state.json`.

## Mini-Plan

**Chosen approach — one shared parser per artifact, thin wrappers at each call
site.**

1. `shared/scripts/lib/plan_manifest.py` — the single `SECTION_MANIFEST`
   parser: names, per-section dependency lists, and the order rule. Replaces
   the *two* existing private parsers (`plugins/shipwright-plan/scripts/lib/
   sections.py` and `plan_checks._parse_section_manifest`), which are already
   drifting copies kept in sync by comment only.
2. `shared/scripts/lib/review_verdict.py` — `parse_verdict(text)` and
   `compare_verdicts(a, b)`. Pure; no I/O, no provider knowledge.
3. `shared/scripts/lib/plan_section_quality.py` — section-file structure
   parsing plus FR linkage in both directions.
4. `shared/scripts/tools/verifiers/plan_gate_checks.py` — the four new
   `CheckResult` wrappers, appended to `run_plan_checks`. A separate module
   because `plan_checks.py` sits at its bloat baseline (315).
5. `plugins/shipwright-plan/scripts/checks/check-plan-gates.py` — the
   in-session CLI (`--gate review|sections|all`), so the SKILL can *run* the
   gates it claims.
6. Prompts + skill prose + docs + the FR-01.03 spec row.

**Alternative considered — derive the verdict from finding severities**
(e.g. "any `high` finding ⇒ reject") instead of asking the reviewer for one.
Rejected: it is deterministic but wrong. An approving reviewer routinely lists
a high-severity finding as a refinement, and a rejecting reviewer may list none
at all because the objection is structural. Severity measures individual
findings; the contradiction we care about is about the *approach as a whole*.
Deriving it would manufacture disagreement where there is none and miss the
case the triage names. Asking for one explicit line costs nothing and is the
only honest oracle.

**Alternative considered — a third LLM adjudicates the disagreement.**
Rejected: not deterministic, and it re-hides the disagreement behind another
summary. The decision is the operator's; the machine's job is to make sure
they see it.

## Design decisions

**Contradiction rule.** Rank `approve=0`, `revise=1`, `reject=2`. Contradiction
iff both verdicts are known and the ranks differ by ≥2 — i.e. approve vs
reject. `approve` vs `revise` and `revise` vs `reject` are differences of
degree, which the finding list already carries. If either verdict is `unknown`
the pair is recorded `comparable: false` — visible, not silently green.

**Dependency syntax.** `NN-slug: dep-a, dep-b`. `:` cannot occur in a slug
(`[a-z0-9-]`), so a bare line stays unambiguous and every manifest written
before today keeps parsing.

**Order rule.** Each declared dependency must appear *earlier* in the manifest
than the section naming it. This subsumes cycle detection: a cycle cannot
satisfy "every dependency is earlier".

**Verdict sentinel.** `SHIPWRIGHT_VERDICT: <word>` — a distinctive token that
does not occur in ordinary review prose, required to appear exactly once.
Reviewer output is untrusted input: a model that quotes the instruction back,
or argues with itself, produces two occurrences and therefore `unknown`
(which blocks per AC3) rather than a silently-picked wrong verdict.

**Requirement linkage field.** `Requirements: FR-01.03, FR-01.16` on its own
line in the section file. One field, parsed at one place, used for both
coverage directions and available to `/shipwright-build`. Parsing prose was
rejected: an FR named in an example, a rationale, or a retired-history note
would count as coverage, and authors would learn to sprinkle ids to satisfy
the gate.

## External Review — findings and dispositions

Both reviewers returned `success` via OpenRouter and both endorsed the
direction. Fourteen findings; dispositions below (each also written to
`decision_log.md`).

| # | Reviewer | Finding | Disposition |
|---|---|---|---|
| 1 | both | verdict must come from a structured sentinel, not prose matching (prompt-injection / self-quoting risk) | **accepted** → AC1 rewritten: `SHIPWRIGHT_VERDICT:`, exactly-once |
| 2 | both | an `unknown` verdict would pass the gate because it is not technically a contradiction | **accepted** — the sharpest finding. AC3 now blocks on `comparable: false` too |
| 3 | openai | FR linkage from a Markdown scan is noisy and gameable | **accepted** → AC6/AC7 read one explicit `Requirements:` field |
| 4 | both | section-quality headings undefined; template must change before enforcement | **accepted** → AC8 names a closed heading set; prompt + template updated in this diff |
| 5 | openai | stricter gates strand plans written before the change | **accepted with a different remedy.** No format version field: adoption is inferred per split from whether the field is used at all, degrading to `strict_exempt` WARNING otherwise (AC11). A version field would need writing, migrating and honouring — the inference needs none and cannot go stale |
| 6 | openai | `--gate review`, W5 and the resume gate will drift into three definitions of "reviewed" | **accepted** → AC12, one shared evaluator |
| 7 | openai | dependencies must be canonical ids; reject duplicates/empties; report line numbers | **accepted** → AC5 |
| 8 | gemini | whitespace tolerance; validate slugs strictly (no traversal payloads) | **accepted** → parser strips tokens and validates every id against the section grammar |
| 9 | gemini | prompt must forbid depending on things outside this plan | **accepted** → `section-index.md` + section-writer prompt |
| 10 | gemini | keep a backward-compatible accessor for the parser's consumers | **accepted** → `SectionManifestResult.sections` stays `list[str]`; dependencies are an added field |
| 11 | openai | old markers lack `verdicts`; define the compatibility branch | **accepted** → absent `verdicts` = pre-format marker, WARNING not FAIL (AC11); `marker_schema: 2` on new markers |
| 12 | openai | record per-provider status so an errored leg is not read as a missing reviewer | **accepted** — cheap and closes a real ambiguity |
| 13 | openai | add a review run-id + per-provider timestamps; reject mixed-run pairs | **declined.** The marker is written from one `external_review.py` invocation's output, so a mixed-run pair has no code path today. Adding run identity would be speculative machinery for a hazard that does not exist yet; #12 covers the ambiguity that does. Revisit if the marker ever gains an incremental-update path |
| 14 | openai | the mini-plan names no tests despite changing a completion gate | **accepted** — that is the Test Completeness Ledger (Step 7.5), mandatory at medium. The enumerated list is folded into it |

## Code Review — findings and dispositions

Two rounds of the external code-review cascade on the diff. Round 1 returned
`reject` (5 findings), round 2 `revise` (5 findings). Both rounds lost the
Gemini leg to the 4096-token output cap on a ~4,900-line diff — recorded as a
degraded condition, not a passing review.

**Round 1 (verdict: openai `reject`, gemini `unknown` — truncated)**

| # | Finding | Disposition |
|---|---|---|
| 1 | `evaluate_review_state` trusts the stored `contradiction` block instead of deriving it; a marker saying approve/reject with `contradiction: null` passes every gate | **accepted — the sharpest finding.** Derived at write time *and* recomputed at read time. "Derived, never asserted" was claimed but only half-applied |
| 2 | a `completed` marker with no verdicts silently passes, so omitting `--verdict` bypasses the whole check | **accepted** → tri-state `STATE_LEGACY`; `W5` warns (audits any age), the in-session gate blocks (AC11) |
| 3 | the verdict sentinel is matched anywhere in the reply | **accepted** → sentinel *line*, exactly once, and it must be last |
| 4 | heading adoption decided per section, not per split as AC11 says | **accepted** → per split |
| 5 | AC5 says an empty dependency token fails, but a trailing comma is tolerated | **accepted as a spec correction.** The behaviour is right — a trailing comma is punctuation, not a missing dependency — so AC5 now says so instead of contradicting the code |

**Round 2 (verdict: openai `revise`, gemini `unknown` — truncated again)**

| # | Finding | Disposition |
|---|---|---|
| 1 | dropping exactly-once lets a self-contradictory reviewer through | **accepted, and it produced a better rule than either side proposed:** exactly one sentinel *line* AND it is last. Satisfies the ambiguity concern, while the quoted-mid-prose case that broke the token count stays readable |
| 2 | `unavailable` should require resolution too — AC3 has no degraded-provider carve-out | **accepted.** One reviewer approving is not what two reviewers guarantee, and the remedy is one flag. Exception kept for *neither* answering: nothing ran, which the degraded gate already fails |
| 3 | `check-sections.py` never checks `is_valid`, so a duplicate id passes | **declined — not reproducible.** The script does check it; run against `01-a\n01-a` it prints `"success": false` with `line 2: duplicate section id` and exits 1 |
| 4 | adoption keys off parsed ids, so an empty `Requirements:` field reads as legacy | **accepted** → `declares_requirements` now tracks field *presence* |
| 5 | any reviewer name is accepted, so `foo`/`bar` verdicts satisfy the gate | **accepted** → names validated against `REVIEWERS`, and a repeated reviewer is rejected rather than overwritten |

**Round 3 — fresh review on the pushed head**, after CI's Tier-3 gate failed
closed on a truncated diff (~5,000 lines; the documented condition). The diff
was split into source / tests / docs so nothing truncated, and each chunk
reviewed against the current head.

| # | Finding | Disposition |
|---|---|---|
| 1 | a `completed` marker with BOTH reviewers `unavailable` returns `ok` — `--verdict gemini=unavailable --verdict openai=unavailable` clears every gate with nobody having reviewed | **accepted, and the sharpest finding of the three rounds.** The "neither answered needs no resolution" exception was right about the *prompt* and wrong about the *state*. `evaluate_review_state` now blocks it outright, pointing at re-run or a justified `skipped_*`; `requires_resolution` stays false, because there are no sides to take |
| 2 | a malformed sentinel line before a valid one still reads the valid one | **accepted** → *purported* sentinel lines are counted before any is validated, so a reviewer that tried twice is ambiguous |
| 3 | the parser tolerates markdown-decorated sentinels, which AC1's literal grammar does not license | **declined on the behaviour, accepted on the mismatch.** Models bold and quote closing lines routinely; rejecting those forms manufactures exactly the false `unknown` the first two rule versions produced. AC1 now states the tolerated decoration explicitly, so spec and code agree |
| 4 | the wiring tests prove only that dependency-order failure propagates — the other three gates could be miswired or silently green | **accepted.** One seeded failure per gate now runs through the real `run_plan_checks`, plus a clean-plan complement so a gate that fails unconditionally cannot satisfy them all |
| 5 | `check-sections.py` never checks `is_valid`, so a duplicate id passes | **declined again — not reproducible, second time raised.** Both scenarios were run: duplicate `01-a` with its file present, and an invalid dependency token. Each prints `"success": false` with the line-numbered parse error and exits 1. The guard sits above the hunk the finding cites |
| 6 | the tests chunk contains no production implementation, so it cannot implement AC1–AC12 | **declined — an artifact of the chunking.** The production code was in the source chunk, reviewed separately (it produced findings 1–2 above). Worth recording as a real limitation of the split-diff workaround: each reviewer sees less than the whole change, so a cross-chunk claim from one of them is not evidence |

## Confidence Calibration

- **Boundaries touched:** see Affected Boundaries above — `SECTION_MANIFEST`,
  reviewer feedback text, `external_review.py` stdout,
  `external_review_state.json`, section `.md` files.

- **Empirical probes run** (producer → file on disk → a *different* consumer,
  each run for real, not reasoned about):

  | Probe | Finding |
  |---|---|
  | Write a `plan.md` with dependency declarations; read it back with the shared parser | `03-api: 01-auth, 02-db` → `{'03-api': ['01-auth','02-db']}`, no order errors |
  | Read the same file with the **plugin's** parser, in a separate process | identical sections and dependencies. Separate process on purpose: `shared/scripts/lib` and `plugins/shipwright-plan/scripts/lib` both import as `lib` and collide in one interpreter (ADR-044), which is how they run in production |
  | `mark-review-state.py` writes a contradicting marker; read it back with all three consumers | `evaluate_review_state` → `block`; `W5` → `FAIL`; `check-plan-gates --gate review` → exit 1. Three readers, one answer |
  | Feed `external_review.py`'s own `verdicts` block into the CLI and read the marker back | gate blocks; the stored contradiction block is byte-identical to the live one |
  | **Run the verdict parser against the two real reviews this iterate received** | The decisive probe. Round 1: exactly-once-token read a genuine `reject` as `unknown` because the reviewer quoted the sentinel in a finding — the rule was wrong and only running it showed that. It now reads `reject`. The other leg was truncated by the 4096-token cap and reads `unknown`, which is correct: a truncated review gave no verdict |
  | `scan_test_hygiene.py --diff` | no findings |
  | `anti_ratchet_check.py` | exit 0. `external_review.py` 430→414, `plan_checks.py` 315→297 — both shrank below their baselines rather than needing an exception |
  | Duplicate-id manifest through `check-sections.py` (to test a review finding) | `success: false`, exit 1 — the finding claiming it passes was **not reproducible** |

- **Test Completeness Ledger:** every behaviour this diff introduces or
  changes, each `tested` or `untestable` with a closed-vocabulary
  `reason_code`. **0 testable-but-untested.**

  | # | Behaviour | Status | Evidence |
  |---|---|---|---|
  | 1 | manifest parses bare `NN-slug` lines exactly as before | tested | `test_plan_manifest.py::test_bare_manifest_still_parses` |
  | 2 | manifest parses `NN-slug: dep, dep` | tested | `::test_dependencies_are_parsed` |
  | 3 | whitespace / trailing comma tolerated | tested | `::test_whitespace_and_trailing_comma_tolerated` (3 cases) |
  | 4 | interior empty, duplicate, self, unknown, non-grammar dependency all fail | tested | 5 tests in `test_plan_manifest.py` |
  | 5 | duplicate section id fails | tested | `::test_duplicate_section_id_rejected` + CLI probe |
  | 6 | prerequisite numbered after its user fails | tested | `::test_prerequisite_after_its_user_fails` + CLI + verifier |
  | 7 | a cycle cannot satisfy the order rule | tested | `::test_a_cycle_cannot_satisfy_the_order_rule` |
  | 8 | diagnostics name the manifest line | tested | `::test_errors_name_the_manifest_line`, `::test_order_errors_name_their_line` |
  | 9 | `check-sections.py` reports dependencies + order errors | tested | `test_check_sections.py` (3 new tests) |
  | 10 | verdict read from one sentinel line, exactly once, and last | tested | 11 tests in `test_review_verdict.py` |
  | 11 | verdict never inferred from prose / injection cannot outrank | tested | `::test_verdict_is_never_inferred_from_prose`, `::test_an_injected_verdict_cannot_outrank_the_real_one` |
  | 12 | truncated reply → `unknown` | tested | `::test_a_truncated_reply_is_unknown` (from the real truncated review) |
  | 13 | provider that errored → `unavailable`, not `unknown` | tested | `::test_non_success_is_unavailable_not_unknown` |
  | 14 | approve-vs-reject is a contradiction; degrees are not | tested | `::test_approve_versus_reject_is_a_contradiction`, `::test_differences_of_degree_are_not_contradictions` (5 cases) |
  | 15 | comparison is symmetric | tested | `::test_comparison_is_symmetric` (25 pairs) |
  | 16 | one silent reviewer requires a decision; neither answering does not | tested | `::test_only_one_reviewer_answering_must_be_decided_not_defaulted`, `::test_neither_reviewer_answering_is_left_to_the_degraded_gate` |
  | 17 | empty-diff short-circuit stays inert and keeps the block's shape | tested | `::test_the_empty_diff_short_circuit_is_inert` |
  | 18 | marker carries verdicts + derived contradiction + schema | tested | `test_review_state_gate.py::test_verdicts_round_trip_through_the_marker` |
  | 19 | contradiction is recomputed on read, not trusted | tested | `::test_the_disagreement_is_recomputed_not_trusted`, `::test_a_stored_contradiction_cannot_invent_one_either` |
  | 20 | unknown / duplicate / malformed reviewer args rejected | tested | 4 tests in `test_review_state_gate.py` |
  | 21 | a completed review with no verdicts is `legacy`, not `ok` | tested | `::test_a_completed_review_with_no_verdicts_is_legacy_not_ok` |
  | 22 | W5 warns on that legacy state; in-session gate blocks | tested | `test_verifiers_plan_w5.py::test_a_marker_predating_verdicts_warns_rather_than_failing`, `test_check_plan_gates.py::test_a_completed_review_that_recorded_no_verdicts_blocks` |
  | 23 | skip branches unchanged (no verdicts required) | tested | `test_verifiers_plan_w5.py::test_skip_handling_is_unchanged` (4 cases) + `::test_a_skip_needs_no_verdicts` |
  | 24 | resolution clears the block; whitespace does not | tested | `::test_recorded_resolution_clears_the_block`, `::test_whitespace_is_not_a_resolution` |
  | 25 | section shape parsed (purpose / ≥2 steps / tests), incl. heading synonyms | tested | 10 tests in `test_plan_section_quality.py` |
  | 26 | linkage read only from `Requirements:`, never from prose | tested | `::test_prose_mentioning_an_fr_is_not_a_declaration` |
  | 27 | an empty `Requirements:` field adopts the format and fails it | tested | `::test_an_empty_requirements_field_counts_as_adopting_but_names_nothing`, `::test_an_empty_field_beside_an_absent_one_still_adopts_the_split` |
  | 28 | both coverage directions | tested | 8 tests in `test_plan_section_quality.py` + 4 in `test_verifiers_plan_gates.py` |
  | 29 | legacy split warns, `strict_exempt`, names the migration | tested | `test_verifiers_plan_gates.py::test_a_split_that_never_adopted_the_field_warns` (2 checks) |
  | 30 | one adopting section holds the whole split (both linkage and headings) | tested | `::test_one_adopting_section_holds_the_whole_split_to_the_format`, `::test_heading_adoption_is_decided_per_split_not_per_section` |
  | 31 | all four gates registered in `run_plan_checks`, and block completion | tested | `test_verifiers_plan_gates_wiring.py` (2 tests) |
  | 32 | in-session gate is strict where the verifier is lenient | tested | `test_check_plan_gates.py::test_an_ill_formed_section_fails_even_in_a_new_plan` |
  | 33 | `--gate` selects only what was asked for | tested | `::test_gate_selection_runs_only_what_was_asked_for` |
  | 34 | reviewer prompts emit the sentinel instruction | tested | `test_prompts.py` (existing) + the two live review runs, which both received it |
  | 35 | the fallback (no prompt dir) carries the same verdict instruction | untestable → `covered-by-existing-test` | `default_review_prompts` is exercised through `test_external_review_cli.py`'s prompt-absent path; the instruction is a constant appended to it, with no branch of its own |
  | 36 | a real provider emits a parseable sentinel | untestable → `requires-external-nondeterministic-service` | needs a live LLM. Probed twice anyway against real OpenRouter responses (see probes); the parser is pinned deterministically by #10–#12 |

- **Confidence-pattern check.**
  *Asymptote (depth):* the verdict parser was rewritten **twice**, each time
  because a real review disproved the rule then in place — token-count →
  final-line → exactly-one-sentinel-line-and-last. Depth here came from
  running the thing on live data, not from thinking harder about it.
  *Coverage (breadth):* every one of AC1–AC12 has at least one test that fails
  if the behaviour regresses; the two `untestable` rows are the LLM boundary
  and one constant with no branch.
  *Integration composition:* `cross_component` did **not** fire — the diff
  touches no hook, phase-validator entry point (`verify_phase` /
  `get_phase_context`), merge/churn resolver, or campaign machinery. The
  compositions that do matter here are covered by the round-trip probes above
  and by `test_verifiers_plan_gates_wiring.py`, which runs the real
  `run_plan_checks` against a seeded project rather than the checks alone.

- **Degraded conditions**
  - `touches_auth` fired from message prose (the classifier keyword-matches
    the message, not the diff). `risk_detectors.py` is diff-authoritative and
    no auth path is touched — recorded as a known false positive.
  - Both external code-review rounds lost the **Gemini** leg to the
    4096-token output cap on a ~4,900-line diff. Not a passing review: it is
    recorded as `unknown`, which is exactly what the new mechanism is for.
    The OpenAI leg completed both times and drove the fixes.

## Rollout / blast radius

This repo was adopted, not planned: there is **no `plan.md` under
`.shipwright/planning/`**. Every new check therefore returns the existing
"nothing to verify" vacuous pass here, and all behaviour is exercised by
synthetic fixtures. The change lands for target projects that run
`/shipwright-plan`; it cannot break this repo's own pipeline state.
