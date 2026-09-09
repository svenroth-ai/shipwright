# ADR: Unforgeable CI-provenance attestation for traceability manifests

**Run:** iterate-2026-09-08-ci-provenance-attestation (P3.4c, campaign req3-04c-ac-identity-wave2)

## Context

The original P3.5-class defect this sub-iterate traces back to: nothing in
the framework could prove that a commit's traceability manifest had actually
been CI-verified, as opposed to merely claimed. `compare_traceability_manifest.py`
already regenerates and structurally diffs the manifest in CI
(iterate-2026-08-26-r1b-ci-manifest-regen-gate), but that check is
deliberately advisory-only (its `_structural_view()` vs `execution_report()`
split is a standing, pre-existing architecture this sub-iterate's own mandate
forbids making blocking) and its result was never durably, non-forgeably
readable by anything outside the CI run itself.

## Decision

Add `shared/scripts/ci_provenance.py` (+ CLI `tools/ci_provenance_check.py`),
a predicate that resolves whether a given commit's manifest was CI-confirmed
by reading GitHub's own Actions Jobs API — never a locally-reported claim or
uploaded artifact. A commit counts as `verified` only for a `push`-triggered
run on the repo's default branch with `conclusion == success`, whose Jobs API
step list shows the drift-check's own confirmation step (`Confirm
traceability manifest verified (no drift)`, gated on the drift-check's own
captured exit code) as `success`. `.github/workflows/ci.yml` gains exactly
one new, infallible `echo` step for this; the existing drift-check step's
body and exit-code contract are otherwise unchanged except one narrowly-scoped
`$GITHUB_OUTPUT` emission line so the new step can read the drift-check's exit
code.

The predicate's own commit-SHA validation requires exactly 40 hex chars (not
an abbreviation) at the library level, not only the CLI, because a future
in-process caller (P3.5) will call `resolve_ci_verification()` directly. Every
failure class that cannot answer the question (gh transport failure, jobs-query
failure, malformed run id, malformed job/step shape, a truncated runs page)
returns `error`, never falling through to a false `not_verified`/`no_record` —
this pattern is applied uniformly via a `query_failed`/`malformed` flag checked
only after the full search exhausts every qualifying run, so a later failure
can never mask an earlier genuine confirmation (extending AC9's original
"search past a non-confirming run" reasoning to failures, not just negatives).

## Consequences

A future consumer (P3.5) gains a durable, non-forgeable way to require
CI-verified manifests before treating a commit as promotion-eligible, without
trusting any self-reported state. The predicate is explicitly **structural-only**
— it proves the manifest's structural fields matched a fresh regeneration,
**not** that tests/coverage/acs execution was itself clean. This scope
limitation is disclosed prominently in the module docstring, the iterate spec's
`## Design (final)` and `## Known limitations` sections, and here, so a future
caller cannot mistake `verified` for full correctness proof — this is exactly
the gap the original P3.5 defect was about, and disclosing it explicitly is a
deliberate part of the fix, not an oversight left for later.

Windows `PATH` executable-search precedence for the `gh`/`git` subprocess calls
(a process's own CWD can be searched before `PATH` entries on Windows) is a
disclosed, not fixed, limitation — raised by Stage-3 doubt review as a real
risk in a repo checkout containing a maliciously-named `gh.exe`/`git.exe`, out
of scope for this sub-iterate's mandate.

## Rationale

Round 3 (Architecture Review) found the original Round-1 artifact-upload +
content-digest design unnecessary: the Jobs API step-conclusion read already
gives GitHub-attested proof without needing an uploaded artifact to reproduce
byte-for-byte between the CI environment and a later consumer process, which
the Round-1 design could never actually guarantee (this was Internal Plan
Review's own Round-1 finding, before any code was written against that shape).
Removing the artifact layer also removed an entire class of digest-mismatch
false-negative failure modes that a byte-identity requirement would have
introduced for no unforgeability benefit — the Jobs API read is already backed
by GitHub's own attestation, not by anything the artifact layer would have
added.

## Rejected alternatives

**Round 1 — artifact-upload + content-digest.** A CI step would upload the
regenerated manifest as a workflow artifact, and the consumer would download it
and compare a content digest. Rejected: the digest could never reproduce
between CI's regeneration environment and a later consumer process (different
timestamps, different working-tree state), and the intended unforgeability
argument had a real hole — a PR's own `ci.yml` runs *before* human review can
catch a malicious edit to that very workflow file, so an attacker landing a
edited `ci.yml` in the same PR could have it self-attest. Both defects were
caught by Internal Plan Review before implementation began.

## Architecture impact

Component — new top-level (ADR-045 flat-module placement, peer of
`github_api.py`) `shared/scripts/ci_provenance.py` + CLI
`tools/ci_provenance_check.py`; one new infallible confirmation step in
`.github/workflows/ci.yml`'s `python-checks` job. See `architecture.md`'s
matching bullet.
