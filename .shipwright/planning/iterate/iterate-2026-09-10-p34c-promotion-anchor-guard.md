# Iterate Spec: Anchor Layers-Promotion to the Newest Verified Ancestor (P3.4c)

- **run_id:** iterate-2026-09-10-p34c-promotion-anchor-guard
- **Campaign:** req3-04c-ac-identity-wave2, sub-iterate p3.4c (continuation)
- **Status:** built
- **Affected FRs:** FR-01.11 (same FR the predecessor CI-provenance-attestation
  iterate filed under — compliance-automation infrastructure for
  `/shipwright-iterate`'s own enforcement mechanism, not a product-facing
  acceptance criterion)
- **Spec Impact:** NONE — no `spec.md` acceptance-criteria text changes; this
  widens WHEN an already-specified mechanism (P3.5's Layers promotion) is
  permitted to act, never what it does.
- **Predecessor:** `.shipwright/planning/iterate/2026-09-08-ci-provenance-attestation.md`
  (built `resolve_ci_verification`), `.shipwright/planning/iterate/2026-09-09-p3-5-promote-layers-per-fr-restart.md`
  (built `promote_required_layers.py` + `ci_execution_evidence.py`)

## Problem, measured not predicted (2026-09-10)

PR #707 refreshed the committed traceability manifest; CI on `8f78b93b`
logged "manifest verified clean" and `resolve_ci_verification` returned
`{"status": "verified", "run_id": 34488566428}` — this repo's first verified
commit ever. A dry run of `promote_required_layers.py` at that commit: 7
promoted, 13 skipped `no_evidence_yet`, 0 escalated — the mechanism works.

One hour later, PRs #709 and #710 merged (both add tests).
`resolve_ci_verification` at the new tip: `{"status": "not_verified", ...}`.
**The window was about one hour, and it closes every time, structurally**:
`compare_traceability_manifest._structural_view()` compares the
requirement→test topology, and `untagged_tests` carries the FULL collected
test-ID list — any PR that adds/renames/removes a test file changes it.
Meanwhile `test-traceability.json` is a `DERIVED_SNAPSHOTS` path, so F11's
`check_no_derived_snapshots_committed` forbids the very PR that changed the
inputs from committing the refreshed file. With several iterates in flight
the steady state is DRIFTED; "verified" is the exception. A mechanism that is
correct and never runs is not delivering the campaign's value.

This does **not** mean P3.5 is broken, and it does **not** mean loosening the
trust boundary (`_qualifying_runs` requiring `event==push` AND
`head_branch==default_branch` is exactly what makes a verdict unforgeable;
off the table, per the P3.5 restart spec's own round-2 decision).

## Options weighed (2026-09-10) — decided: B

- **A. Ritual** (refresh/merge/promote with merges paused) — interim only;
  costs two manual steps (a refresh PR is 100% generated paths, so it also
  needs an admin override every time — `trg-a99ee30d`).
- **B. Anchor to the newest verified ancestor — CHOSEN.** See design below.
- **C. Close the drift loop automatically** — REFUSED, not to be
  re-litigated: needs a robot with write access to the default branch,
  decided against three times (no PAT, no dedicated CI job for one file, no
  weakening of the Actions-create-PRs setting).

## Design

**B is not free.** Promoting at anchor `A` while the tree is at `HEAD` `H`
asserts "these tests ran green" from a run at `A`. Between `A` and `H` a
bound test can have been deleted, renamed, weakened, or moved to another FR
— promotion is one-way into hard enforcement, so a stale assertion here is
exactly the defect class the twelve prior BLOCK rounds were about.

1. **`shared/scripts/ci_verified_anchor.py`** (new) —
   `resolve_verified_anchor(head_commit, *, project_root, workflow_file,
   max_commits=50, since_days=90)` walks `head_commit` then its first-parent
   ancestors (bounded, never unbounded), calling the UNMODIFIED
   `ci_provenance.resolve_ci_verification` on each — the anchor moves, the
   trust boundary does not. Returns `found` / `unavailable` / `error`. A
   query error on one candidate degrades the search toward `unavailable`
   rather than aborting it (an older, genuinely verified commit is still
   worth finding) — this fallback is a best-effort improvement layered on an
   already-safe default, not a new load-bearing check.
2. **`shared/scripts/lib/manifest_at_commit.py`** (new) — the commit-pinned
   `git show <sha>:<path>` read `promote_required_layers.py`'s own
   `_read_committed_manifest` already used for `HEAD`, extracted so the same
   TOCTOU-free primitive reads the anchor commit's manifest too (never a
   second implementation of "read a manifest at an exact SHA").
3. **`shared/scripts/lib/promotion_evidence_staleness.py`** (new) — **the
   guard, deterministic, one git call per run (never per FR)**:
   `changed_paths_between(anchor, head, project_root)` runs
   `git diff --name-only --no-renames anchor..head` exactly once;
   `evidence_stale_since_anchor(node_at_anchor, ci_node_at_anchor,
   node_at_head, spec_paths, changed)` is then a pure per-FR set
   intersection against that one result (shipped signature — 5 arguments,
   `spec_paths` a SET, `ci_node_at_anchor` folded in post-code-review: the
   anchor's COMMITTED manifest node alone is not proof of what its CI run
   actually confirmed, since `tests`/`coverage`/`acs` are excluded from
   `compare_traceability_manifest.structural_diff`'s comparison entirely —
   see the External Code Review section below). `--no-renames` deliberately:
   a bound test file "moved to another requirement" is a rename by git's own
   heuristic, and rename detection can otherwise drop the OLD path from
   `--name-only` output — the exact path this guard checks for.
4. **`shared/scripts/tools/promote_required_layers.py`** — when the tip's
   own `resolve_execution_evidence` is `unavailable` (never on `error`, which
   stays fatal as before), fall back to `resolve_verified_anchor`. When it
   finds a DIFFERENT verified commit, read that commit's manifest, resolve
   ITS execution evidence, and compute `changed_paths` once. `plan_promotions`
   then downgrades a would-be `promote` to a named `skip`
   (`evidence_stale_since_anchor`) per FR whose OWN bound test files (as
   BOTH the anchor's committed manifest AND its CI evidence record them),
   OWN binding (compared directly between the anchor and HEAD), or OWN
   `spec.md` (at either commit) appear in — or differ across — that diff.
   Every other outcome (skip/escalate) is untouched, since those already
   reflect "this run's evidence did not clear the bar" regardless of whose
   commit it came from. A local git fault on the anchor's OWN manifest read
   or diff degrades to the tip's original `unavailable` (never exit 2 — this
   fallback is a best-effort improvement with an obvious safe default); the
   anchor's OWN CI evidence resolving to `error` (a content-binding/
   integrity failure, not a transient fetch failure) stays fatal, deliberately
   symmetric with the tip's pre-existing `error` handling.
