# IT-7a — A superseded review verdict stops blocking the pull request

- **Run ID:** `iterate-2026-07-31-it7a-pr-review-stale-verdict`
- **Anchor:** `trg-fc173418` (IT-7, new) — member **7a** only
- **Intent:** CHANGE (Path B) · **Complexity:** medium
- **Affected FRs:** FR-01.17 (Independent re-check on the code host)
- **Spec Impact:** **NONE**
- **Spec Impact justification:** FR-01.17 (E)4 already promises that *"given a
  review has run, when it reaches a verdict, then the verdict and the reasons
  behind it are written onto the change itself, where the people deciding
  whether to merge it will read them"*. Today the reviewer writes the verdict it
  reached, but GitHub keeps showing an **older, opposite** one — so the verdict
  the merge decider actually reads is not the verdict the review reached. That
  is a defect against an existing criterion, not a new promise, so no criterion
  is minted and no `spec.md` is touched.

---

## 1. What is broken (measured, not assumed)

A Tier-3 review that fails closed posts `CHANGES_REQUESTED`. A later, successful
run posts only `COMMENTED` — and in GitHub a `COMMENTED` review **does not
retract** an earlier `CHANGES_REQUESTED` from the same reviewer. The pull
request therefore keeps `reviewDecision: CHANGES_REQUESTED` and
`mergeStateStatus: BLOCKED` with **every required check green and zero open
review threads**. The symptom is *silence*: nothing on the PR names the blocker.

### Probe P1 — the five dead verdicts on PR #446 (2026-07-31, live API)

`GET repos/svenroth-ai/shipwright/pulls/446/reviews`:

| review id | commit | state today | submitted |
|---|---|---|---|
| 4785240622 | `bdd788a1` | DISMISSED *(by hand)* | 2026-07-27T08:52:03Z |
| 4785347534 | `720f0de8` | DISMISSED *(by hand)* | 2026-07-27T09:03:58Z |
| 4785405393 | `75e538c1` | DISMISSED *(by hand)* | 2026-07-27T09:11:11Z |
| 4785424294 | `2ea75602` | DISMISSED *(by hand)* | 2026-07-27T09:13:21Z |
| 4787142550 | `1086cf4e` | DISMISSED *(by hand)* | 2026-07-27T12:58:30Z |
| 4789286266 … 4790453889 (**six**) | `1e59e536` … `043993ca` | COMMENTED | 16:31Z – 18:55Z |

Six later successful reviews, each on a *newer* commit, did not clear the five.
Exactly the SHAs the card names. Every review — stale and fresh — is authored by
`github-actions[bot]`, `user.type: "Bot"`.

### Probe P2 — why pushing new commits does not clear them

Ruleset `main-protection` (id 17548444), `pull_request` rule:

```json
{"dismiss_stale_reviews_on_push": true,
 "dismissal_restriction": {"allowed_actors": [], "enabled": false},
 "required_approving_review_count": 0,
 "required_review_thread_resolution": true}
```

`dismiss_stale_reviews_on_push` dismisses **approvals** only — a
`CHANGES_REQUESTED` survives every push. That is why six commits and six clean
reviews left the five standing. It also confirms the fix is *permitted*:
`dismissal_restriction.enabled` is **false**, so any actor with
`pull-requests: write` may dismiss, and the stage-2 job already holds exactly
that permission (`.github/workflows/pr-review-run.yml`, job `review`).

### Probe P3 — the identity the fix has to key on

Every review object carries `user.login`, `user.type`, `state`, `commit_id`,
`submitted_at` and `body`. A review the reviewer has already dismissed reads
`state: "DISMISSED"`, never `CHANGES_REQUESTED` — so re-running the fix on an
already-clean PR is a no-op **by construction**, not by bookkeeping.

The legacy bodies carry no machine-readable marker (they are the raw model
summary), so "which of these are mine" cannot be answered from today's data
alone. See §3, alternative B.

### Probe P5 — the legacy backlog is empty

`gh pr list --state open` returns **zero** pull requests on this repository
(2026-07-31). PR #446 was cleared by hand and merged. So there is no unmarked
verdict left for this change to rescue, and buying legacy coverage with a
weaker ownership test would be paying a real risk for nothing. Unmarked reviews
are therefore **deliberately out of scope** (AC7).

