# Corroborated-trunk-ancestry check for the check_binding_completeness rollout grace (`trg-4380c61a`)

## Context

PR #755 (`iterate-2026-09-12-project-gate-rollout-transition`) fixed a
post-merge PR-review gate finding, `trg-4380c61a`: the FR-01.02 #5/#10
rollout-transition grace's trust anchor — a target project's own commit
committer timestamp — is forgeable. A contributor controls every commit on
their own branch, including `GIT_COMMITTER_DATE`, so a backdated, never-merged
commit on that branch satisfies a bare `--before=<epoch>` check without ever
having existed on trunk at that instant. That PR's own ADR
(`iterate-2026-09-12-project-gate-rollout-transition.md`, "Post-merge
PR-review gate finding, fixed") fixed this for its own gate family
(`_project_gate_rollout.py`) but explicitly left the identical gap in the
`check_binding_completeness` precedent's own copy (`_layer_coverage_rollout.py`,
closing `trg-aedcfe7b`/PR #721) untouched — scoped out by the operator's
explicit instruction at the time, and tracked forward as the still-open half
of `trg-4380c61a`.

## Decision

`_layer_coverage_rollout.py`'s `resolve_rollout_commit(project_root,
commit_hash)` now requires a second, independent condition alongside the
existing committer-epoch check: the candidate commit must be an ancestor of
(or equal to) `git_helpers._branch_base_commit`'s resolved trunk boundary for
`commit_hash` — the identical fix `_project_gate_rollout.py` already shipped
for its own sibling gate family, reusing the same already-hardened,
already-tested helper rather than inventing a second trust-anchor mechanism.
No corroborated trunk boundary (no `origin` remote, an ambiguous/renamed
trunk name) withholds grace entirely, the same fail-closed direction the
module already used for a shallow clone or an empty `commit_hash`.

## Consequences

A forged, backdated, unmerged branch commit no longer receives
`check_binding_completeness` rollout-transition grace; a genuine pre-rollout
commit already reachable from the project's own trunk is unaffected. Every
existing `test_layer_coverage_rollout.py` fixture now advances a simulated
`refs/remotes/origin/main` alongside each commit by default (`on_trunk=True`,
mirroring `test_project_gate_rollout.py`'s identical fixture change), standing
in for "already merged" — a real `git clone` of a target project already
provides this shape, so a genuine calling project sees no behavior change on
the common path. `trg-4380c61a` is now closed in full: both rollout-transition
grace copies anchor to corroborated trunk ancestry, not a bare timestamp.

## Rationale

Reusing `git_helpers._branch_base_commit` — already covering this exact
"resolve the trusted trunk boundary" problem for other gates in this same
framework — keeps the fix small, already-hardened, and already-tested in its
own right, rather than a new trust-anchor mechanism for this module alone.
Mirroring `_project_gate_rollout.py`'s fix verbatim (same helper, same
fail-closed direction, same test-fixture shape) keeps the two sibling
resolvers behaviorally identical even though each stays its own
separately-shipped module — the P3.3 ADR's own "each gate family gets its own
rollout instant and resolver" precedent, unchanged by this fix.

## Rejected alternatives

1. **Leave `_layer_coverage_rollout.py` unfixed.** Rejected: it is the
   identical, already-disclosed vulnerability class PR #755 already fixed for
   its own gate family; leaving the `check_binding_completeness` copy open
   indefinitely was only ever a scoping decision for that PR, not a judgment
   that the gap is acceptable.
2. **Factor a shared cross-family rollout-git primitive now** (commit
   resolution: shallow-clone guard, `rev-list --before`, committer-epoch
   re-verification, trunk-ancestry check) instead of duplicating the trunk
   check inline. Rejected here too: the P3.3 ADR's own "Out of Scope"
   precedent already establishes per-gate-family resolvers since each gate
   ships on its own date; this is now a security-relevant duplication
   (`trg-fcb3ee97`, disclosed, not fixed by this change either) but a
   cross-cutting refactor of an already-shipped, heavily-reviewed sibling
   module remains a larger, separately-scoped change than a like-for-like
   trust-anchor fix warrants.

## Scope

`_layer_coverage_rollout.py` only (the `check_binding_completeness` gate
family). `trg-fcb3ee97` (extracting a shared per-family rollout primitive)
stays open and untouched by this change, per the rejected alternative above.

## Tests

`test_resolve_rollout_commit_refuses_a_forged_unmerged_branch_commit` builds a
genuine pre-rollout trunk commit (tracked as merged via `on_trunk=True`) and a
separate, never-merged branch carrying a backdated commit
(`on_trunk=False`), and asserts the forged commit gets no grace while the
genuine trunk commit still does — confirmed, before writing the fix, that this
test fails against the unpatched `resolve_rollout_commit`, a real regression
test. `test_resolve_rollout_commit_none_without_a_corroborated_trunk_anchor`
pins the new fail-closed branch when no trunk candidate resolves at all. Both
new tests live in a new sibling file,
`test_layer_coverage_rollout_trust_anchor.py`, split from
`test_layer_coverage_rollout.py` at the 300-LOC guideline (adding them inline
would have pushed that file to 328 lines). Every existing
`test_layer_coverage_rollout.py`/`test_layer_coverage_rollout_trust_anchor.py`
fixture now defaults to `on_trunk=True`. Re-ran the full rollout suite plus
`test_layer_coverage_binding_transition.py`/`test_layer_coverage_binding_wrapper.py`
(41 tests, all green — the wrapper/transition suites mock `resolve_rollout_commit`
directly and needed no change) and the full `shared/tests` suite; `uvx
ruff@0.15.15 check .` clean.

## Doubt-Review-Findings

Advisory-must-address (`references/iteration-reviews.md`): each doubt answered
in writing below, fix or reasoned rebuttal, per that convention. Technical
detail deliberately kept out of this git-tracked file (constitution's
sensitive-detail rule) — full writeup in the gitignored `Spec/` report named
below.

| # | Severity | Finding (short) | Disposition |
|---|---|---|---|
| 1 | high | `check_binding_completeness`'s own base/head diff resolver (`_layer_coverage_regen._merge_base`, one call away from this module) still resolves its trunk boundary through a less-hardened path than the anchor this run just fixed, and a HARD gap must exist before this module's rollout grace is even consulted | disclosed, not fixed — genuinely distinct from `trg-4380c61a` (detection, not leniency), filed as new triage card `trg-945e4854`, full detail in `Spec/trg-doubt-merge-base-atu-bypass.md`. Out of scope: hardening `_merge_base` is a change to a shared base/head-diff primitive other layer-coverage gates depend on, materially larger than a like-for-like trust-anchor mirror of PR #755 |
| 2 | high | The corroborated-trunk anchor's guarantee ("a value the PR author cannot set") holds only when `origin`'s remote-tracking refs come from a fetch the checked commit's author does not control — not necessarily true of this framework's own local, pre-push iterate run | accepted-and-documented — a shared, unchanged property of `_project_gate_rollout.py`'s identical, already-shipped anchor, not introduced or worsened by this fix; recorded as an explicit invariant in the module docstring rather than a code change, per the reviewer's own suggested resolution |
| 3 | medium | Whether a real CI `pull_request` checkout actually leaves ≥2 independently-resolving trunk candidate names (required by `_branch_base_commit`'s own corroboration rule) is unverified empirically | disclosed, not fixed — same shared-risk framing as #2: a property of the already-shipped, already-reused `_branch_base_commit` helper, not specific to this diff; the fail-closed direction (withhold grace rather than trust one name) is the same conservative choice `_branch_base_commit`'s own design already makes everywhere else it is used |
| 4 | low | The new tests only exercise the two simplest branches (forged commit refused, no-anchor fail-closed), not `_branch_base_commit`'s own multi-candidate-disagreement/rewound-trunk scenarios through this caller's plumbing | rebutted — those scenarios are already covered by `_branch_base_commit`'s own test suite at its definition site; re-exercising them through every caller would duplicate coverage without pinning any caller-specific behavior, since this module only ever threads `commit_hash` through unchanged and treats every non-`True` outcome identically to today's other fail-closed branches |

## Self-Review (references/iteration-reviews.md checklist)

1. **Spec Compliance** — pass. Threads the identical, already-reviewed fix
   from PR #755 through the one remaining copy the operator named
   (`_layer_coverage_rollout.py`), with the same helper, same fail-closed
   direction, and equivalent adversarial test coverage.
2. **Error Handling** — pass. `resolve_rollout_commit` still never raises;
   every new failure path (`_branch_base_commit` returning `None`, the
   `rev-list --count` ancestry probe returning non-zero or non-"0") degrades
   to `None` (no grace), the same direction every other branch in this
   function already takes.
3. **Security Basics** — pass. This diff closes the exact trust-boundary gap
   it exists to fix; no new git argument is user/PR-controlled beyond what
   `_branch_base_commit` (already hardened, already used elsewhere in this
   framework) itself accepts.
4. **Test Quality** — pass. Adversarial forged-commit test confirmed to fail
   against the pre-fix code before the fix was written; fail-closed
   no-anchor test added; full existing suite re-run green.
5. **Performance Basics** — pass. One additional `merge-base` walk plus one
   `rev-list --count` call, only on the already-lazy path (only reached after
   a candidate HARD gap and a passing committer-epoch check) — same cost
   class `_project_gate_rollout.py`'s identical fix already accepted.
6. **Naming & Structure** — pass. New test file follows the established
   per-module test-file split precedent in this same test tree; both touched
   files stay under the 300-LOC guideline.
7. **Affected Boundaries** — n/a. No serialized format's shape changed; this
   unit's own return contract (`str | None`) is unchanged.
8. **Test Hygiene Probe** — pass, no findings on the diff.
