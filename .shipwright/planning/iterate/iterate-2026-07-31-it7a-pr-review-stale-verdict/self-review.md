# Self-review — IT-7a

The eight-point checklist, run after implementation and before commit.

### 1. Spec compliance — **pass**
AC1–AC8 each have a code path and at least one test that fails if the behaviour
is removed; the Test Completeness Ledger in the spec maps all 27 behaviours.
No feature beyond the ACs: the `needs_review=false` path, the exact
`--head-sha`, and the `shipwright-webui` copy are all named in §6 as out of
scope rather than built.

### 2. Error handling — **pass**
Every new boundary is a `gh` subprocess. Each wrapper raises on a non-zero exit
with the stderr attached; `_decode_pages` raises on a page that is not an array
rather than reading it as "no reviews". The orchestrator catches everything and
converts it to a reported, non-fatal report — and the caller wraps it again, so
housekeeping cannot reach the exit code by any route.

### 3. Security basics — **pass, and this is the point of the change**
The untrusted input here is a review body written by another process out of a
pull request's own diff. Ownership is never inferred: a candidate needs a whole
`MARKER_RE` token as the last line of its body, `user.type == "Bot"`, and login
equality with an anchor identified by this run's own 128-bit nonce. A human's
change-request is structurally unreachable. No secret is handled: the
OpenRouter key is never passed to `gh`, and the one sink that prints `gh` output
runs it through the shared control-character sanitiser first, so an error cannot
carry a newline into an Actions log and forge a `::error::` command.

### 4. Test quality — **pass**
Assertions are on outcomes (what was dismissed, what was refused, what was
printed), never on internal state. Every AC has both directions. Two claims were
verified by **mutation** rather than by reading: deleting the head-read ordering,
and deleting the failure-report branch, each turn the suite red — both were
green before the tests that now pin them.

### 5. Performance basics — **pass**
Two extra `gh` calls on the passing path (list + head), plus one head
re-confirmation that is skipped entirely when there is nothing to dismiss, plus
one `PUT` per stale verdict. No loop of calls over an unbounded set: the
candidate list is the pull request's own reviews, and `--paginate` is bounded by
that.

### 6. Naming & structure — **pass**
Module split follows the existing `pr_review_*` convention; the `gh` boundary
keeps only subprocess wrappers and the policy lives in `pr_review_dismiss`.
Every touched file is inside the 300-line guideline — three files were split or
trimmed during the run to keep it that way, and `test_pr_review_render.py` was
left untouched at exactly 300 by giving the new sanitiser tests their own module.

### 7. Affected boundaries — **n/a for round-trip, with a probe run anyway**
No serialized on-disk format changes: nothing here reads or writes a config, a
state file, or an artifact, so `touches_io_boundary` does not fire and no
round-trip test is owed. The boundary that *is* touched is the GitHub REST API,
which has a producer (GitHub) and one consumer (this module). It was probed
live rather than assumed — P1 (the real shape of eleven review objects), P2
(the ruleset that permits dismissal), P3 (a dismissed review reads `DISMISSED`),
P4 (`gh 2.92` merges paginated arrays), P6 (three real `PUT` responses).

### 8. Test hygiene probe — **pass**
`uv run shared/scripts/tools/scan_test_hygiene.py --diff` → `no findings`.
No skip, no `skipif`, no quarantine annotation in any changed test file.
