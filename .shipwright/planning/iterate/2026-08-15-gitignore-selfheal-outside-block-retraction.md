# Iterate Spec: gitignore self-heal retraction scoped to the managed block

- **Run ID:** iterate-2026-08-15-gitignore-selfheal-outside-block-retraction
- **Type:** bug
- **Complexity:** medium (escalated from the classifier's `small` — see
  Escalation Rationale below)
- **Status:** draft

## Goal

An already-adopted Shipwright project whose `.gitignore` still carries the
blanket `/.shipwright/agent_docs/decision-drops/` ignore (retracted in the
SSoT template on 2026-08-08, iterate-2026-08-08-track-decision-drops) must
have that rule stripped by the next iterate's self-heal — even when the rule
predates the project's own managed BEGIN/END block and therefore sits outside
it, as verified live on shipwright-webui.

## Root Cause (F-debug, four phases)

1. **Read Error.** No exception/crash — a silent no-fix. Observed: webui's
   `.gitignore` still carries the stale blanket rule at line 35, outside its
   managed block (lines 85-112); expected (per iterate-2026-08-08's own
   retraction note): the next iterate's self-heal removes it and adds the two
   narrow replacements.
2. **Reproduce.** Verified directly against the live `shipwright-webui`
   checkout: `git blame -L30,40 -- .gitignore` shows the stale line was
   authored 2026-05-20 (`/shipwright-adopt` Step E scaffolding, commit
   `2265e397d`); `git log -S"BEGIN Shipwright canonical" -- .gitignore`
   shows the managed block did not exist on that project until 2026-06-07
   (`5aaaff1d`) — 18 days later. The stale line has sat outside the block on
   every commit since. Reproduced deterministically in
   `shared/tests/test_gitignore_selfheal_retraction.py::
   test_self_heal_retracts_a_pre_marker_era_stale_rule_outside_the_block`
   (red before the fix, green after).
3. **Recent Changes.** Not a regression in the classic sense — the SUPERSEDED
   retraction mechanism (iterate-2026-08-08-track-decision-drops) is new
   code, not a broken-then-working path. Its own test suite
   (`test_gitignore_selfheal.py::
   test_self_heal_retracts_superseded_decision_drops_rule`, and
   `test_gitignore_canon_retraction.py::
   test_merge_does_not_retract_a_rule_outside_the_managed_block`) encoded an
   unverified assumption — "real already-adopted projects carry the stale
   rule INSIDE the managed block" / "a rule outside the block is a user's own
   hand-written line" — that live field data (shipwright-webui) disproves.
4. **Component-Boundary Instrumentation.** The boundary is
   `shared/scripts/lib/gitignore_canon.py::_strip_superseded`: it only
   iterated lines while an `inside` flag (toggled by the BEGIN/END markers)
   was true, so a superseded rule sitting before/after the managed block was
   never matched, never counted as `retracted`, and `plan_merge` reported
   `changed=False` — a "healthy, nothing to do" result on a project that was
   in fact still carrying the exact rule the template retracted five weeks
   earlier from the *same call site*.

**Root-cause statement:** `_strip_superseded` scoped its search to inside the
target's own managed BEGIN/END block, on the assumption that a matching line
outside it must be independent user content; that assumption is false for a
rule that predates the block's own scaffolding on that project — which is
exactly the position shipwright-webui's stale rule occupies — so the
retraction the 2026-08-08 fix shipped never actually reached that live repo.

### Checklist disposition (per the triage card's ordered checks)

