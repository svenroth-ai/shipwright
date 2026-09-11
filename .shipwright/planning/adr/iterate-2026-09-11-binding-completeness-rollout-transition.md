# One-time rollout transition grace for check_binding_completeness

## Context

Stage-3 doubt-review on PR #687 (P3.3, `check_binding_completeness`'s own
launch), tracked as `trg-aedcfe7b`, found that the gate's existing "legacy
valve" (a gap routes ADVISORY instead of HARD when `required_layers_source`
is `inferred_legacy`/`defaulted_legacy`) does not protect a binding that was
already `explicit` (author-declared, not legacy-inferred) *before the gate
existed*. The next unrelated touch to such an FR HARD-blocks on a staleness
the gate itself could never have flagged when the binding was written.
Measured, not hypothetical: `shipwright-webui` promoted 9 FRs from
`inferred_legacy` → `explicit` on 2026-09-07 (PR #440), the same day this
gate merged — those 9 get zero grace today. The card's own revision history
explicitly and repeatedly reprioritized a transition/cutoff rule (option b)
over measuring blast radius via a fixture corpus (option a), with the
explicit instruction: "cut the transition on the gate's own rollout, not on
a date typed by hand."

## Decision

Add a one-time, per-repo transition rule in a new sibling module,
`_layer_coverage_rollout.py`: a HARD-routed gap is downgraded to ADVISORY
(`LayerGap.reason = "BINDING_INCOMPLETE_TRANSITION"`) when the FR's
`required_layers` value at HEAD is a **non-empty superset of** (not merely
equal to) what the SAME project's own git history shows for that FR
at-or-before the gate's own rollout instant (2026-09-07T16:09:19Z UTC — PR
#687's merge commit, `263c9197e6428134ad4e97c55384bf5dad89cbc1`, the instant
this code first existed anywhere), AND the FR's title still matches (a
manifest key can outlive the requirement it names — a repurposed FR keeping
its id must not inherit a predecessor's grace).

The comparison is **deliberately source-agnostic**: it does not require the
rollout snapshot's `required_layers_source` to already read `explicit`, only
that the VALUE was already there. This is the design's central judgment
call — see "Resolution of the architecture-review split" below for why.

The rollout instant is resolved **per calling project**, never a hardcoded
monorepo SHA: `resolve_rollout_commit` runs `git rev-list -1
--before=<epoch> <commit_hash>` against the CALLING project's own history,
then re-verifies the resolved commit's own committer timestamp in Python
before trusting it (belt-and-suspenders against `git rev-list
--before=<garbage>` silently resolving to "now" — measured directly against
this repo). The cutoff is passed as an **epoch integer**, never the ISO
string, for the same reason. A shallow clone is detected
(`--is-shallow-repository`) and short-circuited to "no grace" rather than
risk reading a truncation artifact as a real historical state.

`rollout_manifest` reuses `_layer_coverage_regen`'s own
`_load_collector`/`_archive_tree`/`_build` (never re-implementing archive
extraction) to build a full manifest snapshot at the resolved commit,
`with_evidence=False` (required_layers/required_layers_source are parsed
straight from spec.md, never evidence-derived). The wrapper
(`layer_coverage_binding.py`) calls this **lazily** — only once a candidate
HARD gap already exists — since it is a third, potentially expensive
archive+collector build at the same cost class as the two `regenerate_base_head`
already pays.

## Consequences

An `explicit` (or promoted-to-`explicit`) binding whose declared layers
already existed, unchanged or since-widened, before the gate's own rollout
now survives its next unrelated touch as an ADVISORY finding instead of a
HARD block — closing the exact gap `trg-aedcfe7b` measured. A binding
narrowed, replaced, or newly minted after the rollout instant is judged
normally (HARD), matching today's behaviour exactly. `evaluate_cross_layer`
and the AC-level keystone gate are untouched — both share `route_gap_severity`
but neither gains this leniency in this diff (deliberate, tracked deferral —
see Out-of-Scope below and the new triage follow-up card). This mechanism
becomes a **permanent** part of the gate's behaviour: a fixed historical
reference point and a per-project resolution routine that future maintainers
of this gate family must know about, the same way they already need to know
about the pre-existing legacy-source valve.

## Rationale

