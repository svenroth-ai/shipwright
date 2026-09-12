# One-time rollout transition grace for FR-01.02 #5/#10 (project-phase gates)

## Context

Stage-2 code review on PR #729 (`e2-checks-project-elicitation`, round 3),
tracked as `trg-9583d3a8`, found that two of the four new `/shipwright-project`
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

The finding's own framing ruled out copying the #4/#15/#11 pattern: unlike
#4/#15 (`assumed`'s meaning genuinely differs for extension scope) and #11
(the starting-guidance files literally never exist for extension scope), #5's
implementation-detail ban and #10's zero-row floor are not stated anywhere as
greenfield-only — `fr_hygiene_detectors`'s I1 ban and `split-heuristics.md`'s
cohesion rule both apply universally. A permanent `scope == "extension"` skip
would therefore excuse *all* future extension-scope violations too, not just
the pre-existing ones the finding actually names. The card's own text named
the matching shape: "a one-time rollout/grandfather rule, matching the
precedent in `fix(compliance): one-time rollout transition rule for
check_binding_completeness (#721)`... than a permanent scope skip."

## Decision

Add a one-time, per-repo transition rule, split across two new sibling
modules — `_project_gate_rollout.py` (resolves WHICH historical commit) and
`_project_gate_rollout_snapshot.py` (reads WHAT that commit's `spec.md`/
manifest actually said) — plus a third, `_project_gate_grace.py`, holding the
pure identity/membership comparators both gates share:

- **#5** (`criteria_free_of_implementation_detail`): a violating acceptance
  criterion, one exact string at a time (never the whole row), is downgraded
  from HARD to ADVISORY (`severity="warning"`, `strict_exempt=True`) when
  that exact criterion string already existed on the SAME FR row — identified
  by `(Name, body-text)` matching, refused whenever both sides are entirely
  empty — in this project's own git history at-or-before the gate's rollout
  instant. A hard hit elsewhere in the result (a genuinely new violation, a
  repurposed FR id, a newly-minted row) always keeps the whole `GateResult`
  HARD; the graced hit is still named transparently in the detail string.
- **#10** (`no_empty_split`): a split downgrades from HARD to ADVISORY only
  when it was already **declared** (present in
  `shipwright_project_config.json`/`shipwright_run_config.json`'s own
  `splits` list, not merely "some file happens to sit at that path") at the
  rollout instant, with zero active FR rows there too.
- The rollout instant is resolved **per calling project**, never a hardcoded
  monorepo SHA: `resolve_rollout_commit` runs `git rev-list -1
  --before=<epoch> <commit_hash>` against the CALLING project's own history
  (`HEAD` first resolved to a concrete SHA via `resolve_head_sha`, so no cache
  is ever keyed by a symbolic name), then re-verifies the resolved commit's
  own committer timestamp in Python before trusting it. The cutoff is an
  **epoch integer**, never the ISO string. A shallow clone is detected
  (`--is-shallow-repository`) and short-circuited to "no grace."
- `_project_gate_wiring.py`'s two `check_*` wrappers call the rollout-aware
  variant **lazily** — only once a rollout-unaware first pass already found a
  candidate hit — and a new `_to_check_result` helper forwards
  `severity`/`strict_exempt` from the `GateResult` onto the `CheckResult`
  (a no-op for every other gate in this module).