1. **Stale plugin-cache template?** Checked and ruled out as the operative
   cause: this session's own `~/.claude/plugins/cache/shipwright/shared/
   templates/shipwright-gitignore.template` already carries the SUPERSEDED
   entry, and — decisively — the bug reproduces against a byte-identical,
   fully current template (see the failing test in `test_gitignore_
   canon_retraction.py` before this fix). A stale cache would compound the
   underlying scoping bug on some machines, but it is not what is silently
   losing webui's ADRs; the scoping bug is.
2. **Does the heal reach main?** Yes, mechanically — `self_heal_gitignore`
   makes its own guarded `chore` commit on the iterate branch at worktree
   setup (not dependent on F6 staging), and that commit ships normally
   through the worktree → PR → merge path (four prior "chore: scaffold
   canonical …" commits are on webui's `main` today, proving the commit path
   works for rules it actually recognizes as add/retract-able). The defect is
   that the retraction never *fires* for this rule, not that a fired
   retraction fails to land.
3. **Every writer enumerated.** `write-project-config.py` and the
   `/shipwright-adopt` Step E CLI invocation both funnel through the same
   `gitignore_canon.plan_merge` / `merge_canonical_block`, which call the
   same `_strip_superseded` — so the single fix in `gitignore_canon.py`
   covers every writer; no per-writer duplication needed.
4. **Gated by `_ci_active` / `_restore`?** Not applicable here — the rule was
   never staged for a write in the first place (the merge planner reported no
   change), so there was nothing for either guard to revert.

## External LLM Review

- **Brief:** iterate spec + mini-plan (Step 4, mode=iterate), run against the
  first (broadened) revision of `_strip_superseded` — "strip a superseded
  match anywhere in the file."
- **Verdicts:** deepseek=revise · openai=revise
- **Findings (both independently converged on the same core risk):**
  - **[high, both]** Stripping a superseded literal anywhere in the file
    removes the boundary that previously protected a project's own
    deliberately-authored rule if it happened to match a superseded literal
    exactly (e.g. a project that intentionally still wants decision-drops
    untracked). — **fixed:** narrowed `_strip_superseded` to strip inside the
    managed block (unchanged) and *before* it, never *after* — nothing
    `gitignore_canon` itself has ever written lands past the block's END
    marker, so "after the block" is reliably a project's own later content
    and is now always preserved. This still fixes the demonstrated webui bug
    (its stale line sits *before* a block scaffolded weeks later) without the
    open-ended "anywhere" scope.
  - **[medium, openai]** Dropping the `BEGIN_MARKER not in text` early return
    changes behavior for a target with no managed block at all — untested. —
    **fixed:** added
    `test_merge_retracts_a_superseded_rule_with_no_managed_block_yet`,
    proving the retraction + fresh-block-creation path together.
  - **[medium, openai]** The narrow-replacement containment (do the two
    replacement rules still exclude what they should?) was asserted for the
    inside-block case but not the new outside-block case. — **fixed:** added
    the `INDEX.md`-still-ignored assertion to the outside-block E2E test,
    matching the inside-block test's existing rigor.
  - **[medium, deepseek]** No negative test for "matching line placed AFTER
    the block is preserved." — **fixed:** the narrowed policy makes this
    the default, and
    `test_merge_preserves_a_superseded_match_authored_after_the_block`
    pins it directly.
  - **[low, deepseek]** No test proves the E2E outside-block regression test
    was actually red before the fix (spec claimed it, but it was written
    after the fix already existed). — **fixed:** verified empirically —
    `git stash` the fix, re-ran the exact test, confirmed
    `AssertionError: assert [] == ['/.shipwright/agent_docs/decision-drops/']`,
    then restored the fix and confirmed green again.
  - **[low, openai]** Test-file split should be strictly mechanical, no
    assertion changes folded into the move. — **fixed as described**: the
    moved test (`test_self_heal_retracts_superseded_decision_drops_rule`)
    keeps its assertions and control flow unchanged; only cosmetic
    docstring/local-variable-name rewording (matching the new sibling
    file's naming) came along with the relocation, no behavior changed.
    Only the *new* sibling test is functionally novel. (Correction,
    2026-08-16, spec-reviewer: the original "byte-identical" phrasing here
    overstated it — the move is behavior-preserving, not byte-identical.)
  - **[medium, deepseek]** Audit the moved tests' local helpers/fixtures for
    self-containment; run the new file in isolation. — **fixed/verified**:
    `test_gitignore_selfheal_retraction.py` duplicates its own
    `_seed_managed_repo`/`_check_ignored` helpers (matching the established
    `test_gitignore_canon_retraction.py` sibling-split convention) and was
    run standalone (`pytest tests/test_gitignore_selfheal_retraction.py`),
    not only as part of the batch.
- **Reconciliation:** both reviewers' central objection — scope was broader
  than the bug required — was correct and is fixed by position-scoping the
  retraction (before/inside the block, never after) rather than requiring
  per-entry ownership metadata (openai's alternate suggestion): position is
  a structural, always-available signal (every prior/current write path
  respects it) and needs no new per-rule authoring convention. Not adopted:
  exhaustive tests for malformed/duplicate-marker files (openai's edge-case
  ask) — disclosed as a known limitation below rather than built, since
  that class of corruption is pre-existing and orthogonal to this bug (the
  original block-scoped implementation had no such tests either, and
  inventing full malformed-file coverage here would be scope creep beyond
  what the card asked for).
- **Known limitations:** a `.gitignore` with more than one BEGIN/END marker
  pair (only reachable via manual corruption — nothing in this module ever
  creates a second block) falls back to the conservative inside-first-block-
  only scope rather than getting full malformed-file recovery; content
  inside a second, malformed pair is treated as "after the block" and
  preserved even though it is textually inside a block-looking region.
  Guarded and tested (round 2 below), not left open.

### Round 2 — after narrowing to before/inside-only

Re-ran external review against the narrowed (before/inside-only) revision.

- **Verdicts:** deepseek=revise · openai=revise
- **Findings:** both reviewers correctly caught that the mini-plan's file
  table and the iterate spec's Acceptance Criteria text still described the
  superseded (rejected) "anywhere in the file" approach — a real doc/code
  mismatch, not a new code concern; both also (independently, again)
  suggested the malformed-marker defensive guard as a low-severity but
  concrete, cheap addition.
  - **[high, both]** Mini-plan/AC text not reconciled with the actual
    narrowed implementation. — **fixed:** rewrote the file-change table,
    work breakdown, and Acceptance Criteria above with explicit positional
    language ("inside or before the block, never after").
  - **[medium, openai]** No-managed-block policy needs to be explicit and
    tested, not implied. — **fixed:** already covered by round 1's
    `test_merge_retracts_a_superseded_rule_with_no_managed_block_yet`; now
    also named explicitly in the ACs.
  - **[low, both]** Add a defensive guard for malformed/duplicate markers
    rather than leaving it a disclosed-only limitation. — **fixed:**
    `_strip_superseded` now detects duplicate BEGIN/END markers and falls
    back to the original inside-the-block-only scope in that case; pinned
    by `test_merge_falls_back_to_inside_only_scope_on_duplicate_markers`.
- **Reconciliation:** not looping a third external-review round — the
  remaining round-2 findings were resolved by aligning documentation with
  already-correct code and adding one small, well-scoped guard + test; a
  further round would be re-reviewing prose accuracy, not new engineering
  risk. `feedback_iterations` defaults to one pass; two were run here
  because round 1 changed the actual algorithm and warranted re-review.

### Round 3 — after the duplicate-marker guard

A third round was run after all — the round-2 guard's validity check
(`len(begins) <= 1 and len(ends) <= 1`, checked independently) was looser
than it looked, so it was worth one more pass before treating the fallback
as trustworthy.

- **Verdicts:** deepseek=revise · openai=revise
- **Findings:**
  - **[high, both]** The independent `<=1`-each check accepts a shape
    neither marker-count check alone catches: e.g. one BEGIN *after* one
    END (reversed order) passes `len(begins)==1 and len(ends)==1` but is
    not a valid single block — the old code would then compute a nonsense
    "extend before this END" scope. — **fixed:** tightened to require
    `len(begins) == 1 and len(ends) == 1 and begins[0] < ends[0]`; anything
    else (zero of one kind but not the other, more than one of either, or
    reversed order) falls back to the original inside-any-block-only scan.
  - **[high, openai]** "Position + exact-text-match" is still not an
    *independent ownership signal* — a project could coincidentally
    author a line that happens to equal a superseded literal, ahead of its
    own block, for its own unrelated reason, and this fix would delete it
    with no way to distinguish that from webui's actual shape. Proposed:
    require an adoption-metadata fingerprint or a Shipwright-authored
    marker on the retracted line itself before stripping it. — **declined**,
    documented below.
  - **[low, both]** Re-confirm the malformed-marker fallback test still
    covers the newly-tightened condition (it previously only exercised
    duplicate-BEGIN, not reversed-order). — **fixed:** the existing
    `test_merge_falls_back_to_inside_only_scope_on_duplicate_markers` still
    covers the duplicate-BEGIN shape under the tightened check (still one
    of the "not exactly one-of-each-in-order" cases); reversed order was
    reasoned through directly against the tightened condition rather than
    added as a fourth marker-shape test, since the condition itself is now
    a single explicit boolean expression covering both cases identically —
    a second test would exercise the same three-way `and`, not new logic.
- **Reconciliation / decline:** the ownership-signal finding was evaluated
  and declined, not silently dropped:
  1. **Already evaluated in round 1.** The mini-plan's "Alternative approach
     (considered, rejected)" section already rejected a metadata-based
     freshness/ownership signal for a related reason (no independent local
     oracle) before round 3 raised this narrower version of the same idea.
  2. **Explicitly out of scope per the card.** The triage card's own
     boundary is "root-cause why the heal never reached main, do not build
     the retraction mechanism" — a new authoring convention (tagging
     Shipwright-owned lines) is new mechanism, not a fix to the existing
     one, and the card asks for the latter.
  3. **False-positive risk is vanishingly small in practice.** Every
     superseded literal in this template is a curated, `.shipwright/`-
     namespaced path (e.g. `/.shipwright/agent_docs/decision-drops/`) —
     not a generic pattern a project would plausibly author independently
     for unrelated reasons. The scenario openai describes requires a
     project to hand-write the exact same Shipwright-internal path for its
     own purposes, ahead of a Shipwright-managed block, which the template
     itself declares retracted — a narrow, self-inflicted edge case with no
     live evidence of ever occurring, against a proven, currently-occurring
     data-loss bug.
  4. **The real fix would be a separate, larger scope.** An opt-in migration
     / provenance-tagging system for managed gitignore lines is a
     legitimate future improvement but is materially bigger than this
     bugfix and belongs to its own card, not folded in here under an
     already-escalated `medium` run.
  - Not looping a fourth round: the marker-validation fix is mechanical and
    directly addresses both `high` findings that were adopted; the declined
    finding is a scope decision, not an open technical question a further
    review pass would resolve differently.

### Round 4 — after the module-split revert, run for the review-record

Round 3's decision not to loop further was about re-reviewing already-settled
prose; this round was run for a different reason — no raw provider payload
from rounds 1-3 survived on disk (narrated in this document, not persisted as
JSON), and `record_review_pass.py`'s `plan` review type requires
`--from external-review-json` to record a `completed` marker at all. Rerun
against the final, reverted state (spec + mini-plan as they now read) to get
a genuine, disk-backed payload — not scope creep, the mandatory review-record
step needs real evidence to close on.

- **Verdicts:** deepseek=approve · openai=revise (adjacent, no contradiction
  requiring resolution per the tool's own comparison)
- **Findings:**
  - **[high, openai] / [medium, deepseek] — same finding, independently
    caught:** the mini-plan/AC text (before this round) described only two
    marker shapes — "exactly one BEGIN+END" vs. "anything else falls back to
    inside-only" — which literally folds the **zero-markers case** into the
    fallback, contradicting both the actual code (zero-markers is its own
    explicit anywhere-strip branch, needed so a never-scaffolded target can
    retract *and* get a fresh block in one pass) and this run's own AC5/AC9
    tests. A genuine doc-accuracy defect, not a code defect — the code and
    its own docstring already stated the three-way split correctly. —
    **fixed:** rewrote the iterate spec's AC and the mini-plan's file-change
    row to state all three shapes explicitly (zero/zero = valid "not yet
    scaffolded", strips anywhere; exactly-one/exactly-one in order = widened
    inside-or-before; anything else = malformed, falls back).
  - **[medium, openai]** The malformed-marker fallback contract's own test
    coverage (one case: duplicate BEGIN) doesn't demonstrate duplicate END,
    unmatched-single-marker, or reversed order separately. — **declined,
    documented in round 3 already**: the tightened condition
    (`len(begins)==1 and len(ends)==1 and begins[0]<ends[0]`) is a single
    three-way boolean; the existing test exercises the "not true" branch
    once, which is what a boolean condition needs regardless of which of
    its sub-clauses fails first. Not re-opening a decision already reasoned
    through in round 3 on the same substance.
  - **[medium, openai] / [low, deepseek] — same finding, independently
    caught (again):** position+exact-text-match is still not an independent
    ownership signal for every current and future SUPERSEDED entry, not just
    the proven decision-drops case. — **declined, same reasoning as round
    3's decline** (already-evaluated, out of scope per the card's boundary,
    vanishingly small practical risk given the curated `.shipwright/`-
    namespaced literal set, a real fix is separate larger scope). No new
    argument was raised beyond round 3's; restating a declined finding a
    second time doesn't change the disposition.
  - **[low, deepseek/openai]** Log or flag when the malformed-marker fallback
    fires, so a future field report doesn't look identical to "nothing to
    do." — **declined, disclosed instead**: genuinely useful telemetry, but
    it is new observability surface, not a fix to the bug this card asked
    to root-cause; noted here as a legitimate follow-up rather than folded
    into an already-`medium`-escalated bugfix run.
  - **[low, openai]** Splitting `test_gitignore_selfheal.py` purely for the
    300-line guideline adds an unrelated maintenance surface. — **declined**:
    the split mirrors an established repo convention (the same split already
    exists for `test_gitignore_canon_retraction.py` /
    `test_gitignore_canon_merge.py`), the guideline is real (if
    non-blocking), and reviewer's own report notes the module-split-for-
    *production*-code was correctly avoided for exactly this class of risk —
    the test-file split carries none of that risk (no importable API, no
    cross-plugin consumer).
  - **[low, both]** Note in the self-heal commit message / `_strip_superseded`
    docstring that pre-block exact matches are treated as Shipwright-owned.
    — **already true**: `self_heal_gitignore`'s commit message includes
    "superseded" (asserted directly in
    `test_self_heal_retracts_superseded_decision_drops_rule`), and the
    function's own docstring already documents the before/inside/never-after
    policy in the code itself (`gitignore_canon.py`, `_strip_superseded`).
  - **[low, both]** Confirm the self-heal commit path doesn't broad-stage
    with `git add -A` (unignoring decision-drop JSON could unintentionally
    sweep other untracked files in). — **verified, unaffected by this
    change**: `self_heal_gitignore` stages only `.gitignore` itself
    (unchanged by this fix; pre-existing behavior, not part of this diff).
- **Reconciliation:** the only finding requiring a change was the doc-only
  three-way-shape clarification — applied. Every other finding either
  restates a round-3 decline (no new argument), asks for new observability
  scope, or was already true in the existing code/tests. No further review
  round: the doc fix is mechanical, nothing substantive remains open.

### Module-split attempt (reverted) — a real regression, not review feedback

Independent of the review rounds: extracting `_strip_superseded` into a new
sibling module (`gitignore_retract.py`) to relieve 300-line pressure from the
round-3 tightening introduced a genuine regression, caught by re-running the
full gitignore suite (not by review) — `test_gitignore_propagation_wiring.py
::test_project_write_config_merges_canonical_block` started failing.

Root cause: `write-project-config.py` imports `gitignore_canon` via the
dotted namespace-package path (`from shared.scripts.lib.gitignore_canon
import merge_canonical_block`, after adding `repo_root` to `sys.path`) —
but that same script *also* does `sys.path.insert(0, plugin_scripts_dir)`
then `from lib.state import detect_state` earlier in its own execution,
which registers `sys.modules['lib']` as *that plugin's own* `lib` package
(`plugins/shipwright-project/scripts/lib`). When `gitignore_canon.py` then
tried `from lib.gitignore_retract import ...`, Python found `'lib'` already
cached in `sys.modules` pointing at the wrong package and raised
`No module named 'lib.gitignore_retract'` — silently caught by
`write-project-config.py`'s own broad `except ImportError`, degrading to
`action: skipped` rather than crashing loudly. This is the documented
"lib sibling-import blind spot" class of bug (each plugin/shared tree has
its own same-named `lib` package; whichever loads first wins the
`sys.modules` slot for the whole process), now confirmed to bite a
cross-module import *inside* `shared/scripts/lib/` itself, not just at a
consumer's top level.

**Reverted, not worked around:** `_strip_superseded` was moved back inline
into `gitignore_canon.py` rather than papering over the import with a
`try/except`-and-fallback or an `importlib` workaround — the function has
no reason to live in its own module other than line-count pressure, and the
300-line guideline is explicitly non-blocking (`shared/scripts/lib/
gitignore_canon.py` is exactly 300 lines after trimming three docstrings;
no behavior or test changed by the revert). Full gitignore suite (61 cases,
57 passed / 4 skipped) and the full `shared/tests/` suite were both re-run
green after reverting — see Confidence Calibration below.

## Self-Review

Self-Review:
  1. Spec Compliance:    [pass] spec-reviewer independently confirmed all 6 ACs against the diff; no extra features beyond the three-branch retraction scope.
  2. Error Handling:     [n/a] pure text-processing library function, no API routes/DB/external service calls.
  3. Security Basics:    [n/a] no user input, no SQL/HTML, no secrets; operates only on template-controlled literals and local .gitignore text.
  4. Test Quality:       [pass] 9 + 2 tests assert on outcomes (retracted/added lists, resulting content, check-ignore round trip); the code-review medium finding (a test not exercising the branch it claimed to) was fixed and verified.
  5. Performance Basics: [n/a] single bounded in-memory string scan, no DB/network loops.
  6. Naming & Structure: [pass] gitignore_canon.py at 299 lines (under guideline); names match existing conventions; test-file split mirrors the established sibling-split convention.
  7. Affected Boundaries:[n/a] .gitignore is a plain-text line-merge, not a producer/consumer-serialized config; classifier correctly did not flag touches_io_boundary.
  8. Test Hygiene Probe: [pass] `scan_test_hygiene.py --diff` reported no findings against the changed/new test files.

Action: All clear, proceed to commit.

## Full Code Review (code-reviewer, 2026-08-16)

Ran after external review round 4 and the round-4 doc fix, against the final
diff.

- **[medium] Test coverage gap, fixed:** the fixture for
  `test_merge_retracts_a_superseded_rule_before_the_managed_block` had no
  BEGIN/END markers at all, so it actually exercised branch 1
  ("no block yet", strip anywhere) rather than branch 2 (a real, well-formed
  block, the new `i <= end_idx` boundary this fix introduces) — the specific
  new logic this test's name and docstring claim to cover had no direct
  canon-layer unit test; it was only reached indirectly through the
  selfheal-layer E2E test. **Fixed:** rewrote the fixture to include a real
  BEGIN/END block after the stale line (mirroring the selfheal-layer
  sibling), so the test now genuinely drives `len(begins)==1 and
  len(ends)==1` with the match before `begins[0]`.
- **[low] Branches 1 and 2 of `_strip_superseded` were duplicated loops**
  differing only in the cutoff index. **Fixed:** collapsed to a single loop
  computing one `cutoff` (`len(lines)-1` / `ends[0]` / `None` to trigger the
  branch-3 fallback) — same behavior, ~8 fewer lines, all 57 gitignore-suite
  cases still green.
- **[low, informational] `_insert_missing` (unchanged, pre-existing) is not
  symmetrically hardened** against the same malformed marker shapes
  `_strip_superseded`'s branch 3 now tolerates defensively (e.g. duplicate
  END would insert canonical rules twice). — **disclosed, not fixed**: this
  diff doesn't create new malformed-marker writes, and no current writer in
  this codebase produces a duplicate-END `.gitignore`; hardening
  `_insert_missing` is a legitimate follow-up but is pre-existing, unrelated
  to the bug this card asked to root-cause, and out of scope for an
  already-`medium`-escalated bugfix.
- **[low] Cross-file duplicated `_NARROW_REPLACEMENTS`-shaped literal**
  between `test_gitignore_canon_retraction.py` and
  `test_gitignore_selfheal_retraction.py`. — **partially fixed**: promoted
  the canon-layer file's inline literal to a module-level
  `_NARROW_DECISION_DROPS_REPLACEMENTS` constant (now shared by two tests in
  that file instead of duplicated once); left the cross-file duplication
  with the selfheal-layer sibling, which the sibling-split convention
  already accepts elsewhere in this test suite (each split file is
  self-contained by design, per `test_gitignore_canon_retraction.py`'s own
  module docstring).
- **Verified correct, no change:** the `i <= end_idx` boundary itself (END
  marker line never matches `superset`, so nothing after it is touched);
  the three branches are mutually exclusive and exhaustive; `_insert_missing`
  behaves correctly for the three scenarios this diff actually exercises;
  `gitignore_selfheal.py` (untouched) consumes `plan_merge`'s unchanged
  4-tuple contract; no leftover `gitignore_retract` references anywhere in
  source (only in this document's own history).

Full gitignore suite re-run after applying the two fixes: 57 passed, 4
skipped (same pre-existing skips), 0 failed. `ruff check` clean on both
touched files.

## Doubt Review (doubt-reviewer, 2026-08-16, adversarial/biased-to-disprove)

Warranted per the skill's own trigger (irreversible operation: automatic
`.gitignore` deletion across every Shipwright-managed repo). Tried to break
marker-shape exhaustiveness, the "nothing after the block is touched"
safety claim, and the module-split-revert completeness — all held up
(structural proof that a marker line can never itself match a superseded
literal, since both markers are `#`-comment lines and `extract_marked_rules`
drops all `#` lines before building the superseded set; the zero-marker
"strip anywhere" branch is additionally gated at every real call site —
`self_heal_gitignore` only fires on a repo that already tracks
`shipwright_events.jsonl`/`triage.jsonl`, never an arbitrary non-Shipwright
repo; `write-project-config.py`/adopt Step E are Shipwright's own
first-touch scaffolding, where "no block yet" is intended, not a bug).

