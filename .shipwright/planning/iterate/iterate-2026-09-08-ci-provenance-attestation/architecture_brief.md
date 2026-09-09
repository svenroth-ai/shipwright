# Architecture Brief: CI provenance attestation

## The problem

A compliance system wants to auto-promote a requirement's status based on
"its tests ran green in CI." Today that check reads a committed JSON file
that anyone with repo write access can edit by hand, so the check cannot
actually distinguish a real green CI run from someone typing "green" into a
file. Any one-way, automated decision built on top of it inherits that gap.

## What already exists here

- A CI step already regenerates the same manifest from real, fresh test
  output on every push/PR and compares it to the committed one — advisory,
  reported, never blocking.
- The repo already downloads GitHub Actions artifacts programmatically
  elsewhere (a security-findings ingestion path) and already queries the
  GitHub Actions API for workflow-run state elsewhere (a CI-health check).
- The repo already has a pattern for "this fact is reported, never asserted,
  and never fails the run" for a sibling piece of evidence (a security-scan
  freshness report).

## What would newly, permanently exist

A CI step that publishes a small signed-by-nothing-but-GitHub-itself record
(commit, run identity, a digest of what was checked) as a build artifact when
the existing check finds no drift, and a library function elsewhere in the
repo that answers "was this commit's manifest verified?" by asking GitHub for
that artifact rather than reading anything from the local tree. Both need to
keep working as the repo evolves; the library function becomes something a
requirement-promotion mechanism depends on.

## Options on the table

- **A:** Publish a plain CI artifact carrying the verification record;
  consumers ask GitHub's Actions API for it.
- **B:** Use GitHub's cryptographic build-attestation feature (Sigstore/OIDC
  signing) to publish a verifiable, independently-auditable provenance
  statement.
- **C:** Do nothing automated — a human manually confirms "yes, I checked CI"
  before each promotion decision, with no new code or CI step.

## Constraints that are not negotiable

The existing drift-check CI step must not become a new failing/blocking gate
as a side effect of this change (a standing prior decision for that step).
