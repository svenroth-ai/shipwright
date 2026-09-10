# The keystone AC gate's post-merge detective arm

**Run-ID:** iterate-2026-09-10-keystone-detective-arm
**Campaign:** req3-04c-ac-identity-wave2 follow-up — ruling Q5, triage card `trg-a05c4aba`
(filed at PR #702's merge, `docs(triage)` commit 8f78b93be, #708)

## Context

`check_keystone_ac_gate.py` (P3.6) is a preventive, in-run check: it only fires on
`pull_request` events and trusts the local manifest its own CI job just regenerated, because
same-run evidence needs no cross-machine trust. Two gaps follow directly: a direct push to
`main` is never gated at all, and even a PR-merged commit's *in-run* verdict is never re-checked
against a real trunk CI run after the fact. The triage card scoped a complementary DETECTIVE
control that asks, post-merge, whether a commit already on `main`'s tip genuinely satisfied the
gate — composing with the existing cross-commit resolvers (`ci_provenance.resolve_ci_verification`,
`ci_execution_evidence.resolve_execution_evidence`) rather than reusing the preventive gate's own
same-run producer.

An external Architecture Review (Branch A, both openai/codex and glm/openrouter, `reject` on the
brief as originally scoped — a standalone CLI + `ci.yml`-absence drift test + exit-code contract)
found that scope disproportionate: today's steady-state output on a real commit is
`run_not_verified` (a separately-carded structural-drift fix in P3.6 §2.3 is the blocker), and an
advisory-only control with no wiring and no committed consumer is operationally indistinguishable
from no control. Full findings and the reconciliation are in the iterate spec §3.5.

## Decision

Build the classification logic and the resolver composition as a plain, importable Python module
only — no CLI, no `argparse`, no exit-code contract, no `ci.yml`-absence drift test. Two new
modules: `shared/scripts/tools/verifiers/_keystone_detective_core.py` (`classify_commit` — the
orchestration half: resolves the target commit to a canonical SHA, resolves its first parent,
calls `resolve_ci_verification` then, only if `verified`, `resolve_execution_evidence`, and
returns a `DetectiveResult` naming one of seven outcomes) and
`_keystone_detective_manifest.py` (`build_verified_manifest` — the pure half: substitutes
CI-verified per-link `status`/`executed` into a deep copy of the committed manifest, matched by
link id within each requirement key, fail-closed on any unmatched or malformed link). Full design,
the seven-outcome table, and all fifteen acceptance criteria (AC-D1..D15) are in the iterate spec.

## Consequences

A real, tested, callable `classify_commit(commit, *, project_root)` exists for a future CLI,
compliance-audit consumer, or periodic sweep to call — without committing to a specific
CLI/wiring contract before a real consumer exists to shape one. Nothing currently invokes it in
CI; it ships dormant by design (Architecture Review's own framing), so it earns no false sense of
an active control. The two deliberately deferred follow-ups (a structural-drift fix in P3.6 §2.3,
and a real periodic-sweep consumer) must land in that order — the drift fix first, since a
consumer built against today's `run_not_verified` steady state would need to change again once the
drift fix ships.

## Rationale

Composing with `resolve_ci_verification`/`resolve_execution_evidence` (rather than reusing the
preventive gate's own `_read_head_manifest`, which trusts the current job's own worktree) is what
makes this a genuine DETECTIVE control and not a restatement of the preventive one: it judges a
foreign commit using evidence bound to a real trunk CI run, the same cross-commit trust boundary
`ci_provenance.py`'s own docstring names as Q2. The seven-way outcome taxonomy (never a bare
pass/fail) is what lets a caller distinguish "never had a qualifying trunk run" from "the run
genuinely failed to verify" from "the query itself failed" — the triage card's explicit demand
that this control never ship an open-ended "TBD" for its own failure modes.

## Rejected alternatives

1. **The original CLI-shaped brief** (standalone script, `ci.yml`-absence drift test, exit-code
   contract) — rejected by both external reviewers as disproportionate ownership with no bound
   consumer; see spec §3.5.
2. **A stored `ac_id → tests → last_verified_commit` baseline** (raised and already rejected in
   the preventive gate's own plan review, ruling Q1) — `ci.yml` re-runs every suite on every PR,
   so there is nothing selective for a ledger to compensate for, and a self-reported baseline is
   exactly the trust class this control exists to avoid.
3. **Per-layer (not per-requirement, cross-layer) duplicate-id scoping** in
   `build_verified_manifest` — raised in external code-review round 2 (glm), traced and kept
   as-designed: substitution itself matches by id alone with no layer parameter, so narrowing the
   duplicate check would silently reintroduce the exact last-write-wins ambiguity AC-D11 exists to
   close.
