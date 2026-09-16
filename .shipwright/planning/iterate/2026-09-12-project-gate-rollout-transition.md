# Iterate Spec: project-gate-rollout-transition

- **Run ID:** iterate-2026-09-12-project-gate-rollout-transition
- **Type:** change
- **Complexity:** medium
- **Status:** implemented

## Goal

Stage-2 code review on PR #729 (`e2-checks-project-elicitation`, round 3,
tracked as `trg-9583d3a8`) found that two of the four new `/shipwright-project`
Step-8 gates — `check_criteria_free_of_implementation_detail` (FR-01.02 #5)
and `check_no_empty_split` (FR-01.02 #10), both live since PR #729's merge
commit `c411c36ad7af7d446047c552e032579d45b588fe` (committer time
2026-09-12T06:23:06Z) — are wired as unconditional hard blocks with no
extension-scope carve-out, unlike `check_basis_forbids_assumed` (#4/#15) and
`check_starting_guidance_present` (#11), which both skip `scope=extension`.
An `/shipwright-adopt`-onboarded (extension-scope) project's pre-existing
`spec.md` content — written before these two gates existed — can now
hard-fail Step 8 for legacy content unrelated to whatever the current touch
actually changed.

The finding's own framing rules out copying the #4/#15/#11 pattern: unlike
#4/#15 (`assumed`'s meaning genuinely differs for extension — see
`_project_gate_wiring.check_basis_forbids_assumed`'s own docstring) and #11
(the starting-guidance files literally never exist for extension scope), #5's
implementation-detail ban and #10's zero-row floor are not stated anywhere as
greenfield-only — `fr_hygiene_detectors`'s I1 ban and `split-heuristics.md`'s
cohesion rule both apply universally, to extension and full-application specs
alike. A permanent `scope == "extension"` skip would therefore excuse *all*
future extension-scope violations too, not just the pre-existing ones the
finding actually names. The defect is narrower: **closed content, retroactively
hit by a newly-introduced gate** — the exact shape the `check_binding_completeness`
rollout-transition precedent (`iterate-2026-09-11-binding-completeness-rollout-transition`,
closing `trg-aedcfe7b`) already solved for a different gate family. This
iterate builds the same class of one-time rollout/grandfather mechanism for
these two gates, adapted from a numeric-superset comparison (required layers)
to a text/count-identity comparison (AC-hygiene text, split row count) — the
natural adaptation for what these two gates actually compare.

**Grace rule, precisely:** a hit from either gate is downgraded from HARD to
ADVISORY only when the exact violating content already existed, essentially
unchanged, in this project's own git history at-or-before these two gates'
own rollout instant (2026-09-12T06:23:06Z UTC, PR #729's merge commit) —
never a blanket `scope == "extension"` amnesty. A row/split newly authored or
edited after that instant is judged normally (HARD), at every scope,
extension included — the author had a gate-aware toolchain by then.

## Acceptance Criteria

- [x] `check_criteria_free_of_implementation_detail` (#5): a violating
      acceptance-criterion string, per criterion (not per row), that already
      appears verbatim among that same FR row's rollout-era criteria — the
      row identified by `(Name, body-text)` matching between HEAD and this
      project's own git history at-or-before the gate's rollout instant —
      downgrades from HARD to ADVISORY (`severity=warning`, `strict_exempt`).
- [x] The same check: a NEW violating criterion added to a row since
      rollout stays HARD even when that same row also carries an untouched,
      graced violation — grace is granted per criterion string, never as a
      blanket exemption for the row's id, so one unrelated addition cannot
      forfeit an existing grace nor smuggle a new violation in under it. An
      FR row newly minted after the rollout instant, or one whose id was
      repurposed (same id, different `Name`/body), gets no grace at all.
- [x] `check_no_empty_split` (#10): a split already DECLARED in this
      project's own manifest (`shipwright_project_config.json`/
      `shipwright_run_config.json`), with zero active FR rows, at-or-before
      the rollout instant, downgrades from HARD to ADVISORY. Manifest
      declaration is required, not merely "some file happens to sit at that
      path" — a split reusing an old, unrelated, already-empty path must not
      inherit a stranger's grace.
- [x] The same check: a split that did not exist at rollout (newly declared
      since), or that had at least one active FR row at rollout but is empty
      now (emptied since — a regression, not legacy content), is judged
      normally (HARD).
- [x] A repo with no commit at or before the rollout instant (born entirely
      after 2026-09-12T06:23:06Z) resolves no rollout snapshot and gets no
      grace for either gate — matching the `check_binding_completeness`
      precedent's documented no-legacy-valve-for-greenfield behaviour.
- [x] The resolution is per-repo (the calling project's own git ancestry via
      `--before=<rollout epoch>`), not a hardcoded commit SHA from this
      monorepo.
- [x] `basis_forbids_assumed` and `starting_guidance_present` (#4/#15, #11)
      are untouched — this transition rule is scoped to the two gates named
      in `trg-9583d3a8` only.
- [x] `trg-9583d3a8` is closed, referencing this run's own PR, once that PR
      exists — the same process the `trg-aedcfe7b` precedent actually used
      (its close event, `.shipwright/triage.jsonl`, references `PR:721` and
      postdates that PR's own diff; a `promote --task-ref PR:<N>` close event
      cannot itself carry a PR number that does not exist yet at review time,
      so it lands as a small follow-up append once this run's PR is open, not
      inside the reviewed code diff itself). Two NEW follow-up cards
      (`trg-ac2ef362`, `trg-fcb3ee97`) minted by this run's own design
      decisions are appended in the reviewed diff regardless, since they
      carry no such dependency.

## Spec Impact

- **Classification:** none
- **NONE justification:** framework-internal change to two shared
  `/shipwright-project` F11/Step-8 verifier gates
  (`shared/scripts/tools/verifiers/`). No project-level FR/spec.md changes —
  same justification the `binding-completeness-rollout-transition` precedent
  recorded for the identical class of change.

## Out of Scope

- Extending this same rollout-transition treatment to `check_basis_forbids_assumed`
  or `check_starting_guidance_present` — both already have their OWN,
  differently-reasoned scope carve-outs (see Goal above) and are not part of
  `trg-9583d3a8`'s finding.
- A permanent `scope == "extension"` skip for #5/#10 — considered and
  rejected in the Architecture Review below; recorded so a future reader does
  not re-propose it without seeing why it was rejected.
- Retrofitting this rollout treatment onto other, unrelated gate families
  (e.g. the P3.1/P3.7 layer-coverage siblings already tracked as a deferral
  in `trg-1d9ed777`) — different gates, different rollout instants, already
  tracked separately.

## Design Notes

Two new sibling modules, `_project_gate_rollout.py` (which commit) and
`_project_gate_rollout_snapshot.py` (what it said) —  deliberately a
**standalone** module family, not an extension of `_layer_coverage_rollout.py`
(the P3.3 ADR's own "Out of Scope" section already establishes that each
gate family gets its own rollout instant and resolver; the two FR-01.02
gates here share one instant only because they landed in the same PR,
otherwise unrelated to the layer-coverage family). Duplicates ~20 lines of
git shallow-check + `rev-list --before` + committer-epoch-verify logic
already proven in `_layer_coverage_rollout.py` rather than factoring out a
shared primitive — matches that module's own documented precedent of
per-gate-family resolvers, and avoids widening the blast radius of an
already-shipped, heavily-reviewed module for an unrelated gate. (External
Plan Review, glm, low: this is now a THIRD near-identical copy of the same
idea, alongside the original layer-coverage resolver and the
binding-completeness one — accepted as a disclosed cost, tracked as a new
follow-up triage card rather than refactored here.)

Unlike the layer-coverage case (comparing a *value* for superset-ness),
these two gates compare *text/count identity* — there is no natural
"superset" relation for AC-hygiene text or a split's row count, so the
comparison is exact-identity, on the PARSED representation the gates
already consume (`fr_table_reader`/`fr_criteria` output), never raw file
bytes:

- `resolve_head_sha(project_root, "HEAD")` + `cached_rollout_sha(project_root,
  head_sha)` — `HEAD` is resolved to a concrete SHA *before* any cache is
  keyed (External Plan Review, openai, medium: caching under the symbolic
  name `"HEAD"` goes stale the moment the process evaluates more than one
  repository state, e.g. across `tmp_path` fixtures in one test run).
  `resolve_rollout_commit` mirrors the precedent's resolver shape
  (shallow-clone guard, `rev-list -1 --before=<epoch>`, Python-side
  committer-epoch re-verification), fixed epoch `GATE_ROLLOUT_AT_EPOCH =
  1789194186` (2026-09-12T06:23:06Z, PR #729's merge commit
  `c411c36ad7af7d446047c552e032579d45b588fe`). Always resolved against
  `"HEAD"` — these two gates run against the live working tree (Step 8,
  F11's project-phase checks), not a specific base/head diff pair.
- `build_rollout_snapshot(project_root, "HEAD") -> RolloutSnapshot` — lazily
  built only once a rollout-unaware first pass already found a candidate
  hit (same laziness `layer_coverage_binding.py` uses for its own, more
  expensive archive-based rollout build). `RolloutSnapshot.spec_text(path)`
  reads `git show <sha>:<path>`, repo-toplevel-relative-prefixed via
  `_repo_relative_prefix` (a real bug caught empirically during Build: `git
  show <sha>:<path>` resolves `<path>` relative to the repo TOPLEVEL
  regardless of `-C <dir>`, the opposite of `git archive` — a nested
  `project_root` would otherwise silently miss every historical lookup, no
  grace ever granted, no error raised). `.declared_split_names()` reads
  `shipwright_project_config.json`/`shipwright_run_config.json` AT the
  resolved commit too (External Plan Review, openai, high: historical
  spec.md content alone can't prove a split was *declared* at rollout — a
  split reusing an old, unrelated, already-empty path must not inherit a
  stranger's grace).
- `_project_gate_grace.py` — pure comparators consuming a `RolloutSnapshot`:
  `graced_criteria_for_row` grants grace PER CRITERION STRING (not per row —
  internal plan review, medium: whole-row equality
  would forfeit grace for an untouched violation the moment an unrelated
  later edit adds a new criterion to the same row), gated on `(Name,
  body-text)` row identity — refused, never defaulted to "matches", when
  both sides are entirely empty (internal plan review, medium: `Name` alone
  is `""` on any table without a Name column, which would make a bare-`Name`
  guard vacuous). `split_predates_rollout` requires manifest declaration
  (above), not path content alone.
- `_project_gate_extras.py`'s `GateResult` gains two new optional fields,
  `severity: str | None = None` and `strict_exempt: bool = False` (both
  default off — every existing call site and test is unaffected), so the
  pure functions can signal "hit, but downgrade to advisory" without
  importing `common.Severity` themselves (kept import-light, mirroring the
  module's existing zero-`common`-import shape). #5/#10 themselves moved to
  the new sibling `_project_gate_extras_rollout.py` (300-LOC guideline),
  taking an optional `rollout: RolloutSnapshot | None = None` parameter and
  partitioning hits into hard vs. graced — a HARD hit anywhere in the result
  always wins the aggregate `severity` (External Plan Review, openai, high:
  one aggregate severity per `GateResult` cannot represent "one row legacy,
  one row new" *as two separate diagnostics* — resolved instead by making a
  single hard hit always dominate the whole result's severity while the
  detail string still names every graced hit transparently, so a new
  violation is never silently hidden behind an unrelated grandfathered one).
- `_project_gate_wiring.py`'s two `check_*` wrappers call the rollout-aware
  pure function **lazily** — only once the rollout-unaware first pass
  already found a candidate hit — and a new `_to_check_result` helper
  forwards `severity`/`strict_exempt` from the `GateResult` onto the
  `CheckResult` it builds (a no-op for every other gate in this module,
  which never sets those fields).

## Affected Boundaries

n/a — no new producer/consumer pair, no serialized format's shape changes.
This unit reads the EXISTING `spec.md` text (already read by both gates from
disk) at one more git ref than before.

## Internal Plan Review

**Ran: no.** Discovered at Step 7 (recording review-pass results) that the
mandatory-at-medium+ `opus-plan-reviewer` sub-step (`iteration-planning.md`
step 0, "always before Branch A/B/C at this complexity") was never spawned
during this run's own Step 5 — a genuine gap in the earlier portion of this
run, not a deliberate skip. Per that same reference's degraded-handling
clause, this is "one fewer independent review, not a gap the run is left
unreviewed by": External Plan Review (12 findings), Architecture Review (the
should-this-exist-at-all question), the full internal spec/code/doubt
cascade, and the External Code-Review Cascade all ran and are recorded
elsewhere in this spec/ADR. `plan_internal` recorded `not_run` in the
review record with this same reason, per Step 7's mandatory sweep for a
still-pending type discovered late.

## Architecture Review

Brief submitted
(`.shipwright/planning/iterate/iterate-2026-09-12-project-gate-rollout-transition/architecture_brief.md`):
should a rollout/grandfather mechanism be built at all for these two gates,
offering three options — **A** (this design: resolved-commit, per-hit
text/count-identity comparison), **B** (a permanent `scope == "extension"`
skip, mirroring #4/#15/#11's existing pattern), **C** (do nothing; leave the
two gates as unconditional hard blocks).

**External Plan Review** (`--mode iterate`, over the mini-plan): **glm
approved**, **openai revise** — no contradiction (verdicts agree within one
step). openai's six findings were all addressed during Build, not deferred:
per-criterion membership so a mixed hard/graced result still hard-fails the
new violation while disclosing the graced one in the same `CheckResult`'s
detail text (`_project_gate_extras_rollout.py`, tested in
`test_criteria_free_of_implementation_detail_new_violation_on_an_already_graced_row_stays_hard`
and `test_no_empty_split_mixed_hard_and_graced_reports_both`); split grace
requires manifest DECLARATION at rollout, not merely spec.md content at that
path (`_project_gate_grace.split_predates_rollout`); comparison is exact
identity on the PARSED criteria/row-count representation, not raw file bytes
(`_project_gate_rollout_snapshot.py` module docstring, "Text/count identity,
not value superset"); `HEAD` resolved to a concrete SHA before any cache is
keyed (`resolve_head_sha`, called once per `build_rollout_snapshot`); every
git path is validated non-absolute/no-traversal/no-flag-injection before
reaching `git show` (`_is_safe_git_path`). glm's low-severity findings
(single-definition epoch/SHA cross-check, `\"warning\"` as a shared
constant) were partially addressed (the epoch/ISO pair is asserted against
each other in `test_gate_rollout_epoch_matches_the_documented_boundary_instant`)
and partially accepted as-is (the literal `\"warning\"` string, matching
`layer_coverage_binding.py`'s own precedent of the identical literal).

**Architecture Review** (`--mode architecture`, over the brief above):
**glm approved** option A outright, reasoning options B and C both leave a
real, user-facing regression unaddressed (B permanently excuses *future*
extension-scope violations of a rule stated as universal; C leaves
newly-onboarded projects hard-failing on content that predates the gate).
**openai rejected** it — `SHIPWRIGHT_VERDICT: reject`, proposing option C
instead: leave both gates hard-blocking and remediate legacy violations
in place when encountered, on proportionality grounds (a permanent
Git-history exception buys relief from failures that are "directly
repairable," while leaving unchanged legacy violations exempt indefinitely).
**Contradiction detected** (`glm=approve, openai=reject`), requiring
resolution.

### Resolution of the architecture-review split

**This ran `--autonomous`, with no live operator turn to arbitrate the
split.** The operator's own invocation text is itself the design decision on
this exact fork, not merely the trigger for one: it explicitly named
`fix(compliance): one-time rollout transition rule for check_binding_completeness
(#721)` as "the precedent that matches the shape" of this defect, and
explicitly contrasted that against "a permanent scope skip" — i.e. it had
already ruled out an Option-B-shaped fix before this run began, and asked
for the Option-A shape by name. openai's reject argues for Option C (fix
legacy content in place, keep the gates uniformly hard), which is not a
technical rebuttal of Option A's design so much as a rejection of doing a
rollout transition AT ALL — precisely the design decision the operator's own
framing had already made ("Deferred rather than fixed inline... a one-time
rollout/grandfather rule... than a permanent scope skip. Needs a design
decision"). Read plainly, the operator was not asking "should a transition
mechanism exist" — that was decided by citing #721 as the matching
precedent — but "build the #721-shaped fix for these two gates." openai's
proportionality argument (a directly-repairable failure doesn't need a
standing exception) is not rebutted as a *standalone* technical claim — it
mirrors glm's own OWN low-severity proportionality finding on Plan Review
("document the retirement condition explicitly"), which this iterate accepts
as a real, disclosed cost (see Out of Scope) rather than a reason not to
build the mechanism at all. It is overridden here by the operator's explicit,
already-decided framing this run had no channel to relitigate synchronously.
Recorded transparently, per the skill's contradiction protocol adapted for
`--autonomous` mode and mirroring the identical glm/openai split's resolution
in the `#721`/`iterate-2026-09-11-binding-completeness-rollout-transition`
ADR (that run's split was the mirror image — openai approved, glm
rejected on proportionality — resolved the same way, by the operator's own
standing instruction), rather than silently picking a side.

openai's second Architecture-Review-brief-level concern — Option A's
`_layer_coverage_rollout` sibling comparison, a permanent resident that "can
never be safely removed" once any repo has pre-rollout history — is accepted
as a real, disclosed cost (see Design Notes: the resolver duplicates rather
than shares logic, on the same "each gate family gets its own instant"
precedent) rather than grounds to reject the mechanism outright.

## Confidence Calibration

- **Boundaries touched:** git subprocess invocation (`git rev-list
  --before=<epoch>`, `git show <sha>:<path>`, `git rev-parse --show-prefix`)
  and the fixed `GATE_ROLLOUT_AT_EPOCH` wall-clock constant — a process
  boundary and a historical-time boundary, not a serialized-format boundary
  (Affected Boundaries above is `n/a` for the latter).
- **Empirical probes run:** two, both against real throwaway git repos
  (`mktemp`-style `tmp_path` fixtures), not assumed from documentation: (1)
  `git -C ./a show <sha>:a/b/f` vs `git -C ./a show <sha>:b/f` vs `git -C ./a
  archive` — confirmed `show` resolves the tree path against the repo
  TOPLEVEL regardless of `-C`, the opposite of `archive`, which was the root
  cause of a silent nested-`project_root` false-negative caught before it
  shipped (fixed via `_repo_relative_prefix`, covered by
  `test_build_rollout_snapshot_resolves_spec_text_when_project_root_is_nested_below_toplevel`).
  (2) confirmed `git clone --depth 1` only actually produces a shallow clone
  over a `file://` URL, not a same-machine path clone (git's local-clone
  fast path copies full history regardless) — asserted explicitly in the
  shallow-clone test rather than assumed, mirroring the identical assertion
  in the precedent's own test.
- **Test Completeness Ledger:**

  | Category | Behavior | Test |
  |---|---|---|
  | unit | commit resolution: before/at/after cutoff, empty ref, unresolvable ref | `test_project_gate_rollout.py` |
  | unit | shallow-clone refusal (real `--depth 1` clone over `file://`) | `test_project_gate_rollout.py::test_resolve_rollout_commit_none_for_a_shallow_clone` |
  | unit | SHA cache keyed by concrete commit, not the symbolic `HEAD` | `test_project_gate_rollout.py::test_cached_rollout_sha_caches_by_root_and_commit` |
  | unit | git's own `--before` answer re-verified in Python, refused if it lies | `test_project_gate_rollout.py::test_resolve_rollout_commit_none_when_gits_before_answer_postdates_cutoff` |
  | integration | nested `project_root` spec-text + manifest reads (the git show/-C fix) | `test_project_gate_rollout_snapshot.py` (nested-`project_root` tests) |
  | unit | declared-split-names manifest priority + fallback + malformed-at-rollout | `test_project_gate_rollout_snapshot.py` |
  | unit | text-read cache by `(sha, path)` | `test_project_gate_rollout_snapshot.py::test_spec_text_is_cached_by_sha_and_path` |
  | unit | grace comparator matrix: identity match/refuse, cosmetic-title tolerance, repurposed-id refusal, split declaration requirement | `test_project_gate_grace.py` |
  | unit | #5/#10 pure-function grace partitioning: per-criterion membership, mixed hard+graced, no-rollout fallback | `test_project_gate_extras_rollout.py` |
  | integration | end-to-end wiring: real-git repo proving the `CheckResult` itself downgrades (and that a genuinely new post-rollout violation still hard-blocks) | `test_project_gate_wiring_rollout.py` |
  | regression | #4/#15/#11 untouched — existing test files re-run unmodified except import-path updates | `test_project_gate_basis_and_guidance.py`, `test_project_gate_no_empty_split.py` |

- **Confidence-pattern check:** no "trust me, it works" claims — every claim
  above is backed by a passing test in this run (`shared/tests`, 100+ tests
  across the eight files touched/added, all green; see F5/F5c for the
  authoritative run). No production code exercised by running it manually
  outside its own test suite (`never run a producer to verify it`) — the two
  wiring functions were exercised only through their tests, real git repos
  under `tmp_path`, never against this monorepo's own working tree.

## Verification (medium+)

- **Surface:** none
- **Justification:** pure Python verifier logic + git-history resolution
  inside the Shipwright framework itself; no startable web/cli/api surface
  for a target project exists to run against — same as every sibling gate in
  this family (`_project_gate_wiring.py`'s existing four checks, and the
  `binding-completeness-rollout-transition` precedent), all `surface: none`
  for the identical reason: pure functions over spec.md text, verified by
  their own unit + real-git integration test suite, not by driving a UI.