---

## 2. Acceptance criteria

- **AC1** — Given a Tier-3 review run that reaches a non-blocking verdict, when
  its own review has been posted and **is the verdict on the pull request's
  current head**, then every `CHANGES_REQUESTED` review this reviewer itself
  left on that pull request against a *different* commit is dismissed, so a
  green pull request stops being held by a verdict about code that is no longer
  there.
- **AC2** — Given a `CHANGES_REQUESTED` review left by a **human**, when the
  reviewer clears its own stale verdicts, then that review is never touched —
  the guard is structural (`user.type == "Bot"`), not a body-text guess.
- **AC3** — Given a `CHANGES_REQUESTED` review left by **another bot** — or by
  *another workflow running under the same `github-actions[bot]` identity* —
  when the reviewer clears its own stale verdicts, then that review is never
  touched, because a candidate must carry this reviewer's own marker.
- **AC4** — Given a run whose verdict is `block`, when it posts, then **nothing
  is listed and nothing is dismissed** — a fail-closed verdict is never cleared
  by the run that issued it, and a verdict standing against the *current* commit
  is never cleared at all.
- **AC5** — Given this run did not review the commit that is now the head —
  whether because the head moved after it posted, or because it read an *older*
  commit while the head ran on ahead of it — then **nothing is dismissed**,
  because a verdict that is not about the current head has no standing to
  retract one that might be. The commit this run *read* is proven separately
  from the commit its review is *stamped with*; GitHub assigns the latter when
  the review is submitted, so it cannot answer the former.
- **AC6** — Given dismissal is refused (permission, rate limit, the review
  already gone) or the listing fails or returns unparseable output, when the run
  finishes, then the required check keeps the value the *review* earned —
  clearing stale state is best-effort and never flips the gate — and the refusal
  is printed, never swallowed silently.
- **AC7** — Given a `CHANGES_REQUESTED` review that carries **no marker**
  (posted before this change shipped), when the reviewer clears its stale
  verdicts, then it is left alone and the run says so. Ownership is proven, never
  inferred from a shared actor login.
- **AC8** — Given the run clears (or declines to clear) stale verdicts, when it
  logs, then it **names** what it did and why, so the "nothing tells you what is
  blocking" symptom is answered on the run that fixes it.

---

## 3. Options considered

| Option | Verdict |
|---|---|
| **A. Post an `APPROVED` review instead of `COMMENTED` on success** — a new approval from the same reviewer supersedes that reviewer's change-request. | **Rejected.** `required_approving_review_count` is 0 *today*, but making the gate bot an approving reviewer means that the moment the count is raised, the bot's approval satisfies a human-review requirement. That trades a stuck merge for a security downgrade, and `pr_review_gh.post_pr_review_state` already documents "deliberately never `--approve`". |
| **B. Dismiss by author login alone (`github-actions[bot]`)** | **Rejected.** Hard-codes the identity of one deployment. The vendored copy in `shipwright-webui` may run under a different actor, and any *other* `github-actions[bot]` workflow's change-request would be in scope. |
| **C. Dismiss only reviews whose body carries a marker this reviewer stamps** | **Chosen, with a second guard.** The marker answers "is this mine"; `user.type == "Bot"` answers "is this a human's". A maintainer who quotes the bot's comment into their own review is caught by the second guard — that is the realistic way a body-text-only rule would dismiss a human's verdict. |
| **D. Also clear stale verdicts on the workflow's "no review needed" success path** | **Deferred, recorded.** Real hole (a PR that drops its sensitive path re-tiers to `needs_review=false` and keeps its old block), but it needs a step in `.github/workflows/pr-review-run.yml`, and `.github/workflows/**` is reserved for anchor IT-9. Filed rather than smuggled in. |

**Why C needs both guards.** `user.type == "Bot"` alone would put dependabot's
and any scanner's change-requests in scope (AC3). The marker alone would let a
human who quotes the bot's text into their own review be dismissed (AC2).

**And why the marker must be on the CANDIDATE, not only on the anchor.** The
first draft used the marker only to *find* this reviewer and then matched
candidates on `user.login`. External review (GPT-5.4, high/security) killed it:
every workflow in a repository posts as the same `github-actions[bot]` login, so
that rule dismisses *any other workflow's* change-request — the very thing
option B was rejected for, reintroduced through the back door. Candidates now
carry the marker themselves.

