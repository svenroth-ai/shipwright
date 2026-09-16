# Judgement-line drift tests close the 19/25 discrepancy, no gate built

## Context

Campaign `req3-06-enforcement-mono` sub-iterate `e6`'s job: every
`prompt-only (judgement)` row in the AC-evidence ledger gets a drift test
on its instruction text, and NOTHING ELSE — campaign decision D7 forbids
any content-judging gate here (naive LLM-flag rate 98%, purpose-built
precision 0.52-0.66, ignored within weeks). The campaign card's launch
count (2026-09-06) named 19 judgement lines; `e1`-`e5` and two external
P4.2/P4.4 iterates split several mechanisable rows into new judgement
halves since then, per D7's own abort condition (no oracle → downgrade,
never a weaker gate).

## Investigation

Re-measured the live ledger with `measure_ac_evidence_ledger.py`: 31
backtick occurrences, of which 25 are genuine per-criterion table rows (6
are legend/prose/historical-table/sibling-pointer, not criteria). Checked
each of the 25 against the actual test suite (not the ledger's own
evidence-cell prose) before writing anything: 16 already had a real,
passing test (10 previously cited correctly, 6 had the test but no
citation on their own row); 1 (FR-01.02 #4b) was not a judgement line at
all — `check_blank_dimension` already enforces it, confirmed via
`shipwright_ac_coverage_baseline.json`'s bound/unbound list, not
inference; 8 had no test anywhere.

## Decision

Wrote exactly one new drift test per genuinely-untested row (8), each
asserting the governing instruction's literal, whitespace-normalized
sentence — no LLM, no scorer, no heuristic. Added the 6 missing citations
and corrected FR-01.02 #4b's stale status tag to `enforced, tested`,
citing the pre-existing mechanism (no new check built). Added a 9th new
test after external code review (both providers) correctly found the
first FR-01.16 #1 citation (a heading-presence pin) insufficient — it now
pins the actual `## 2`/`## 3` rule sentences, not just their headings.

## Consequences

25/25 live judgement rows now carry a real drift test; zero gates were
built anywhere. A future prose edit to any of the 9 governing docs fails
the matching test — a deliberate signal to update the pinned text, not a
bug. The ledger's own count is honest again (25, not the stale 19) and
records *why* it moved, so the next re-measurement does not re-litigate
the discrepancy.

## Rationale

D7's own abort condition is explicit: no deterministic oracle exists for
reading-comprehension judgements ("is this sentence still the same
instruction"), so the only honest, non-gate enforcement is a drift test —
literally what the spec calls "the entire deliverable." Citing existing
coverage rather than duplicating it keeps the ledger truthful without
inflating the test suite with redundant pins.

## Rejected alternatives

- Trusting the campaign card's "19" without re-measuring — spec explicitly
  forbade this ("verify... rather than trusting the number blindly").
- Leaving FR-01.02 #4b tagged judgement despite an existing enforced
  mechanism — would misreport a real guarantee as unenforced.
- A shared normalize-and-strip-markdown helper to make pins
  formatting-agnostic (external review, GLM, low severity) — rejected as
  unneeded cleverness for a trivial-test class; every sibling drift test
  in this codebase already pins headings/bold markers the same way, and
  each of the 9 new tests also pins the underlying prose sentence
  separately, so a cosmetic-only heading change does not solely trip the
  test in practice.

## External Plan Review Findings

Mini-plan reviewed via `external_review.py --mode iterate` before commit.
GLM: approve. OpenAI: revise (verdicts one step apart, no contradiction
requiring escalation per the tool's own comparability check).

| # | Provider | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | GLM | medium | Re-run the measurement/baseline after the FR-01.02 #4b status flip and confirm only intended diffs. | accepted-and-fixed — re-ran `measure_ac_evidence_ledger.py` after every edit (264 marks, stable); the AC-coverage baseline (REQ3.04's own artifact) was read-only, never regenerated — out of this campaign's ownership per `campaign.md`. |
| 2 | GLM | low | Drift-test failures on legitimate copy edits should be documented as a signal, not a bug, or a future maintainer deletes the test. | accepted-and-fixed — added a one-sentence note to each of the 4 new plugin test files' module docstrings. |
| 3 | GLM | low | The 6-row exclusion taxonomy (why 31 backticks ≠ 25 rows) should live in the ledger, not only the mini-plan, or the next re-measure re-litigates it. | accepted-and-fixed — the ledger's own `Re-measured 2026-09-16` paragraph states the taxonomy explicitly. |
| 4 | GLM | low | Confirm the `covers` marker is already registered in build/deploy/changelog before adding it only to preview. | accepted — verified via `grep -A3 "^markers"` across all touched plugins' `pyproject.toml` before editing; only `shipwright-preview` was missing it (fixed). Documented here as the verification record OpenAI's own finding #4 below also asked for. |
| 5 | GLM | low | Four new files for 8 assertions is slightly duplicative; consider one shared helper. | rejected-with-reason — each file sources a different plugin's own doc; co-locating by plugin (not by helper) matches the established per-plugin judgement-drift-test precedent (`shipwright-plan`, `shipwright-security`). A shared assertion helper would be premature abstraction for a 1-line `assert x in normalized` body. |
| 6 | OpenAI | high | Redefining the work unit from 19 to 25 without an explicit scope amendment risks ambiguous acceptance. | rejected-with-reason — the sub-iterate spec itself pre-authorizes exactly this: "if you find a different count, stop and treat it as a real finding... write tests for however many you actually find and document the discrepancy in your ADR." This is not a silent redefinition; it is the spec's own explicit instruction, executed and documented (this ADR, the ledger paragraph, the result.json). |
| 7 | OpenAI | medium | Provide a concise 25-row evidence matrix (source, instruction, test, command) and confirm the pre-existing 16 tests actually run and pin the CURRENT text. | accepted-and-fixed (partial) — the ledger's per-row citations ARE the matrix, one row at a time; re-ran the full `shared/tests` suite (10986 passed) and every touched plugin's suite locally. Did not additionally build a centralized matrix file — would be a second, redundant source of truth for what the ledger rows already state. |
| 8 | OpenAI | medium | "Whitespace-normalized form" is underspecified; broad normalization could mask a meaningful edit. | accepted-and-fixed — normalization is `" ".join(text.split())` only (collapses whitespace/line-wraps, never strips punctuation or reorders words) uniformly across all 9 new assertions; the literal expected sentence stays inline in every test for a reviewer to see exactly what is protected. |
| 9 | OpenAI | low | New plugin-specific test files may not be collected by CI if plugin pytest configs differ. | accepted — ran each touched plugin's full suite locally (`shipwright-build` 151 passed, `shipwright-deploy` 145 passed, `shipwright-preview` 12 passed, `shipwright-changelog` 94 passed) plus `shared/tests` (10986 passed); all four new files collected and ran under their own plugin's existing pytest config with no changes needed beyond the one marker registration (finding 4). |
| 10 | OpenAI | low | The FR-01.02 #4b ledger correction mixes historical cleanup with new-test work and should cite the mechanism/test directly, stating it is metadata correction. | accepted — already done in the original edit: the row cites `check_blank_dimension` and `test_run_project_checks_detects_grill_trace_blank_dimension` directly and states "no new check was built to do this." |

## External Code Review Findings

Full working-tree diff (761 lines) reviewed via `external_review.py --mode
code`. GLM: revise. OpenAI: revise (agree within one step).

| # | Provider | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | GLM | medium | Claims FR-01.13 #2's citation is absent from the diff. | rejected-with-reason — verified false via `git diff HEAD -- <ledger>` showing the exact added line citing `test_adopt_positively_states_the_plain_language_rule`; the edit is present. Reviewer error, not a real gap. |
| 2 | GLM | low | `covers` marker registered only in `shipwright-preview`; unconfirmed elsewhere. | Same as Plan-Review finding 4 — already verified and documented. |
| 3 | GLM | low | Pinned strings include markdown formatting tokens, reintroducing brittleness the self-review claimed was fixed by normalization. | rejected-with-reason — see "Rejected alternatives" above; matches established house convention, and each test also pins the underlying prose separately. |
| 4 | GLM | low | Ledger presents the work as closed while spec/code/doubt reviews are `not_run` and `external_code` was still pending at review time. | rejected-with-reason — by design per the campaign sub-iterate-runner contract (ADR-029): `spec`/`code`/`doubt` are delegated to the orchestrator's 3f-bis cascade before merge, recorded `not_run` with a disposition, never silently skipped; `external_code` completed in the same pass this finding was raised in. Nothing is released or merged by this runner. |
| 5 | OpenAI | medium | FR-01.16 #1's cited test only pinned section headings, not the governing instruction sentences — a genuine gap. | accepted-and-fixed — added `test_module_pins_one_question_at_a_time_and_look_it_up_rules` pinning §2/§3's actual rule sentences; updated the ledger row's citation accordingly. |

## Confidence Calibration

Not triggered — effective complexity is `small` and no `touches_io_boundary`
risk flag fired (only `touches_build`, from the new files under
`plugins/shipwright-build/tests/`). Self-Review (F3.6, 7/7 pass, 1
not-applicable) is the only review this class of change requires beyond
the mandatory cascade.
