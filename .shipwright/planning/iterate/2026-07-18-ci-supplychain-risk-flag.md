# Iterate — CI supply-chain risk flag with a non-dodgeable acknowledgement gate

- **Run ID:** `iterate-2026-07-18-ci-supplychain-risk-flag`
- **Type:** CHANGE · **Complexity:** medium · **Spec Impact:** MODIFY
- **Triage:** `trg-9509c2e8` (item 3 of 5 — items 1/2/4 follow as their own
  iterates, item 5 is deliberately not promised)
- **Upstream decision (NOT re-opened):** webui ADR
  `iterate-2026-07-18-unpin-actions-no-dependabot`

## Problem

`classify_complexity.RISK_TAXONOMY` has no pattern for `.github/workflows/**` or
`.github/dependabot.yml`. Changing the files that decide *which third-party code
runs with repository credentials* fires zero risk flags.

Verified twice, live:

1. webui PR #285 recorded `risk_flags: []` while running a full **medium**
   iterate — external plan review, code review, confidence calibration — and
   still reversed an accepted-risk position (#208) without anyone noticing.
2. The revert reproduced `risk_flags: []` on the same 7 files.

## Why "mandatory review" alone is not the fix

The triage item proposes `min_complexity: small, enforces: [mandatory_review]`.
That would **not** have caught #285: #285 already ran *more* review than
`mandatory_review` imposes, and the contradiction still passed. A flag that only
says "look again" repeats the control that already failed.

Owner decision (2026-07-18, approval gate): the flag must force an **explicit
written acknowledgement**. The author of a CI-trust-boundary change must state
which recorded posture decision the change is consistent with. That is precisely
the sentence nobody could have written for #285 without noticing the conflict.

## External review (GPT-5.4 + Gemini 3.1 Pro, both succeeded)

The first draft was **broken by construction** and the review caught it. Changes
folded in below; one suggestion rejected with reasoning.

- **GPT #3 (high) — stale ack.** The ack was not bound to the run or the diff, so
  an old `iterate_latest.ci_supplychain_ack` would satisfy the gate for a *later*
  CI change. False-green by design. → AC-2 now binds run_id **and** a changed-path
  fingerprint.
- **GPT #1 (high) — classifier integration unspecified.** A taxonomy entry with
  only prose patterns never emits the flag. → AC-1 names the integration point
  and is tested on real paths, not prose.
- **Both (high/medium) — weak validation + hand-edited machine artifact.**
  → validated fields + a dedicated CLI writes the block (owner decision).
- **GPT #6 / Gemini — pattern semantics, deletions, renames.** → explicit regexes,
  near-miss and deletion/rename tests.
- **REJECTED — Gemini's "hoist patterns into `shared/contracts/iterate.py` and drop
  the duplicate".** `contracts/iterate.py` itself imports from the plugin lib, so
  it is not import-free; the verifier must not cross-plugin-import (ADR-044). The
  duplicate + both-directions drift test is the settled `cross_component` posture,
  deliberate, not accidental.
- **NOTED, not built — Gemini's bot-exception path.** An `actor == bot` bypass is a
  hole in a gate whose entire value is non-dodgeability. Dependabot is deleted by
  decision; if another bot ever touches `.github/`, a human takes the change over.

## Acceptance Criteria

- **AC-1** — `is_ci_supplychain_change(changed_files)` returns True for
  `.github/workflows/**`, `.github/dependabot.y(a)ml` and `.github/actions/**`,
  from `git diff --name-only` paths. Additions, modifications, **deletions** and
  **renames** all trigger; near-misses (`docs/.github/workflows/x.yml`,
  `.github/workflow/x.yml`, `.github/dependabot.json`) do not.

  > **Correction to the review (GPT #1).** GPT asked for the detector to be called
  > from `classify()`. It cannot be: `classify()` is Stage 1 and runs **before any
  > code exists**, so there is no diff to inspect — which is why no existing
  > diff-based flag (`touches_build`, `touches_io_boundary`, `cross_component`) is
  > invoked there either; they are imported for the contract and evaluated at
  > verification time. The finding is right that a prose-only taxonomy entry has no
  > teeth; the cure is that the authority lives in the F11 recompute (AC-2), with
  > the taxonomy entry contributing only a Run-Summary hint. AC-1 originally
  > claimed a classify-time diff call — that was wrong and is corrected here.
- **AC-2** — When the flag recomputes true at F11, finalization **STOPs** unless
  `iterate_latest.ci_supplychain_ack` carries all of:
  `run_id` == the run being verified, `paths_fingerprint` == the recomputed
  fingerprint of this diff's CI paths, and validated `consistent_with` +
  `statement`. A stale or foreign ack is rejected, not honoured.
- **AC-3** — Validation is not satisfiable by filler: both fields must be strings
  whose trimmed length clears a floor, and `consistent_with` must name a
  recognizable recorded decision (`ADR-NNN`, an `iterate-YYYY-MM-DD-*` run id,
  `#NNN`, or `DO-NOT #NNN`).
- **AC-4** — `shared/scripts/tools/record_ci_supplychain_ack.py` writes the block
  with the correct run/fingerprint binding, so no one hand-edits a machine artifact.
- **AC-5** — The verifier's self-contained pattern copy and the SSoT stay pinned in
  **both** directions (registry-driven SSoT meta-test rule).
- **AC-6** — The gate fails **closed**: if the diff cannot be obtained, that is an
  error, never "no CI change".

## Design

Mirrors the settled `cross_component` posture exactly:

| Layer | File | Role |
|---|---|---|
| SSoT patterns + predicate | `plugins/shipwright-iterate/scripts/lib/risk_detectors.py` | `CI_SUPPLYCHAIN_FILE_PATTERNS`, `is_ci_supplychain_change()` |
| Taxonomy entry | `plugins/shipwright-iterate/scripts/lib/classify_complexity.py` | message hints (Run-Summary only), `min_complexity: small` |
| Public contract | `shared/contracts/iterate.py` | re-export |
| Non-dodgeable gate | `shared/scripts/tools/verifiers/ci_supplychain.py` | drift-pinned copy + `check_ci_supplychain_ack` |
| Registration | `shared/scripts/tools/verifiers/iterate_checks.py` | into `run_all_checks` |

The verifier keeps a **local** copy on purpose — it runs in every shared/tests
session and must never cross-plugin-import the iterate lib (ADR-044).

Plus `shared/scripts/tools/record_ci_supplychain_ack.py` — the writer CLI (AC-4).

### Ack block shape (run- and diff-bound)

```json
"iterate_latest": {
  "ci_supplychain_ack": {
    "run_id": "iterate-YYYY-MM-DD-slug",
    "paths_fingerprint": "<sha256 over the sorted, normalized CI paths in this diff>",
    "consistent_with": "<recorded decision this change agrees with>",
    "statement": "<what the change does to the CI trust boundary>"
  }
}
```

The fingerprint is what makes the ack non-reusable: acknowledging a workflow
tweak cannot later license a `dependabot.yml` reintroduction, because the path
set — and therefore the fingerprint — differs.

### Semantics guard (explicit)

The flag enforces that a trust-boundary change is **reasoned about and
recorded** — it must never enforce *pinning*. GitHub-owned actions stay on
mutable tags by decision; a flag demanding pins would contradict the ADR it
exists to protect.

## Deliberately out of scope

- `shared/templates/github-actions/*` — the shipped CI templates are the same
  trust boundary *for adopters*, but stripping hosted services from them is
  item 1 of the triage list. Mixing it here would blur this flag's semantics.
- Contradiction detection (item 5) — the ack makes the author state the posture;
  it does not yet machine-verify the claim.

## Confidence Calibration

- **Boundaries touched:** {filled at Step 7.5}
- **Empirical probes run:** {filled at Step 7.5}
- **Test Completeness Ledger:** {filled at Step 7.5}
- **Confidence-pattern check:** {filled at Step 7.5}
