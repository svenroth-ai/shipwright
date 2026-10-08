# Mini-plan: U11 integration scenario for the finalization-claims gates

Add one integration test file (`shared/tests/test_finalization_claims_scenario.py`) plus one records helper
(`shared/tests/_finalization_scenario_records.py`). The test builds a compliant run in a tmp git repo at run time (never a
committed fixture) and, per case, breaks exactly one claim:
- U1 untagged added test; U3 missing self / free-text closure (trivial, small, medium); U4 150-line small diff closed with a
  code that denies the trigger; U5 `none` over an API route / absent evidence / mismatched count (medium); U6
  `spec_impact: none` without a closed code, and a `docs` label over runtime code.
- Each case asserts the owning gate's diagnostic AND that every other gate stays green (isolation), plus a converse test
  breaking all small-scope claims at once.
No production code changes. All tests tagged `pytest.mark.covers` (FR-01.11). Files <= 300 lines.
