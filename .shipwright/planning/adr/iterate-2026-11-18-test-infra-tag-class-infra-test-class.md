# Infrastructure class for harness tests in the F11 test-tag gate

Harness tests (golden-trace driver, gh stub, hash helper) prove no product requirement, yet the F11 test-tag gate demanded a requirement tag, so authors attached stand-ins that inflated coverage.

Chosen: a source-declared marker `@pytest.mark.covers_none("tooling"|"infra")`, honoured only for a file named exactly in `shared/config/infra_test_paths.json` as read at the merge-base. Infra tests never count toward requirement coverage; the gate reports their number. A stand-in correction is accepted only while every requirement and criterion it carried keeps another linked test, and never when a tagged test vanished and left one uncovered.

Rejected: a third per-test F5c exemption code (a self-reported word the gate cannot cross-check against where the test lives; the operator's constraint is no loophole), a per-run label (relaxes every test of a mixed run), a real harness requirement (puts a non-product capability in the requirement catalog and counts harness tests as coverage).

Known limits: an exact-path catalog entry for a real test is possible in a reviewed PR (CODEOWNERS is the guard); the merge-base resolver is shared with every F11 gate; the catalog is not seeded here, so the six harness files are retagged in a follow-up merge; downstream traceability reports still list infra tests as untagged.