5. **`shared/scripts/lib/layer_promotion_ledger.py`** — `append_decision`
   gains an additive `anchor_commit` kwarg (same shape as the existing
   `ci_run_id`), recorded on every ledger entry `plan_promotions` produces
   (even the plain, non-anchored case — it is then simply the promoted
   commit itself). "A promotion whose provenance cannot be reconstructed is
   not evidence."

**What must never change, restated:** `_qualifying_runs` keeps requiring
`event==push` AND `head_branch==default_branch` AND `conclusion==success` —
the anchor moves, the trust boundary does not. The anchor must itself be
`verified` via the unmodified `resolve_ci_verification`, never "the newest
commit that looks close enough." The walk is first-parent ancestors of
`HEAD` only, bounded (`max_commits=50` / `since_days=90`, matching the
GitHub Actions artifact-retention horizon `ci_execution_evidence.py`
already documents), reporting `unavailable` rather than searching forever.

## Backward compatibility (why the 927-line existing test suite needed zero
behavior changes)

The anchor fallback triggers ONLY when the tip's own `resolve_execution_
evidence` returns `unavailable` — the happy path (tip already verified,
which is what every existing `_mock_evidence_from(..., status="confirmed")`
test exercises) never calls `resolve_verified_anchor` at all, proven directly
by `test_tip_is_verified_never_triggers_the_anchor_fallback_at_all` (makes
`resolve_verified_anchor` raise if invoked). This is also AC4, below.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** low
- **Summary:** Design sound and the trust boundary stays unmodified; one
  finding required a fix (already integrated), two are disclosed as
  accepted, non-blocking limitations.
- **Findings:**
  - category: correctness, severity: medium, disposition: fix — `bound_test_files`
    silently dropped any unparseable/malformed test link instead of treating
    the resulting unknown file-set as invalidating, narrowing the guard's own
    "widen, never narrow" contract. Fixed: it now returns `None` on any
    malformed shape, and `evidence_stale_since_anchor` treats `None` (from
    either the anchor or HEAD node) as unconditionally stale.
  - category: observability, severity: low, disposition: disclose —
    `resolve_verified_anchor` reports one aggregate `unavailable`/`error`
    outcome for the whole walk; a caller cannot distinguish "every candidate
    genuinely returned `not_verified`" from "the CI-provenance query itself
    failed on some or all candidates" without re-deriving it. Declined to
    widen now — no caller needs the distinction today. (Independently
    reinforced by the external plan review's Branch A pass below: a
    persistent API outage would silently suppress all anchored promotions
    with `rc==0`, indistinguishable from "genuinely nothing verified.")
  - category: performance, severity: low, disposition: disclose —
    `resolve_ci_verification` re-resolves owner/repo/default_branch on every
    candidate commit in the walk instead of caching them once per run.
    Declined: touching `resolve_ci_verification`'s own signature/internals is
    explicitly out of scope per this iterate's own design decision (the
    predicate must stay unmodified). (Independently reinforced by the
    external plan review: up to `max_commits` GitHub API calls per run in the
    drifted steady state this mechanism exists for.)
- **Known limitations:** anchor-walk observability gap (one aggregate
  outcome, not per-candidate); no memoization of owner/repo/default_branch
  across ancestor candidates — both above, neither acted on.
- **Status:** 1 fixed, 2 disclosed

## External Plan Review (Branch A — glm=approve, openai=revise)

Both reviewers independently found the same real gap, since fixed: the
staleness guard compared HEAD's file-content diff against the ANCHOR's own
recorded bound-test set, but never compared the requirement's bound-test SET
itself between the anchor and HEAD — so a test newly bound to (or unbound
from) an FR at HEAD, without the underlying file's bytes ever changing, was
invisible to the guard entirely. `evidence_stale_since_anchor` now takes
both `node_at_anchor` and `node_at_head` and is unconditionally stale on any
difference between their bound-test sets, independent of the git diff (see
`shared/scripts/lib/promotion_evidence_staleness.py`, and
`test_anchor_promotion_is_refused_when_the_bound_test_set_changed_at_head`).

- **Fixed:** binding-drift blind spot above (glm/medium, openai/high).
- **Fixed:** first-parent-only walk had no documented rationale for why it
  is sufficient, not merely convenient — a one-sentence addition to
  `ci_verified_anchor.py`'s module docstring now states it: a `verified`
  verdict requires a push to the default branch, and a push-triggered
  commit lands on that branch's own first-parent chain by construction
  (glm/low).
- **Fixed:** the staleness guarantee ("direct bound-test-file staleness
  only", not transitive test-behavior staleness — shared fixtures,
  `conftest.py`, runner config) is now stated explicitly in
  `evidence_stale_since_anchor`'s docstring (openai/medium).
- **Fixed:** a docstring obligation note — any new evidence input added to
  `resolve_execution_evidence` must be added to this guard's invalidating
  set, or an anchored promotion will silently reuse stale evidence for FRs
  bound to it (openai/medium's "proportionality" framing, reinforced by the
  architecture review below).
- **Disclosed, not acted on:** Windows/path-representation mismatch between
  `git diff`'s output and manifest-stored paths (openai/medium) — git
  normalizes `--name-only` output to forward-slash repo-relative paths
  regardless of host OS, and every staleness test in this diff runs against
  a REAL git repo on this session's own Windows host and passes, so the
  concern is not reproducible against this implementation; left disclosed
  rather than added defensively.
- **Disclosed, not acted on:** trust in unmodified evidence/manifest-
  generator tooling semantics between anchor and HEAD (glm/low) — out of
  scope; `resolve_execution_evidence` and the manifest generator are
  untouched by this diff, and reasoning about their own semantic drift is a
  separate concern from this guard's own invalidating-file set.
- **Disclosed, not acted on:** up to `max_commits` GitHub API calls per run
  in a drifted steady state (glm/low) — same accepted limitation as the
  Internal Plan Review's performance finding above; not a correctness
  concern.

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-09-10-p34c-promotion-anchor-guard/architecture_brief.md`
- **Verdicts:** glm=approve · openai=approve
- **Smallest thing that would do (per reviewers):** as proposed — both
  reviewers independently confirmed Option B as scoped is the smallest shape
  that solves the measured problem; Option A does not solve it (the window
  closes structurally, forever) and Option C was refused for a materially
  larger permanent obligation (standing default-branch write access).