The rollout-manifest-snapshot approach (comparing the VALUE a spec.md parse
already trusts) was chosen over a cheaper git-blame-on-the-spec-row
alternative because line-level git-blame against a reformatted/reordered
markdown table is a known-fragile primitive — this exact confound
(a bulk-authoring commit swallowing every prior edit's real date) was
already hit and documented as a negative result in the original P3.3 ADR's
Rejected #4, for an adjacent problem (the evidence-ledger `(E)`-bullet
reconciliation). Reusing the archive+collector machinery `regenerate_base_head`
already trusts for base/head avoids introducing a second, less-tested
git-history primitive for the same class of comparison.

Source-agnostic, superset-based comparison (rather than exact-match,
source-gated) is the design that actually protects the measured population:
an exact-match rule would deny grace to any post-rollout *widening* edit,
punishing partial improvement harder than inaction (internal plan review,
opus); a source-gated rule (requiring the rollout snapshot's
`required_layers_source` to already read `explicit`) would deny grace to
precisely `shipwright-webui`'s 9 FRs — they were `inferred_legacy` at the
resolved rollout snapshot and only promoted to `explicit` afterward, value
unchanged (external plan review, glm). A value-preserving relabel is
metadata catching up with a fact that already existed, not the operator
"writing a new binding under the gate's watch."

## Resolution of the architecture-review split

The architecture-mode review (brief: should this mechanism exist at all,
options A/B/C) split: **openai approved** option A (this design) as the
smallest mechanism that closes the measured population without weakening
enforcement for new bindings; **glm rejected** it on two high-severity
grounds — (1) *proportionality*: the failure this defends against (a false
HARD block whose fix is a one-line `required_layers` edit reflecting
evidence the FR already demonstrates) is a cheap, self-correcting cost, and
a standing time-travel mechanism to avoid it is disproportionate; (2)
*simpler-alternative*: a one-time backfill (hand-annotate the known pre-gate
FRs into the existing legacy-valve label set, ship nothing in the verifier)
solves the measured population with zero new permanent logic.

