# The claims-hardening docs say what the code now does, each gate once

Run: `iterate-2026-10-08-u12-docs-reconcile` (campaign `2026-10-07-finalization-claims-hardening`, unit U12).

## Context

Units U0-U6, U9-U11 and U13 each documented their own gate in their own diff, so the docs were mostly correct but had no single place that said where each gate lives, and a few sentences predated the gates (ledger "small+", external review "skipped by default" with no unavailable path, no write-matrix row for the hook override log).

## Decision

`docs/hooks-and-pipeline.md` gains one index under *Finalization claim checks* that points each gate at its section and its ADR in `.shipwright/planning/adr/`, plus a write-matrix row for the tracked `compliance_overrides.log`. `docs/guide.md` ch. 8 gets finalization item 0.7 (claim gates) and corrected small-vs-medium, ledger and degraded-mode sentences. No code changed; the claim-checks table is untouched so the registry meta-test still holds.

## Rejected

Re-describing each gate in the guide (a second copy drifts); touching the claim-checks table rows (the registry test parses them).