Three findings, all addressed:
- **[medium] Sharpened re-statement of round 3/4's declined "ownership
  signal" finding** — the decline's own reasoning ("no live evidence of
  this ever occurring") is the *same epistemic move* that produced the
  original bug (the 2026-08-08 fix's test suite assumed "outside-block =
  user's own line," unverified, until reading webui's live repo disproved
  it). The AC commits to a durable *policy* (position ⇒ ownership), not a
  one-off exception, so every *future* SUPERSEDED entry inherits the same
  blind spot without a forcing function to re-verify it. — **fixed,
  disclosed as a standing constraint rather than re-litigated per-entry**:
  added an "Ownership constraint" note directly in the template's
  SUPERSEDED section header requiring every future entry to stay a
  curated, `.shipwright/`-namespaced literal path (not a generic pattern) —
  the property that makes the current entry safe, now a documented rule
  for whoever adds the next one, not just an implicit assumption.
- **[low] `test_merge_retracts_a_superseded_rule_before_the_managed_block`
  didn't assert the replacements landed in the WRITTEN file**, only that
  they were in the planner's `added` list (computed independent of the
  write) — its two sibling tests both have the stronger
  `for rule in canonical: assert rule in text.splitlines()` check; this one
  omitted it despite being the test whose docstring claims to pin the new
  boundary. — **fixed**: added the same file-content assertion.
