# Review record and ledger enforced at every complexity (campaign unit U3)

Campaign `2026-10-07-finalization-claims-hardening`, unit U3. New `verifiers/review_record_closure.py` (self must be completed with evidence; every skipped row carries a closed `reason_code`, `trivial-auto` at trivial only); `review_record_check.py` enforced at trivial; ledger check moved to `verifiers/_ledger_completeness.py` with the trivial SKIP replaced by a recorded `{"status":"n/a","reason_code":"trivial-auto"}` row; `lib/reason_codes.py` gains `TRIVIAL_AUTO` and `no-spawn-site`.

## Architecture Review

External, `--mode architecture` over `architecture_brief.md`: GLM **approve**, GPT **approve** (option A).

- GLM (low): the trivial default rows should be filled by tooling, not typed. **Accepted** - it is one existing command, `close-missing --status not_applicable --reason-code trivial-auto`, named in SKILL.md, iteration-reviews.md and in the gate's own failure message.

## External-Plan-Review-Findings

| Reviewer | Finding | Disposition |
|---|---|---|
| GLM high | Mechanical extraction and behaviour change in one diff | rejected-with-reason: the extraction is mandated by the BRIEF touch set (`iterate_checks.py` at cap); the PR is squash-merged so a second commit buys no bisect; the move is verbatim except the trivial branch, the re-export is pinned by a test and every pre-existing ledger test passes unchanged |
| GLM high | not_run vs not_applicable at trivial; is trivial-auto mandatory | accepted-and-fixed: both statuses are treated alike; trivial-auto is the default, any closed code is accepted at trivial (test) |
| GLM medium | Legacy records fail when re-verified | accepted-and-fixed: documented - F11 verifies the run being finalized; a pre-U3 record would fail if re-verified (iteration-reviews.md) |
| GLM medium | Precedence when several rules fail | accepted: deterministic order pending -> self -> codes -> floor -> Stage-1 -> committed |
| GLM medium | Who writes the trivial ledger row | accepted-and-fixed: the author, in the F5c entry; a missing block fails naming the exact row (F5.md, F5c.md, SKILL.md) |
| GLM low | `no-spawn-site` unused by this unit | rejected-with-reason: this unit's own campaign-row docs and this run's record use it |
| GLM low | `trivial-auto` single source | accepted-and-fixed: `lib.reason_codes.TRIVIAL_AUTO` is used by both gates and their messages |
| GLM low | trivial-auto refusal symmetric across both gates | accepted-and-fixed: tests on both gates |
| GPT high | Writer for the trivial default not identified | accepted-and-fixed: existing `close-missing --reason-code trivial-auto`; CLI round-trip test, and `close-missing` cannot satisfy `self` (test) |
| GPT medium | Per-type code compatibility | rejected-with-reason: a type-to-code matrix in the verifier re-encodes the phase matrix, the design the gate's docstring rejects; presence + closed vocabulary + no trivial default above trivial is enforced, the choice of code is the reviewable claim |
| GPT medium | All-not_run regression independent of the fixture helper | accepted-and-fixed: CLI-driven parametrised test at every complexity |

## Self-Review

1. Spec Compliance - pass: all-not_run fails at every complexity; self unconditional; one-command trivial-auto close; closed codes from small up; ledger trivial row recorded; SKILL.md + F5c.md updated.
2. Error Handling - pass: closure runs after schema validation and the pending check; unknown complexity keeps its prior SKIP.
3. Security Basics - pass: no new input surface; frozen vocabulary.
4. Test Quality - pass: 30+ new tagged tests, positive and negative, CLI subprocess round-trips.
5. Performance Basics - pass: one pass over eight types.
6. Naming & Structure - pass: iterate_checks.py 1082 -> 855; every touched source file under 300 lines.
7. Affected Boundaries - pass: F5c entry `test_completeness` and `reviews.json` `reason_code`, both probed through their real producers.

## External-Code-Review-Findings

| Reviewer | Finding | Disposition |
|---|---|---|
| GPT medium | SKILL.md override table still lists the trivial ledger as Advisory and the review record as small+ | accepted-and-fixed: both moved to Mandatory, every complexity |
| GLM medium | Doc promised merged records are never re-verified, the code has no cutoff | accepted-and-fixed: doc now says F11 verifies the run being finalized and a pre-U3 record would fail if re-verified |
| GLM low | Docs say each type names its OWN code, enforcement only checks presence | accepted-and-fixed: docs state presence + not-trivial-auto is enforced, the choice is the reviewable claim |
| GLM low | `recorded_by="none"` as a magic value in a test | rejected-with-reason: `none` is the documented no-op adapter `carries_evidence` excludes (review_record_floor.py) |
| GLM low | Empty status message when the self row is absent | rejected-with-reason: unreachable - an absent self row is reported by the pending check first |

## Confidence Calibration

Boundaries: the F5c entry's `test_completeness` block and the review record's `reason_code`. Probes: (1) a trivial F5c entry carrying the default row written through the real `append_iterate_entry.py`, read back by the ledger gate - passes, not skipped; (2) `record_review_pass.py` self + `close-missing --reason-code trivial-auto` as real subprocesses read by the gate - passes, and the same without `self` fails at all four complexities; (3) a whitespace-padded or non-trivial ledger code - refused with a message naming the one valid code. 3 probes, 0 findings: asymptote reached. Not probed: the webui consumer (reason_code is an additive row key since U0).