- **Findings:**
  - ownership/observability (glm, low) — accepted-and-folded: the "re-run
    after the next verified refresh and check whether the same 7 FRs
    promote again" operational follow-up already relies on the ledger the
    mechanism writes; the `skipped` list's `evidence_stale_since_anchor`
    reason_code count is exactly the "swing" signal glm asked for, already
    observable with no new code — the Operational follow-up section below
    is written to say so explicitly rather than relying on a human
    remembering a separate ritual.
  - proportionality (glm, low) — accepted-and-fixed: the "any new evidence
    input must be added to the staleness check" obligation is now stated in
    `promotion_evidence_staleness.py`'s docstring (same fix as the External
    Plan Review section above).
- **Reconciliation:** neither reviewer recommended an alternative to Option
  B; nothing from the mini-plan's rejected alternatives (A, C) needed
  re-litigating.

## Code Review (Stage 2 — shipwright-build:code-reviewer)
- **Findings:** 1 high, 3 medium, 3 low. All fixed.
- **High** — the anchor's COMMITTED manifest node is not proof of what the
  anchor's CI run actually confirmed: `tests`/`coverage`/`acs` are
  `compare_traceability_manifest._REQUIREMENT_EXECUTION_KEYS`, excluded from
  `structural_diff` entirely, so `resolve_execution_evidence`'s content-
  binding check never vouches for the committed manifest's `tests` block
  matching the CI artifact's. A test retagged onto an FR between the
  committed anchor manifest and the anchor's actual CI run was structurally
  invisible to the staleness guard. Fixed by adding a third parameter,
  `ci_node_at_anchor`, to `evidence_stale_since_anchor` — the same CI-
  evidence node already used to build the promotion decision's own
  `eval_node["tests"]`, unioned into the anchor-side bound-file set. Pinned
  by `test_evidence_stale_since_anchor_true_when_only_ci_evidence_knew_about_the_changed_file`.