**This ran `--autonomous`, with no live operator turn to arbitrate the
split.** glm's proposed alternative is a narrower instance of exactly the
"measure/patch by hand" approach (the card's own option (a)) the card's
revision history explicitly and repeatedly moved away from, with the
operator's own explicit, standing instruction: "cut the transition on the
gate's own rollout, not a date typed by hand." A hand-annotation backfill is
precisely a date/fact-typed-by-hand act, repeated per adopting project,
forever — it does not generalize past the one measured population the way
the operator explicitly asked the fix to ("closes the gap... not just for
this monorepo"). glm's proportionality argument is not rebutted as a
*standalone* technical claim; it is overridden here by an explicit, standing
user directive this run had no channel to relitigate synchronously. Recorded
transparently, per the skill's contradiction protocol adapted for
`--autonomous` mode, rather than silently picking a side.

## Out of Scope

- Extending this transition grace to `evaluate_cross_layer` (P3.1) or the
  AC-level keystone gate (`_keystone_layer_gap.py`, P3.7) — both call the
  same shared `route_gap_severity`, and both would need their OWN rollout
  instants (each gate shipped on a different date) if extended.
  Deliberately deferred; tracked as a new triage follow-up card (mirrors the
  `trg-875104ac` precedent from the original P3.3 ADR).
- Fixing plugin-adoption-date vs framework-ship-date precision — a target
  project that adopts a much older plugin version and only later upgrades to
  one carrying this gate can author a binding in good faith, gate-unaware,
  well after 2026-09-07 wall-clock, and still get no grace. Fixing this
  precisely needs new infrastructure (per-project plugin-version-adoption
  tracking) this card does not build — disclosed in `_layer_coverage_rollout.py`'s
  own module docstring, same precedent as every other named-but-unfixed gap there.
- The `schema_version` 3-vs-4 manifest question the doubt-review card raised
  in an earlier revision — withdrawn by the card's own later revision after
  re-verifying `shipwright-webui`'s manifest is already schema_version 4.
- Re-running/estimating option (a) (a representative greenfield fixture
  corpus dry-run) — the card's own re-scoping raised option (b) above option
  (a) because it removes the risk rather than merely measuring it.

## Rejected alternatives

1. **Git-blame on the FR's spec.md row, compared against a fixed ISO-date
   cutoff**, instead of a resolved-commit-manifest-snapshot diff. Rejected:
   blaming a single line inside a markdown table is fragile against
   reformatting/reordering that touches the line without changing the
   cell's *value* — the original P3.3 ADR's own Rejected #4 already
   documents hitting exactly this confound (a bulk-authoring commit
   swallowing every prior edit's real date) for an adjacent problem.
2. **Exact-match comparison** (rollout value == head value) instead of a
   superset check. Rejected: punishes a post-rollout WIDENING edit — an
   operator who partially improved a stale binding — harder than one who
   left it untouched entirely (internal plan review, opus).
3. **Requiring the rollout snapshot's `required_layers_source` to already
   read `explicit`** before granting grace. Rejected: excludes the measured
   motivating population outright — `shipwright-webui`'s 9 FRs were
   `inferred_legacy` at the resolved rollout snapshot, only promoted to
   `explicit` afterward with the value unchanged (external plan review,
   glm).
4. **Grace-by-diff-against-merge-base** (compare head's `required_layers`
   only against THIS run's own merge-base, not a separately-resolved
   historical snapshot) — surfaced by opus during internal plan review.
   Rejected: this would over-grant grace to essentially every pre-existing
   binding forever, since almost no binding is touched between merge-base
   and HEAD in an unrelated iterate — defeating the gate's entire
   enforcement purpose for the pre-existing (~20-FR) population the legacy
   valve does not already cover.
5. **Reusing `lib/manifest_at_commit.py`** (`read_manifest_at_commit`, used
   by `promote_required_layers.py`'s evidence-anchor path) instead of a
   fresh archive+collector build. Rejected: that helper reads the
   *committed* `.shipwright/compliance/test-traceability.json` via `git show
   <sha>:<path>` — exactly the derived-snapshot trust this gate family's own
   R3 rule forbids as an enforcement source (a committed manifest can be
   stale, missing at an older commit, or absent entirely in a repo that
   gitignores it). `rollout_manifest` instead regenerates from `spec.md` via
   the same collector `regenerate_base_head` already trusts for base/head —
   the two helpers solve genuinely different problems (provenance-anchor
   evidence vs. enforcement-grade regeneration) and are not interchangeable.
6. **Unconditional amnesty for every `explicit` binding** (architecture
   brief's option B, no snapshot resolution at all) and **do nothing / measure
   only** (option C) — see "Resolution of the architecture-review split" above.
7. **A hand-annotation backfill** (glm's architecture-review counter-proposal:
   tag the known pre-gate FRs into the existing legacy-valve label set,
   ship nothing in the verifier) — see "Resolution of the architecture-review
   split" above; rejected as a per-repo, non-generalizing, hand-typed act the
   operator's own standing instruction explicitly ruled out.

## Disclosed, not fixed

Mirrors the original P3.3 ADR's own precedent of naming a residual gap
rather than eliminating it at disproportionate cost — full detail in
`_layer_coverage_rollout.py`'s and `_layer_coverage_binding.py`'s own module
docstrings:

- A shallow clone or a brownfield repo with rewritten history may have no
  commit reachable at-or-before the rollout instant even though its code is
  conceptually older — treated identically to "genuinely born after
  rollout" (no grace), the conservative direction for an optional leniency.
- Plugin-adoption-date vs framework-ship-date (see Out of Scope above).
- `rollout_manifest`'s blanket `except Exception` conflates a genuine "no
  pre-rollout history" answer with an unrelated infra hiccup (collector
  crash, tar-extraction failure) — both degrade to `None` (no grace) with no
  diagnostic. Fail-open only ever withholds an optional leniency, never
  grants a false one, so the worst outcome is an unexplained HARD block
  identical to today's pre-existing behaviour.
- Exact title-match is a blunter instrument than strictly needed for the
  repurposed-FR case it exists to catch — an ordinary wording tweak to an
  FR's description forfeits grace forever, even though the FR is the same
  requirement. Accepted: there is no separate immutable identity token to
  compare instead, and `behavior_changed_keys` already treats a title edit
  as a real behaviour-change signal for the same reason.
- `git rev-list --before` assumes monotonically increasing commit dates and
  can pick a non-optimal ancestor on out-of-order committer-date history (a
  rebase, or clock skew across a merge). The narrow failure mode this leaves
  open is picking an OLDER-than-necessary pre-rollout commit — the
  conservative direction, since it can only withhold grace a slightly-newer,
  still-legitimate snapshot would have granted.

## Rollout blast-radius measurement (empirical dry-run, AC6)

This monorepo's own `.shipwright/compliance/test-traceability.json` is 100%
`inferred_legacy` (already fully covered by the pre-existing legacy valve),
so a dry-run against it would be tautological — it cannot demonstrate this
rule's effect. Instead, ran the transition-aware evaluator against a
synthetic fixture modeling the actual measured population: an FR whose
`required_layers` value already existed (source `inferred_legacy`) at a
resolved pre-rollout snapshot and was later promoted to `explicit` with the
value unchanged (the `shipwright-webui` shape), plus a genuinely-new FR
minted after the rollout instant as a control.

- **Before this rule** (`rollout=None`, today's behaviour): the promoted FR's
  gap routes HARD (its `required_layers_source` is `explicit`, and the
  legacy valve does not apply); the control FR also routes HARD (it is
  genuinely new, so this is correct either way).
- **After this rule**: the promoted FR's gap routes ADVISORY
  (`BINDING_INCOMPLETE_TRANSITION`) — grace granted. The control FR is
  unaffected — still HARD, exactly as intended (a genuinely new binding
  gets no grace).

Hard-count delta on this fixture: **2 → 1** (one gap moved HARD → ADVISORY;
the genuinely-new control stayed HARD). See
`.shipwright/planning/iterate/iterate-2026-09-11-binding-completeness-rollout-transition/dry_run_fixture.py`
for the exact fixture and assertions this measurement reproduces.

## Self-Review (references/iteration-reviews.md checklist)

1. **Spec Compliance** — pass. All 6 ACs implemented and test-pinned: superset/
   source-agnostic grace (AC1), narrowing/replacement/newly-minted forfeits
   grace (AC2), greenfield no-grace (AC3), per-repo resolution (AC4),
   `route_gap_severity` untouched + tracked deferral (AC5), synthetic-fixture
   dry-run recorded above (AC6).
2. **Error Handling** — pass. `rollout_manifest` never raises (degrades to
   `None`, no grace, on any git/archive/collector failure); `resolve_rollout_commit`
   fails closed on a shallow clone, an empty commit hash, or any git failure.
3. **Security Basics** — pass. No user input, no injected git ref strings (the
   epoch constant is a fixed literal; `commit_hash` reaches `_run_git` as an
   argv element, never shell-interpolated); reuses the same hardened
   archive-extraction path (`_safe_extract`) every sibling gate already uses.
4. **Test Quality** — pass. Real-git tests for `resolve_rollout_commit`/
   `rollout_manifest` (before/at/after the cutoff, shallow clone verified via
   `--is-shallow-repository` after clone, empty-commit-hash, cache behaviour);
   pure-evaluator tests for every transition-grace branch including the
   empty-rollout-value and title-mismatch edge cases found in external code
   review; wrapper-level test proving the wiring end-to-end.
5. **Performance Basics** — pass. `rollout_manifest` is LAZY — only invoked
   once a candidate HARD gap already exists, never on a clean run — and is
   process-cached by `(root, commit)`, same precedent as `_layer_coverage_regen`'s
   own base-manifest cache.
6. **Naming & Structure** — pass. New module follows the exact sibling-gate
   split precedent already established in this family
   (`_layer_coverage_removal.py`/`layer_coverage.py`); test files split at the
   same 300-LOC guideline that flagged `test_layer_coverage_binding.py`
   (`test_layer_coverage_binding_transition.py` new sibling), same p3.2/P3.3
   precedent.
7. **Affected Boundaries** — n/a. No serialized format's shape changed; this
   unit reads the EXISTING `required_layers`/`required_layers_source` fields
   at one more, older git ref.
8. **Test Hygiene Probe** — pass, no findings on the diff.

## External-Plan-Review-Findings

| # | Severity | Source | Finding (short) | Disposition |
|---|---|---|---|---|
| 1 | high | openai | Mini-plan text specified an equality comparator, contradicting the spec's superset AC | accepted-and-fixed — comparator is a superset check (`rollout_layers <= head_layers`); mini-plan text corrected to match |
| 2 | high | openai | Title-identity safeguard absent from the mini-plan's comparator signature/test plan | accepted-and-fixed — `_norm_title` comparison added to `binding_predates_rollout`; dedicated test added |
| 3 | medium | openai | "Source-agnostic" design conflicted with mini-plan test wording ("edited/promoted since rollout" grouped together) | accepted-and-fixed — split into distinct scenarios; the promoted-value-unchanged case is a dedicated grace-granted test |
| 4 | medium | openai | Planned dry-run used this repo's own (100% legacy) manifest, contradicting the synthetic-corpus AC | accepted-and-fixed — synthetic fixture built and recorded above; mini-plan step corrected |
| 5 | medium | openai/glm | Git-history resolution can silently fail (shallow clone, unreachable commit) without distinguishing failure classes | accepted-and-fixed for the shallow-clone case (explicit `_is_shallow` check, tested); the general infra-failure case is disclosed, not fixed (see "Disclosed, not fixed") |
| 6 | low | openai/glm | `required_layers` canonicalization (ordering/duplicates) unspecified before comparison | accepted-and-fixed — comparison is a `set()`-based subset check, order- and duplicate-independent by construction |
| 7 | medium | glm | Design-notes text described exact-match, contradicting the spec's superset AC (same root cause as #1) | accepted-and-fixed — see #1 |
| 8 | medium | glm | `with_evidence=False` parsing needs verification it never derives `required_layers`/source from evidence flags | accepted — confirmed by code inspection (`_requirement_parse.py` parses these fields from spec.md text alone; the collector's `evidence` param only feeds `coverage`/link status, never these two fields) |
| 9 | medium | glm | Fragile against shallow clones / old-schema manifests at the resolved ref | accepted-and-fixed for shallow clones (see #5); old-schema-manifest handling deferred as unmeasured/low-likelihood (this framework has not shipped a schema_version bump since P3.3's own rollout instant) |
| 10 | low | glm | Internal contradiction: mini-plan's dry-run step named this repo's own manifest while the spec's AC6 named a synthetic fixture | accepted-and-fixed — mini-plan corrected to match the spec |
| 11 | low | glm | New `LayerGap.reason` enum value — audit exhaustive-match consumers | accepted — confirmed `reason` is only ever used in message-building strings (`_advisory_tag`, `_binding_result`), never matched exhaustively elsewhere |
| 12 | low | glm | Process-level cache key must include both `project_root` and `commit_hash`; tests must clear it between cases | accepted — confirmed the cache key is `(str(project_root), commit_hash)`; every real-git test uses an autouse `clear_rollout_cache()` fixture |
| 13 | low | glm | Clock-skew / misconfigured committer dates in target repos | accepted, disclosed as a known limitation (recorded commit timestamps are trusted as-is; not worth engineering around) |
| 14 | low | glm | No meaningful security exposure | confirmed, no action needed |

## Architecture-Review-Findings

See "Resolution of the architecture-review split" above for the full
reasoning; summarized:

| # | Severity | Source | Finding (short) | Disposition |
|---|---|---|---|---|
| A1 | — | openai | Approve: option A is the smallest mechanism that closes the measured gap without weakening enforcement for new bindings | accepted (design proceeds) |
| A2 | high | glm | Proportionality: the failure's fix is a cheap, self-correcting one-line edit; a standing mechanism is disproportionate | acknowledged, overridden by the operator's own standing, explicit, thrice-reaffirmed instruction to build the transition rule rather than rely on manual fixes |
| A3 | high | glm | Simpler alternative: a one-time hand-annotation backfill solves the measured population with zero new logic | rejected-with-reason — a hand-annotation backfill is precisely the "date/fact typed by hand, per repo" approach the operator's own instruction explicitly ruled out, and does not generalize past the one measured population |
| A4 | medium | glm | Forecloses: couples the verifier to the readability of its own input format's past (old refs) | acknowledged as a real, permanent maintenance cost; accepted as the price of closing a gap the operator explicitly prioritized over the cheaper, non-generalizing alternative |

## External-Code-Review-Findings

| # | Severity | Source | Finding (short) | Disposition |
|---|---|---|---|---|
| 1 | high | glm | Every grace-granting test fixture forced `head`'s title to "changed" to trigger the behaviour-change signal, while leaving the rollout snapshot's title at its default — since `binding_predates_rollout` requires an exact title match, this either fails the tests as written or proves nothing about the title-match guard | accepted-and-fixed — rewrote `test_layer_coverage_binding_transition.py` and the wrapper's transition test to trigger the behaviour-change signal via a `required_layers` diff between base/head instead, keeping title constant across base/rollout/head except in the one test that deliberately exercises a title mismatch |
| 2 | high | glm | Missing deliverables: no ADR, no architecture.md update, no triage follow-up card, no recorded dry-run | accepted-and-fixed — this ADR, the architecture.md bullet, the triage follow-up card, and the dry-run above all landed in this diff |
| 3 | medium | glm | `rollout_manifest`'s blanket exception-swallowing conflates infra failure with genuine greenfield, with no diagnostic | accepted, disclosed not fixed — see "Disclosed, not fixed"; same disposition the internal plan review independently reached |
| 4 | low | glm | Duplicated `evaluate_binding_completeness` call (once to find a candidate HARD gap, once with `rollout` passed) risks future divergence between the two invocations | accepted, disclosed not fixed — both calls take the identical arguments plus the added `rollout` parameter; a future signature change would need updating in one place regardless, and restructuring to avoid the second call is a larger change than this fix warrants |
| 5 | high | openai | An FR that existed at rollout with an EMPTY `required_layers` vacuously satisfied the subset check (`set() <= anything`), granting grace to a binding that is, in substance, brand new | accepted-and-fixed — `binding_predates_rollout` now requires a non-empty rollout value before the subset check; dedicated pure-evaluator and matrix tests added |
| 6 | medium | openai | The shallow-clone test cloned from a local PATH with `--depth 1`; git ignores `--depth` for a same-machine path clone (only a `file://` URL forces the real network-clone code path), so the clone was not actually shallow | accepted-and-fixed — clone now uses `origin.as_uri()`, with an explicit assertion that `--is-shallow-repository` reports `true` before the resolver is exercised |
| 7 | medium | openai | Missing dry-run/ADR/triage/architecture-doc deliverables (same root cause as glm #2) | accepted-and-fixed — see #2 |

Every finding from both providers is either fixed in this diff or has a
recorded, non-silent reason; see `reviews.json`'s `external_code`/`plan`
entries for the raw payloads.

## External-Code-Review-Findings, round 2 (after round-1 fixes landed)

| # | Severity | Source | Finding (short) | Disposition |
|---|---|---|---|---|
| 8 | medium | openai | Blanket `except Exception` in `rollout_manifest` converts infra failures into "no grace", indistinguishable from greenfield; suggested surfacing via `_infra_result` | rejected-with-reason — converting to an infra ERROR would HIDE an already-correct HARD finding behind an infrastructure-failure message (this function only runs after a candidate HARD gap already exists), the opposite of fail-closed intent; reasoning finalized in the module's exception-handler comment and "Disclosed, not fixed" list after being raised independently by opus, glm, and openai |
| 9 | medium | glm | `with_evidence=False` claim in the design notes was not demonstrably implemented — the `_build` call site passes a bare `{}` with no visible flag, and `_evio` is unpacked but unused | accepted-and-fixed — added an explicit comment at the call site plus a dedicated test, `test_rollout_build_is_evidence_independent_for_required_layers`, proving `required_layers`/`required_layers_source` are byte-identical between an empty- and non-empty-evidence build of the same tree while `coverage` differs |
| 10 | low | glm | No test exercises the Python-side `committer_epoch > GATE_ROLLOUT_AT_EPOCH` re-check independently of git's own `--before` filtering (a regression there would pass the whole suite) | accepted, disclosed not fixed — constructing a reliable out-of-order-committer-date fixture is disproportionate effort for a low-severity gap already named in the module's own "Disclosed, not fixed" list (opus's out-of-order-history finding) |
| 11 | low | glm | `_ROLLOUT_CACHE` does not document its history-immutability assumption | accepted-and-fixed — one-line docstring note added, matching the disclosure style used elsewhere in the module |
| 12 | low | openai/glm | Duplicated `evaluate_binding_completeness` call (round-1 finding #4) re-raised; confirmed still present, still disclosed | no change — same disposition as round 1's #4, re-confirmed sound (the one existing wrapper test would fail if the second call were deleted, so the disclosure is verified accurate, not just asserted) |
| 13 | low | glm | `reviews.json`'s `external_code`/`code`/`spec` entries were still `pending` while this ADR's findings tables already recorded dispositions | resolved by process, not code — this ADR is written progressively during the run; all entries are recorded via `record_review_pass.py` before finalization, closing the gap this finding correctly caught mid-flight |

Both providers' round-2 verdict was `revise`, no contradiction; every finding above is fixed or has a recorded, non-silent reason.