Fixed epoch: `GATE_ROLLOUT_AT_EPOCH = 1789194186` (2026-09-12T06:23:06Z, PR
#729's merge commit `c411c36ad7af7d446047c552e032579d45b588fe`).

## Consequences

An extension project's pre-existing `spec.md` content — an implementation-
detail-laden criterion, or an empty declared split — that already existed
before these two gates' rollout now survives Step 8 as an ADVISORY finding
instead of a HARD block, closing the exact gap `trg-9583d3a8` named. Content
newly authored, edited, or newly declared after the rollout instant is judged
normally (HARD), at every scope, matching today's behaviour exactly. This
becomes a **permanent** part of both gates' behaviour: a fixed historical
reference point and a per-project resolution routine future maintainers of
this gate family must know about. `check_basis_forbids_assumed` (#4/#15) and
`check_starting_guidance_present` (#11) are untouched.

**Follow-up, `trg-4380c61a` (see "Post-merge PR-review gate finding, fixed"
below):** grace additionally requires the resolved commit to be an ancestor
of a corroborated trunk boundary, not merely committer-date arithmetic. A
project with no `origin` remote, or whose local trunk branch matches none of
the trunk-candidate names, now gets no grace at all rather than a
timestamp-only answer — the same fail-closed direction as a shallow clone,
just a narrower set of repos it now applies to.

## Rationale

Text/count identity, not value superset (unlike the layer-coverage
precedent, which compares a *value* for superset-ness — an FR's required
layers can only legitimately widen): there is no equivalent partial order for
AC-hygiene text or a split's row count, so the comparison is exact identity
on the PARSED representation the existing gates already use
(`fr_table_reader.read_active_fr_rows` row count, `fr_criteria.criteria_for`
criterion text) — never raw file bytes, so cosmetic reformatting (line
endings, whitespace) between commits does not itself forfeit grace, since
both sides are compared post-parse.

Per-criterion membership, not whole-row equality (internal plan review,
opus, medium): an earlier draft compared a row's full criteria tuple for
identity between rollout and HEAD, which would forfeit grace for an
untouched, pre-existing violating criterion the moment an unrelated later
touch added a new criterion to the same row (count/order changes, tuple
inequality). Granting grace per criterion string instead means one unrelated
addition can neither forfeit an existing grace nor smuggle a new violation in
under it.

Split declaration required, not path content alone (external plan review,
openai, high): historical `spec.md` text alone cannot prove a split was
*declared* at rollout — a split reusing an old, unrelated, already-empty path
would otherwise inherit a stranger's grace, inverting the fail-closed
direction this whole mechanism depends on. `RolloutSnapshot.declared_split_names`
reads the project's own manifest at the resolved historical commit too.

A single hard hit dominates the whole result's severity, rather than one
`GateResult` per hit (external plan review, openai, high: "a single aggregate
severity... either hides the warning or incorrectly exempts the hard
violation"): resolved by making any hard hit anywhere in the result win the
aggregate `severity`, while the detail string still names every graced hit
transparently — so a genuinely new violation on an otherwise-graced row is
never silently hidden behind the older, legitimate grace. A richer
per-hit-diagnostic model (openai's literal suggestion) was considered and
rejected as disproportionate: it would require every `CheckResult` consumer
in this framework to understand a list-of-diagnostics shape instead of one
name/ok/detail/severity tuple, for a defect this narrower fix already closes.

## Resolution of the architecture-review split

The architecture-mode review (brief: should this mechanism exist at all,
options A/B/C) split: **glm approved** option A outright, reasoning that
options B and C both leave a real, user-facing regression unaddressed (B
permanently excuses *future* extension-scope violations of a rule stated as
universal; C leaves newly-onboarded projects hard-failing on content that
predates the gate). **openai rejected** it, proposing option C instead —
leave both gates hard-blocking, remediate legacy violations in place when
encountered — on proportionality grounds: "a permanent Git-history exception
buys relief from failures that are directly repairable... while allowing
unchanged legacy violations to remain indefinitely."

**This ran `--autonomous`, with no live operator turn to arbitrate the
split.** The operator's own invocation text is itself the design decision on
this exact fork, not merely the trigger for one: it explicitly named
`fix(compliance): one-time rollout transition rule for check_binding_completeness
(#721)` as the precedent matching this defect's shape, and explicitly
contrasted that against "a permanent scope skip" — i.e. it had already ruled
out an Option-B-shaped fix before this run began, and asked for the Option-A
shape by name, closing with "Needs a design decision, not a mechanical copy
of the #4/#15/#11 pattern." Read plainly, the operator was not asking
"should a transition mechanism exist" — that was decided by citing #721 as
the matching precedent — but "build the #721-shaped fix for these two
gates." openai's reject is not a technical rebuttal of option A's design so
much as a rejection of doing a rollout transition at all, which the
operator's own framing had already settled. openai's proportionality
argument is not rebutted as a *standalone* technical claim — it mirrors
glm's own low-severity proportionality finding on Plan Review (document the
retirement condition explicitly), which this iterate accepts as a real,
disclosed cost (see Disclosed, not fixed) rather than a reason not to build
the mechanism at all. It is overridden here by the operator's explicit,
already-decided framing this run had no channel to relitigate synchronously.
Recorded transparently, per the skill's contradiction protocol adapted for
`--autonomous` mode and mirroring the identical glm/openai split's resolution
in the `#721`/`iterate-2026-09-11-binding-completeness-rollout-transition`
ADR (that run's split was the mirror image — openai approved, glm rejected
on proportionality — resolved the same way, by the operator's own standing
instruction), rather than silently picking a side.

## Out of Scope

- Extending this same rollout-transition treatment to `check_basis_forbids_assumed`
  or `check_starting_guidance_present` — both already have their OWN,
  differently-reasoned scope carve-outs and are not part of `trg-9583d3a8`'s
  finding.
- A permanent `scope == "extension"` skip for #5/#10 — considered and
  rejected above (Resolution of the architecture-review split).
- Retrofitting this rollout treatment onto other, unrelated gate families
  (e.g. the P3.1/P3.7 layer-coverage siblings already tracked as a deferral
  in `trg-1d9ed777`) — different gates, different rollout instants, already
  tracked separately.
- Extending grace to a `/shipwright-adopt` onboarding run that happens AFTER
  the gate's own rollout instant, whose mined acceptance-criteria bullets
  (`plugins/shipwright-adopt/scripts/lib/test_acceptance_miner.py`) routinely
  trip #5's implementation-detail ban — a producer-vs-gate conflict for
  FUTURE onboardings, a different and larger unit of work than grandfathering
  pre-existing content. Tracked as a new triage follow-up card (`trg-ac2ef362`).
- Factoring `_project_gate_rollout.py`'s commit-resolution logic into a
  shared primitive with `_layer_coverage_rollout.py` (now a third
  near-identical copy of the same idea) — deliberately duplicated per the
  P3.3 ADR's own "each gate family gets its own rollout instant and resolver"
  precedent; tracked as a new triage follow-up card (`trg-fcb3ee97`), mirroring
  the `trg-1d9ed777` precedent from the binding-completeness ADR.
- Making `common.summarise()`/`verify_phase.py`'s own `--strict` blocking
  calculation honor `CheckResult.strict_exempt` (code review, medium) — a
  cross-cutting fix touching every gate family that sets the field
  (`layer_coverage.py`, `plan_gate_checks.py`, and now this one), not scoped
  to FR-01.02 #5/#10 alone; tracked as a new triage follow-up card
  (`trg-b996bc21`).

## Rejected alternatives

1. **Byte-identical raw-text comparison**, instead of exact identity on the
   parsed criteria/row-count representation. Rejected: a repo whose spec.md
   was reformatted (line-ending normalization, whitespace cleanup) after
   rollout would lose all grace even though the violating *content* is
   unchanged — reintroducing the exact bug this change exists to fix
   (external plan review, glm).
2. **Whole-row criteria-tuple equality**, instead of per-criterion string
   membership. Rejected: forfeits grace for an untouched, pre-existing
   violation the moment an unrelated later touch adds a new criterion to the
   same row (internal plan review, opus).
3. **Spec.md content alone as proof a split predates rollout**, instead of
   requiring manifest declaration too. Rejected: a split reusing an old,
   unrelated, already-empty path would inherit a stranger's grace (external
   plan review, openai, high).
4. **A single `GateResult.severity`/`strict_exempt` pair per-hit-diagnostic
   redesign** (openai's literal Plan Review suggestion: model diagnostics per
   hit, or emit separate `CheckResult`s for hard and advisory subsets).
   Rejected as disproportionate: "any hard hit dominates the aggregate
   severity, graced hits stay visible in the detail string" already closes
   the concrete failure mode (a new violation silently exempted by an
   unrelated old one) without requiring every `CheckResult` consumer to learn
   a new list-of-diagnostics shape.
5. **Caching the resolved rollout commit under the symbolic name `"HEAD"`**,
   instead of resolving to a concrete SHA first. Rejected: goes stale the
   moment the process evaluates more than one repository state — e.g. across
   `tmp_path` fixtures in one test run (external plan review, openai, medium).
6. **A permanent `scope == "extension"` skip** (architecture brief's option
   B) and **do nothing / fix legacy violations manually** (option C) — see
   "Resolution of the architecture-review split" above.
7. **Factoring `_project_gate_rollout.py` into a shared primitive with
   `_layer_coverage_rollout.py`** now, rather than disclosing it as a
   follow-up. Rejected: the P3.3 ADR's own precedent already establishes
   per-gate-family resolvers since each gate ships on its own date; a
   cross-cutting refactor of an already-shipped, heavily-reviewed sibling
   module is a larger, separately-scoped change than this fix warrants.

## Disclosed, not fixed

- A `/shipwright-adopt` onboarding run AFTER the gate's own rollout instant
  gets no grace at all for content its own AC-miner produces — see Out of
  Scope, `trg-ac2ef362`.
- The identical trust-anchor gap in the `check_binding_completeness`
  precedent (`_layer_coverage_rollout.py`) is **not** fixed by this change —
  scoped to this PR's own gate family only, per the operator's explicit
  instruction. `trg-4380c61a`'s tracked pointer is updated to reflect that
  the FR-01.02 #5/#10 copy is fixed and the `check_binding_completeness`
  copy remains open, rather than closed outright.
- Three near-identical copies of git shallow-check + `rev-list --before` +
  committer-epoch-verify logic now exist across the gate families
  (`_layer_coverage_rollout.py`, its binding-completeness sibling, and this
  one) — see Out of Scope, `trg-fcb3ee97`.
- No explicit "retirement condition" is recorded for when this mechanism
  could ever be safely removed (external plan review, glm, low) — mirrors
  the identical, already-accepted gap in the `check_binding_completeness`
  precedent (that ADR's own "Disclosed, not fixed" section carries the same
  unresolved question); this mechanism is a permanent resident once any repo
  has commits before its rollout epoch, same as its precedent.
- The fail-open "no rollout commit → no grace" direction means a
  shallow-cloned legacy project silently loses its grandfather and hard-fails
  on old content, with no diagnostic distinguishing that from a genuinely new
  violation (external plan review, glm, low) — accepted as the same
  conservative direction the precedent already takes: fail-open only ever
  withholds an optional leniency, never grants a false one, so the worst
  outcome is an unexplained HARD block identical to today's behaviour.
- A cosmetic title (`Name` column) rewording between rollout and HEAD is
  tolerated (case/whitespace-insensitive), but a genuine title CHANGE on an
  otherwise-unchanged row forfeits grace — arguably stricter than strictly
  needed for "essentially unchanged," but the safe (fail-closed) direction,
  same disposition the precedent recorded for its own identical trade-off.
- ~~`strict_exempt=True` is honored by `verify_iterate_finalization.py` (the
  gate every real iterate actually goes through) but NOT by
  `common.summarise()`/`verify_phase.py`'s own `--strict` blocking calc, so
  a direct `verify_phase.py --phase project --strict` call still hard-blocks
  on a fully-graced rollout warning (code review, medium) — pre-existing gap
  shared with `layer_coverage.py`/`plan_gate_checks.py`, not introduced here;
  see Code-Review-Findings #1, `trg-b996bc21`.~~ **Fixed** post-merge — see
  "Post-merge PR-review gate finding #2, fixed" below. `trg-b996bc21`
  promoted/closed against this PR.

## Self-Review (references/iteration-reviews.md checklist)

1. **Spec Compliance** — pass. All 8 ACs implemented and test-pinned:
   per-criterion membership grace for #5 (AC1), mixed hard/graced stays hard
   (AC2), declared+empty split grace for #10 (AC3), newly-declared/regressed
   split stays hard (AC4), greenfield no-grace (AC5), per-repo resolution
   (AC6), #4/#15/#11 untouched (AC7); `trg-9583d3a8` closure (AC8) lands as a
   small follow-up append once this run's own PR exists, referencing it —
   the same process the `trg-aedcfe7b` precedent's own close event actually
   used (Stage-1 spec-review caught the original AC8 wording asking for a
   PR reference this diff cannot yet have; corrected rather than
   fabricating a task-ref).
2. **Error Handling** — pass. `build_rollout_snapshot` never raises
   (degrades to an unresolved snapshot on any git failure); `resolve_rollout_commit`
   fails closed on a shallow clone, an empty commit hash, or any git failure;
   `_read_at_commit`/`_parse_declared_split_names` degrade permissively
   (never raise) on a historical-commit read/parse failure.
3. **Security Basics** — pass on injection/path-safety: every git path is
   validated non-absolute, `..`-free, and not flag-injectable before reaching
   `git show` (`_is_safe_git_path`); the epoch constant is a fixed literal;
   `commit_hash` reaches `_run_git` as an argv element, never
   shell-interpolated. Trust-boundary caveat (Stage-3 doubt review, high —
   see Doubt-Review-Findings #1), **fixed post-merge, see "Post-merge
   PR-review gate finding, fixed" below**: the rollout instant this grace
   relied on was originally proven only by a target project's own commit
   timestamp, a value its own author sets; `resolve_rollout_commit` now
   additionally requires the candidate to be an ancestor of a corroborated,
   contributor-uncontrolled trunk boundary (`trg-4380c61a`).
4. **Test Quality** — pass. Real-git tests for commit resolution (before/at/
   after cutoff, shallow clone verified via `--is-shallow-repository` after a
   `file://` clone, empty ref, cache behaviour) and snapshot reading
   (including the nested-`project_root` git show/-C regression); pure
   comparator-matrix tests for the grace rules; real-git, wiring-level
   end-to-end tests proving the `CheckResult` itself downgrades — and that a
   genuinely new post-rollout violation still hard-blocks.
5. **Performance Basics** — pass. `build_rollout_snapshot` is LAZY — only
   invoked once a candidate hit already exists from the rollout-unaware first
   pass, never on a clean run — and process-cached by `(root, sha)`/`(sha,
   path)`.
6. **Naming & Structure** — pass. New modules follow the exact sibling-gate
   split precedent already established in this family
   (`_project_gate_wiring.py`/`_project_gate_manifest.py`); every new module
   and its test file stay under the 300-LOC bloat-baseline guideline.
7. **Affected Boundaries** — n/a. No serialized format's shape changed; this
   unit reads the EXISTING `spec.md` text and manifest fields at one more,
   older git ref.
8. **Test Hygiene Probe** — pass, no findings on the diff.

## External-Plan-Review-Findings

| # | Severity | Source | Finding (short) | Disposition |
|---|---|---|---|---|
| 1 | high | openai | A single `GateResult.severity`/`strict_exempt` can't represent one legacy + one new violation on the same result | accepted-and-fixed — a hard hit always dominates the aggregate severity; graced hits stay named in the detail string (see Rationale) |
| 2 | high | openai | Historical `spec.md` text alone can't prove a split was DECLARED at rollout | accepted-and-fixed — `RolloutSnapshot.declared_split_names` reads the manifest at the resolved commit too |
| 3 | medium | openai | "Byte-identical" is stronger than parsed-criteria-tuple equality; whitespace/line-ending drift could forfeit grace | accepted-and-fixed — comparison is exact identity on the PARSED representation, never raw bytes |
| 4 | medium | openai | Process-level caches underspecified around the symbolic `"HEAD"` input; could go stale across repos in one process | accepted-and-fixed — `HEAD` resolved to a concrete SHA (`resolve_head_sha`) before any cache is keyed |
| 5 | medium | openai | `GateResult`/`CheckResult` conversion path and consumers need auditing before adding new fields | accepted-and-fixed — `_to_check_result` is the single, tested conversion point; every other gate in the module leaves both fields at their default (no-op) |
| 6 | low | openai | Git revision/path args need containment validation, not just POSIX normalization | accepted-and-fixed — `_is_safe_git_path` rejects absolute paths, `..` segments, and flag-injection-shaped strings before any `git show` call |
| 7 | medium | glm | Row→source-path mapping for the grace lookup is implicit; a multi-split project could cross-check a row against the wrong split's rollout text | accepted-and-fixed — grace lookup is per-`(path, row)` pair, keyed by the same display path the caller already associates with each row; cross-split isolation is structurally impossible by construction, not test-pinned (code review, low — corrected an overclaim; see Code-Review-Findings #3) |
| 8 | low | glm | Process-level caches could go stale across repos/commits within one process (measured directly in the test suite's `tmp_path` fixtures) | accepted-and-fixed — same fix as #4 above; every cache is keyed by a concrete `(root, sha)`/`(sha, path)` pair |
| 9 | low | glm | `GateResult.severity: str \| None` reintroduces a stringly-typed severity next to `common.Severity` | accepted, disclosed not fixed — kept import-light (mirrors the module's existing zero-`common`-import shape), same trade-off `layer_coverage_binding.py`'s own advisory branch already makes |
| 10 | low | glm | Title-unchanged-but-text-changed inverse of the repurposed-id rule isn't covered | accepted, disclosed not fixed — fail-closed direction is safe; recorded in Disclosed, not fixed |
| 11 | low | glm | Git path/revision args need explicit safety assertions | accepted-and-fixed — same fix as #6 above |
| 12 | low | glm | Epoch constant and merge SHA duplicated across spec/module/ADR prose risk silent drift | accepted-and-fixed — `test_gate_rollout_epoch_matches_the_documented_boundary_instant` asserts the ISO string and epoch integer against each other |

## Architecture-Review-Findings

See "Resolution of the architecture-review split" above for the full
reasoning; summarized:

| # | Severity | Source | Finding (short) | Disposition |
|---|---|---|---|---|
| A1 | — | glm | Approve: option A is correct; B permanently excuses future violations, C leaves a real user-facing regression | accepted (design proceeds) |
| A2 | medium | openai | Reject — proportionality: a directly-repairable failure doesn't need a standing exception; choose option C | acknowledged, overridden by the operator's own explicit, already-decided framing (naming `#721` as the matching precedent before this run began) |
| A3 | low | glm | No recorded retirement condition for the mechanism; consider a fail-open diagnostic naming the shallow-clone cause | accepted, disclosed not fixed — mirrors the identical already-accepted gap in the `#721` precedent's own ADR |

## Code-Review-Findings (internal Stage-2 subagent)

| # | Severity | Finding (short) | Disposition |
|---|---|---|---|
| 1 | medium | `common.summarise()`/`verify_phase.py`'s `blocking = errors > 0 or (strict and warnings > 0)` never reads `CheckResult.strict_exempt` — a direct `verify_phase.py --phase project --strict` invocation still hard-blocks on a fully-graced rollout warning, contradicting this diff's own docstring claim that grace is "never promoted to a hard failure under `--strict`" | **fixed** post-merge (see "Post-merge PR-review gate finding #2, fixed" below) — originally accepted/disclosed-not-fixed as a cross-cutting `common.py` fix out of proportion to this diff alone; the automated PR-review gate independently re-raised it as a blocker, so it was fixed here after all, once, in `common.py`, benefiting every gate family that sets the field (`layer_coverage.py`, `plan_gate_checks.py`, this one) |
| 2 | medium | `_rollout_declared_split_names`'s fallback fell through to `shipwright_run_config.json` whenever `shipwright_project_config.json` was unparseable/`splits`-less at the historical commit, diverging from `_declared_split_names`'s live-manifest priority (existence alone is authoritative, no fallback) — could let a stale `run_config.json` split grant grace the authoritative manifest at that same commit never declared | fixed — `_rollout_declared_split_names` now checks the primary file's raw existence (via `_read_at_commit`'s `None`-means-absent contract) before ever reading the fallback, mirroring `_declared_split_names` exactly; new test `test_build_rollout_snapshot_declared_split_names_does_not_fall_back_when_project_config_exists_but_is_splitless` pins it |
| 3 | low | ADR row #7 claimed multi-split cross-check isolation was "test-pinned"; no test actually exercises two splits with colliding FR content | fixed (wording) — row #7 above corrected to "structurally impossible by construction, not test-pinned" |

## Doubt-Review-Findings

Advisory-must-address (`references/iteration-reviews.md`): each doubt answered
in writing below, fix or reasoned rebuttal, per that convention. Technical
detail deliberately kept out of this git-tracked file (constitution's
sensitive-detail rule) — full writeup in the gitignored `Spec/` report named
below.

| # | Severity | Finding (short) | Disposition |
|---|---|---|---|
| 1 | high | Both this diff's and the `check_binding_completeness` precedent's rollout-transition grace anchor "existed before rollout" to a target project's own commit timestamp — a value the commit's own author sets, with no external verification. Under the threat model this gate family already documents elsewhere (running against untrusted PR content in CI), that timestamp cannot be trusted as proof against an adversarial author, letting a genuinely new violation potentially receive grace it should not | **fixed** (post-merge PR-review gate finding — see "Post-merge PR-review gate finding, fixed" below) for this diff's own gate family: `resolve_rollout_commit` now additionally requires the candidate to be an ancestor of a corroborated trunk boundary (`git_helpers._branch_base_commit`), a value the PR's own author cannot set. The `check_binding_completeness` precedent's identical copy is deliberately **not** touched here — out of scope per the operator's explicit instruction, remains open, see Disclosed-not-fixed |
| 2 | low | The `#10` (`no_empty_split`) grace path shares the same root cause as #1 above, just with a smaller blast radius (downgrades an empty-split hard-block, not banned content) | fixed — same disposition as #1; both gates share one `resolve_rollout_commit` call, so the fix covers both at once |

## External-Code-Review-Findings (GPT/openai + GLM cascade, medium+ default-on)

Both legs independently returned `SHIPWRIGHT_VERDICT: revise`. Per
`references/iteration-reviews.md`'s handling rule ("merge any high/medium
findings into the ADR... address before commit... each finding marked
accepted-and-fixed or rejected-with-reason"), each finding below is
addressed; none required looping the cascade again since none of the
dispositions are "fix and re-ask for approval" in nature.

| # | Severity | Source | Finding (short) | Disposition |
|---|---|---|---|---|
| 1 | high | glm | `_TEXT_CACHE` keyed by `(sha, posix_path)` only, omitting `project_root` — two nested projects in one repo sharing a rollout SHA and the same relative spec.md path would read each other's historical text (the sibling `_MANIFEST_CACHE` already included `project_root`; this was an accidental omission) | accepted-and-fixed — key widened to `(str(project_root), sha, posix_path)`; new test `test_two_sibling_nested_projects_at_the_same_sha_do_not_share_text_cache_entries` pins two sibling nested projects at the same SHA/path resolving to their own distinct text |
| 2 | medium | openai | Same `_TEXT_CACHE` finding, independently found | accepted-and-fixed — same fix as #1 |
| 3 | high | openai | Rollout grace trusts the target project's own commit committer timestamp, which its author controls — a genuinely new post-rollout violation could be backdated into apparent legacy content | fixed, same disposition as Doubt-Review-Findings #1 — independently confirmed that finding at the same severity from a second, separate review route, and independently reproduced post-merge by the CI PR-review gate; see that section and "Post-merge PR-review gate finding, fixed" below |
| 4 | medium | openai | `strict_exempt` not honored by `verify_phase.py --strict`'s blocking calc | fixed, same disposition as Code-Review-Findings #1 — independently confirmed that finding; see `trg-b996bc21` and "Post-merge PR-review gate finding #2, fixed" below |
| 5 | low | glm | `criteria_free_of_implementation_detail`'s mixed hard+graced branch summarized graced hits as a bare count, unlike `no_empty_split`'s mixed branch which lists graced locations — inconsistent with the stated "every graced hit named transparently" rationale | accepted-and-fixed — mixed branch now lists the first 5 graced hit locations (same truncation policy as hard hits); test assertion added pinning the graced hit's own location string appears after "granted transition grace", not just a count |
| 6 | low | glm | `_PREFIX_CACHE` unbounded, same cross-root contamination surface as #1 | acknowledged — fixed implicitly by #1's key widening (per the reviewer's own note) |

## Post-review mechanical fix (self-caught, layer-1 canon lint)

After all review rounds above, a full `shared/tests` re-run (post
git-config-corruption incident, see session log) surfaced one failure not
from any review: `test_artifact_path_canon.py::test_no_legacy_artifact_paths
[planning-migrated]`. `_project_gate_grace.py`'s `_PLANNING_PREFIX =
(".shipwright", "planning")` carried an isolated, bare `"planning"` string
literal — exactly what the Layer-1 canon-path lint (`artifact_migrations.py`)
exists to catch, per this same gate family's own established convention of
not duplicating the canonical constant across sibling modules (the sibling
`_project_gate_manifest.py` already defines `_PLANNING_DIRNAME =
".shipwright/planning"` as a single combined-string literal that passes the
lint). Fixed by deriving `_PLANNING_PREFIX` from that existing constant
(`tuple(_PLANNING_DIRNAME.split("/"))`) instead of re-declaring it, preserving
`split_name_from_path`'s exact two-segment-prefix-matching behavior. No new
design decision — a mechanical lint fix, not re-reviewed.

## Post-merge PR-review gate finding, fixed (`trg-4380c61a`)

After this PR (#755) opened, CI's automated `PR Review` gate blocked merge
twice in a row citing the identical finding already disclosed above
(Doubt-Review-Findings #1, External-Code-Review-Findings #3): the rollout
grace's trust anchor — a target project's own committer timestamp — is
forgeable by a contributor who backdates a new, unmerged commit on their own
branch (`GIT_COMMITTER_DATE` before `GATE_ROLLOUT_AT_EPOCH`) to receive
advisory treatment for a violation that never actually predated the gate.
Both prior disclosures had deliberately left this open as out-of-proportion
for an unreviewed autonomous fix to a security-relevant trust boundary; a
live operator decision was required, and required the transition mechanism
itself stay intact — not weakened, not gated around.

**Decision.** `resolve_rollout_commit` now requires a second, independent
condition alongside the existing committer-epoch check: the candidate commit
must be an ancestor of (or equal to) `git_helpers._branch_base_commit`'s
resolved trunk boundary for `resolved_commit_sha` — the same hardened,
already-shipped corroborated-trunk-resolution helper other ERROR gates in
this framework already trust (candidate names `origin/HEAD` /
`origin/main` / `origin/master` / local `main` / `master`, deliberately
excluding a branch's own `@{u}`, requiring ≥2 independently-resolving
candidates to agree before any base is trusted). A value only the branch's
own commits can walk past — not one its author can set — decides whether
grace applies. No corroborated trunk boundary (no `origin` remote, an
ambiguous/renamed trunk name) withholds grace entirely, the same
fail-closed direction the module already used for a shallow clone.

**Why this, not the alternatives the operator considered.** Weakening or
removing the grace mechanism was explicitly ruled out — the mechanism closes
a real, named defect (`trg-9583d3a8`) and the trust-anchor gap is a
narrower, fixable flaw in its proof, not a reason to remove the leniency
itself. Overriding the CI gate was explicitly ruled out — the gate correctly
caught a real vulnerability my own review cascade had already found and
disclosed rather than fixed; overriding it would launder a known,
disclosed-not-fixed security gap into main. Reusing
`git_helpers._branch_base_commit` (already covering this exact "resolve the
trusted trunk boundary" problem for other gates in this same framework, not
a general shared primitive spanning gate families) rather than inventing a
new trust-anchor mechanism keeps the fix small, already-hardened, and
already-tested in its own right.

**Consequence.** All the existing rollout-family test fixtures relied on a
single local branch with no `origin` remote; that shape can no longer
corroborate a trunk boundary at all, so every test's shared `_commit_at`
helper (`test_project_gate_rollout.py`, `test_project_gate_rollout_snapshot.py`,
`test_project_gate_wiring_rollout.py`) now advances a simulated
`refs/remotes/origin/main` alongside each commit by default (`on_trunk=True`),
standing in for "already merged" — an opt-out (`on_trunk=False`) builds a
commit that exists only on its own branch, unreachable from that anchor, for
the new adversarial tests below. This mirrors what a normal `git clone` of a
real project already provides (an `origin` remote with `origin/HEAD`/
`origin/main`), so a genuine calling project sees no behavior change on the
common path; a project with no remote configured at all (or a renamed trunk
matching no candidate) now gets no grace rather than a timestamp-only
answer.

**Tests.** `test_resolve_rollout_commit_refuses_a_forged_unmerged_branch_commit`
builds a genuine pre-rollout trunk commit (tracked as merged) and a separate,
never-merged branch carrying a backdated commit, and asserts the forged
commit gets no grace while the genuine trunk commit still does (confirmed,
before writing the fix, that this test fails against the unpatched
`resolve_rollout_commit` — a real regression test, not a vacuous one).
`test_resolve_rollout_commit_none_without_a_corroborated_trunk_anchor` pins
the new fail-closed branch when no trunk candidate resolves at all. Re-ran
the full three-file rollout suite (29 tests) and `shared/tests` in full,
green; `uvx ruff@0.15.15 check .` clean.

**Scope.** This PR's own gate family only (FR-01.02 #5/#10). The identical
gap in the `check_binding_completeness` precedent (`_layer_coverage_rollout.py`)
is untouched — see Disclosed, not fixed.

## Post-merge PR-review gate finding #2, fixed (`trg-b996bc21`)

After the trust-anchor fix above landed, CI's `PR Review` gate re-ran and
passed on that finding — but blocked on a **second, distinct** one: the
`strict_exempt` gap already named in this ADR's own Code-Review-Findings #1
and External-Code-Review-Findings #4, and already disclosed above as
deliberately out of scope for this diff (a cross-cutting `common.py` fix
benefiting three gate families, not narrowly scoped to FR-01.02 #5/#10
alone). The automated Tier-3 reviewer independently re-raised the identical,
already-reviewed finding as a blocker. Per this PR's own stop condition
("blocks again with a new distinct finding → stop and report"), this was
reported back; the operator's decision was to fix it now, in this PR, rather
than wait for a separate cross-cutting card or get a human reviewer to waive
the gate.

**Decision.** Added `ReportSummary.strict_blocking_warnings` to
`common.py` — a count that excludes every `CheckResult.strict_exempt`
warning, mirroring the filtered calc `verify_iterate_finalization.py`
already carried on its own, separate path. `verify_phase.py`'s blocking
line now reads `summary.strict_blocking_warnings` instead of the raw
`summary.warnings`. `ReportSummary.warnings` itself is untouched — it stays
a raw display count ("how many warnings fired"), not a blocking decision;
`format_report`'s footer text is unaffected. This is the single shared fix
site the original disclosure asked for: every gate family that sets
`strict_exempt` (`layer_coverage.py`, `plan_gate_checks.py`, this one)
benefits without a separate patch each. `verify_iterate_finalization.py`'s
own inline calc is untouched — it was already correct, and refactoring it
onto the new property is not needed to close this finding.

**Tests.** `test_verifiers_common.py` gained two tests pinning
`strict_blocking_warnings`' exempt-exclusion (a mix of exempt/non-exempt,
and all-exempt). A new file, `test_verify_phase_strict.py` (no test file for
`verify_phase.py` existed before this), adds the integration test the
reviewer's finding literally asked for: `main()` invoked end-to-end with
`--phase project --strict`, `dispatch_project` monkeypatched to a fixed
`CheckResult` list, proving a fully-graced warning no longer blocks, a
genuine warning still does under `--strict` (and not under a plain run),
and an ERROR still blocks even alongside a fully-graced warning. Re-ran the
full `shared/tests` suite and `uvx ruff@0.15.15 check .`, both green.

**Scope.** `common.py`/`verify_phase.py` only — the one shared path every
`--phase ... --strict` CLI invocation goes through. `trg-b996bc21` closed
(promoted, task ref `PR:755`).