The price is that verdicts posted **before this change** can never be attributed
and are left alone (AC7). Probe P5 measured that price: **zero** open pull
requests, so the legacy backlog this would have rescued is empty.

**Anchoring: the run's own review, on the commit it actually read.** The marker
carries a per-run nonce (`<!-- shipwright-pr-review:{nonce} -->`), so the anchor
is *this invocation's* review rather than "the newest marked one" — which a
concurrent run could have replaced between posting and listing (GPT-5.4,
medium). The run then dismisses only if the pull request's current head is both
the commit the anchor is stamped with **and** the commit whose diff this run
read (Gemini, high; corrected by the code-reviewer, medium — the two are not the
same thing, see §4). Anchoring on a commit rather than on wall-clock also makes
a timestamp comparison unnecessary, and a timestamp comparison would have
mis-handled ties at GitHub's one-second precision (GPT-5.4, low).

---

## 4. Design

Three modules, no new dependency, no workflow change.

| File | Change |
|---|---|
| `plugins/shipwright-security/scripts/lib/pr_review_dismiss_select.py` | **New, pure.** `MARKER_RE`, `new_nonce()`, `stamp_review_body()`, `StaleSelection`, `select_stale_verdicts()`. The whole safety surface, readable without the subprocess plumbing. |
| `plugins/shipwright-security/scripts/lib/pr_review_dismiss.py` | **New, the calls.** `DISMISSAL_MESSAGE`, `DismissalReport`, `read_reviewed_head()`, `dismiss_own_stale_verdicts()` (best-effort orchestrator returning a report). Re-exports the selector's names so callers see one module. |
| `plugins/shipwright-security/scripts/lib/pr_review_gh.py` | `list_pr_reviews()`, `fetch_pr_head_sha()`, `dismiss_pr_review()` — three more thin `gh` wrappers in the module that already owns that boundary. |
| `plugins/shipwright-security/scripts/tools/pr_review.py` | Reads the head via `read_reviewed_head()` before fetching the diff; `_post_verdict` stamps the review-state body with this run's nonce and reports whether the post landed; on a non-`block` verdict that landed, call the orchestrator with that head. |

**The marker** is a whole structured token, `MARKER_RE` =
`<!-- shipwright-pr-review:[0-9a-f]{32} -->`, matched entire **and positionally**
— it counts as ownership only as the last line of the body, which is exactly
where `stamp_review_body` puts it. A substring test on a bare prefix is how a
near-miss, or another tool's namespace, would read as ownership (GPT-5.4,
medium); and a *quoted* marker mid-body is how a summarising bot under the same
`github-actions[bot]` login would inherit ownership by repeating PR-authored
text back (code-reviewer, medium). No bare-prefix constant is exported.

**Selection rule (pure,
`select_stale_verdicts(reviews, nonce, head_sha, reviewed_sha)`).**

1. **Anchor** = the review whose *last line* is this run's exact marker
   (`<!-- shipwright-pr-review:{nonce} -->`) and whose `user.type == "Bot"`.
   None → dismiss nothing, and say why.
2. **Refuse** unless `reviewed_sha == head_sha == anchor.commit_id` (AC5).
3. **Dismiss** every review that is all of: `state == "CHANGES_REQUESTED"` ·
   last line matches `MARKER_RE` · `user.type == "Bot"` ·
   `user.login == anchor.user.login` · `commit_id != anchor.commit_id`.

**Why step 2 needs all three terms.** GitHub stamps a review's `commit_id` when
it is **submitted** — the head as it then stood, not the commit whose diff was
read. So `anchor.commit_id == head_sha` alone says only *"the head has not moved
since I posted"*. A run that reviewed X while the head advanced to Z has its
review stamped Z, passes that test, and would retract a live verdict about the
intermediate commit Y — the exact case AC5 forbids (code-reviewer, medium). The
third term is the head captured by `read_reviewed_head()` immediately **before**
the diff is fetched, threaded through by the caller; unreadable → `None` →
refuse everything.

