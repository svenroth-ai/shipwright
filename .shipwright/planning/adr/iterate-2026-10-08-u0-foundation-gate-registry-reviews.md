# Finalization gate registry and shared reason codes (campaign unit U0)

Campaign `2026-10-07-finalization-claims-hardening`, unit U0. Registry module `verifiers/_finalization_claims.py`, closed vocabulary `lib/reason_codes.py`, optional `reason_code` on review rows, optional `exemptions` block in the F5c entry.

## Architecture Review

External, `--mode architecture` over `architecture_brief.md`: GLM **approve**, GPT **revise** (no reject, so the unit did not halt).

- GPT (medium, simpler-alternative): move the *whole* existing check list into one new module and let later units extend that single list. **Rejected-with-reason:** that re-points the importers of a 1,086-line capped file and ~100 tests in one diff for no extra capability; the registry trails the historical list, ordering is preserved, and the capped file shrank. Revisit only if the two-list split proves confusing.
- GLM (low): keep the registration meta-test scoped to the claim-checks table, not a repo-wide doc sweep. **Accepted** - it reads the marker-delimited table only.
- GLM (low): the cap on `iterate_checks.py` is the enforcement that later units use the registry. **Accepted**; a test pins `iterate_checks.py <= 1086` lines.

## External-Plan-Review-Findings

| Reviewer | Finding | Disposition |
|---|---|---|
| GPT medium | New writers may still omit `reason_code`, so free text lives on | rejected-with-reason: making it mandatory is U3/U10's job per complexity; U0 ships vocabulary + field + writers |
| GPT medium | `count` vs `items` consistency, bool/negative counts, per-kind family check, absent vs zero | accepted-and-fixed: `exemptions_error` validates all of it; a missing key is legacy |
| GPT medium | F12 / PR-body integration not proven | partly accepted: `exemption_summary.py` is tested end to end; F11.md/F12.md instruct its use (prose templates cannot be unit-tested) |
| GPT low | Crash handling of the registry needs a test | accepted-and-fixed: crashing check reads RED, siblings still run |
| GLM medium | Cross-family code use must be invalid | accepted-and-fixed: parametrised negative tests (`unavailable` under `test_exemption`, `fixture-or-helper` in a review row) |
| GLM medium | Empty / null `reason_code`; override footgun for code+disposition | accepted-and-fixed: `""` and unknown codes are errors, null = absent; an explicit disposition is kept next to the code |
| GLM low | Import failure at the splice crashes F11 | rejected-with-reason: a registry import error fails every test at once; swallowing it would hide a missing gate |
| GLM low | Doc scraping brittleness | accepted-and-fixed: marker-delimited table |

## Self-Review

1. Spec Compliance - pass: registry + one splice, shrink-neutral; closed vocabulary importable by verifiers and `record_review_pass.py`; `reason_code` in schema and F5c with legacy reads; count in F5c, F12 and PR body.
2. Error Handling - pass: crashing check -> RED, malformed block -> named error, writer refuses before any write.
3. Security Basics - pass: scopes are path-safe (no absolute, no `..`, no control chars, length cap); vocabulary closed.
4. Test Quality - pass: 62 new tests, both-direction meta-test, negative and legacy cases, real subprocess CLI runs.
5. Performance Basics - pass: the new check reads one entry file.
6. Naming & Structure - pass: capped files shrank (iterate_checks 1086 -> 1082, schema 317 -> 300, record_review_pass 408 -> 397); no file crossed a limit.
7. Affected Boundaries - pass: reviews.json (producer `record_review_pass.py`, consumers the F11 gate + older plugin-cache readers) and the F5c entry; real round-trip probes below.

## External-Code-Review-Findings

| Reviewer | Finding | Disposition |
|---|---|---|
| GPT medium | A bare `--reason-code` leaves the companion marker's `reason` null | accepted-and-fixed: marker receives the synthesised disposition; test added |
| GPT medium | Explicit `"exemptions": null` accepted as legacy | accepted-and-fixed: only a MISSING key is legacy; writer, F11 and summary refuse null |
| GLM low | `--reason-code` on a non-terminal status | rejected-with-reason: `pending` is already refused earlier by `_validate_record_args` |
| GLM low | Size test pinned the post-change cap | accepted-and-fixed: pinned at the pre-change 1086 |
| GLM low | Empty-project `run_all_checks` test depends on every historical check | rejected-with-reason: it passes on an empty project today and is a useful canary |
| GLM low | `..` check covered only the path part of `scope` | accepted-and-fixed: the whole scope is split and checked |

## Confidence Calibration

Boundaries: the review record (`reviews.json`) and the F5c entry. Probes: (1) an OLDER plugin-cache `validate_record` reads a record written by the new code with `reason_code` rows - valid; (2) non-ASCII disposition next to a code round-trips through the CLI; (3) F5c entry with `exemptions` through the real `append_iterate_entry.py`, summary CLI, and a count-mismatch refusal. 3 probes, 0 findings (two consecutive no-finding probes: asymptote reached). Not probed: the cross-repo webui consumer rendering an unknown `reason_code` key on a row (additive key; its reader maps unknown row keys, not entry fields - low risk, flagged).
