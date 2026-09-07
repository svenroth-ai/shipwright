# Binding-completeness F11 gate + ledger/(E)-bullet reconciliation (P3.3)

## Context

Campaign `req3-04c-ac-identity-wave2`, sub-iterate P3.3: "producers emit and
require the binding, including the highest observable layer." The two literal
ACs are (1) a binding naming only unit tests must be rejected when a higher
layer (integration/e2e) has executed-passing evidence for the same
requirement, and (2) the evidence ledger's row numbering and spec.md's `(E)`
bullets must be reconciled — they are not aligned today.

## Decision

Deliver the **require** half as a new F11 verifier,
`check_binding_completeness` (`_layer_coverage_binding.py` pure evaluator +
`layer_coverage_binding.py` CheckResult wrapper), wired into
`run_all_checks` alongside the existing `check_cross_layer_coverage` /
`check_removal_coverage` sibling gates. It reuses the SAME behaviour-change
signal (`behavior_changed_keys` + `criteria_changed_keys`) so the three gates
can never disagree about which FRs are in scope for a given run, and it
extracts a shared `route_gap_severity(ambiguous, source)` helper into
`_layer_coverage_core.py` so `evaluate_cross_layer` and the new
`evaluate_binding_completeness` share ONE severity-routing rule instead of
two copies that could drift.

The **emit** half of the sub-iterate's own title — the three producers
(`/shipwright-project`, `/shipwright-adopt`, `/shipwright-iterate`) writing a
complete binding at requirement-creation/update time — is explicitly deferred,
NOT delivered here. See "Rejected" below for why, and `campaign.md`'s P3.3
line for the tracked deferral note (added in this same diff).

For AC2, the ledger reconciliation, appended two sections to
`.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`:
a table of every FR whose `(E)` bullets carry a trailing
`(iterate-YYYY-MM-DD-...)` citation dated AFTER that FR's own ledger walk
date (bullets the walk could not have seen), plus an explicit statement that
the ledger's row numbering and spec.md's bullet numbering are NOT meant to be
1:1 (proven via FR-01.18: 8 `(E)` bullets vs. a 10-row table, because 2 rows
are synthesized from a split, not derived from any single bullet).

## Consequences

A behaviour-changed FR whose declared `Layers` cell understates what this
run's own evidence proves (e.g. names only `unit` when an `integration` test
tagged for the same requirement executed and passed) now HARD-blocks at
`medium`+ complexity — unless its `required_layers_source` is
`inferred_legacy`/`defaulted_legacy` (pre-rollout valve, ADVISORY) or its
display id collides across namespaces (structurally ambiguous, ADVISORY).
An empirical dry-run against the live corpus (see "Rollout blast-radius
measurement" below) shows the gate cannot immediately HARD-block any FR
active in THIS monorepo today — that measurement's scope is this repo only
(see the caveat below); it is not evidence about target Shipwright-managed
projects. The ledger now carries an explicit, falsifiable reconciliation
statement instead of two silently-diverging numbering schemes.

## Rationale

The narrow "require, not emit" scope keeps this unit's blast radius to ONE
enforcement mechanism reviewable in isolation. Wiring three independent
producer pipelines in the same diff would have mixed three unrelated blast
radii and inflated this card past its own AC list — exactly the "Producers
act on YOUR run" trap this campaign's own SPEC (§9) flags for other tracks.
The emit half is P3.5's job (it is the sub-iterate that actually SETS the
binding per requirement) or a named follow-up card if P3.5 does not cover it
— tracked in `campaign.md`, not silently dropped.