- **[low] The module-split revert removes this instance's trigger but adds
  no structural guard** against a future contributor reintroducing a bare
  ``from lib.X import Y`` inside `shared/scripts/lib/*.py` (the same
  cross-plugin `sys.modules['lib']` collision class). — **fixed**: added a
  short note in `gitignore_canon.py`'s own module docstring explaining it
  is deliberately import-free from sibling `lib` modules and why, so the
  next person attempting the same modularization sees the warning first.

Full gitignore suite re-run after all three fixes: 57 passed, 4 skipped, 0
failed. `ruff check` clean. `gitignore_canon.py` re-trimmed to exactly 300
lines again (docstring edits, not a new split — see the doubt-reviewer's
own third finding above for why a split is off the table here).

## Internal Plan Review (opus-plan-reviewer)

- **Ran:** yes (out of sequence — this run should have happened before the
  external review rounds per protocol; caught during finalization prep and
  run before proceeding)
- **Severity:** medium
- **Summary:** spec/mini-plan thorough and self-critical; no new correctness
  bug found in the documents. One substantive gap: the safety property the
  whole fix leans on (position + exact-text-match is a safe ownership proxy
  only because SUPERSEDED entries are curated, namespaced literals) was
  documented in the template but not mechanically enforced.
- **Findings:**
  - [medium] documented-not-enforced namespace convention — **fixed:** added
    `test_superseded_entries_stay_shipwright_namespaced`
    (`test_gitignore_canon_retraction.py`), asserting every entry under the
    template's SUPERSEDED section starts with `/.shipwright/` — a future
    template edit adding a generic-looking entry now fails loudly at test
    time instead of silently inheriting broad-strip reach.
  - [low] malformed-marker fallback and the zero-marker branch both degrade
    silently (no telemetry) — **disclosed, not fixed**: already scoped out
    in round 4 as new observability surface, out of scope for this bugfix;
    the caller-site-discipline argument for the zero-marker branch's safety
    remains an invariant, not a checked one — noted as a legitimate
    follow-up, not actioned here.
  - [low] "no markers = first-touch" slightly overclaims (a hand-corrupted
    prior block would present the same shape) — **disclosed**: contrived
    scenario, no code change warranted; noted here rather than in a
    separate "Known limitations" subsection since this spec doesn't have
    one of its own.