Step 3 needs no timestamp: once the anchor is pinned to the reviewed head, "a
different commit" *is* "superseded". An already-dismissed review reads
`DISMISSED`, so the rule is idempotent by construction (P3). A single review of
an unexpected shape is counted `unreadable` and skipped rather than allowed to
abort the sweep — letting it escape would report every legitimate dismissal as
a failure to read the pull request, naming the wrong cause.

**One more head read, immediately before the first dismissal.** Selecting and
dismissing are separate API calls and can never be made atomic (external code
review, medium). A candidate cannot *become* current while the sweep runs — the
list was taken when it was already superseded — but a force-push can put a
candidate's commit back at the head, and then a verdict about to be retracted
describes the code again. So the head is re-confirmed once the candidate list is
fixed, and any change (or an unreadable answer) abandons the sweep. It is
skipped when there is nothing to dismiss: the read exists to protect a mutation.
The irreducible residual is a force-push landing *inside* the dismissal loop;
that is bounded by the `PR Review` status being recorded per commit SHA, which
this change never touches.

**An unreadable listing is an error, not an empty pull request.** `gh` can exit
0 and return `{"message": "Not Found"}`. Decoding that to `[]` would report a
pull request nobody could read as one with no reviews — and the run would then
say *"this run's own review is not visible yet"*, sending the reader to the
wrong place. A page that is not an array raises, and AC6 turns it into a named
failure (external code review, medium — it had been the opposite, with a test
pinning the wrong behaviour).

