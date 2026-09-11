# iterate-2026-09-11-pr-review-evidence-filter-gap

**Status:** implemented (all review passes completed — self, plan-internal,
plan-external x3, code, doubt, external-code, spec, plus a Round 4 fix from
the live PR-review gate on this iterate's own PR #727 — see review sections
below; F0 green, F0.5/F1 clean)
**Type:** bug
**Complexity:** medium (classifier, keyword `prior_source`)

## Origin

PR #722's automated "PR Review" gate BLOCKed twice in a row with the same
class of finding: `.shipwright/planning/iterate/<run>/spec_review_reply.json`
and `.../external-code-review-raw.json` (tool-written transcripts of THIS
repo's own review pipeline) contain reviewer-verdict-shaped text
(`SHIPWRIGHT_VERDICT: approve`, "Code-reviewer may proceed") that an
automated reviewer cannot distinguish from an attacker-planted fake approval
directive. `deliver_pr.py`'s non-converging circuit breaker correctly
stopped and handed the PR back to the operator rather than re-pushing blind
fixes (per its own design intent).

Root cause, independently verified against
`plugins/shipwright-security/scripts/lib/pr_review_generated.py`:
`_REVIEW_EVIDENCE_RE` matches `reviews.json` and the legacy
`[^/]*-external-[^/]*review[^/]*\.json` shape, but misses
`external-code-review-raw.json` (nothing precedes "external-") and the
`*_reply.json` reply-file convention entirely. The module's own docstring
already states the intent ("the raw reviewer replies `external_review.py`
emits ... are tool-written transcripts OF a review — feeding them to the
reviewer is circular") — the regex just doesn't reach every file that
intent covers. Confirmed this is a pre-existing, repo-wide gap: `git grep`
on `main` finds 10 already-merged `external-code-review-raw.json` files
carrying `SHIPWRIGHT_VERDICT`, none of which triggered this gate before
(PR #722 is not new in kind, just the first to hit the two-consecutive-BLOCK
circuit breaker).

## Out of scope

- Anything inside PR #722 itself — no artifact there is deleted, redacted,
  or rewritten. This run only fixes the filter; PR #722 re-triggers its own
  "PR Review" check once this merges.
- The wider historical naming inconsistency across old iterates
  (`code-review-payload.json`, `stage1-spec-review.json`, etc.) — those are
  merged history, not a live gap for future PRs, and redesigning review-
  artifact naming into a single enforced convention is a separate, larger
  change this run does not attempt.
- `self-review-payload.json` is deliberately left matching neither
  `is_generated_path` nor `is_safe_to_skip_review` — it is the payload SENT
  TO a review stage, not a transcript OF one, and needs a reviewer's eyes.

## Acceptance Criteria

*All four ACs verified satisfied by spec-reviewer (Stage 1, PASS) against
the final code — see `## Spec Review` disposition below (recorded as the
`spec` review-cascade row).*

1. ✓ **AC1 (is_generated_path, revised after External Plan Review rounds 1 and
   2, see below).** `is_generated_path` returns `True` for exactly
   `spec_review_reply.json`, `code_review_reply.json`,
   `doubt_review_reply.json` (a closed set — repo-wide history has never
   produced a fourth name), plus `external-code-review-raw.json`,
   `external-code-review.json`, and their `.md` siblings under an
   open `external-[^/]*review[^/]*` wildcard (no fixed output filename to
   close it against) — but ONLY when nested exactly one directory segment
   below `.shipwright/planning/iterate/` (a genuine run directory), never at
   the bare top level or nested deeper. An attacker-chosen reply name like
   `evil_reply.json` is therefore never hidden at all (round 2 closed that
   wildcard); an attacker-chosen `external-...` name is still hidden (round
   2 left that one open, matching AC2's existing skip-side treatment of the
   same family) but never skip-safe. `self-review-payload.json` in the same
   directory still returns `False` from both functions.
2. ✓ **AC2 (is_safe_to_skip_review — revised after Internal Plan Review,
   External Plan Review Round 3, and Round 4, see below; narrative corrected
   after External Code Review, see that section).** NO review-evidence path
   returns `True` from `is_safe_to_skip_review` any more — not even
   `reviews.json`. Every review-evidence shape from AC1 (`reviews.json`, the
   `{spec,code,doubt}_review_reply.json` reply family, and the
   `external-*review*.json`/`.md` raw-transcript files) is hidden from the
   model (`is_generated_path`) but does NOT skip the gate — a PR touching
   only one of these still gets a real (if trivial) review call.
   `self-review-payload.json` returns `False` from both functions. Two
   earlier revisions of this AC each added something to the skip set —
   first the reply family (Round 3 reverted, below), then kept only
   `reviews.json` itself — before Round 4 (the live PR-review gate's own
   bot, on this iterate's own PR #727) found even that floor unsafe: an
   exact PATH is not PROVENANCE, and a contributor's own PR can commit a
   forged `reviews.json` at a self-chosen run directory. This narrower
   scope than AC1 is pinned by dedicated tests, not left to accidentally
   pass or silently inherit AC1's breadth.
3. ✓ **AC3 (regression coverage, no weakening).** All pre-existing tests in
   `plugins/shipwright-security/tests/test_pr_review_filter.py` and
   `test_pr_review_generated_skip_review.py` continue to pass — the legacy
   `[^/]*-external-[^/]*review[^/]*\.json` shape, the `_GENERATED_AGENT_DOCS`
   exclusion, and the canonical-basename anchoring are all unchanged.
4. ✓ **AC4 (documented reasoning, not silent widening).** The module comment
   above `_REVIEW_EVIDENCE_RE` and the `is_safe_to_skip_review` docstring
   both explain why the widened match is safe for the skip-review side
   effect, and why `self-review-payload.json` is deliberately excluded.

## Verification (medium+)

- **Surface:** none — pure library-logic change, verified by the plugin's
  own unit test suite (`plugins/shipwright-security/tests/`), not a running
  app surface.
- **Runner:** `uv run pytest plugins/shipwright-security/tests/ -q` (F0's
  canonical `run_test_suite.py` covers this unit in the full-suite run).
- **Evidence:** `shipwright_test_results.json.iterate_latest.test_completeness`
  (F5), citing the specific test functions per AC.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** high (one finding; rest medium/low)
- **Summary:** The regex widening was correct for `is_generated_path`, but
  sharing it verbatim with `is_safe_to_skip_review` handed an attacker an
  unbounded, self-chosen filename that could bypass the PR-review Required
  Check entirely.
- **Findings:**
  - security/high — `is_safe_to_skip_review` reused the wide, unanchored
    `_REVIEW_EVIDENCE_RE` verbatim; an attacker-chosen `evil_reply.json` (or
    `external-...review....json`) would post `success` with no model call.
    **fix** — introduced `_REVIEW_EVIDENCE_SKIP_RE`, a separate, closed,
    run-directory-anchored set covering only `reviews.json` and the exact
    `{spec,code,doubt}_review_reply.json` basenames — zero wildcards.
    `external-*review*.json`/`.md` stay hidden-but-not-skippable (AC2
    revised accordingly).
  - completeness/medium — `.md` raw transcripts (e.g.
    `external-code-review.raw.md`) also slipped through, same root cause,
    `.json`-only regex. **fix** — extended `_REVIEW_EVIDENCE_RE`'s
    (hide-only) match to include `.md`.
  - completeness/medium — AC1's wording implied run-directory anchoring that
    `is_generated_path` doesn't actually enforce (pre-existing laxity,
    shared with the legacy `reviews.json` behavior). **decline** — changing
    `is_generated_path`'s anchoring is a separate, larger behavior change
    not needed to close the security finding; `_REVIEW_EVIDENCE_SKIP_RE`
    (the function that actually matters for the bypass) is anchored.
  - architecture/low — redundant-looking `[^/]*-external-...` vs
    `external-...` branches. **disclose** — left as-is; collapsing them
    risks silently dropping the legacy flat-naming shape a few historical
    (already-merged) run dirs still use, for a purely cosmetic gain.
  - confirmation — `self-review-payload.json`'s exclusion (matched by
    neither regex) is correct.
- **Known limitations:** the `external-*review*` family (raw LLM transcript
  dumps) has no fixed, tool-enforced filename — `external_review.py` prints
  to stdout and the calling agent names the file — so no closed set can be
  drawn for it without either being too narrow for legitimate future runs or
  falling back to a wildcard. Resolved by keeping those files out of the
  skip-set entirely (hidden-but-reviewed) rather than trying to enumerate
  them; the wider free-form-naming problem stays explicitly out of scope
  (see spec's "Out of scope").
- **Status:** 1 fixed (high), 1 fixed (medium), 1 declined (medium, reason
  above), 1 disclosed (low, reason above), 1 confirmed clean.

## External Plan Review (glm + openai)
- **Ran:** yes
- **Verdicts:** glm=revise · openai=revise (converged on the same core
  finding independently)
- **Summary:** Both reviewers correctly caught that the Internal Plan
  Review's fix closed the *skip* bypass but left the *hide* side
  (`is_generated_path`'s new alternatives) unanchored — matching
  `*_reply.json` / `external-...review....json` at ANY depth under
  `.shipwright/planning/iterate/`, not just inside a genuine run directory.
- **Findings:**
  - security/medium (glm) + security/high (openai) — new hide-side
    alternatives unanchored, same class of attacker-chosen-filename problem
    as the (already-fixed) skip-side bug, one level down in severity since
    hiding costs visibility on one file, not a gate bypass. **fix** — split
    `_REVIEW_EVIDENCE_RE` into a LEGACY piece (unchanged, pre-existing
    `reviews.json` + old flat shape) and a new
    `_REVIEW_EVIDENCE_RE_RUN_ANCHORED` piece requiring exactly one
    run-directory segment. AC1 revised to state the anchoring explicitly.
  - approach/high (openai) — mini-plan text didn't actually describe the
    Internal-Plan-Review fix (separate skip regex). **fix** — mini-plan
    steps 7-9 added, documenting both review rounds' fixes explicitly.
  - edge-case/spec-consistency medium (glm) + dependency medium (openai) —
    mini-plan/spec didn't explicitly call out `.md` support, risking it
    silently not shipping despite being claimed fixed. **fix** — mini-plan
    step 3 now names `.(json|md)` explicitly; `.md` coverage already had a
    dedicated test (`test_raw_review_transcripts_in_markdown_are_also_excluded`),
    confirmed still passing.
  - edge-case/low (glm) — `[^/]*_reply.json` could hide an unrelated
    `user_reply.json` fixture. **disclose** — accepted: the hide-only match
    is scoped to `.shipwright/planning/iterate/<run>/`, a directory an
    ordinary source file has no reason to live in; the run-anchoring fix
    above already narrows the blast radius to that one directory.
  - risk/low (glm) — verify no other `is_generated_path` consumer is
    surprised by the widened match. **fix** — `git grep -n
    "is_generated_path\|pr_review_lib\.is_generated_path"` across
    `plugins/shipwright-security` confirms the only consumers are
    `pr_review_diff_filter.filter_generated_paths` (hides sections from the
    reviewed diff — the documented, intended use) and the test suites
    themselves; no other call site.
  - approach/positive (glm) — the hide/skip split itself, and treating the
    naming-convention redesign as out of scope, judged the right
    proportionality call.
  - edge-case/medium (openai) — requested explicit negative tests for
    nested/lookalike paths. **fix** — added
    `test_reply_and_external_hiding_requires_a_run_directory_segment` and
    `test_a_lookalike_suffix_does_not_borrow_the_closed_match` (the `.bak`
    suffix case).
- **Known limitations:** none beyond what Internal Plan Review already
  disclosed (the free-form `external-*review*` naming problem, out of
  scope).
- **Status:** revise → fixed (2 findings collapse to the same anchoring fix,
  1 mini-plan documentation gap fixed, 1 low disclosed as already-mitigated
  by the anchoring fix, 1 verified via grep, 1 confirmed sound approach).

## External Plan Review — Round 2 (glm + openai, after the anchoring fix)
- **Ran:** yes
- **Verdicts:** glm=approve · openai=revise (`requires_resolution: false` —
  a one-step gap, not flagged as a true contradiction)
- **Summary:** No high-severity findings. Both reviewers converged on the
  same cheap tightening (close the hide-side reply wildcard to an exact
  three-name set, matching the skip-side's existing closed design) plus a
  few verification/documentation requests.
- **Findings:**
  - security/medium (openai) + risk/low (glm) — the hide-side
    `[^/]*_reply\.json` alternative in `_REVIEW_EVIDENCE_RE_RUN_ANCHORED` was
    still a wildcard, unlike the already-closed skip-side
    `_REVIEW_EVIDENCE_SKIP_RE`. **fix** — before changing it, ran `git log
    --all --diff-filter=A --name-only --oneline -- "*_reply.json"` across
    every branch in this repo and confirmed exactly three basenames were
    ever produced: `spec_review_reply.json`, `code_review_reply.json`,
    `doubt_review_reply.json`. Closed the regex to that exact set;
    `external-[^/]*review[^/]*` keeps its wildcard (no fixed output
    filename — `external_review.py` prints to stdout, the calling agent
    names the file, per the Internal Plan Review's own known-limitations
    note). An attacker-chosen reply name is now not even hidden from the
    model, let alone skip-safe — pinned by a new test,
    `test_an_attacker_chosen_reply_name_is_not_even_hidden_after_round_2`.
  - edge-case/medium (openai) — asked for explicit tests proving
    `reviews.json`'s skip-anchoring at bare-top-level and deeper-nested
    paths. **verified, already covered** — checked before assuming either
    the reviewer's gap-claim or my own recollection:
    `test_review_evidence_skip_is_anchored_to_exactly_one_run_segment`
    (test_pr_review_generated_skip_review.py) already asserts `False` for
    both `.shipwright/planning/iterate/reviews.json` (no run segment) and
    `.shipwright/planning/iterate/iterate-x/nested/reviews.json` (extra
    nesting). No new test needed.
  - risk/low (openai) — asked to confirm the actual path
    `record_review_pass.py` writes `reviews.json` to, to validate the
    anchoring assumption against real producer behavior. **verified** —
    `plugins/shipwright-security/scripts/tools/record_review_pass.py`'s own
    module docstring states the path as
    `.shipwright/planning/iterate/<run_id>/reviews.json`: exactly one
    run-directory segment, matching `_REVIEW_EVIDENCE_SKIP_RE`'s
    assumption.
  - security/medium (glm) — questioned whether `is_safe_to_skip_review`
    should validate file CONTENT/provenance in addition to path, since a
    run-directory name is free-form and attacker-creatable, not
    tool-enforced. **disclose, out of scope** — this is the same
    free-form-naming-convention problem Internal Plan Review already
    disclosed (no tool in this repo enforces run-directory names either),
    just applied one level up; a content/provenance check is a materially
    larger redesign (touching `record_review_pass.py`'s write path and
    what the gate trusts, not just this filter), inconsistent with the
    peer-relayed instruction to keep this "a small dedicated iterate" — see
    the mini-plan's "Alternative approach (rejected)" section, which this
    finding is a specific instance of.
  - edge-case/low (glm) — `.md` siblings are only hidden for the
    `external-*review*` family, not a hypothetical `*_reply.md`.
    **disclose** — the same repo-wide history survey used for the fix above
    found zero `.md` reply files ever produced (only `.json`), unlike the
    `.md` external-transcript case fixed in Internal Plan Review, which was
    empirically confirmed to exist in merged history. Speculative coverage
    for a file shape that has never existed is deferred rather than added
    now.
  - risk/low (glm) — the final regex mixes an anchored, closed piece
    (`_REVIEW_EVIDENCE_RE_RUN_ANCHORED`) and an unanchored, legacy piece
    (`_REVIEW_EVIDENCE_RE`) in one file; a future "simplification" refactor
    might accidentally merge them and reopen the anchoring gap. **fix** —
    extended the module comment above both regexes to state this
    explicitly (see `pr_review_generated.py`, the "Round 2" comment block).
  - approach/positive (glm) — the hide/skip split, the naming-convention
    redesign staying out of scope, and this round's exact-set tightening
    were judged proportionate.
- **Known limitations:** unchanged from Internal Plan Review and Round 1 —
  the free-form `external-*review*` naming problem, and now also
  run-directory naming, stay explicitly out of scope (glm's content/
  provenance finding above).
- **Status:** 1 fixed (medium/low collapse to the same tightening), 1
  verified as already-covered (no code change), 1 verified via source read,
  1 disclosed (medium, architectural, out of scope), 1 disclosed (low,
  speculative), 1 fixed (low, comment-only), 1 confirmed sound approach. No
  further review round needed — remaining items are disclosed with
  reasoning, not silently dropped, per the established triage protocol
  ("for low/medium: note in ADR, proceed").

## External Plan Review — Round 3 (openai + glm, after the round-2 tightening)
- **Ran:** yes
- **Verdicts:** glm=approve · openai=revise (`requires_resolution: false`)
- **Summary:** openai's high-severity finding correctly caught that AC2, as
  it stood after round 2, had quietly expanded the PR-review gate's bypass
  surface: adding `{spec,code,doubt}_review_reply.json` to
  `_REVIEW_EVIDENCE_SKIP_RE` was never required to fix PR #722 (that bug was
  entirely about the reviewer SEEING these files — the hide side), and an
  exact basename is not provenance an attacker can't forge. glm's findings
  were all low, mostly documentation/completeness.
- **Findings:**
  - security/high (openai) — AC2's reply-file skip-set addition is an
    unforced, unjustified expansion of the gate-bypass surface; an attacker
    can hand-craft a file with one of these three exact names, in a
    self-chosen run directory, with forged `SHIPWRIGHT_VERDICT: approve`
    content, and skip review with zero model call. **fix** — reverted
    `_REVIEW_EVIDENCE_SKIP_RE` to `reviews.json` only, its exact pre-iterate
    shape. Reply files now get the same hide-only treatment
    `external-*review*` files already had. AC2 revised accordingly.
  - approach/medium (openai) — the stated objective (keep reviewer
    transcripts out of the model's context) doesn't require expanding the
    skip set at all; narrower scope was the materially simpler fix.
    **fix** — same revert as above; this finding and the high one share one
    fix.
  - risk/medium (openai) — asked whether the classifier's anchored regex is
    validated against the actual path shape callers pass (normalized
    POSIX, no leading `./`, no absolute paths). **verified for the hide
    side; correction below for the skip side** — read `_section_paths` in
    `pr_review_diff_filter.py`: for `is_generated_path`, paths are
    extracted only from `diff --git a/X b/X` headers and `---`/`+++`
    lines, which git always emits repo-relative with forward slashes.
    Doubt review (below) found this verification checked the wrong
    consumer for `is_safe_to_skip_review`: that function's real consumer,
    `classify_generated_only` in `review_record_tier.py`, is fed by
    `.github/workflows/pr-review-run.yml`'s `gh api --paginate
    "repos/$REPO/pulls/$PR_NUMBER/files" --jq '.[] | .filename,
    (.previous_filename // empty)'` — GitHub REST API JSON fields, not diff
    parsing at all. Traced end to end: `.filename`/`.previous_filename` are
    also repo-relative POSIX with no leading `./`, so the conclusion holds,
    but the originally-recorded verification named the wrong code path.
    No code change; this note corrects the record.
  - edge-case/low (openai) — requested an explicit test that an
    `external-*review*`-only PR still triggers a real review call.
    **disclose, already covered at the unit level** — the combination
    `is_generated_path(...)=True` + `is_safe_to_skip_review(...)=False`,
    pinned by `test_review_evidence_siblings_are_hidden_but_NOT_safe_to_skip`,
    is what `classify_generated_only` (review_record_tier.py) reads to
    reach exactly this outcome; a full gate-invocation integration test is
    a materially larger addition this small iterate's scope does not need.
  - approach/low (glm) — mini-plan step 3 still described the superseded
    intermediate design (a bare `[^/]*_reply\.json` wildcard), contradicting
    steps 7-12. **fix** — step 3 updated to point at the final design.
  - security/low (glm) — the hide-side `external-[^/]*review[^/]*` wildcard
    remains attacker-creatable (can conceal, not skip). **disclose,
    already accepted** — matches AC1's explicit, already-documented
    decision; no closed set is drawable for this family (see
    `_REVIEW_EVIDENCE_SKIP_RE`'s own comment).
  - edge-case/low (glm) — the closed reply set is closed against this
    repo's history only; a future 4th review stage's transcript would
    silently not be hidden. **fix** — added a maintenance comment above
    `_REVIEW_EVIDENCE_RE_RUN_ANCHORED` instructing future stages to extend
    the hide side (never the skip side, given this round's revert).
  - risk/low (glm) — noted the pre-existing loose legacy branch is
    consistent and hide-only; no action needed. **confirmed, no change.**
  - approach/positive (glm) — the overall two-round convergence (hide/skip
    split, verified-not-assumed tightenings, disclosed scope boundaries)
    judged sound; the only real defect was the stale mini-plan text.
- **Known limitations:** unchanged — `external-*review*` naming and
  run-directory naming stay unenforced and explicitly out of scope, per
  Internal Plan Review's and Round 2's disclosures.
- **Status:** 1 fixed (high + medium collapse to the same revert), 1
  verified via source read (no change), 1 disclosed as already covered at
  the unit level, 1 fixed (low, mini-plan text), 1 disclosed (low,
  already-accepted), 1 fixed (low, comment-only), 1 confirmed no action, 1
  confirmed sound approach. No further review round run: the round-3 fix is
  a strict narrowing back to pre-iterate skip-side behavior — the same
  direction every prior round pushed — not a new design decision needing
  fresh eyes.

## Code Review (shipwright-build:code-reviewer)
- **Ran:** yes
- **Summary:** One real, previously-undetected high-severity finding —
  `re.IGNORECASE` on both `_REVIEW_EVIDENCE_SKIP_RE` and
  `_REVIEW_EVIDENCE_RE_RUN_ANCHORED` contradicted the skip set's own "EXACT
  basenames, zero wildcards" design, none of the four prior review rounds
  or any test having used a mixed-case name to catch it.
- **Findings:**
  - security/high — case-insensitive matching let an attacker-authored
    `REVIEWS.JSON` (never produced by the real tool, which only writes
    lowercase) borrow the skip-safe classification on a case-sensitive CI
    runner. **fix** — dropped `re.IGNORECASE` from both patterns; pinned
    with `test_a_mixed_case_basename_borrows_neither_hide_nor_skip`.
  - readability/low — `is_safe_to_skip_review`'s docstring said "in two
    ways" but this iterate had added a third enumerated reason.
    **fix** — updated to "in three ways".
  - architecture/low — `_REVIEW_EVIDENCE_SKIP_RE` hardcoded the
    `.shipwright/planning/iterate/` literal instead of reusing
    `_REVIEW_EVIDENCE_PREFIX`. **fix** — built from
    `re.escape(_REVIEW_EVIDENCE_PREFIX)`.
  - readability/low — the module's dense comment blocks re-narrate the
    review-round history already in this spec. **disclose, no change** —
    reviewer explicitly flagged this as optional and consistent with the
    file's pre-existing convention (the lockfile/agent-docs comments above
    it predate this diff); left as-is.
- **Status:** 1 fixed (high), 2 fixed (low), 1 disclosed (low, reviewer-
  flagged optional). Re-ran full suite (1028 passed), lint, and LOC after
  fixing — all clean.

## Doubt Review (shipwright-build:doubt-reviewer)
- **Ran:** yes (fresh context, biased to disprove)
- **Summary:** Two doubts raised, neither inside this diff's own edits.
  Doubt 1 (high) is real and live but predates this iterate — filed as a
  tracked follow-up rather than fixed inline, consistent with this run's
  explicit scope boundary. Doubt 2 (medium) is a record-accuracy
  correction, no live exploit found.
- **Findings:**
  - security/high — `is_safe_to_skip_review`'s `_GENERATED_PREFIXES` check
    (introduced 2026-09-10, NOT touched by this diff) is a plain
    directory-prefix match with no closed-set/canonical-path anchoring,
    unlike every other category this function protects (the basename set
    was anchored, and this iterate's own review-evidence set was
    anchored across three rounds) — the same attacker-controlled-filename-
    with-no-provenance class this whole review series spent its effort
    closing elsewhere, left unexamined three lines above the fix.
    **disclose, filed as tracked follow-up** — out of scope for this
    "small dedicated iterate" (explicit spec boundary + the peer-relayed
    operator instruction that started this run): the code is pre-existing
    and unmodified here, and the fix belongs in its own iterate following
    the same anchor-or-disclose pattern this one used. Filed as triage
    card `trg-dd297923` (neutral title/detail per the triage tool's own
    sensitivity rule — no exploit shape in the git-tracked card).
  - process/medium — Round 3's verification of openai's path-normalization
    finding traced the hide-side consumer (`pr_review_diff_filter.py`) but
    the finding also covered the skip-side, whose real consumer
    (`review_record_tier.py` via the GitHub Actions workflow's `gh api`
    call) was never traced. **fix** — corrected the Round 3 entry above
    with the actual consumer and the trace; the conclusion (POSIX,
    repo-relative, no leading `./`) still holds — no live exploit, a
    record-accuracy gap only.
  - Five other angles attacked (path traversal / `.strip()` edge cases,
    legacy-vs-anchored regex interaction, `_SKIP_REVIEW_CANONICAL_
    BASENAME_PATHS` overlap, `classify_generated_only`'s other
    assumptions) — **nothing found**, reported plainly rather than
    manufacturing a finding.
- **Status:** 1 disclosed (high, tracked follow-up filed), 1 fixed (medium,
  record correction, no code change), 0 findings on five other attacked
  angles.

## External Code Review (glm + openai, full merge-base diff)
- **Ran:** yes
- **Verdicts:** glm=approve · openai=revise (`requires_resolution: false`)
- **Summary:** glm traced every regex against every AC and every test and
  found no correctness bugs — "ship-as-is". openai found two legitimate,
  cheap test-coverage gaps (not correctness bugs in the implementation
  itself) and glm separately flagged one spec-narrative inaccuracy.
- **Findings:**
  - test/medium (openai) — `test_review_evidence_siblings_are_hidden_but_
    NOT_safe_to_skip` covered `external-*review*.json` but not the `.md`
    sibling AC2 also requires hidden-but-not-skip-safe; a regression
    mistakenly adding only `.md` transcripts to the skip set would pass
    unnoticed. **fix** — added `external-plan-review.md` to that test's
    loop.
  - test/low (openai) — the anchoring test covered an over-nested reply
    file but not an over-nested `external-*review*` file; a regression
    loosening only the external branch's anchoring would pass. **fix** —
    added `.shipwright/planning/iterate/a/b/external-code-review.md` as a
    negative case to `test_reply_and_external_hiding_requires_a_run_
    directory_segment`.
  - narrative/low (glm) — the spec and module comments claimed
    `_REVIEW_EVIDENCE_SKIP_RE`'s final `reviews.json`-only shape was
    "unchanged from before this iterate" / "exactly its pre-iterate
    shape". **fix, verified via `git show` at the merge-base** — before
    this iterate, `is_safe_to_skip_review` shared `_REVIEW_EVIDENCE_RE`
    verbatim with the hide side, so the legacy
    `[^/]*-external-[^/]*review[^/]*\.json` shape (unanchored, any depth)
    was ALSO skip-safe pre-iterate. This iterate's final shape is narrower
    than pre-iterate, not merely a restoration — a strictly safer outcome,
    but the narrative was imprecise. Corrected AC2, the Round 3 section,
    the mini-plan, and the module's own comments.
- **Known limitations:** none beyond what prior rounds and the doubt
  review already disclosed.
- **Status:** 2 fixed (test coverage), 1 fixed (narrative accuracy, no
  behavior change), 1 confirmed sound (glm's full trace against all four
  ACs). Re-ran full suite (1028 passed), lint, and LOC after fixing — all
  clean. No further review round needed: both fixes are additive test
  coverage plus a documentation correction, not new design decisions.

## Round 4 — the live PR-review gate, on this iterate's own PR #727
- **Ran:** yes (not a spawned reviewer — the actual CI "PR Review" Required
  Check on PR #727, exercising this exact code against a real diff)
- **Summary:** After PR #727 was pushed and `deliver_pr.py` armed auto-merge,
  the gate posted two consecutive BLOCK verdicts. The first (14:15 UTC)
  repeated a finding already fixed by prior rounds (the hide-side
  `external-*review*` wildcard, already disclosed/accepted — see Round 3).
  The second (14:24 UTC, after that PR's own regenerated diff) found a NEW,
  real gap: `_REVIEW_EVIDENCE_SKIP_RE` still granted skip-safety to any
  repo-supplied `.shipwright/planning/iterate/<run>/reviews.json`, but
  neither the run directory nor the file's content is tool-enforced or
  authenticated — a contributor's own PR could commit a forged `reviews.json`
  with fabricated `SHIPWRIGHT_VERDICT: approve` content and skip the review
  gate with zero model call. `deliver_pr.py`'s non-converging circuit
  breaker (two consecutive BLOCKs sharing a recurring finding — both about
  this same regex family trusting path over provenance) correctly stopped
  and refused to re-push blindly, handing the decision to the operator.
- **Findings:**
  - security/high — `_REVIEW_EVIDENCE_SKIP_RE` grants skip-safe status to
    any PR-supplied `reviews.json` at a self-chosen run directory, content
    unverified. **fix, operator-authorized** — presented the operator two
    remediation options (real provenance/content validation vs. removing
    the skip-shortcut entirely) plus accepting the risk; the operator
    delegated the choice. Removed `_REVIEW_EVIDENCE_SKIP_RE` and its call
    site from `is_safe_to_skip_review` entirely — no review-evidence path
    is skip-safe any more, full stop. Chosen over building real provenance
    validation (a materially larger, genuinely out-of-scope change — the
    same class of expansion Round 3 already rejected once) because the
    origin bug (PR #722) never needed the skip-shortcut at all, only the
    hide side (`is_generated_path`, unaffected by this fix). Cost: a PR
    whose only changed file is `reviews.json` now gets one real (trivial)
    review call instead of a free zero-call pass — the same trade-off
    already accepted for every other review-evidence shape since Round 3.
- **Status:** 1 fixed (high, operator-authorized removal of the
  skip-shortcut). Updated `pr_review_generated.py`'s comments and
  `is_safe_to_skip_review`'s docstring; updated
  `test_pr_review_generated_skip_review.py` (renamed
  `test_review_evidence_files_stay_safe_to_skip` to assert the opposite,
  folded the now-dead anchoring/lookalike-suffix tests into one
  `test_review_evidence_is_never_safe_to_skip_in_any_shape`). Full plugin
  suite re-run (1027 passed, 7 skipped — one net test removed via the fold),
  lint clean, both files under the 300-line guideline.

## Round 4 — code review and doubt review on the operator-authorized fix
- **Ran:** yes, both (`shipwright-build:code-reviewer`,
  `shipwright-build:doubt-reviewer`) against the Round 4 diff, per this
  repo's standing review-cascade grant.
- **Code review summary:** No defect in the diff itself. One real,
  cross-file finding: `pr_review_gate_verdict.py`'s `decide_gate` docstring
  (and its matching test's docstring) illustrated the waiver-failure-must-
  win-over-all_generated guard with an example — "a PR whose only changed
  path is a corroborated `reviews.json`" — that Round 4's own fix makes
  structurally unreachable (`needs_review=False` now requires `reviews.json`
  among the changed paths, but that same path always makes
  `classify_generated_only` return `False`). **fix** — rewrote both
  docstrings to state the check is retained as defense-in-depth against a
  future loosening of either function, not as a currently-reachable case;
  the guard's ORDERING (still correct, still tested) is unaffected. Traced
  every other caller of the touched functions (`review_record_tier.py`,
  `pr_review_gate_verdict.py`, both test files) and confirmed no other code
  path assumed `reviews.json` was still skip-safe.
- **Doubt review summary:** Two doubts, neither a defect in this diff —
  both are pre-existing, unrelated code the diff didn't touch. Doubt 1
  (high) is a substantive escalation of the already-filed, already-tracked
  `_GENERATED_PREFIXES` provenance gap (triage `trg-dd297923`, filed during
  this iterate's earlier Doubt Review section above): it traces
  `.shipwright/compliance/` — one of `_GENERATED_PREFIXES`'s four
  bare-prefix, no-provenance-check entries, structurally the same
  unanchored shape Round 4 just closed for `reviews.json` — to a concrete
  downstream consumer (a deploy-time security gate reading a file under
  that prefix without independent verification), meaning a PR whose only
  changed file is under that prefix could both skip the PR-review model call
  AND, if merged, affect what that later gate trusts. Doubt 2 (medium) is
  the same shape on the other two `_GENERATED_PREFIXES` entries, with a
  weaker (not concretely traced) consumer.
- **Disposition — disclose, filed as tracked follow-up, not fixed inline:**
  consistent with this run's explicit "small dedicated iterate" scope
  boundary (used identically for the original `_GENERATED_PREFIXES` finding
  earlier in this same iterate) and with the fact that neither doubt names
  code this diff touched — `_GENERATED_PREFIXES` and the deploy gate that
  consumes `.shipwright/compliance/` predate this entire iterate.
  **`trg-dd297923` amended** (not duplicated) with the concrete-consumer
  finding, raising it from an abstract "lacks anchoring" note to a traced
  risk chain — severity confirmed `high`. A full fix (anchoring or
  disclose-and-accept per prefix, following this iterate's own pattern, or
  independently verifying the deploy gate's input) belongs in its own
  iterate, not bolted onto a fix whose own scope was already stretched once
  by Round 4's operator-authorized change.
- **Status:** 1 fixed (medium, cross-file docstring accuracy, Round 4 code
  review), 1 disclosed + triage-amended (high, pre-existing, out of scope,
  Round 4 doubt review), 1 disclosed (medium, weaker evidence, same
  disposition). Full plugin suite re-run (1027 passed, 7 skipped) and lint
  after the docstring fix — clean.
