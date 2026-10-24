# Architecture Brief: brief package library and dry-mode harness

## The problem
A later feature lets an operator hand /shipwright-run a committed "Brief package" directory and have it run unattended. Nothing today can say whether such a directory is well-formed, nor prove it is unchanged since a person approved it; a run could silently proceed on an edited package, including edited consent settings (autonomy, parallel builders, deploy target). CI also has no way to exercise the package flow without paying for model calls.

## What already exists here
- shared/scripts/lib/brief_intake.py reads a single brief FILE (four wizard answers).
- No hashing or layout validation of a multi-file input exists.
- integration-tests/ holds flat helper modules plus test files; no harness for brief-driven runs.

## What would newly, permanently exist
One shared library module (layout validator plus a manifest hash) that later units import and never re-implement, and an integration-test helper that builds a synthetic fixture package, drives a scratch project in a no-model "dry" mode and writes a schema-pinned JSON report. Tests keep both correct.

## Options on the table
- **A:** One shared lib module with validator and hash, plus a test-side harness (dry mode).
- **B:** Validate the package with a JSON schema file only, no hash.
- **C:** Do nothing now; add the hash inside the later unit that first needs it.

## Constraints that are not negotiable
The hash must be identical for LF and CRLF checkouts and must change when consent fields change. New files only under shared/scripts/lib, shared/scripts/tests and integration-tests (a sibling unit edits other files concurrently).