- **Medium** — `bound_test_files` raised `AttributeError` on a non-dict
  `tests` block (a committed manifest node's `tests` is never shape-checked
  upstream, unlike a CI evidence node's). Fixed with an `isinstance` guard;
  returns `None` (unconditionally stale) instead of crashing.
- **Medium** — the anchor-fallback path in `main()` added three new `exit 2`
  paths for what are, on inspection, three different failure classes.
  Resolved asymmetrically, not by blanket-catching: a local git fault
  reading the anchor's own manifest, and a local git fault diffing
  anchor..HEAD, both degrade to the tip's original `unavailable` (a good
  fallback is already in hand — give up on the anchor, not on the run); the
  anchor's own CI evidence resolving to `error` (a content-binding/integrity
  signal, not a transient fetch failure) stays fatal, deliberately symmetric
  with the tip's pre-existing `error` handling.
- **Medium** — missing test coverage for the above branches and for
  `manifest_at_commit.read_manifest_at_commit`'s non-dict-JSON rejection.
  Added tests for all five gaps.
- **Low** — stale docstring/spec text describing the pre-fix 3-arg
  `evidence_stale_since_anchor` signature. Fixed in both the function's own
  docstring and this spec's Design section.
- **Low** — a 24-line redundant inline comment block. Trimmed to a short
  pointer.
- **Low, security (defense-in-depth, not currently exploitable)** — no
  commit-SHA injection guard on the three new git-boundary functions
  (`resolve_verified_anchor`, `read_manifest_at_commit`,
  `changed_paths_between`): each reaches a `git` subprocess call with a
  commit string that, today, always comes from an already-validated source
  (`resolve_head_sha`'s own output or `ci_verified_anchor`'s validated
  candidates), but nothing enforced that invariant at the function boundary
  itself. Fixed by mirroring `ci_provenance._COMMIT_RE`'s own 40-char-hex
  validation locally in each of the three modules, failing closed (`error`/
  `None`/`ManifestReadError`, never running `git`) on a non-SHA input, with
  a regression test per function.
