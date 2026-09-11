# Mini-Plan — iterate-2026-09-11-pr-review-evidence-filter-gap

**run_id:** iterate-2026-09-11-pr-review-evidence-filter-gap

## 1. Files to create/modify

- `plugins/shipwright-security/scripts/lib/pr_review_generated.py` (edit) —
  widen `_REVIEW_EVIDENCE_RE`, extend both nearby comments/docstrings.
- `plugins/shipwright-security/tests/test_pr_review_filter.py` (edit) —
  regression tests for `is_generated_path` on the new file shapes + the
  deliberately-excluded `self-review-payload.json`.
- `plugins/shipwright-security/tests/test_pr_review_generated_skip_review.py`
  (edit) — pin the `is_safe_to_skip_review` side effect explicitly.

## 2. Work breakdown

1. Write failing tests for `is_generated_path` (AC1) — confirm red against
   the current regex. *(done — 2 failures, exactly the two new-file-shape
   assertions; all pre-existing assertions, including the
   `self-review-payload.json` one, already passed.)*
2. Write failing/pinning tests for `is_safe_to_skip_review` (AC2). *(done —
   same shape, confirmed red.)*
3. Widen `_REVIEW_EVIDENCE_RE` with two new alternatives
   (`external-[^/]*review[^/]*\.(json|md)`, `[^/]*_reply\.json`), leaving the
   legacy `[^/]*-external-[^/]*review[^/]*\.json` branch untouched. *(done —
   superseded by steps 7-11 below: the final hide-side shape is a LEGACY
   piece (unchanged) plus `_REVIEW_EVIDENCE_RE_RUN_ANCHORED` — run-anchored,
   reply alternative closed to the exact `{spec,code,doubt}_review_reply.json`
   set — and the skip-side ends up as `_REVIEW_EVIDENCE_SKIP_RE`, matching
   `reviews.json` only, narrower than even its pre-iterate shape (see step
   14). See the spec's `## External Plan Review` sections, Rounds 1-3, for
   why each step revised.)*
4. Document reasoning in both the module-level comment above the regex and
   the `is_safe_to_skip_review` docstring (AC4). *(done.)*
5. Re-run the full `plugins/shipwright-security/tests/` suite — confirm
   green, no regressions elsewhere in the 1000+ test suite that also
   exercises this shared regex (AC3). *(done — 1021 passed, 7 skipped.)*
6. Lint + LOC check on the three touched files. *(done — ruff clean, all
   files under the 300-line cap.)*
7. **Internal Plan Review found this design unsafe as-is** (high-severity):
   `is_safe_to_skip_review` reused the wide regex verbatim, letting an
   attacker-chosen `*_reply.json` skip the review gate entirely. Split into
   a wide, hide-only `_REVIEW_EVIDENCE_RE` and a closed, exact-basename,
   run-directory-anchored `_REVIEW_EVIDENCE_SKIP_RE` used only by
   `is_safe_to_skip_review`. *(done — see spec's `## Internal Plan Review`
   section.)*