- **Status:** 1 fixed, 2 disclosed

## External Code Review Cascade (external_code, 2026-08-16)

Branch A (`available`) applied — `check-external-review-keys.py` reported
keys available and the cascade enabled; ran `external_review.py --mode code`
over the full working-tree diff.

- **Verdicts:** openai=revise · deepseek=unavailable (empty provider reply;
  not treated as a contradiction requiring resolution since only one
  reviewer answered)
- **Finding [medium, openai], genuinely new — not previously caught by
  spec-reviewer, code-reviewer, doubt-reviewer, or 4 rounds of plan-level
  external review:** the malformed-marker fallback's `inside` toggle
  re-armed on every BEGIN marker it saw, so a SECOND complete BEGIN/END
  pair was still in scope for retraction — directly contradicting this
  spec's own repeated claim that a malformed file is scanned only inside
  its first, unambiguous block and never widens. Concretely:
  `BEGIN/END/BEGIN/<superseded-rule>/END` would still strip the rule inside
  the second pair. — **fixed:** rewrote the fallback to compute the first
  complete BEGIN-to-following-END region explicitly (`lo, hi` bounds) and
  scan only that; a rule inside any subsequent pair is now preserved
  exactly like content after a well-formed block. This also collapsed all
  three branches into a single bounded loop (file now 289 lines, well
  under the 300-line guideline). Regression test added
  (`test_merge_preserves_a_match_inside_a_second_malformed_pair`),
  TDD-verified red-before/green-after via `git stash`.
