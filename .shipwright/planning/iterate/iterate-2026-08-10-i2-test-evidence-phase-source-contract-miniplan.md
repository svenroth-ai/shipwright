# Mini-plan: I2 test-evidence phase source contract

Run ID: `iterate-2026-08-10-i2-test-evidence-phase-source-contract`

1. Add a shared phase-source serialization helper. Test that it accepts only a declared phase/run identity and rejects malformed data.
2. Stamp the generated test-evidence report in `update_compliance.py`, fail the report update when that stamp cannot be written, and strip this provenance marker in the Group-E snapshot normalizer. Test the producer round trip and metadata-only snapshot stability.
3. Change I2 to compare the report marker with the latest phase-start identity. Test old mtime/current identity, a changed identity, a missing marker, and a legacy event.
4. Elevate Decision-Drop prompt-override findings to critical. Test that the existing scanner output is critical; the existing CI workflow already blocks critical prompt risks.

Alternative: use the generic `Source-State` banner. Rejected because it identifies the latest work event, not the phase whose regeneration I2 audits.