- **Post-fix regression:** re-running the full suite after these fixes
  surfaced one bug in the new tests themselves (not in the shipped code) —
  `test_a_local_git_fault_reading_the_anchors_manifest_degrades_not_exit_2`
  raised a freshly-imported `scripts.lib.manifest_at_commit.ManifestReadError`
  instead of `mod.ManifestReadError`, a different class object under this
  repo's ADR-044/045 package-collision behavior (`lib.X` vs `scripts.lib.X`
  load as two distinct modules), so `main()`'s own `except ManifestReadError`
  never caught it. Fixed by raising `mod.ManifestReadError` directly.

## Doubt Review (Stage 3 — shipwright-build:doubt-reviewer)
- **Findings:** 7 doubts (1 high, 4 medium, 2 low). Fixed: high + 3 medium +
  1 low. Documented as accepted, reasoned limitations: 1 medium + 1 low.
- **High — HEAD's own manifest is never CI-verified on the anchor path.**
  On the direct (non-anchor) path, `evidence.status == "confirmed"` implies
  CI regenerated the manifest fresh at that exact commit and found zero
  drift (`ci_manifest_drift_check.py`, gating both the artifact upload and
  the "verified" step at `code == '0'`) — so a "confirmed" committed
  manifest is proven to match reality at that commit. On the anchor path,
  HEAD's own manifest is never regenerated or diffed by anything (CI never
  ran successfully against HEAD — that's why the fallback exists at all),
  so nothing establishes that HEAD's manifest still accurately reflects
  what's actually bound in the tree. Concretely: a new test file added
  between the anchor and HEAD, whose binding was never reflected in a
  re-run manifest regeneration (the exact "drifted, unregenerated HEAD
  manifest" state this whole mechanism exists to operate in), is invisible
  to every existing check — it's absent from the anchor's bound set (never
  compared against, since nothing knew to compare it), absent from HEAD's
  stale manifest (so the binding-drift check sees no difference), and not
  yet "bound" anywhere the invalidating-file-set check would recognise.
  Fixed two ways in `evidence_stale_since_anchor`: (1) an identity check —
  `node_at_anchor["id"] != node_at_head["id"]` is unconditionally stale,
  closing the adjacent gap where nothing compared FR identity across the
  two nodes at all; (2) any changed path that looks like a Python test file
  (`_looks_like_test_path` — this repo's own pytest collection convention)
  and is NOT already a member of the anchor's bound set is unconditionally
  invalidating, regardless of whether any manifest names it as bound —
  necessarily a run-wide signal (not per-FR: no cheap way to attribute an
  as-yet-unbound file to one specific FR without a second git call or
  content inspection per FR, which this guard's "one git call per run"
  design already rules out). Pinned by
  `test_evidence_stale_since_anchor_true_when_a_new_unaccounted_test_file_changed`
  and the end-to-end
  `test_anchor_promotion_is_refused_when_a_new_test_file_is_unaccounted_for_in_any_manifest`.
  Accepted trade-off: this can refuse a promotion that was genuinely fine
  (an unrelated FR's new test elsewhere in the tree) — conservative by
  construction, matching the guard's own "widen, never narrow" rule
  throughout.
- **Medium — the anchor's own `error` evidence status was wrongly treated
  as always a content-binding/integrity signal.** On inspection,
  `resolve_execution_evidence` returns `error` for plain transient/
  operational download faults too ("could not list artifacts", "selected
  artifact could not be retrieved", "downloaded artifact is not a JSON
  object"), indistinguishable here from a genuine mismatch without fragile
  prose-matching against `.detail`. Keeping it fatal made a best-effort
  fallback into a new, self-repeating exit-2 for the SAME anchor commit on
  every run until it ages out of the walk's bound — the same shape
  `ci_execution_evidence.py`'s own `_ZERO_SHA` design note already rejects
  elsewhere in this mechanism. Reversed from the Stage-2 code-review round:
  now degrades the same way the two git-plumbing faults do.
- **Medium — the bounded ancestor walk's worst-case cost was undercounted
  and unbounded on a systemic fault.** The real cost is 2-3 `gh api`
  subprocess spawns per candidate (not 1), and a systemic condition (`gh`
  offline/unauthenticated/rate-limited) burned the FULL `max_commits`
  candidates to reach the same `unavailable` conclusion a handful already
  establishes — worsening the very rate-limit backoff it's failing on.
  Fixed with a circuit breaker: `_CONSECUTIVE_ERROR_LIMIT` (5) consecutive
  `error` verdicts end the walk early; the counter resets on any
  non-error verdict, so a merely-spotty (not systemic) query path can still
  reach a verified commit further back.
- **Medium — the walk's stopping predicate (`verified`, structural
  provenance) is not what the caller actually needs (`confirmed` execution
  evidence).** If the newest verified ancestor's own artifact is missing
  (a swallowed upload), the current design gives up on the whole fallback
  rather than trying the next verified ancestor further back — the
  mechanism could still fail to fire in exactly the case it exists to
  handle. **Accepted, documented limitation, not fixed this round:**
  extending the walk to probe execution evidence at each verified
  candidate (not just structural verification) is a real design extension,
  not a proportionate fix within this iterate's scope — it changes
  `resolve_verified_anchor`'s own contract (today: "the newest verified
  commit"; would become: "the newest verified commit with confirmed
  evidence", a materially different, more expensive predicate needing its
  own review). Filed as a follow-up rather than folded in here; the current
  behavior is a usefulness gap ("fires less often than it could"), never a
  safety gap (never a false promotion) — no evidence is ever manufactured
  by giving up early.
- **Medium — the staleness guard's git diff only covers COMMITTED anchor..
  HEAD history, but `plan_promotions` reads spec.md live from disk
  (`full_path.read_text()`), which can differ from HEAD's own commit in an
  iterate worktree's normal in-flight state.** Examined in depth: the part
  of this that actually matters — spec.md's live CONTENT — is already,
  independently guarded by `evaluate_fr`'s own live-read checks
  (`live_required_layers`, `live_cell_has_non_canonical_content`), which
  read the CURRENT file and would skip rather than promote over live
  residual content; this guard's own `spec_paths` check is about file
  IDENTITY (which file a promotion writes into), not spec.md's prose
  staleness. The residual gap — an UNCOMMITTED edit to a bound TEST file's
  content, made after the anchor but before this tool runs and before that
  edit is committed — is real but was judged not proportionate to close by
  widening `changed_paths_between` to include the working tree: doing so
  correctly (capturing untracked new files, not just modified tracked
  ones) needs either mutating the caller's git index (`git add -N .` risks
  sweeping in state this tool has no business touching — a documented
  footgun already avoided elsewhere in this codebase) or a second,
  more invasive git call. **Accepted, documented limitation:** an anchored
  promotion's guarantee is stated as covering commits, not an uncommitted,
  in-flight edit to a bound test file made after the anchor and not yet
  committed at the moment this tool runs.
- **Low, fixed — `resolve_verified_anchor` didn't normalise `head_commit`'s
  case before use.** `git log --format=%H` always emits lowercase, so an
  uppercase/mixed-case `head_commit` could make the depth-0 candidate's
  `sha` differ from the caller's own string by case alone, defeating an
  `anchor.commit != sha` guard at the call site. Latent (today's only
  caller already passes lowercase), fixed anyway — normalised once at the
  top of the function, used for both the `git log` argv and every returned
  `commit`/`detail`.
- **Low — an anchored `escalate` decision's `detail` doesn't flag that its
  inputs came from an anchor, or that the same staleness facts that would
  suppress a promotion weren't consulted for it.** `escalate` reaches a
  human via `record_layer_promotion_decision.py`; `ci_evidence.anchor_commit`
  is present on the decision (so the commit IS recoverable), but nothing
  in the reason/detail text itself says "anchored." **Accepted, documented
  limitation, not fixed this round:** this is a decision-transparency gap,
  not a safety gap — the human reviewing an escalation already has the
  full manifest, spec.md, and ledger in front of them, and
  `ci_evidence.anchor_commit` is queryable from the same decision record
  the operator CLI reads. Running the staleness computation for
  `escalate` outcomes too (to annotate, without changing the action) is a
  reasonable follow-up, filed rather than folded in here to keep this
  round's diff scoped to what doubt-review actually forced.

## Acceptance Criteria

1. An FR whose bound test files are untouched since a verified ancestor
   promotes, and the ledger names that anchor (`anchor_commit`) beside
   `ci_run_id`. — `test_anchor_promotion_succeeds_when_nothing_invalidating_
   changed_since_the_anchor`
2. The same FR does NOT promote once one of its bound test files is touched
   in `A..HEAD` — it skips with the named reason
   `evidence_stale_since_anchor`, spec.md is left untouched, and the ledger
   gets no new entry for it. — `test_anchor_promotion_is_refused_when_a_
   bound_test_file_changed_since_the_anchor`, and the reason-code is asserted
   directly in `test_anchor_promotion_reports_stale_reason_code_in_the_
   result`.
3. A HEAD with no verified ancestor inside the bound reports `unavailable`,
   not an error and not a promotion (`rc == 0`, nothing promoted). —
   `test_no_verified_ancestor_within_the_bound_reports_unavailable_not_
   error`. A query error walking candidates degrades the same way, never
   `exit 2` — `test_a_query_error_walking_the_anchor_degrades_to_
   unavailable_not_exit_2`.
4. The existing tip-is-verified path promotes IDENTICALLY when the tip IS
   verified — `test_tip_is_verified_never_triggers_the_anchor_fallback_at_
   all`, plus all 34 pre-existing tests in `test_promote_required_layers.py`
   passing unmodified (only one pre-existing test needed a signature update,
   for a locally-defined test double that now receives the new optional
   kwargs — not a behavior change).

## Confidence Calibration

- **Boundaries touched:** git subprocess invocation (`git log
  --first-parent`, `git diff --name-only --no-renames`, `git show
  <sha>:<path>`) — a process boundary, and the JSON manifest/ledger
  read/write boundary already governed by `touches_io_boundary` (this diff
  is `json.loads`/`json.dumps`-heavy throughout the ledger and manifest
  code, hence the mandatory Boundary Probe below).
- **Empirical probes run:**
  - Round-trip: `test_write_then_load_round_trips` (pre-existing, still
    green) plus the two new `test_append_decision_*_anchor_commit` tests
    prove `anchor_commit` survives an `append_decision` → `write_ledger` →
    `load_ledger` → `latest_decision` round trip exactly like `ci_run_id`
    already does.
  - `--no-renames` behavior: `test_changed_paths_between_no_renames_shows_
    the_old_path_on_a_pure_rename` performs a REAL `git mv`-equivalent
    (rename via `Path.rename` + `git add -A`) between two real commits and
    asserts the OLD bound path still appears in the diff — proving the
    documented rename-hiding risk (a memory-recorded gotcha in this
    monorepo, "rename detection hides CI paths") is actually closed, not
    merely asserted in a docstring.
  - Git's `--since` day-count parsing was probed manually (`git log
    --since="36500 days ago"` returns nothing — an internal approxidate
    overflow at that magnitude; `"3650 days ago"`/`"100 years ago"` both
    work) — this is why `DEFAULT_SINCE_DAYS=90` stays small and the test
    (`test_since_days_bound_is_threaded_through_without_crashing`) uses
    `3650`, not an arbitrarily large sentinel.
  - Real end-to-end composition against a real two-commit git repo (not a
    hand-built decision dict) in all six new
    `test_promote_required_layers.py` cases — `resolve_execution_evidence`
    and `resolve_verified_anchor` are the ONLY two mocked seams; the `git
    diff`/`git log`/`git show` calls underneath the staleness guard and the
    manifest-at-commit read are real.
- **Test Completeness Ledger:**

  | Behavior | Disposition |
  |---|---|
  | Anchor found at depth 0 (tip itself verified) | tested — `test_head_itself_verified_is_found_at_depth_zero` |
  | Anchor found at a first-parent ancestor | tested — `test_falls_back_to_a_verified_parent_when_head_is_not_verified` |
  | No verified commit within the bound → `unavailable`, never `error` | tested — `test_no_verified_commit_within_bound_reports_unavailable_not_error` |
  | A query error on one candidate does not abort the search | tested — `test_a_query_error_on_one_candidate_does_not_abort_the_search` |
  | `max_commits` bounds the walk deterministically | tested — `test_max_commits_bounds_the_walk` |
  | `since_days` is threaded into the git invocation | tested — `test_since_days_bound_is_threaded_through_without_crashing` |
  | `git log` failing outright (not a repo) → `error` | tested — `test_git_log_failure_reports_error` |
  | `bound_test_files` extracts the file half of a `path`/`id` test link, tolerating malformed links | tested — 4 cases in `test_promotion_evidence_staleness.py` |
  | `evidence_stale_since_anchor` true on a bound-test-file change, true on a spec.md change, false otherwise, false on empty diff | tested — 4 cases |
  | `changed_paths_between` lists real changed files, empty on identical commits, `None` on git failure, keeps a renamed file's OLD path visible | tested — 4 cases |
  | `manifest_at_commit` reads the exact commit (not the working tree), raises on an unresolvable HEAD/commit/missing-path/invalid-JSON | tested — 5 cases in `test_manifest_at_commit.py` |
  | `append_decision`/`record_ledger_entries` carry `anchor_commit` when given, omit it when absent | tested — 4 cases across `test_layer_promotion_ledger.py` / `test_layer_promotion_apply.py` |
  | End-to-end: clean anchor promotion, staleness-refused promotion, no-anchor-available, query-error-degrades, tip-verified-bypasses-fallback-entirely | tested — 6 cases in `test_promote_required_layers.py` (listed under Acceptance Criteria) |
  | 34 pre-existing `promote_required_layers.py` behaviors (dry-run, concurrency, ledger contradiction, collision handling, etc.) | tested — regression: all still green, zero behavior change on the non-anchor path |

  0 untested-testable rows.
- **Confidence-pattern check:** Asymptote (depth) — the staleness guard is
  probed against REAL git rename/diff behavior, not a hand-simulated file
  list, closing the exact "rename hides the old path" trap the module
  docstring warns about. Breadth (coverage) — all four outcomes of
  `resolve_verified_anchor` (found-at-tip, found-at-ancestor, unavailable,
  error) and all three outcomes at the `promote_required_layers.py`
  composition layer (clean promotion, staleness-refused, no-anchor) are each
  independently exercised, plus the explicit non-regression pin for the
  unchanged tip-verified path. `cross_component` does not apply — this diff
  touches neither the merge/churn/event-log resolver, hooks, pipeline
  validators, nor campaign drain, so no Integration Coverage behavior is
  owed.

## Operational follow-up (not part of this diff — an operator action after
merge, per the task brief's own "FIRST, AND IT IS ONE COMMAND")

After the next manifest refresh reaches `main` and CI reports it verified,
re-run `promote_required_layers.py --project-root . --manifest
.shipwright/compliance/test-traceability.json` (dry-run) and check whether
the same seven FRs (FR-01.01, .06, .07, .09, .11, .13, .14) promote again.
Stable across windows ⇒ this mechanism is safe and mechanical as designed.
Swinging ⇒ the evidence base is more run-dependent than the design assumes,
and that swing — not the anchoring itself — is the finding to investigate
next. This cannot be exercised inside this worktree (no real verified commit
history exists here to walk), so it is recorded here as the next concrete
step rather than left implicit.

**No separate watch is needed to notice a bad swing (Architecture Review
finding, glm/low, accepted-and-folded):** every anchored run's `skipped`
list already carries a `reason_code: "evidence_stale_since_anchor"` entry
per refused FR. A growing count of that reason_code across runs IS the
"swing" signal — observable directly from the ledger this mechanism already
writes, with no new code and no human needing to remember a separate
ritual.

## Files created / modified

- `shared/scripts/ci_verified_anchor.py` (new)
- `shared/scripts/lib/manifest_at_commit.py` (new)
- `shared/scripts/lib/promotion_evidence_staleness.py` (new)
- `shared/scripts/lib/layer_promotion_ledger.py` (additive `anchor_commit` kwarg)
- `shared/scripts/lib/layer_promotion_apply.py` (`record_ledger_entries` reads `anchor_commit` from `ci_evidence`)
- `shared/scripts/tools/promote_required_layers.py` (anchor fallback + staleness override + refactored `_read_committed_manifest`)
- Tests: `shared/tests/test_ci_verified_anchor.py`, `shared/tests/test_manifest_at_commit.py`,
  `shared/tests/test_promotion_evidence_staleness.py`, extensions to
  `shared/tests/test_layer_promotion_ledger.py`, `shared/tests/test_layer_promotion_apply.py`,
  `shared/scripts/tools/tests/test_promote_required_layers.py`
