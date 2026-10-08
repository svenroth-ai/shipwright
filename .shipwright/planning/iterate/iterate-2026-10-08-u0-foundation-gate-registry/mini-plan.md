# Mini-plan: U0 foundation - gate registry + shared reason codes

Spec: campaign U0 (BRIEF section 2). Complexity: medium. Risk: touches the F11 verifier list, review-record schema (shared serialized format), F5c entry.

## Steps
1. `lib/reason_codes.py`: frozen `REASON_CODES` {untestable, review_not_run, test_exemption}; `UNTESTABLE_REASON_CODES` in `iterate_checks.py` now reads it (file shrinks).
2. `verifiers/_finalization_claims.py`: ordered `CLAIM_CHECKS` + `run_claim_checks` (a crashing check reads RED); `run_all_checks` splices it in once, trailing the historical list. First tenant: `exemption_record_check.check_exemption_record`.
3. Review record: optional `reason_code` per entry validated against the `review_not_run` family (only on not_run/not_applicable); legacy rows without it stay valid. Writers: `record_review_pass.py record|close-missing --reason-code` (a bare code supplies a rule-naming disposition). Capped files shrink: `_validate_finding` moved to `lib/review_entry_checks.py`, `_marker_reason` moved to `lib/review_companion.py`.
4. F5c: optional `exemptions {count, items[{kind, scope, reason_code}]}` validated by `lib/exemption_record.py`; refused at write time in `append_iterate_entry.py` and re-checked at F11. `tools/exemption_summary.py` prints the count; F11.md (PR body), F12.md (summary), F5c.md document it.
5. Docs: `docs/hooks-and-pipeline.md` claim-checks table; `iteration-reviews.md` `--reason-code`.
6. Tests (shared/tests only, tagged `pytest.mark.covers("FR-01.11")`): registry both-directions meta-test, vocabulary, exemption record + writer + F11 + CLI, review reason_code schema + CLI incl. legacy.

## Alternatives considered
Extract the whole check list into a new module (rejected: large diff of a capped file, breaks the 18+ tests that import from it); do nothing (rejected: every later unit would collide on the capped file).
