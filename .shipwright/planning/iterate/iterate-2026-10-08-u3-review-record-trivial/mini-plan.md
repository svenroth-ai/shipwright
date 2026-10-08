# Mini-plan: U3 review record at trivial / all-not_run

Spec: campaign U3 (BRIEF section 2). Complexity: medium (BRIEF Cx). Touches the F11 review-record gate, the Test Completeness Ledger gate, the review-record writer docs, and the shared reason-code vocabulary.

## Steps
1. `verifiers/review_record_closure.py` (new): `self_review_recorded` (`self` must be `completed` with evidence, `carries_evidence`, at every complexity) and `reason_codes_closed` (every `not_run`/`not_applicable` row carries a `reason_code`; at trivial any closed code, `trivial-auto` the one-command default; from small up `trivial-auto` refused). Read through `entry_for` so legacy `gates.spec` rows are held to the same rule.
2. `review_record_check.py`: enforced at every complexity (trivial no longer SKIP); closure rules run after the pending check and before the medium+ floor; remediation names `--reason-code`.
3. Ledger: `check_test_completeness_ledger` + vocabulary moved to `verifiers/_ledger_completeness.py` (shared F5c-entry messages to `verifiers/_entry_details.py`), re-exported by `iterate_checks.py` (shrinks 1082 -> 855). At trivial the SKIP becomes a recorded row `{"status":"n/a","reason_code":"trivial-auto"}`; no block fails; `trivial-auto` refused above trivial and is the only n/a ledger code.
4. `lib/reason_codes.py`: `TRIVIAL_AUTO` constant (one definition) + `no-spawn-site` (campaign runner internal arms, which are neither delegated nor below a threshold).
5. Docs in the same diff: SKILL.md (Step 7 record, ledger, phase matrix), F5.md, F5c.md, F11.md, iteration-reviews.md (reason-code now required; trivial one-command close; campaign runner rows carry codes), hooks-and-pipeline.md + guide.md rows.
6. Tests (shared/tests, `pytest.mark.covers("FR-01.11")`): new `test_review_record_closure.py`, `test_ledger_trivial_row.py`, CLI round-trips in `test_record_review_pass_cli_floor.py`; existing fixtures gain reason codes / a completed `self` via `_review_background_row.py`.

## Alternatives considered
Require exactly one physical row at trivial (schema change to the cross-repo `reviews` contract, which requires every known type present); make `--reason-code` mandatory in the CLI (breaks the gate-first contract that validators and writers ship compatible: the CLI keeps accepting, F11 refuses).