For AC2, a raw table-row-count vs. bullet-count comparison was tried first
and rejected: the ledger's own tables include synthesized/split/merged rows
and non-criterion tables (a "removed from catalog" table, a "test pyramid"
table) that a naive row-counter cannot distinguish from the criteria table
(see the ledger doc's own "Reconciliation" section for the FR-01.18 proof).
The citation-based method was chosen instead and spot-verified against two
citations before being trusted at scale.

## Rejected alternatives

1. **Wire all three producers in this same sub-iterate** (external plan
   review, both providers, HIGH). Rejected: three independent plugin
   pipelines, three independent blast radii, one card's AC list. Formally
   deferred (not silently dropped) to P3.5 or a named follow-up card —
   recorded in `campaign.md`.
2. **A new machine-readable ledger schema for AC2** instead of prose +
   citation table. Rejected: REQ3.06 (`trg-0845a2f5`) owns making the
   register machine-readable; duplicating that here would pre-empt a
   dedicated card's design space.
3. **Raw ledger-row-count reconciliation.** Rejected: proven structurally
   incompatible with the ledger's own split/merge/synthesis conventions
   (FR-01.18: 8 bullets, 10 rows) — see Rationale.
4. **Git-blame as the reconciliation cross-check.** Tried, then rejected as
   confounded: every uncited bullet across every FR blames commit
   `28491e1c9` ("REQ-3 Phase 2 — every requirement now states what it
   guarantees", #436), the single bulk commit that first landed the whole
   `(E)`-bullet catalog 1-3 days after each walk session's own recorded
   date. Git blame answers "when did this line's current text land," which
   for nearly every bullet is that one bulk-authoring commit, not "when was
   this bullet last substantively touched" — a false universal-drift signal.
   Documented as a negative result in the ledger, including the residual gap
   it leaves open (a bullet edited in place post-Phase-2 without adding a
   citation escapes both methods).
5. **Share one regen snapshot across all three `run_all_checks` gates**
   (external plan review, both providers, LOW/MEDIUM). Not done in this
   diff: `check_binding_completeness` adds a THIRD independent
   `regenerate_base_head(..., with_evidence=True)` call, at the same cost
   class as the two pre-existing ones. Sharing one snapshot across all three
   checks would need a broader `run_all_checks` signature change outside
   this unit's scope; deferred to a future consolidation pass if profiling
   shows the added regen cost matters in practice. Disclosed, not fixed.

## Rollout blast-radius measurement (external plan review finding #1, glm)

Ran `evaluate_binding_completeness` against the live
`.shipwright/compliance/test-traceability.json`, forcing every active FR to
read as behaviour-changed (worst case for this run):

- 20 of 20 active FRs currently carry `required_layers_source:
  inferred_legacy` (zero `explicit`).
- Result: `hard: 0`, `advisory: 1`.

The gate therefore cannot immediately HARD-block any FR active in this repo
today — every gap it would find right now routes ADVISORY via the
pre-rollout legacy valve, exactly as `evaluate_cross_layer` already does for
the same corpus.

**Scope caveat (added at Stage-3 doubt-review, PR #687):** this measurement
is a self-test of this monorepo's own corpus, not a rollout-safety guarantee
for the population `shared/scripts/` actually ships to. This repo's
`test-traceability.json` is 100% `inferred_legacy` because it was
adopt/backfill-bootstrapped (`iterate-backfill-plugin-fr-tags-BRIEF.md`) —
not because Shipwright-managed projects are typically legacy-sourced. A
greenfield target project authored via the normal `/shipwright-project` path
produces `required_layers_source: explicit` immediately
(`fr-authoring.md` §Layers), which receives no legacy-valve grace period from
this gate. The blast radius on real, non-adopt target projects is therefore
**unmeasured**, not zero. Tracked as `trg-aedcfe7b` rather than left as an
implicit assumption in this ADR.

## Self-Review (references/iteration-reviews.md checklist)

1. **Spec Compliance** — pass. Both literal ACs implemented and test-pinned;
   AC-level binding, a new producer-wiring CLI, and a machine-readable ledger
   schema were all considered and deliberately rejected as out of scope.
2. **Error Handling** — pass. `check_binding_completeness` fail-closes on
   missing `--commit`, a failed regen (`None`), an `ac_error`, and any regen
   exception via the SAME `_infra_result` path `check_cross_layer_coverage`
   already uses; `.get(...) or {}` guards absent `coverage`/`required_layers`.
3. **Security Basics** — pass. No user input, no SQL/HTML, no secrets; local
   git/manifest analysis reading fields an existing gate already reads.
4. **Test Quality** — pass. 28 tests (13 pure-evaluator + wrapper skip/error
   paths added after the F0 diff-coverage gate found the wrapper at 50%
   line coverage, then 4 more from the external code-review cascade) assert
   on verdict outcomes, not internals; 100% line coverage on both new files;
   plus the empirical dry-run above recorded rather than merely asserted.
5. **Performance Basics** — pass. No N+1/unbounded loop; adds one more
   expensive regen call at the same cost class as two pre-existing ones
   (disclosed, not fixed — see Rejected #5).
6. **Naming & Structure** — pass. New files follow the exact sibling-gate
   split precedent (`_layer_coverage_removal.py`/`layer_coverage.py`);
   `iterate_checks.py` is an existing ADR-125 bloat exception deliberately
   bumped 1085→1087 with the baseline updated in the same diff.
   `test_layer_coverage_binding.py` crossed the 300-LOC guideline (354 lines)
   after the code-review test additions and was split into
   `test_layer_coverage_binding.py` (pure evaluator, 184 lines) +
   `test_layer_coverage_binding_wrapper.py` (CheckResult wrapper + wiring,
   220 lines) — same p3.2 precedent (`test_traceability_contract*.py`),
   flagged by the shared worktree's Stop-hook bloat gate.
7. **Affected Boundaries** — n/a. No serialized format's shape changed and
   no new producer/consumer pair introduced; this unit only reads the
   EXISTING `coverage`/`required_layers`/`required_layers_source` fields P3.2
   already defined. `risk_recheck.json`'s `touches_io_boundary` did not fire.
8. **Test Hygiene Probe** — pass. `scan_test_hygiene.py --diff` → no findings.

## External-Plan-Review-Findings

| # | Severity | Source | Finding (short) | Disposition |
|---|---|---|---|---|
| 1 | high | glm | No dry-run of blast radius before wiring a HARD gate | accepted-and-fixed — dry-run above: 0 hard / 1 advisory across all 20 active FRs |
| 2 | high | openai | Plan declines to wire producers despite the "producers emit" title | rejected-with-reason — scope deliberately narrowed to the require half; deferral tracked in `campaign.md` (P3.5/follow-up card) |
| 3 | high | openai | No authoritative rule for deriving "the highest observable layer" | accepted-and-fixed — `_highest_ok_layer` docstring pins the exact existing `_cov_status` eligibility contract; unrecognised-label test added |
| 4 | medium | glm | Emit-half deferral has no tracked owner | accepted-and-fixed — `campaign.md` P3.3 line updated with an explicit deferral note |
| 5 | medium | openai | Migration boundary: a previously-valid FR could unexpectedly HARD-fail | accepted-and-fixed, disposition corrected at Stage-3 doubt-review — legacy/defaulted-**source** FRs route ADVISORY (pre-rollout valve); dry-run confirms 0 HARD today. **Correction:** the boundary is the provenance MARKER (`inferred_legacy`/`defaulted_legacy`), not FR **age** — a genuinely old FR authored via the normal `explicit` path gets no grace period on its next unrelated touch. See "Rollout blast-radius measurement" scope caveat. |
| 6 | medium | openai | Test matrix omits ambiguity cases (multiple required layers, declared-higher-than-evidence, empty required_layers) | accepted-and-fixed — dedicated tests added for each case |
| 7 | medium | openai | Ledger reconciliation described as a method, not a concrete deliverable | accepted-and-fixed — explicit per-FR table (walk date / bullet count / post-walk-citation count) added to the ledger doc |
| 8 | medium | glm | AC2 has no defined deliverable | accepted-and-fixed — same table as #7 |
| 9 | low | glm | A mirrored severity table will drift from `evaluate_cross_layer`'s | accepted-and-fixed — extracted shared `route_gap_severity`; parity test pins both gates route through it |
| 10 | medium | glm | Unrecognised layer label behaviour unspecified | accepted-and-fixed — docstring specifies rank-below-canonical; dedicated test added |
| 11 | low | glm | Ledger citation method spot-verified on only two rows | accepted-and-fixed — investigated further via git-blame cross-check, found confounded (bulk commit `28491e1c9`), documented as a negative result with the residual gap disclosed |
| 12 | low | openai | Third independent expensive regen call, justified only by precedent | rejected-with-reason (disclosed, not fixed) — see Rejected #5; deferred to a future consolidation pass |
| 13 | — | glm (summary) | Overall: producer work + highest-layer contract underspecified before this can show end-to-end behaviour | addressed by findings #2/#3/#5 above; verdict overall was "reject" from openai / "revise" from glm — both providers' concrete findings are individually dispositioned above |

## Stage-3 Doubt-Review Findings (PR #687, internal cascade)

Spec-review and code-review both passed clean. Doubt-review independently
re-derived the dry-run number against the live corpus (confirmed genuine:
20/20 `inferred_legacy`) rather than trusting the ADR's claim, then attacked
the claim's *scope* rather than its arithmetic.

| # | Severity | Finding (short) | Disposition |
|---|---|---|---|
| D1 | high | The dry-run measures this monorepo's own self-referential, adopt-bootstrapped corpus (100% `inferred_legacy`), not the target-project population `shared/scripts/` actually ships to; a greenfield `/shipwright-project` FR is `explicit` immediately and gets no grace period. Blast radius on real target projects is unmeasured, not zero. | accepted-and-tracked — "Rollout blast-radius measurement" section above amended with an explicit scope caveat; `trg-aedcfe7b` minted as the concrete tracked owner (options: fixture-corpus dry-run, or a rollout-cutoff/transition rule) |
| D2 | medium | The Consequences section and finding #5's disposition described the safety boundary as FR **age** ("a previously-valid FR"), but the code's actual boundary is the provenance **marker** (`inferred_legacy`/`defaulted_legacy`), which is orthogonal to age and only coincides with it in this one bootstrapped corpus. | accepted-and-fixed — Consequences section and finding #5's disposition row corrected above to state the marker-based boundary precisely |

## External-Code-Review-Findings

| # | Severity | Source | Finding (short) | Disposition |
|---|---|---|---|---|
| 1 | high/medium | openai + glm | Producer "emit" half deferred without a guaranteed owner card | rejected-with-reason (design already settled at plan-review) — AND accepted-and-fixed on the incremental ask: minted `trg-875104ac` as the concrete tracked fallback owner, referenced from `campaign.md` and here, so "P3.5 or a follow-up" is a real card id, not prose |
| 2 | medium | openai | Rank-only comparison lets a binding declare an untested HIGHER layer and read as clean | rejected-with-reason — by design (division of labor with the sibling `evaluate_cross_layer` gate, which already fail-closes on a declared-but-not-`ok` layer); this exact scenario was raised and accepted at plan-review (finding #6 above) and is pinned by `test_binding_declared_higher_than_any_evidence_is_clean` |
| 3 | low | openai | Wrapper full-path test only exercised a clean manifest | accepted-and-fixed — added `test_wrapper_full_path_hard_gap_propagates` (real hard-gap manifest through the real wrapper call) |
| 4 | low | glm | Unrecognised-label fail-open when `required_layers` is empty reads inconsistently with the docstring's fail-closed framing | accepted-and-fixed — `_highest_ok_layer`'s docstring now states the asymmetry explicitly and why it is unreachable from a real manifest, rather than leaving it implicit |
| 5 | low | glm | `test_registered_in_run_all_checks` only checks the name is present, not correct wiring | accepted-and-fixed — added `test_run_all_checks_binding_gap_propagates_to_failure`, a real gap through the full `run_all_checks` list |
| 6 | low | glm | Truncated gap lists (`[:6]`) gave no "+N more" indicator | accepted-and-fixed — both hard/advisory branches now append `(+N more)`; two dedicated truncation tests added |

Both providers' overall verdict was `revise`; every actionable, non-duplicate
finding above is either fixed in this diff or has a recorded, non-silent
reason. See `reviews.json`'s `external_code` entry for the raw payload.