8. **External plan review (glm + openai) then found step 7's hide-only
   regexes were ALSO unanchored** — `*_reply.json` /
   `external-...review....json` matched at any depth under
   `.shipwright/planning/iterate/`, not just inside a genuine run's own
   directory. Split `_REVIEW_EVIDENCE_RE` into a LEGACY (unchanged, loose)
   piece and a NEW `_REVIEW_EVIDENCE_RE_RUN_ANCHORED` piece requiring
   exactly one run-directory segment. *(done — see spec's `## External Plan
   Review` section.)*
9. Re-run the full suite + lint + LOC after the anchoring fix. *(done —
   1027 passed, 7 skipped; ruff clean; all files under cap.)*
10. **External plan review round 2 (glm=approve, openai=revise) found the
    hide-side reply alternative was still a wildcard** despite step 8's
    anchoring fix. Before tightening it, ran a repo-wide `git log
    --diff-filter=A` survey across every branch for `*_reply.json` and
    confirmed exactly three basenames ever existed
    (`{spec,code,doubt}_review_reply.json`) — then closed
    `_REVIEW_EVIDENCE_RE_RUN_ANCHORED`'s reply alternative to that exact
    set, matching the skip-side's already-closed design.
    `external-[^/]*review[^/]*` keeps its wildcard (no fixed producer
    filename). Two round-2 findings (openai's anchoring-test request, its
    `reviews.json`-path-confirmation request) were verified as already
    satisfied by existing tests/producer code, no new code needed; two
    (glm's content/provenance question, glm's speculative `.md` reply
    coverage) disclosed out of scope with reasoning. *(done — see spec's
    `## External Plan Review — Round 2` section.)*
11. Re-run the full suite + lint + LOC after the round-2 tightening. *(done
    — 1028 passed, 7 skipped; ruff clean; all four touched files under
    cap.)*
12. **External plan review round 3 (openai, high severity) found the
    round-2 fix had ALSO added the closed `{spec,code,doubt}_review_reply.json`
    set to the SKIP side** (`_REVIEW_EVIDENCE_SKIP_RE`) — an unforced
    expansion, since fixing PR #722 never required reply files to be
    skip-safe, only hidden. Reverted: `_REVIEW_EVIDENCE_SKIP_RE` now matches
    `reviews.json` only — narrower than even its pre-iterate shape, since
    pre-iterate the skip side shared the legacy external-review regex too
    (external code review, glm, caught this narrative gap post-hoc; see
    step 14). Reply files stay
    hide-only, same treatment as `external-*review*`. Also addressed glm's
    round-3 low findings: this step-3 text updated to point at the final
    design instead of the superseded intermediate one, and a maintenance
    comment added above `_REVIEW_EVIDENCE_RE_RUN_ANCHORED` about extending
    the hide-side (never skip-side) set for a future 4th review stage.
    *(done — see spec's `## External Plan Review — Round 3` section.)*
13. Re-run the full suite + lint + LOC after the round-3 revert. *(done —
    1027 passed, 7 skipped; ruff clean; all four touched files under cap.)*
14. Self-review, code-reviewer, and doubt-reviewer cascade. code-reviewer
    caught `re.IGNORECASE` on both anchored regexes (high) — fixed and
    pinned. doubt-reviewer flagged a pre-existing, out-of-scope
    `_GENERATED_PREFIXES` provenance gap (filed as triage `trg-dd297923`,
    not fixed here) and a record-accuracy correction for Round 3's
    consumer trace (fixed in the spec, no code change). *(done — see
    spec's `## Code Review` and `## Doubt Review` sections.)*
15. External code review (glm + openai) against the full merge-base diff.
    glm=approve; openai=revise with two test-coverage gaps (missing
    `external-*review*.md` in the hidden-but-not-skip test; missing an
    over-nested `external-*review*` negative case) and one narrative
    correction (the skip side shared the legacy external-review regex
    pre-iterate too, so this iterate narrows further than "unchanged").
    *(done — both tests added, spec and module comments corrected; see
    spec's `## External Code Review` section.)*

## 3. Component hierarchy

N/A — no UI.

## 4. Data model changes

None.

## 5. Test strategy

Unit tests only, in the plugin's existing test root
(`plugins/shipwright-security/tests/`). No E2E — this is a pure diff-path
classification function with no running-app surface. Both consumers of
`_REVIEW_EVIDENCE_RE` (`is_generated_path` via `test_pr_review_filter.py`,
`is_safe_to_skip_review` via `test_pr_review_generated_skip_review.py`) get
direct regression coverage, matching the pattern each file already used for
the pre-existing `reviews.json` / legacy-external-review-shape cases.

## 6. Alternative approach (rejected)

**Considered:** redesign review-artifact naming into one small set of fixed,
tool-enforced filenames (e.g. `record_review_pass.py` always writes
`review-reply-<stage>.json`), instead of pattern-matching whatever an agent
happened to name the file.

**Rejected because:** it's the structurally more correct fix (the `git grep`
survey turned up over 80 distinct historical basenames for review artifacts,
none of them enforced by any tool — free-form agent-chosen naming is the
actual root cause of this whole class of gap), but it is a materially larger
change: it would touch `record_review_pass.py`, `external_review.py`, and
every skill reference that tells an agent what to name these files, plus a
migration story for already-merged history. That is explicitly out of scope
for this run (see spec's "Out of scope" section) — this run closes the
specific, currently-blocking gap with a minimal, well-tested regex widening,
consistent with the peer-session-relayed operator instruction to keep this
"a small dedicated iterate."