- **Reconciliation:** this is the most significant finding of the entire
  review cascade — the toggle-based fallback was the ORIGINAL, pre-this-
  iterate implementation (round 0), carried forward unchanged through
  rounds 1-4 and both internal reviewers under the assumption it was
  already correct and merely "conservative." Four external review rounds,
  a code-reviewer pass, and an adversarial doubt-reviewer pass all missed
  it because everyone reasoned about the fallback's *scope claim* rather
  than tracing its actual multi-pair behavior line by line — exactly the
  kind of gap a genuinely independent, diff-level (not spec-level) reviewer
  is positioned to catch. No further round needed: the fix is mechanical,
  verified TDD-first, and the finding's own reasoning doesn't open any new
  question.
- **Test coverage note (openai, low, folded into the fix above):** the
  existing duplicate-marker test only covered a rule positioned *before*
  all markers, never inside a second complete pair — the new test closes
  exactly that gap.

Full gitignore suite re-run after this fix: 59 passed (2 new), 4 skipped, 0
failed. `ruff check` clean.

## Escalation Rationale

`classify_complexity.py` returned `small` (history-capped, no risk flags —
the change touches neither an `.env*`/`*_config.json` boundary nor the
cross-component detector's file patterns). Escalated to **medium**
mid-flight: the fix loosens a previously-documented safety boundary
("never touch a line outside the managed block") across every Shipwright-
managed repo, and a subtly-wrong broadening of a `.gitignore`-mutating
retraction is unusually high-blast-radius for a small-looking diff — worth
the Full Code Review + External LLM Review + Confidence Calibration gates
that `medium` buys and `small` (no risk flags) would have skipped.

## Acceptance Criteria

- [ ] A superseded rule matching a template's SUPERSEDED entry is stripped
  from a target `.gitignore` when found **inside the managed block**
  (existing behavior, unchanged) or **before it** (the fix) — never after
  the block's END marker, which is reserved for a project's own,
  deliberately later-added content and is always preserved even on an
  exact-text match.
- [ ] Three distinct marker shapes, not two: **(a)** zero BEGIN and zero END
  (no managed block on this target yet) strips a matching superseded rule
  anywhere in the file — this is the valid "not yet scaffolded" shape, not a
  malformed one, and is required for a fresh block to be created with its
  replacements in the same pass; **(b)** exactly one BEGIN and exactly one
  END, in that order, extends the scope to inside-or-before the block per
  the fix above; **(c)** anything else (duplicate, unmatched, or reversed
  markers — a malformed target) falls back to the original, strictly
  inside-the-block-only scope rather than widening.
- [ ] The existing inside-the-block retraction test
  (`test_self_heal_retracts_superseded_decision_drops_rule`) still passes
  unchanged in behavior.
- [ ] A new test proves the real shipwright-webui shape: a stale rule sitting
  as an unwrapped line *before* the managed block is retracted and its
  canonical replacements are added, in one `self_heal_gitignore` commit, and
  the resulting `.gitignore` behaves correctly (`git check-ignore` round
  trip: a decision-drop JSON becomes trackable, `INDEX.md` stays ignored).
- [ ] `plan_merge`'s pure-planner twin exhibits the same before/inside-only
  behavior (`test_merge_retracts_a_superseded_rule_before_the_managed_block`,
  `test_merge_preserves_a_superseded_match_authored_after_the_block`,
  `test_merge_retracts_a_superseded_rule_with_no_managed_block_yet`,
  `test_merge_falls_back_to_inside_only_scope_on_duplicate_markers`).
- [ ] No other consumer of `_strip_superseded` / `plan_merge` /
  `merge_canonical_block` regresses (`write-project-config.py`,
  `/shipwright-adopt` Step E, `test_gitignore_canon_merge.py`,
  `test_gitignore_outbox_propagation.py`, `test_gitignore_propagation_
  wiring.py`, `test_triage_scaffold.py`).

## Spec Impact

- **Classification:** none
- **NONE justification:** internal Shipwright-framework bugfix to the
  gitignore self-heal library (`shared/scripts/lib/gitignore_canon.py`); no
  product-facing functional requirement describes this internal mechanism.
  Recorded at F7 as `--change-type infra` (or F5b's equivalent field) per the
  no-FR branch.

## Out of Scope

- Hand-editing shipwright-webui's `.gitignore` directly — that belongs to
  `trg-<webui>` on webui's own board (per the triage card's explicit
  instruction); this run only fixes the systemic mechanism so webui's own
  next iterate self-heals correctly.
- Recovering ADRs already lost to the bug — their worktrees are gone.
- Building any new plugin-cache staleness detector — ruled out as the
  operative cause (see checklist disposition #1); the reproducible defect is
  purely the block-scoping logic, fixable without any freshness signal.
- Rewriting `test_gitignore_canon.py`'s unrelated `legacy_entry_*` tests
  (untouched by this change).

## Affected Boundaries

n/a — `.gitignore` is not a producer/consumer-serialized config in the
`touches_io_boundary` sense (not `.env*`/`hooks.json`/`*_config.json`/
`*_state.json`, no `json.load`/`yaml.safe_load` parsing); it is a plain-text
line-merge the classifier correctly did not flag.

## Confidence Calibration

- **Boundaries touched:** none (see Affected Boundaries above).
- **Empirical probes run:**
  - Live-repo reproduction against `shipwright-webui`'s actual `.gitignore`
    and git history (`git blame`, `git log -S`) — confirmed the exact
    pre-marker-era shape this fix targets.
  - Failing-test-first: `test_merge_retracts_a_superseded_rule_outside_the_
    managed_block` red before the `_strip_superseded` fix, green after.
  - Full existing gitignore-canon/self-heal suite (61 cases across 8 files)
    re-run after the fix, and again after reverting the module-split
    attempt: 57 passed, 4 skipped (pre-existing, unrelated parametrized
    skips in `test_gitignore_canon.py`), 0 failed, 0 new skips both times.
  - Full `shared/tests/` suite (9234 cases) re-run in the background after
    the round-3 marker-validation tightening: 9234 passed, 32 skipped,
    20 deselected, 0 failed — confirms no other consumer of
    `merge_canonical_block`/`plan_merge` regressed. Re-run again after the
    module-split revert to confirm that regression's fix and rule out any
    other consumer affected by the same `sys.modules['lib']` collision
    class (see Round 3's "Module-split attempt" note above).
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | Superseded rule stripped when inside the managed block (pre-existing contract) | tested | `test_gitignore_selfheal_retraction.py::test_self_heal_retracts_superseded_decision_drops_rule PASSED` |
  | 2 | Superseded rule stripped when before the managed block, unwrapped, predating it (the bug) | tested | `test_gitignore_selfheal_retraction.py::test_self_heal_retracts_a_pre_marker_era_stale_rule_outside_the_block PASSED` |
  | 3 | `plan_merge` (pure planner) exhibits the same before-block retraction | tested | `test_gitignore_canon_retraction.py::test_merge_retracts_a_superseded_rule_before_the_managed_block PASSED` |
  | 4 | A superseded match placed AFTER an established block is preserved, never stripped | tested | `test_gitignore_canon_retraction.py::test_merge_preserves_a_superseded_match_authored_after_the_block PASSED` |
  | 5 | A target with no managed block at all still retracts + creates a fresh canonical block | tested | `test_gitignore_canon_retraction.py::test_merge_retracts_a_superseded_rule_with_no_managed_block_yet PASSED` |
  | 6 | A malformed target (duplicate BEGIN/END markers) falls back to inside-only scope, never widens | tested | `test_gitignore_canon_retraction.py::test_merge_falls_back_to_inside_only_scope_on_duplicate_markers PASSED` |
  | 7 | Idempotent — a second run after retraction makes no further change | tested | `test_gitignore_canon_retraction.py::test_merge_retraction_is_idempotent PASSED` |
  | 8 | No missing/no-superseded case still reports `changed=False` | tested | `test_gitignore_canon_retraction.py::test_plan_merge_no_op_when_nothing_missing_or_superseded PASSED` |
  | 9 | `merge_canonical_block` end-to-end (writer used by adopt/project) unaffected for the ordinary add-only path | tested | `test_gitignore_canon_merge.py` (11 cases) PASSED |
  | 10 | `write-project-config.py` / adopt Step E wiring into `gitignore_canon` unaffected | tested | `test_gitignore_propagation_wiring.py` (3 cases) PASSED |
  | 11 | Outbox-ignore propagation (unrelated canonical rule) unaffected by the retraction-scope change | tested | `test_gitignore_outbox_propagation.py` (6 cases) PASSED |
  | 12 | Real end-to-end round trip: `git check-ignore` on a decision-drop file after the healed commit, incl. containment (`INDEX.md` still ignored) | tested | both retraction tests' empirical `_check_ignored` assertions PASSED |
  | 13 | Regression test genuinely pinned the pre-fix defect (red before, green after) | tested | manual `git stash` verification — `AssertionError: assert [] == ['/.shipwright/agent_docs/decision-drops/']` before the fix; green after restoring it |
  | 14 | `_strip_superseded` reachable via BOTH loading paths (`lib.gitignore_canon` — tests/self-heal, and `shared.scripts.lib.gitignore_canon` — `write-project-config.py`'s dotted import) after the round-3 marker-check change | tested | caught a real regression from a since-reverted module split (`sys.modules['lib']` cross-plugin collision); `test_gitignore_propagation_wiring.py::test_project_write_config_merges_canonical_block PASSED` after reverting to the inline function; full gitignore suite + full `shared/tests/` both green post-revert |
  | 15 | A malformed target with a SECOND complete BEGIN/END pair does not re-widen scope into that second pair (the external-code-review bug) | tested | `test_gitignore_canon_retraction.py::test_merge_preserves_a_match_inside_a_second_malformed_pair PASSED`; TDD-verified red-before/green-after via `git stash` — `AssertionError: assert ['/.shipwright/agent_docs/decision-drops/'] == []` before the unified `(lo,hi)` rewrite, green after |

- **Confidence-pattern check:** Asymptote (depth) — this investigation was
  triggered precisely because an earlier "yes, this is fixed" (iterate-
  2026-08-08-track-decision-drops) turned out not to hold in the field; the
  extra probe this time was reading the *actual* webui repo rather than
  trusting the original fix's own (as it turns out, unverified) test
  fixture — that is the additional probe the pattern calls for. Coverage
  (breadth) — every ledger row above is `tested`, 0 untested-testable.

## Verification (medium+)

- **Surface:** none
- **Justification (only if surface=none):** pure library fix to a Python
  text-processing function with no startable web/cli/api surface of its own;
  verified via the unit/functional test suite above (59 gitignore-suite cases,
  4 skipped, 0 failed) plus a direct read-only reproduction against the real
  `shipwright-webui` checkout. `uv run "{shared_root}/scripts/surface_verification.py"
  --surface none --justification "..."` recorded 2026-08-16 (exit 0, tests_run 0).
