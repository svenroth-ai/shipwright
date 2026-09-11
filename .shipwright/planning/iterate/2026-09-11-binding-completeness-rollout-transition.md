# Iterate Spec: binding-completeness-rollout-transition

- **Run ID:** iterate-2026-09-11-binding-completeness-rollout-transition
- **Type:** change
- **Complexity:** medium
- **Status:** done

## Goal

`check_binding_completeness` (P3.3, F11, `shared/scripts/tools/verifiers/layer_coverage_binding.py`,
live since PR #687 / 2026-09-07) HARD-blocks a behaviour-changed FR whose
declared binding (`required_layers`) understates its own executed-passing
evidence, UNLESS its `required_layers_source` is a known legacy marker
(`inferred_legacy`/`defaulted_legacy`). Stage-3 doubt-review on PR #687 (D1,
tracked as `trg-aedcfe7b`) found this valve does not cover a real, measured
population: a binding that was already `explicit` — correctly, deliberately
authored, not adopt-inferred — **before this gate existed** gets no grace at
all, and the very next unrelated touch to that FR (e.g. an AC wording edit)
HARD-blocks on staleness the gate itself could never have flagged when the
binding was written. Confirmed live, not hypothetical: `shipwright-webui`
promoted 9 FRs from `inferred_legacy` to `explicit` on 2026-09-07 (PR #440),
the same day this gate merged; those 9 get zero legacy-valve grace today.

Add a one-time transition/cutoff rule: a binding whose `required_layers`
VALUE (regardless of what `required_layers_source` it carried historically —
source-agnostic, see rationale below) is already covered by what this repo's
own history recorded for that FR at-or-before `check_binding_completeness`'s
own rollout instant (2026-09-07T16:09:19Z UTC — the committer time of PR
#687's merge commit, `263c9197e6428134ad4e97c55384bf5dad89cbc1`, the instant
this code first existed ANYWHERE) is routed ADVISORY instead of HARD, the
same bucket the legacy-source valve already uses. "Already covered" is a
SUPERSET check (head's `required_layers` ⊇ the rollout snapshot's value), not
exact-match — a post-rollout WIDENING edit keeps grace (it must not be
punished harder than leaving the binding untouched), while a narrowing or
wholesale replacement forfeits it, and the FR's title must still match (a
repurposed FR id does not inherit a predecessor's grace). A binding narrowed,
replaced, or newly minted since that instant is judged normally — the author
had (or could have had) a gate-aware toolchain at that point, so no grace
applies. Source-agnostic is deliberate: the measured motivating population
(`shipwright-webui`'s 9 FRs) were themselves promoted `inferred_legacy` →
`explicit` the same day the gate merged, value unchanged — a design that also
required the rollout snapshot's source to already read `explicit` would
exclude the very case this rule exists for. This works per target-project
(each repo supplies its own git history for the "at or before
2026-09-07T16:09:19Z" resolution), not just for this monorepo, closing the
gap the doubt-review measured as monorepo-only in the original dry-run.

## Acceptance Criteria

- [x] A behaviour-changed FR whose `required_layers` value at HEAD is a
      superset of (or equal to) what this repo's own history already
      recorded for that FR at-or-before the gate's rollout instant
      (2026-09-07T16:09:19Z) routes ADVISORY, not HARD — regardless of what
      `required_layers_source` the FR carried at that historical snapshot
      (source-agnostic: a same-day `inferred_legacy` → `explicit` promotion,
      value unchanged, still gets grace).
- [x] The same FR, if its `required_layers` value was narrowed or replaced
      with an unrelated value on/after the rollout instant, or is newly
      minted on/after that instant, is judged normally (HARD, per the
      existing rule) — the transition grace is not a blanket amnesty for
      every binding, only for a value that genuinely predates the gate.
- [x] A repo with no commit at or before the rollout instant (born entirely
      after 2026-09-07T16:09:19Z — the greenfield case the doubt-review
      flagged) resolves no rollout snapshot and gets no grace, matching
      today's documented no-legacy-valve-for-greenfield behaviour exactly.
- [x] The resolution is per-repo (uses the calling project's own git
      ancestry via `--before=<rollout instant>`), not a hardcoded commit SHA
      from this monorepo — the WebUI's 9 promoted FRs must be judged against
      the WebUI's *own* history, since this monorepo's commit SHA has no
      meaning inside another repository.
- [x] `route_gap_severity` (shared by `evaluate_cross_layer` and the AC-level
      keystone gate) is untouched — this transition rule is scoped to
      `check_binding_completeness`/`evaluate_binding_completeness` only, per
      the doubt-review card's own scope. Documented as a deliberate,
      tracked deferral (not a silent gap) for the sibling gates.
- [x] Empirical dry-run recorded (same convention the original ADR set), using
      a SYNTHETIC fixture corpus, not this monorepo's own manifest — this
      monorepo's `required_layers_source` population is 100% `inferred_legacy`
      today (the legacy valve already covers it), so a dry-run against it
      would be tautological (zero hard-count delta, proving nothing about the
      rule this change adds). The fixture models the actual motivating
      population instead: an `explicit`-sourced (or promoted-to-`explicit`)
      binding whose value predates the rollout instant, alongside a
      genuinely-new post-rollout binding as a control. Record the before/after
      hard-count delta for that fixture.

## Spec Impact

- **Classification:** none
- **NONE justification:** framework-internal change to a shared F11 verifier
  module (`shared/scripts/tools/verifiers/`). No project-level FR/spec.md
  changes — mirrors the original P3.3 ADR's own "Affected Boundaries: n/a,
  this unit only reads the EXISTING coverage/required_layers/
  required_layers_source fields" self-review finding; this change reads one
  more existing field set (a historical snapshot of the same fields) and
  changes no serialized schema.

## Out of Scope

- Extending the same transition grace to `evaluate_cross_layer` (P3.1) or the
  AC-level keystone gate (`_keystone_layer_gap.py`, P3.7) — both also call
  the shared `route_gap_severity`, and both would have their OWN, different
  rollout instants if this treatment were extended to them. Deliberately
  deferred; tracked as a new triage follow-up card in this same diff (mirrors
  the `trg-875104ac` precedent from the original P3.3 ADR).
- The `schema_version` 3-vs-4 manifest question the doubt-review card raised
  in an earlier revision — re-verified 2026-09-11 (in the card's own text)
  that `shipwright-webui`'s manifest is already schema_version 4; the
  scope caveat was withdrawn by the card's author before this run started.
- Re-running/estimating option (a) (a representative greenfield fixture
  corpus dry-run) — the card's own re-scoping raised option (b) (this
  transition rule) above option (a) because it removes the risk rather than
  merely measuring it; not duplicating both.
- Wiring the "emit" half (producers writing a complete binding at
  create/update time) — out of scope for this card, already tracked
  separately as `trg-875104ac`.

## Design Notes

New sibling module `shared/scripts/tools/verifiers/_layer_coverage_rollout.py`
(kept separate from `_layer_coverage_regen.py`, which is already at the
300-LOC guideline) resolves, per target project, the commit at-or-before the
gate's fixed rollout instant and builds a manifest snapshot there
(`with_evidence=False` — `required_layers`/`required_layers_source` are
parsed straight from `spec.md`, never evidence-derived, so no evidence
collection pass is needed for this comparison). `evaluate_binding_completeness`
gains an optional `rollout` parameter (default `None`, so every existing
pure-evaluator test call site is unaffected); when a would-be-HARD gap's FR
already carried the SAME `required_layers` value in that snapshot, the gap is
downgraded to advisory with a new `LayerGap.reason` value
(`BINDING_INCOMPLETE_TRANSITION`) so the CheckResult message says
"pre-rollout transition grace" instead of misleadingly reusing the
legacy/collision wording for an `explicit`-sourced gap.

## Affected Boundaries

n/a — no new producer/consumer pair, no serialized format's shape changes.
This unit reads the EXISTING `required_layers`/`required_layers_source`
fields (already defined by P3.2) at one more git ref than before; the
manifest schema itself is untouched.

## Architecture Review

Brief submitted (`iterate-2026-09-11-binding-completeness-rollout-transition/architecture_brief.md`):
should this transition mechanism exist at all, offering three options — **A**
(resolved-commit snapshot comparison, this design), **B** (unconditional
amnesty for every `explicit` binding, no snapshot resolution), **C** (do
nothing; measure blast radius only).

**Verdicts split: openai=approve (option A), glm=reject.** No contradiction
in the technical read — both reviewers converge on the same tradeoff, they
just weigh it oppositely. glm's high-severity findings: (1) *proportionality*
— the failure this defends against (a false HARD block whose fix is a
one-line `required_layers` edit reflecting evidence the FR already
demonstrates) is a self-correcting, cheap cost, and a standing time-travel
mechanism to avoid it is disproportionate; (2) *simpler-alternative* — a
one-time backfill (tag the known pre-gate FRs into the existing
`inferred_legacy`/`defaulted_legacy` label set, ship nothing in the
verifier) solves the measured population with zero new permanent logic.
openai's approval reasons identically about the population but weighs the
scoped, per-repo, title-matched superset design as the smallest mechanism
that closes it without weakening enforcement for new bindings.

**Resolution (autonomous run, no live operator turn to arbitrate):** proceeded
with option A. glm's proposed alternative — hand-annotating the known FRs
per repo — is a narrower instance of the "measure/patch by hand" approach
(option (a) in the doubt-review card's own numbering) that the card's own
revision history explicitly and repeatedly moved AWAY FROM in favor of this
mechanism, with the operator's own explicit instruction: "cut the transition
on the gate's own rollout, not a date typed by hand." A hand-annotation
backfill is exactly a date-typed-by-hand act (worse: a fact-typed-by-hand act,
repeated per repo, per adopting project, forever) — it does not generalize
past the one measured population (`shipwright-webui`'s 9 FRs) the way the
operator explicitly asked the fix to ("closes the gap... not just for this
monorepo"). glm's proportionality point is fair as a STANDALONE technical
argument and is not rebutted by that reasoning — it is overridden by an
explicit, standing user directive this run has no channel to relitigate. Not
silently overridden: recorded here, in the review record, and in the ADR's
own findings table, exactly as an unresolved provider disagreement should be
per the skill's contradiction protocol, adapted for `--autonomous` mode where
no synchronous STOP-and-ask is possible.

## Confidence Calibration

- **Boundaries touched:** git subprocess invocation (`git rev-list
  --before=<epoch> --first-parent`, `git archive`/`git show`, wrapped by the
  existing `_safe_extract` used by every sibling gate) and the fixed
  `GATE_ROLLOUT_AT_EPOCH` wall-clock constant — a process boundary and a
  historical-time boundary, not a serialized-format boundary (Affected
  Boundaries above is `n/a` for the latter).
- **Empirical probes run:**
  - Real-git resolution: `test_resolve_rollout_commit_finds_a_commit_strictly_before_cutoff`,
    `..._accepts_a_commit_exactly_at_the_boundary_instant`,
    `..._none_when_repo_born_entirely_after_rollout` each build an actual git
    repo with `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` pinned to an explicit UTC
    offset (never ambient clock or bare local-time), so pass/fail cannot
    depend on when the suite runs.
  - Shallow-clone fail-closed: `test_resolve_rollout_commit_none_for_a_shallow_clone`
    clones via `origin.as_uri()` (a same-machine PATH clone is a no-op for
    `--depth`; only a `file://` URL forces git's real network-clone path) and
    asserts `--is-shallow-repository` returns `"true"` before proceeding, so a
    future git behavior change fails the test loudly instead of silently
    becoming a full-clone no-op.
  - Evidence-independence: `test_rollout_build_is_evidence_independent_for_required_layers`
    builds the identical tree with `evidence={}` vs. a populated evidence
    dict and asserts `required_layers`/`required_layers_source` are
    byte-identical while `coverage` differs — closing the round 2 external
    code review gap where this was asserted in a comment but never pinned by
    a test.
  - Empirical dry-run (AC6): `dry_run_fixture.py` — synthetic fixture modeling
    the actual motivating shape (an FR promoted `inferred_legacy` →
    `explicit` with unchanged layers) plus a genuinely-new control FR. Real,
    executed output: `BEFORE (rollout=None): hard=2 advisory=0` →
    `AFTER (transition rule applied): hard=1 advisory=1` — the control FR
    stays HARD, only the pre-existing binding downgrades.
  - Full `shared/tests` regression: 10481 passed, 33 skipped, 20 deselected,
    0 failures (1185.09s) — confirms zero behavior change outside this gate's
    own transition-grace branch.
- **Confidence-pattern check:** Asymptote (depth) — the git-resolution path is
  probed against REAL git history and a REAL shallow clone, not simulated
  timestamps or a hand-built manifest, closing the two risks a synthetic-only
  test suite would have left open (approxidate/timezone drift, `--depth`
  silently no-op'ing). Breadth (coverage) — every branch of
  `binding_predates_rollout` is independently exercised (source-agnostic
  promotion, widening survives, narrowing forfeits, empty rollout value
  forfeits, title-mismatch forfeits, no-rollout-snapshot forfeits, FR-absent-
  from-snapshot forfeits, collision gaps never consulted). `cross_component`
  does not apply — this diff touches neither the merge/churn/event-log
  resolver, hooks, pipeline validators, nor campaign drain.

## Verification (medium+)

- **Surface:** none
- **Justification:** pure Python verifier logic + git-history resolution
  inside the Shipwright framework itself; no startable web/cli/api surface
  for a target project exists to run against (same as the original P3.3
  change, and every sibling gate in this family — `layer_coverage.py`,
  `_keystone_layer_gap.py` — which are all `surface: none` for the same
  reason: they are pure functions over regenerated manifests, verified by
  their own unit + real-git integration test suite, not by driving a UI).

## Test Completeness Ledger

| Behavior | Disposition |
|---|---|
| A behaviour-changed, previously-`explicit` FR whose value at HEAD is a superset of the rollout snapshot's value routes ADVISORY (source-agnostic — historical source doesn't matter) | tested — `test_transition_grace_downgrades_an_unchanged_explicit_binding`, `test_transition_grace_is_source_agnostic_for_a_promoted_binding` |
| A widening edit since rollout still gets grace | tested — `test_transition_grace_survives_a_widening_edit_since_rollout` |
| A narrowing edit since rollout forfeits grace | tested — `test_transition_grace_withheld_when_binding_narrowed_since_rollout` |
| An empty rollout-snapshot value is not a value that "already existed" (vacuous-subset guard) | tested — `test_transition_grace_withheld_when_rollout_value_was_empty` |
| FR absent from the rollout snapshot forfeits grace | tested — `test_transition_grace_withheld_when_fr_absent_from_rollout_snapshot` |
| No rollout snapshot at all (git resolution failed/greenfield) forfeits grace | tested — `test_transition_grace_withheld_with_no_rollout_snapshot_at_all` |
| A repurposed FR id (title mismatch) does not inherit a predecessor's grace | tested — `test_transition_grace_withheld_when_title_shows_fr_was_repurposed` |
| A collision gap never consults the rollout snapshot | tested — `test_transition_grace_never_applies_to_a_collision_gap` |
| Pure `binding_predates_rollout` matrix (equal/superset/narrowed/empty/title-mismatch/no-rollout) | tested — `test_binding_predates_rollout_pure_helper_matrix` |
| Wrapper wiring: a HARD gap downgrades to advisory end-to-end via `layer_coverage_binding.py` | tested — `test_wrapper_transition_grace_downgrades_hard_gap_to_advisory` |
| `resolve_rollout_commit` finds a commit strictly before / exactly at the cutoff instant | tested — real-git, pinned author/committer dates |
| `resolve_rollout_commit` returns `None` for a repo born entirely after rollout (greenfield, AC3) | tested — `test_resolve_rollout_commit_none_when_repo_born_entirely_after_rollout` |
| `resolve_rollout_commit` returns `None` for a genuinely shallow clone (verified via `--is-shallow-repository`, not assumed) | tested — `test_resolve_rollout_commit_none_for_a_shallow_clone` |
| `resolve_rollout_commit` returns `None` for an empty/garbage commit hash | tested — `test_resolve_rollout_commit_none_for_empty_commit_hash` |
| `rollout_manifest` builds a snapshot from the resolved pre-rollout commit, keyed by FR id (not spec-directory-derived key) | tested — `test_rollout_manifest_builds_a_snapshot_from_the_resolved_pre_rollout_commit` |
| `rollout_manifest` is evidence-independent for `required_layers`/`required_layers_source` (evidence only affects `coverage`) | tested — `test_rollout_build_is_evidence_independent_for_required_layers` |
| `rollout_manifest` returns `None` when no rollout commit resolves | tested — `test_rollout_manifest_none_when_no_rollout_commit_resolves` |
| `rollout_manifest` caches by `(root, commit)` — no re-resolution on a cache hit | tested — `test_rollout_manifest_caches_by_root_and_commit` |
| Empirical dry-run: synthetic fixture shows a real 2→1 hard-count delta (AC6) | tested — `dry_run_fixture.py`, executed, output recorded in the ADR |
| `route_gap_severity` body unchanged (AC5 scope boundary) | tested — re-confirmed by spec-reviewer against the actual diff; zero lines touched in `_layer_coverage_core.py` |
| 12 pre-existing `test_layer_coverage_binding.py` behaviors (non-transition gaps, collision routing, legacy-source valve) | tested — regression: all still green, zero behavior change on the non-transition path |

0 untested-testable rows.