**Dismissal call.** `PUT repos/{repo}/pulls/{n}/reviews/{id}/dismissals`
carrying **only** the required, non-model-generated `message`
(`DISMISSAL_MESSAGE`: *"Superseded by a later automated Shipwright review of
commit `<sha>`. This verdict was about a commit that is no longer the head of
this pull request."*). Both halves of that shape are settled by probe **P6**, not
by reading docs: without a message the endpoint answers `422 "message" wasn't
supplied` before any other validation, so a wrapper lacking it would have parked
the feature permanently in its best-effort failure path (GPT-5.4, medium); and
`event=DISMISS` is *accepted but changes nothing*, so — not being part of the
documented request (GPT-5.4, medium) — it is not sent. A test pins both, the
presence of the message and the absence of `event`.

---

## 5. Affected Boundaries

- **`gh` CLI / GitHub REST** — a new *mutating* call (`PUT
  …/reviews/{id}/dismissals`). Read via `gh api --paginate`, whose array-per-page
  output is decoded with `json.JSONDecoder().raw_decode` so both the merged-array
  (gh ≥ 2.92, measured) and concatenated-pages shapes parse.
- **The `PR Review` required status** — unchanged by construction: the
  dismissal runs *after* the verdict is posted and its outcome never reaches the
  exit code.
- **Cross-repo:** the vendored `pr_review` in `shipwright-webui` needs the same
  change; it is a different repository and cannot ship in this PR.

## 5b. What this does NOT unblock (Stage-3 findings, answered)

The adversarial pass could not break the over-reach direction — it tried CRLF,
empty and marker-only bodies, near-miss namespaces, a planted anchor, a deleted
user, and a model echoing the marker out of the diff, and every one was refused.
What it did break is the *completeness* claim, in exactly the place this run is
named for. Three residuals, stated rather than left to be discovered:

**(a) A same-head re-review cannot retract this reviewer's own earlier block.**
A candidate whose `commit_id` equals the anchor's is skipped as
`current_commit`. Since `commit_id` is a *submission* stamp, that test cannot
actually prove the verdict is current — it is the conservative reading of an
uncertainty, and the conservative reading is the only safe one. The alternative
(dismiss a same-head block once a later run passes, ordering by review `id`) was
**rejected**: re-running the review is cheap and model output is not
deterministic, so it would let any verdict be re-rolled away by re-reviewing
until it agrees. That is a worse failure than a stuck merge. Consequence: after
a truncation block, only a **new commit** — not a re-run, not a label — clears
the way, and a maintainer may still need one manual dismiss.

**(b) A block posted by a concurrent run outlives the head it was stamped with.**
Two runs on different SHAs are not cancelled (`concurrency` is keyed on
`head_sha`). A slow run on X can land its `block` while the head is Y, so GitHub
stamps it Y; later runs at head Y then read it as `current_commit` and skip it.
Same mechanism as (a), same reason for accepting it.

**(c) The reviewer's own printed waiver does not unblock.** The truncation notice
tells a maintainer to apply `skip-pr-review`. That greens the required check but
leaves the change-request standing, because the relabelled re-run takes the
`needs_review=false` branch and `pr_review.py` never runs. The notice now says
so in the same breath rather than promising an unblock the pipeline cannot
deliver; the real fix is the workflow half, which is IT-9's tree.

**On shipping an irreversible write unverified** (Stage 3, high): dismissal has
no inverse, and row 27 of the ledger admits the live behaviour is untested. The
blast radius is nevertheless **zero on the day this merges** and grows only over
reviews this same code has itself stamped: ownership requires *our* marker, and
no review in existence carries one. So the first thing it can possibly dismiss
is a change-request this code posted after shipping — and the identity chain
that guards that is the part Stage 3 could not break. A kill switch was
considered and not built: an env gate is inert until the workflow passes it, and
the workflow is IT-9's tree, so it would read as a safety feature while being
none. Recorded as a follow-up alongside the other two workflow items.

**Not built, recorded:** there is no retry when this run's own review is not yet
visible in the listing (GitHub REST is not guaranteed read-after-write across a
POST then a separate GET). The failure is a self-healing silent no-op — the next
qualifying run clears the backlog — but it is indistinguishable from the defect
while it lasts.

## 6. Out of scope (named, not silently dropped)

1. **Option D** — the `needs_review=false` success path (workflow file; IT-9 owns that tree).
2. **An exact `reviewed_sha` instead of a fresh one.** `read_reviewed_head()`
   reads the head at T0 and `gh pr diff` fetches at T1 *by PR number*, which
   tracks the moving head. A force-push sequence X → Y → X straddling the run
   makes all three terms agree on X while the diff actually read was Y — the one
   head movement that does not fail safe. Closing it needs the workflow to pass
   its trusted `github.event.workflow_run.head_sha` in as `--head-sha`, and
   `.github/workflows/**` belongs to IT-9. The merge decision is protected
   meanwhile: the required `PR Review` status is per commit SHA and
   `pr-review-run.yml` re-checks the head against that same trusted field before
   posting it, failing closed. This costs defence in depth, not the gate.
3. **A kill switch for the dismissal loop** — an env gate is inert until the
   workflow passes it (§5b), so it belongs with the two items above.
4. **A retry on the read-after-write anchor miss** (§5b, last paragraph).
5. **The `shipwright-webui` vendored copy** — separate repository.
6. **7b / 7c / 7d** of the anchor — their own iterates; 7d is blocked on `shipwright-webui trg-5469bec0`.

> **On the module split.** `pr_review_dismiss.py` hit the 300-line guideline three
> times during review hardening. Rather than shave the reasoning the reviewers
> valued, or open a bloat exception on a file created in this same diff, it was
> split at its natural seam — pure selection (`_select`, 171 lines) vs the
> `gh`-facing calls (162) — mirroring the test split already in place. No
> baseline entry is needed and none was added.

## 7. Assumptions taken (no interview — `--autonomous`)

1. The unit of this run is anchor member **7a** alone, because the anchor names
   it "ZUERST und klein". 7b and 7c follow interleaved-serial.
2. Clearing stale verdicts is best-effort: a refusal must not turn a passed
   review into a failed check (AC5). The alternative — failing the gate when
   housekeeping fails — would newly block PRs that are fine.
3. Dismissal happens on success only, as the card states. A `block` run leaves
   older blocks standing (they are redundant, not wrong).

---

## Confidence Calibration

- **Boundaries touched:** GitHub REST via the `gh` CLI (one new mutating
  endpoint, one new read endpoint); the `PR Review` required status context
  (read-only from this change's perspective); no config or on-disk state.
- **Empirical probes run:**
  - *P1* — read PR #446's eleven review objects live: five `CHANGES_REQUESTED`
    on superseded commits survived six later clean `COMMENTED` reviews. The
    failure is real and matches the card's five SHAs exactly.
  - *P2* — read ruleset 17548444: `dismissal_restriction.enabled = false`
    (the fix is permitted) and `dismiss_stale_reviews_on_push = true` affects
    approvals only (which is why pushing did not help).
  - *P3* — a dismissed review reads `state: "DISMISSED"`, so re-running is
    idempotent without extra bookkeeping.
  - *P4* — `gh 2.92.0` `--paginate` returned one merged array for
    `per_page=5` over 11 reviews; the decoder handles both shapes.
  - *P5* — no pull request is open on the repository right now, so this change
    cannot disturb in-flight work, and the unmarked-verdict backlog AC7 declines
    to rescue is empty.
  - *P6* — sent three real `PUT …/dismissals` requests at a review that was
    **already dismissed**, so the probe could not change anything: `message`
    omitted → `422 "message" wasn't supplied` (it is required, and checked
    first); `message` + `event=DISMISS` → `422 Can not dismiss a dismissed pull
    request review`; `message` alone → the identical `422`. So the message is
    mandatory, `event` is accepted but inert, and re-dismissing is a no-op the
    selection rule already avoids. This is what §4's request shape is built on.
- **Test Completeness Ledger:** see §Ledger below.
- **Confidence-pattern check:**
  - *asymptote (depth)* — the risky direction is over-dismissal, so the tests
    push on identity (human, other bot, no anchor) rather than on the happy path.
  - *coverage (breadth)* — every branch of the selection rule has a case, plus
    the two orchestration invariants (never on `block`, never flips the gate).
  - *integration composition* — `cross_component` is not triggered: this diff
    touches neither the merge/churn/event-log resolvers, Claude-Code hooks,
    pipeline phase validators, nor campaign drain.

### Test Completeness Ledger

**33 behaviors · 32 `tested` · 1 `untestable` · 0 testable-but-untested.**

Rows 28–32 were added by Stage 3 and the external code review; four of the
guards below are pinned by **mutation** — the behaviour was deleted and the
suite confirmed to go red — rather than by reading the assertion.

| # | Behavior | AC | Status | Evidence |
|---|---|---|---|---|
| 1 | A passing run dismisses its own superseded change-requests | AC1 | tested | `test_it_dismisses_and_reports`, `test_own_marked_verdict_on_a_superseded_commit_is_selected` |
| 2 | The posted review-state body carries this run's nonce, and the cleanup is handed that same nonce | AC1 | tested | `test_the_cleanup_looks_for_the_nonce_this_run_actually_posted` |
| 3 | The head is read **before** the diff is fetched | AC1, AC5 | tested | `test_the_head_is_read_before_the_diff_is_fetched` — **mutation-verified**: moving the read below `fetch_pr_diff` turns the module red |
| 4 | A human's change-request is never dismissed, even carrying the marker | AC2 | tested | `test_a_humans_change_request` |
| 5 | An anchor that is not a `Bot` is refused | AC2 | tested | `test_an_anchor_that_is_not_a_bot` |
| 6 | Another bot's change-request is never dismissed | AC3 | tested | `test_another_bots_change_request` |
| 7 | A marker quoted mid-body is not ownership (anchor and candidate) | AC3 | tested | `TestOwnershipIsPositional` (3 cases) |
| 8 | An unmarked change-request under the same shared login is never dismissed | AC7 | tested | `test_an_unmarked_verdict_under_the_same_shared_bot_login` |
| 9 | A change-request about the *current* commit is never dismissed | AC4 | tested | `test_a_verdict_about_the_commit_that_is_current` |
| 10 | A `block` / truncated / nothing-reviewed / unknown-decision run clears nothing | AC4 | tested | `TestItClearsOnlyAfterPassing` (4 cases) |
| 11 | Reviewed ≠ head, or stamped ≠ head → nothing dismissed | AC5 | tested | `test_anything_at_all_when_the_head_has_moved`, `test_a_run_that_reviewed_an_older_commit_clears_nothing` |
| 12 | An unreadable reviewed-head → nothing dismissed | AC5 | tested | `test_an_unreadable_head_clears_nothing` |
| 13 | The head is re-confirmed before the first dismissal; moved or unreadable abandons the sweep | AC5 | tested | `TestTheHeadIsReconfirmedBeforeMutating` (2 cases) |
| 14 | With nothing to dismiss, no second head read is spent | AC5 | tested | `test_nothing_to_dismiss_costs_no_extra_head_read` |
| 15 | A listing / head / dismissal failure never flips the gate | AC6 | tested | `test_a_failing_cleanup_does_not_flip_the_gate`, `test_a_listing_failure_is_contained_and_named`, `test_one_refused_dismissal_does_not_stop_the_others` |
| 16 | Unparseable or non-array listing output raises rather than reading as "no reviews" | AC6 | tested | `test_a_zero_exit_body_that_is_not_json_raises`, `test_an_error_object_instead_of_an_array_raises` |
| 17 | Every refusal is printed, never swallowed | AC6, AC8 | tested | three `*_contained_and_named` tests — **mutation-verified**: deleting the `failed` branch of `_describe` turns the module red |
| 18 | One malformed review row does not void the sweep | AC6 | tested | `test_a_malformed_entry_is_counted_and_the_rest_still_clear` |
| 19 | An already-dismissed review is not selected again (idempotent) | AC1 | tested | `test_an_already_dismissed_verdict_is_not_selected_again` |
| 20 | A marker echoed by the model is stripped before stamping | AC3 | tested | `test_a_marker_echoed_by_the_model_is_stripped_before_stamping` |
| 21 | An empty summary still yields a postable body | AC1 | tested | `test_an_empty_summary_still_yields_a_postable_body` |
| 22 | Nonces are unique and match the pattern the selector accepts | AC1 | tested | `TestNonce` (2 cases) |
| 23 | The dismissal request sends `PUT` + the required `message`, and no `event` | AC1 | tested | `TestDismissReview` (3 cases), built on probe P6 |
| 24 | The listing decodes both the merged-array and concatenated-pages shapes | AC1 | tested | `TestListReviews` (3 cases) |
| 25 | Every emitted line is scrubbed at one choke point, whichever producer wrote it | AC6, AC8 | tested | `test_every_reported_line_is_scrubbed_wherever_the_text_came_from`, `TestStripDisplayUnsafe` (4 cases) |
| 26 | The report names what was dismissed, what was left alone and why | AC8 | tested | `test_it_says_why_when_it_dismisses_nothing`, `test_the_default_log_goes_to_stderr` |
| 28 | A body as GitHub actually returns it (CRLF) is recognised as anchor and candidate | AC1 | tested | `test_a_body_as_github_actually_returns_it_is_recognised` — the trailing `.strip()` is load-bearing and was previously unguarded |
| 29 | The nonce comes from the cryptographic source, not just a 32-hex shape | AC1 | tested | `test_it_comes_from_the_cryptographic_source` — the anchor's whole safety argument, previously unpinned |
| 30 | A non-object `user` aborts neither the candidate loop nor the anchor scan | AC6 | tested | `test_a_non_object_user_does_not_abort_the_sweep` (×3) + `..._cannot_break_the_anchor_scan_either` — **mutation-verified**: restoring `or {}` fails 4 tests |
| 31 | The truncation notice does not promise an unblock the pipeline cannot deliver | AC8 | tested | `test_the_truncation_notice_does_not_promise_an_unblock` |
| 32 | The log sanitiser strips control/invisible only — `gh` JSON stays legible, a newline cannot forge a workflow command | AC6, AC8 | tested | `TestStripDisplayUnsafe` (6 cases) |
| 33 | The two read wrappers and the selector work against the **live** GitHub API | AC1 | tested | F0.5: 10 read-only checks on PR #446 — 11 real reviews decoded, real head read, selector refuses without an anchor, selects a real superseded verdict with one, refuses again when the reviewed sha disagrees |
| 27 | A dismissal actually taking effect against live GitHub | AC1 | **untestable** | `reason_code: requires-external-nondeterministic-service` — needs a real stale change-request on a real pull request under a real token. Probe P6 went as far as is possible without one: it drove the endpoint three ways against an already-dismissed review and read the real 422s, which is what the request shape is built on. |

**Where the confidence is thin, stated plainly.** Everything above the last row is
offline. The one thing no test in this repository can establish is that
`PUT …/dismissals` clears a *live* verdict when the workflow's `GITHUB_TOKEN`
makes the call. Probe P2 shows it is *permitted*
(`dismissal_restriction.enabled = false`, job holds `pull-requests: write`) and
P6 shows the request is *well-formed*; the first real Tier-3 PR after this merges
is what turns those two into evidence.
