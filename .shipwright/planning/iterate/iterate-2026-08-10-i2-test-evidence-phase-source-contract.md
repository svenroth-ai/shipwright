# Iterate Spec: I2 test-evidence phase source contract

## Intent and decision

- **Run ID:** `iterate-2026-08-10-i2-test-evidence-phase-source-contract`
- **Intent:** bug fix
- **Complexity:** medium — a shared verifier and a compliance producer must share one serialized phase-source contract.
- **Spec impact:** NONE — this restores internal evidence validation without changing a product requirement.
- **Root cause:** I2 compares filesystem mtime to `phase_started`, even though checkout and merge operations can change mtime without changing the evidence and mtime cannot identify which phase run the report represents.
- **Decision:** stamp `test-evidence.md` with the run identity declared by the phase that regenerated it, then make I2 compare that identity with the latest matching phase-start event. Legacy phase events without a declared run identity remain explicitly unverified rather than being guessed.

## Acceptance criteria

1. **Phase-source contract:** When a compliance update regenerates test evidence for a phase with a declared run identity, the report records that phase and run identity; I2 passes only when the latest matching phase-start event declares the same identity. The marker is provenance, so the Group-E snapshot normalizer strips it and a stamping failure makes that report generation fail rather than claiming success.
2. **Meaningful freshness:** I2 ignores checkout-dependent mtimes, fails for missing or mismatched phase source identity, and reports the concrete regeneration action. It continues to skip only when no phase-start event exists or when a legacy phase event has no usable run identity.
3. **Decision-drop security enforcement:** Establish that the installed pre-commit hook does not run the prompt scanner and CI scans prompt risks but blocks only critical findings. Ensure a prompt-override finding in a Decision-Drop is classified as critical so the existing CI critical gate blocks it.

## Affected boundaries

- `plugins/shipwright-compliance/scripts/tools/update_compliance.py` — test-evidence producer.
- `shared/scripts/tools/verifiers/infrastructure_checks.py` — I2 consumer.
- `shared/scripts/` — serialized phase-source contract shared by producer and consumer.
- `plugins/shipwright-security/scripts/tools/prompt_injection_decision_drops.py` — decision-drop severity boundary.

## Investigation and reproduction

- **Read error:** I2 currently calls `_check_doc_fresh(... event_type="phase_started")`, which compares `test-evidence.md` mtime against the latest event time.
- **Reproduction:** create a current report, set its mtime old, then write a phase-start event; the current I2 fails although the report content is unchanged.
- **Recent change:** PR #620 replaced W3's mtime proxy with its per-iterate `Source-State` run identity and deliberately filed I2 because that run identity does not identify a pipeline phase.
- **Boundary:** `update_compliance --phase <phase>` writes the report, while I2 reads the phase-start event. Their only shared fact today is an unreliable timestamp.

## Mini-plan

1. Add a small shared phase-source parser/renderer and tests for valid, legacy, and malformed event identities.
2. Have the compliance update path stamp test evidence after successful generation using the latest matching phase-start identity; update Group-E normalization and test producer output plus write failure handling.
3. Replace I2's mtime comparison with source-identity comparison and add focused old-mtime/current, mismatched, missing, and legacy coverage.
4. Verify decision-drop hook/CI coverage and elevate Decision-Drop prompt findings to critical so the existing CI gate enforces them; add a focused test.

## Alternative considered

Keep the existing `Source-State` banner and compare it to the phase event. Rejected: it names the latest completed work event, which is intentionally a different contract and can legitimately predate the current pipeline phase.

## Confidence Calibration

- **Boundaries touched:** compliance generation → test-evidence markdown → shared phase-source parser → I2 verifier; Decision-Drop JSON → prompt scan → existing CI critical gate.
- **Empirical probes run:** focused producer/consumer tests will prove the same identity is written and read; scanner tests will prove the existing critical gate receives a critical finding.
- **Test Completeness Ledger:** each acceptance criterion is represented by focused automated tests; 0 untested-testable behaviors.
- **Confidence-pattern check:** depth is a producer-to-consumer round trip; breadth covers current, stale, missing, legacy, and checkout-mtime cases.

## Internal Plan Review (Sol/high)

- **Ran:** yes
- **Severity:** medium
- **Summary:** The identity contract is sound, but provenance-only phase metadata must be excluded from Group-E content drift and stamping must be part of a successful generator result.
- **Findings:** medium — strip the Phase-Source marker in the evidence snapshot normalizer and add coverage; low — treat a failed marker write as a test-evidence generator failure.
- **Known limitations:** none
- **Status:** 2 findings accepted and fixed in the implementation plan

## Verification (medium+)

- **Surface:** none — Python producer/verifier and CI scanner policy only.
- **Runner:** focused pytest roots plus canonical F0 suite.
- **Evidence path:** test output and F5/F5c test-completeness ledger.
