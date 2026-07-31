# F11 delivers the change, or says plainly that it did not

- **Run ID:** `iterate-2026-07-31-f11-delivery-truth`
- **Anchor:** `trg-5387cafb` (IT-3b) — consolidates `trg-68e39bd5` (high) + `trg-b9d56b6b` (low)
- **Predecessor:** IT-3 (`trg-e3ca4314`, closed as PR #498). Same subject — *F11
  says something untrue about the run it is checking* — moved from the ledger
  side to the **delivery** side.
- **Intent:** CHANGE (Path B) · **Complexity:** medium
- **Affected FRs:** FR-01.11 (/shipwright-iterate)
- **Spec Impact:** **MODIFY** — five criteria appended to FR-01.11, no row minted
  (MINT-vs-FOLD → FOLD: this *completes* an existing capability, `shared/fr-authoring.md` §3)

---

## 1. What is broken (measured, not assumed)

### Defect A — auto-merge cannot be armed without branch protection, so F11 never delivers

Measured 2026-07-29 on throwaway PR #501 into an unprotected base (every
PR-triggered workflow is scoped to `branches: [main]`, so that base had **zero**
checks):

```
$ gh pr merge --auto --squash
GraphQL: Pull request Protected branch rules not configured for this branch
(enablePullRequestAutoMerge)
```

GitHub does **not** merge immediately as was feared — it refuses to arm at all.
F11 tolerates that by design (fail-soft; the warning even names "no branch
protection"), and then `watch_pr_delivery.py` only *watches*. It never merges.
Exit 4, pending-timeout, after 1800 seconds.

So on any repo without branch protection **every** iterate ends not-delivered,
with an open, green, unmerged PR. 100% reproducible, not an edge case, and it
hits the most pragmatic persona hardest: a private repo on GitHub Free **cannot**
have rulesets, so it can never arm.

### Defect B — the freshness check's own warning contradicts itself

`check_session_handoff_fresh` emitted, on `iterate-2026-07-28-ci-ack-per-run-home`:

> WARN: 'Current Iterate Progress' names `iterate-2026-07-28-ci-ack-per-run-home`,
> not `iterate-2026-07-28-ci-ack-per-run-home`

**The card's stated cause is wrong, and it matters.** It says
`generate_session_handoff.py` writes the run id in backticks. It does not, and
never has:

| Probe | Result |
|---|---|
| the only producer, `lib/handoff_iterate.py:95` | `f"- **Run ID**: {run_id}"` — bare |
| `git log --all -S'Run ID**: ` + backtick` over both producers | **no commit, ever** |
| the runtime plugin cache copy | identical, bare |
| the canon-frontmatter parser | already strips surrounding quotes |

The real mechanism is narrower and worse: **the check compares raw values but
renders normalized ones.** `handoff_marker.clip()` collapses whitespace runs and
strips C0/C1, bidi and zero-width characters before the value reaches the
message. The comparison at `handoff_freshness.py:94` sees neither treatment. So
*any* difference `clip()` erases — a trailing space on the passed `--run-id`, a
zero-width character in the tracked file, backticks if a producer ever grows them
— fails the comparison while both sides of the "not" render identically.

A gate that says something visibly false trains readers to ignore it. That is the
same failure mode as the predecessor card, one layer further out: not a wrong
number, a self-refuting sentence.

## 2. The decision this needed first, and what was decided

Defect A's fix is a **decision, not a bugfix**: today's behaviour ("PR left open
for manual merge") is deliberate, and an active `gh pr merge --squash` was
declined in practice once before. May a Shipwright agent merge a PR itself?

**Decided by the operator (2026-07-31): yes — as the fallback the host cannot
perform, on by default, with an opt-out.** The reasoning that shaped it: the
answer must work for *three* repositories, without the tool trying to guess which
kind it is looking at.

| Case | Host capability | Who merges |
|---|---|---|
| A — this repo: protection + auto-merge on | arms | GitHub, as today |
| B — protected base, auto-merge switched **off** | refuses to arm | **nobody — reported as exit 6**, see below |
| B′ — protected base with no required checks | arms, merges almost at once | GitHub, already true today |
| C — private, GitHub Free, no branch protection possible | can never arm | Shipwright |

**Case B is deliberately NOT self-merge-eligible, and that narrowing came from review.**
The first design merged there too, on the reasoning that the host would still refuse a
merge whose required checks were unmet. Stage 3 pointed out that this is an *untested
assumption about a bypass-capable actor*: an iterate typically runs with the operator's
own token on the operator's own repository, i.e. an admin who may merge without meeting
requirements — so a protected base's required reviews could be silently bypassed. The
external code review then found the same hole reachable a second way, through the
structural-marker path, even after the narrowing. Both are closed: a base that reads as
`protected: true` can never license a self-merge, whatever the error wording says. The
remedy for case B is one checkbox (*Settings → General → Pull Requests → Allow
auto-merge*), which is a far smaller thing to ask than a new authority. Case C has no such
remedy, which is why it gets one.

**One ladder covers all three, because the delivery bar never moves — delivered =
the PR is `MERGED` and every check that exists is green. Only the actor differs.**

1. Attempt the arm, exactly as today. Armed ⇒ GitHub merges when green.
2. If the arm fails, classify *why* — from **hard facts**, not from GitHub's error
   wording. Two are readable without admin rights, both confirmed on this repo:

   | Fact | Call | Covers |
   |---|---|---|
   | `allow_auto_merge` | `gh api repos/{o}/{r}` | the repo-wide switch (case B) |
   | `protected` | `gh api repos/{o}/{r}/branches/{base}` | **rulesets *and* classic branch protection** (case C) |

   `protected: false` ⇒ **structurally impossible AND self-merge-eligible**.
   `allow_auto_merge: false` on a *protected* base ⇒ structurally impossible but
   **reported**, never merged (see below). Anything else ⇒ **transient** ⇒ keep watching,
   exactly as today. The host's error wording is corroborating evidence only: it can
   promote a failure, never demote one, and it can never promote past a base that reads as
   protected. An unreadable picture is transient, so the change can only add outcomes,
   never remove one.
3. Structurally impossible ⇒ deliver it here: wait for green → refresh-if-behind
   → re-verify → **merge the exact commit that was verified** → confirm the state
   really is `MERGED`.

**`protected` replaced an earlier, weaker plan.** The first draft used "the base
branch has no rules" (`/rules/branches/{branch}`) as a sufficient condition. That
endpoint reports **rulesets only**, so a repo on classic branch protection answers
`[]` while arming works perfectly — the discriminator would have silently demoted a
whole class of repositories to self-merge. External review caught it as HIGH; the
probe above found a fact that has neither weakness.

Protection with no required checks arms in step 1 and merges almost at once, which is
already true today — no new path for it either.

### Why this is in line with the refresh work, and the one gap it opens

`ensure_current` exists because GitHub's server-side merge **cannot** run the
regenerate-at-merge resolver, so a branch that fell behind merges stale
(Group-E). Arming *narrows* that window but does not close it: `--auto` merges the
moment checks pass, however far the branch has drifted by then. A self-merge
**closes** it, because the moment of merging is ours — refresh, then merge. Step 3
is stricter than `--auto`, not looser.

PR #503 is what makes that survivable at all: it taught the derived-snapshot gate
to measure `merge-base..HEAD` instead of the tip commit, so an `ensure_current`
merge commit no longer blinds it. Before #503 a refresh loop would have hidden
exactly the eleven forbidden paths that gate exists to catch.

**The gap that opens, and closes here.** Today the F11 verifier runs *before* the
watch, and `ensure_current` runs before *both* — so the commit that merges is
always the commit that was verified. A refresh that happens *during* the wait
would break that invariant for the first time. Step 3 therefore re-runs the
verifier after any mid-wait refresh, and refuses to merge if it comes back red.
Confirmed unowned: none of the nine parallel worktrees touches
`verify_iterate_finalization.py`, `watch_pr_delivery.py`, `references/F11.md` or
`handoff_freshness.py`.

## 3. Acceptance criteria

**Arming, and why it failed** (`lib/pr_delivery.py`, pure)

- (E) Given the arm command succeeded, when the outcome is classified, then it is
  `armed` and the delivery path is byte-for-byte today's.
- (E) Given the arm failed and both the repository's auto-merge setting is off and the
  base is unprotected, when the outcome is classified, then it is `unavailable`.
- (E) Given the arm failed, the repository's auto-merge setting is off, but the base IS
  protected, when the outcome is classified, then self-merge is **not** offered and the
  operator is pointed at that one setting — a protected base's required reviews are not
  something to merge past on the strength of a local test run.
- (E) Given the arm failed and the host's wording says the refusal is structural, when the
  base nevertheless reads as protected, then self-merge is still not offered: a readable
  fact outranks an error string.
- (E) Given the arm failed and the base branch is not protected, when the outcome
  is classified, then it is `unavailable`.
- (E) Given the arm failed and the host itself said protected-branch rules are not
  configured, when the outcome is classified, then it is `unavailable` **even
  though** neither readable fact could be fetched.
- (E) Given the arm failed while both facts say arming should have been possible —
  the draft-PR case among them — when the outcome is classified, then it is
  `blocked`: keep watching, today's behaviour.
- (E) Given the arm failed, the error wording is unrecognised **and** either fact
  is unreadable, when the outcome is classified, then it is `blocked`, never
  `unavailable` — an unreadable picture may not license a merge.

**Ready is not the same as pending** (`lib/pr_readiness.readiness` + `watch_pr_delivery.py`)

- (E) Given an open PR with no failing check, nothing still running, and a merge
  state that does not structurally block, when the caller asks for it, then the
  verdict is the new terminal `ready`.
- (E) Given the caller does not ask for readiness, when any payload is classified,
  then the verdict, the message and the exit code are **identical to before this
  change** — asserted over a matrix covering every status the watcher already
  recognises, not argued from the default value.
- (E) Given a check is still queued or in progress, when readiness is judged, then
  it is `pending`, never `ready`.
- (E) Given the host has not finished computing mergeability and reports the state
  as unknown, when readiness is judged, then it is `pending` — an uncomputed state
  is not a clear one.
- (E) Given the merge state structurally blocks — blocked, conflicted, or draft —
  when readiness is judged, then it is `blocked` and never `ready`.
- (E) Given the merge state says the branch is behind its base, when readiness is
  judged, then it is `refresh_needed` — a named third answer, so the driver cannot
  wait forever for a state only a refresh can clear.
- (E) Given checks reported on an earlier poll, when readiness is judged on a later
  head, then every one of those **names** must have reported again — a count is not
  enough, because three checks reporting where three were seen before proves nothing if
  the base gained two workflows in between.
- (E) Given the very first look at a PR shows no checks at all, when readiness is judged,
  then it is `pending` until a poll interval has passed — an empty rollup because the
  host has not created its runs yet is indistinguishable from a host that runs none, and
  mergeability turns clear faster than runs appear.
- (E) Given a merge state the tool does not recognise, when readiness is judged, then it
  is `pending` and names the state — an unknown answer is never a clear one.
- (E) Given the branch conflicts with its base, when readiness is judged, then it is
  `refresh_needed`, because the resolver that fixes it is already part of this step.
- (E) Given the host ran no checks at all, when readiness is judged, then it is
  `ready` and the count of checks observed is reported as zero.

**Delivering it here** (`tools/deliver_pr.py`)

- (E) Given the PR is not this run's — its head branch, its base branch, or its open
  state is not what delivery expects — when delivery runs, then it refuses **before
  the arm**, because `--auto --squash --delete-branch` merges and deletes that branch
  the moment its checks go green and is therefore itself a mutating command.
- (E) Given the PR cannot be read at all, when delivery runs, then it refuses rather
  than arming blind — an unreadable identity is not a permissive one.
- (E) Given the PR already reached a terminal state, when delivery runs again, then it
  is **reported** with that state's own verdict — merged is delivered, closed is closed
  — never refused. Delivery is re-run on a timeout or a host error by design, so a
  re-run after the merge landed must not turn a delivered PR into a failure.
- (E) Given the PR is in some other non-open state, when delivery runs, then it is
  still refused — only the two terminal states are reportable.
- (E) Given the host says the branch is behind its base, when delivery runs, then it
  **refreshes** rather than waiting: a state only a refresh can clear must never be
  polled to the timeout, which is this defect's own shape one state over.
- (E) Given the host insists the branch is behind but there is nothing to integrate,
  when delivery continues, then it re-polls and ends **pending** after the attempt
  bound — never merging against a state it cannot explain, and never spinning.
- (E) Given the host cannot be read while waiting, when delivery reports, then it is
  the existing host-error verdict and exit code, not an unhandled exception.
- (E) Given the head commit could not be read, when the merge would be issued, then
  delivery refuses rather than sending an empty pin and leaving the whole guarantee
  to the host's argument parsing.
- (E) Given arming is structurally impossible and self-merge is switched off, when
  delivery runs, then it stops **immediately** with a not-delivered verdict naming
  the reason — no waiting for a merger that cannot exist.
- (E) Given the self-merge switch holds a value that is neither on nor off, when it
  is read, then self-merge is refused and the unusable value is named — an
  unparseable setting fails closed.
- (E) Given the PR does not belong to this run — its head branch, its base branch,
  or its open state is not what delivery expects — when delivery runs, then it
  refuses before issuing any mutating command.
- (E) Given arming is structurally impossible and the PR reaches ready, when the
  branch is already current, then the PR is merged here **pinned to the verified
  commit**, and delivery succeeds only after the state is re-read as `MERGED`.
- (E) Given the head commit moved between verification and merging, when delivery
  reaches the merge, then the host refuses it because the pin does not match, and
  the wait-and-refresh loop restarts instead of merging an unverified commit.
- (E) Given the pull request's head is not the commit this run verified — because
  something else pushed to the branch — when delivery reaches the merge, then it refuses:
  pinning that commit would merge unverified work, and no refresh reconciles it.
- (E) Given the pull request is merged or closed by someone else while the branch is
  being brought up to date, when delivery looks again, then that state is reported with
  its own verdict rather than as a refusal.
- (E) Given a pull request in a different repository with the same branch names, when
  delivery checks identity, then it refuses — the repository is checked, not only the
  branches, and every host command names the repository explicitly.
- (E) Given a delivery timeout, when the wait is retried after a refresh, then the whole
  delivery shares **one** budget — three attempts may not silently cost three timeouts.
- (E) Given the base moved while waiting, when readiness reports `refresh_needed`,
  then the branch is refreshed, pushed, **re-verified**, and waiting resumes.
- (E) Given the re-verification after a refresh comes back red, when delivery
  continues, then it STOPS and does not merge.
- (E) Given the merge command itself fails, when delivery reports, then it is
  not-delivered with the host's reason named, never a silent fall-through.
- (E) Given the merge command exits zero but the PR does not read as `MERGED`,
  when delivery reports, then it is not-delivered — the command's exit code alone
  is never accepted as proof.
- (E) Given a required check fails while waiting, when delivery reports, then it
  is the existing checks-failed verdict and exit code, unchanged.
- (E) Given the change was merged here rather than by the host, when the closing
  summary is printed, then it names who merged it and how many checks the host
  actually ran.

**The freshness check compares what it renders** (`verifiers/handoff_freshness.py`)

- (E) Given the handoff names this run and the two values differ only in
  surrounding whitespace, when the check runs, then it PASSES.
- (E) Given the handoff names this run wrapped in backticks, when the check runs,
  then it PASSES.
- (E) Given two genuinely different run ids that agree for longer than the display
  limit, when they are compared, then they are **not** equal — canonicalising for
  comparison must not truncate, or the fix would introduce a false PASS where
  there was a false WARN.
- (E) Given an invisible character sits inside an otherwise different run id, when
  the check runs, then it still WARNs — stripping invisibles may not erase a real
  difference.
- (E) Given the handoff names a genuinely different run, when the check warns,
  then the warning shows two different names — the self-refuting sentence is
  impossible by construction, not merely unobserved.

**The calls to the outside world** (`lib/pr_delivery_host.py`)

- (E) Given a capability read fails, when it is reported, then the fact is `None` and
  never `False` — `False` would say "the host cannot arm, merge it yourself", which
  an unreadable answer must never license.
- (E) Given the capability is read, when the endpoints are chosen, then the branch's
  `protected` flag is read and the rulesets endpoint is **not** consulted.
- (E) Given a refresh integrated nothing, when the refresh returns, then nothing is
  pushed; given it integrated a commit, then the push uses `git -C <root>`.
- (E) Given the guard's output cannot be parsed, when the refresh reports, then it is
  treated as "nothing integrated" — pushing on a guess could push an unrelated commit.
- (E) Given the re-verification runs, when it is invoked, then it carries this run's
  id, project root and the new commit, so it is the same check as the original.
- (E) Given any call to the outside world, when it is made, then it carries a timeout —
  the polling clock is only consulted after a call returns, so an untimed one escapes
  every stated bound and the run neither delivers nor fails.
- (E) Given a call times out or the command is not installed, when it returns, then it is
  a failed result rather than an exception, and delivery reports the host-error verdict
  instead of a traceback.
- (E) Given the production host is assembled, when its capability reader is used, then it
  is bound to that same host — so faking one part can never leave another talking to the
  real code host.

**Composition** (integration)

- (E) Given a repo whose base is unprotected, when a full delivery runs from arm
  refusal through green, refresh, re-verify and pinned merge, then the PR ends
  `MERGED` and each step ran in that order.

## 4. Criteria appended to FR-01.11

Plain business language, no paths or symbols; provenance in the criterion line.

1. Given a finished change whose code host cannot be asked to merge it
   automatically — the branch it merges into has no protection, or the host's
   automatic-merge setting is switched off — when the change is delivered, then it
   is merged once every check the host actually ran has passed, instead of being
   left open for a person to merge by hand. Where the host merely refuses for the
   moment, waiting continues as before; where the situation cannot be read at all,
   the previous behaviour is kept.
2. Given a change was merged by the tool rather than by the host, when delivery is
   reported, then the report names who merged it and how many checks the host
   actually ran — so a delivery resting only on the checks run on the author's own
   machine can never read as one the host confirmed.
3. Given a project would rather nothing was ever merged on its behalf, when that
   preference is recorded, then the tool only ever asks the host to merge, and a
   change it cannot get merged is reported as not delivered straight away rather
   than waited on.
4. Given a change fell behind the work it merges into while it was waiting, when
   the tool merges it, then it is first brought up to date and checked again, so
   what gets merged is what was checked and never a stale copy.
5. Given the check that a change's record names the run now finishing, when the two
   names differ only in punctuation or in characters that cannot be seen, then they
   count as the same name — so the check can never report a mismatch while showing
   the same name on both sides of it.

All five carry `(iterate-2026-07-31-f11-delivery-truth)`. FR-01.11's `Layers` cell
stays `unit (inferred)`: a bare cell is a binding declaration and would hard-abort
the coverage gate.

## 5. Out of scope, and why

- **`lib/pr_blockers.py` is read, never edited.** IT-7a
  (`iterate-2026-07-31-it7a-pr-review-stale-verdict`) is live in a parallel
  worktree on the neighbouring subject — why a green PR is BLOCKED — and may well
  land there. The capability read gets its own small home instead of a second
  caller inside their file.
- **The 1800-second default and the poll interval** are unchanged. The complaint
  was never that the wait is long; it is that it waits for a merger that cannot
  exist.
- **`trg-d0e4592e`** (the derived gate's printed remedy is a no-op on a merge HEAD)
  stays filed. Different subject: what a gate *says*, not what it *does*.

## 6. External plan review — and what it changed

Two providers, both reached: **gemini `approve`**, **openai `revise`** (verdicts
agree within one step, no contradiction to resolve). The `revise` earned its keep —
one of its findings would have shipped a *new* defect inside the fix.

| # | Sev | Finding | Disposition |
|---|---|---|---|
| GPT-2 | high | "no rulesets" is not evidence auto-merge is impossible — classic branch protection answers `[]` | **Fixed in plan.** Probed `gh api .../branches/{base}` → `protected` is readable without admin and covers both. Rulesets endpoint dropped as a discriminator. |
| GPT-3 | high | Race on head **and** base between verification and merge; must not merge a head F11 did not verify | **Fixed in plan.** Pin the verified SHA, re-read before merge, and merge with `gh pr merge --match-head-commit` — probed, the flag exists, so the host enforces the pin. |
| GPT-1 | high | A new tool plus prose wires nothing; exit 6 needs a handler | **Fixed in plan.** Probed every caller: only prose calls the watch, so `references/F11.md` *is* the entry point, and its `case` block gains `6`. Campaign defer stays untouched. |
| GPT-7 | med | `clip()` **truncates at 120 chars** — comparing clipped values would accept two distinct long ids | **Fixed in plan.** A separate non-truncating `canonical_run_id`; display keeps `clip`. Now an AC with its own negative test. |
| GPT-4 | med | `BEHIND` / `UNKNOWN` / post-push settling unmapped; an empty rollup after a refresh push could read as green | **Fixed in plan.** `refresh_needed` is a named third answer, unknown ⇒ pending, and a "checks do not vanish" floor. |
| GPT-6 | med | Reuse the watcher's rollup logic; prove `ready_is_terminal=False` is unchanged | **Fixed in plan.** `_failing_checks` is promoted into the shared pure module and the watcher calls it there; identity is asserted over a matrix, not argued from a default. |
| GPT-5 | med | Default-on self-merge widens token authority; validate the PR is this run's, fail closed on a bad switch value | **Fixed in plan.** Identity preconditions before any mutating call; an unparseable switch refuses. |
| Gem-1 | med | Transient `UNKNOWN` mergeability | Same fix as GPT-4. |
| Gem-2 | med | Base advances during verification | Same fix as GPT-3. |
| Gem-3 | low | Re-verification needs `--run-id` passed through | **Fixed in plan.** `deliver_pr.py` takes `--run-id` / `--project-root` and passes them on. |
| Gem-4 | low | Draft-PR arm failure must be transient | Correct **by construction** under the definitive-facts rule: a draft has auto-merge on and a protected base, so it classifies `blocked`. Now an explicit AC. |

Nothing was declined.

## 7. Stage 1 review — REJECTED once, and what it caught

The spec-compliance HARD-GATE rejected the first implementation. Four findings, all
real, all fixed; nothing was argued away. Two are worth recording because they are the
*same class of defect this iterate exists to remove* — a gate computing something true
and nothing acting on it.

| Finding | Why it mattered | Fix |
|---|---|---|
| **`refresh_needed` was computed and never acted on.** `classify_delivery` mapped it to `pending`, so a BEHIND branch polled to the 1800-second timeout. | This is the bug being fixed, one state over: waiting for something that will never happen. The AC's antecedent was wired to nothing. | `refresh_needed` is now **terminal** in the watcher, and the ladder refreshes on it. A host that insists on BEHIND with nothing to integrate re-polls and ends pending after the attempt bound. |
| **Identity was checked before the *merge*, ~80 lines after the *arm*.** | `gh pr merge --auto --squash --delete-branch` IS mutating: on a stale PR number it merges and deletes somebody else's branch the moment their checks go green. `identity_problem`'s own docstring claimed "before any mutating call". | The identity read is now step **0**, before the arm. Three tests assert the arm did not run. |
| **A `gh` failure during the watch became an unhandled `RuntimeError`.** `watch_pr_delivery.main` used to map it to exit 5; the driver dropped that, so rung 1 was *not* byte-for-byte today's behaviour and exit 5 was unreachable — while the same diff documented it in F11.md. | | Both watch call sites catch `RuntimeError` → exit 5. Tested on both rungs. |
| **`pr_delivery_host.py` had zero tests** while the ledger claimed 0 testable-but-untested — including the external reviewer's own HIGH fix (that `protected` is the discriminator), asserted nowhere but a docstring. | Every function already carried an injection seam put there for testing. Seams nobody drives are decoration. | `shared/tests/test_pr_delivery_host.py`, 18 tests, incl. the `None`-not-`False` rule the merge licence rests on. |

Three minor items the same pass raised, also fixed: `--match-head-commit ""` on an
unreadable head now refuses locally instead of delegating to the host's argument
parsing; the Kern `SKILL.md` F11 index row named `watch_pr_delivery.py` as the delivery
step and now names `deliver_pr.py` (with a drift test pinning both directions); and two
miscounted citations in this spec were corrected.

Stage 1 also confirmed, so the next pass need not re-litigate it: `spec.md` carries
exactly the five criteria with no minted row and an untouched `Layers` cell; the three
external-review HIGH fixes are real in the code; Defect B is fully met and tested; and
no YAGNI behaviour was found.

**Structure changed under review pressure.** Fixing these took `deliver_pr.py` over the
300-line limit twice, so the family was split along the seams that already existed:
`lib/pr_readiness.py` (what state is the PR in) · `lib/pr_delivery.py` (what may we do
about it) · `lib/pr_delivery_host.py` (the outside world) · `lib/pr_self_merge.py` (the
wait→refresh→verify→merge cycle) · `tools/deliver_pr.py` (which rung, and the CLI).
Every file is under the limit and each has one job.

## 8. Stage 2 code review — 17 findings, 2 HIGH, all fixed

Stage 2 read the code as code. Nothing was declined. Two findings were ways to **merge
when it should not**, which is the only direction that really matters here.

**HIGH — the "checks do not vanish" floor was a count, and it started at zero.** Two
reachable merge-anyway paths. (a) On the *first* poll the floor is 0, so a rollup that is
empty only because Actions has not created the check runs yet — while `mergeStateStatus`
has already flipped to CLEAN, which it does faster — read as "green, zero checks" and
merged immediately. (b) A count cannot tell *which* checks: floor 3 from the old head,
the refresh integrates a base that gained two workflows, three of the new five report,
`observed >= min_checks` passes, and the merge lands before the other two exist. Fixed
by making the floor a **name set** — every previously seen name must report again — and
by refusing to believe an empty rollup until one poll interval has passed.

**HIGH — three test files crossed the 300-line source limit with no baseline entry**,
which the Group H audit fails *after* merge. Split rather than baselined: nine focused
files, each under the limit, every one still green.

The mediums, each a real hole:

| Finding | Fix |
|---|---|
| `readiness` fell through to **green** for any `mergeStateStatus` it did not recognise — a new enum member would license a merge on no evidence, the one direction the module's own docstring forbids | Clear states are now a **whitelist**; anything unrecognised is `pending` and names itself. Plus a drift test: no state this module calls clear may be one the blocker probe calls blocking. |
| **DIRTY** was bucketed with BLOCKED, so a branch that conflicted after another iterate merged polled for 1800s — when `ensure_current`, already wired into this ladder, is the remedy | DIRTY joins BEHIND as `refresh_needed`. |
| The pin guaranteed less than it read: `--match-head-commit` pins whatever the PR head *is*, so a commit pushed **by anyone else** during the wait would have been pinned and merged, unverified — and `ensure_current` integrates `origin/main`, not `origin/<branch>`, so no refresh reconciles it | The PR head is now compared with the local HEAD this run verified; a mismatch refuses. |
| The pre-merge re-read ran a PR that had **just been merged** (by a human, or the campaign orchestrator) through the OPEN-only identity check and returned a *refusal*, aborting the iterate over a PR that was merged and green | `terminal_state_result` is extracted and used at **both** read sites. |
| **No subprocess call had a timeout.** `timeout_seconds` bounds the polling clock, and that clock is consulted only *after* a fetch returns — so a hung `gh` escaped every stated bound and the run neither delivered nor failed | Every child process is timed out; a timeout becomes a failed result, not an exception. |
| "Never raises" was false: `gh` missing from PATH is an `OSError`, a blank-stdout zero exit is a `JSONDecodeError`, and a null rollup entry an `AttributeError` — all escaped the `except RuntimeError` sites as a traceback instead of the documented exit 5 | `HOST_ERRORS` covers every shape; the rollup readers skip non-dict entries. |
| **`--repo` was omitted on every mutating call** while the watcher passed it, and identity compared branch *names* only — so a fork and its upstream both matched, and the arm could act on one repo while the watch watched the other | Every gh call goes through `Host.call*`, which pins `--repo`; `identity_problem` now checks the repository too. |
| `timeout_seconds` was spent **per attempt**, silently making `--timeout-seconds 1800` a 5400-second block | One deadline, computed once; each wait gets the remaining budget. |
| Six loose host callables whose defaults disagreed — `capability` closed over the *module-level* `gh_json`, so faking `gh_json` alone still fired real `gh api` calls at the operator's live GitHub | One frozen `Host` bundle with a `default()` factory that binds `capability` to its own reader. The half-faked host is now unrepresentable. |

Lows, all fixed: the campaign predicate had two readers (now `campaign_defers`, with the
drift test re-pointed at the helper rather than the literal it pinned); the structural-marker
comment claimed a gating that the code did not do (the code is right — GitHub refuses
structurally on a `protected: true` base with no waitable rule — so the comment was
corrected); `render_pair` blamed *truncation* for every collision, including two 30-character
ids differing by a non-breaking space, and the invisible class was missing SOFT HYPHEN,
WORD JOINER, BOM and the grapheme joiner; two assertions that could not fail; the
composition harness would **hang** rather than fail on a non-terminating implementation
(frozen clock — now advancing, and `fetch` raises when the script runs out); and one ledger
citation named a test that no longer existed.

Stage 2 confirmed, so it need not be re-checked: no false-PASS in `canonical_run_id`, no
off-by-one in the attempt bound, no second implementation of `failing_checks`, no
hardcoded secrets, no `shell=True`, and the five-file split has a real seam.

## 9. Stage 3 (adversarial) and the external code review

**Stage 3 broke it four times.** Its whole value is that it assumed the change was wrong,
and on a step that merges pull requests that assumption paid four times over. Recorded in
full in the review record; the shape of each:

| Doubt | Why it mattered | Fix |
|---|---|---|
| **A merged PR reported NOT DELIVERED.** The exit code was distrusted in one direction only, and gh's `--delete-branch` does *local* git surgery **after** the merge API call has already succeeded — so the merge lands, the command fails, and F11 printed "NOT DELIVERED … do NOT retry blindly" for a change that was on `main`. | The worst possible lie for this gate to tell: a delivered change reported as lost, with the operator told not to look again. | The **state** is the evidence in both directions, and `--delete-branch` is gone from the self-merge entirely — the remote ref is deleted separately, after `MERGED` is confirmed. |
| **An unreadable local HEAD failed OPEN.** `if local and pinned != local` — so any git failure made `head_sha` return `""`, skipped the comparison, and merged whatever the PR head was. | The host module's own rule is that an unreadable fact is never a false one, and two lines above the same function refuses on an unreadable pin. | An unreadable local HEAD refuses. |
| **A re-run could merge a verifier-REJECTED commit.** Verification was keyed on *"did I push inside this process"*. So: attempt refreshes, pushes, re-verification comes back red, exit 7 — and the branch is now on an unverified commit **on origin**. Re-run: nothing to integrate, `verify` never called, pin matches, and the commit the previous run refused is squashed to `main`. | The invariant the whole rung claims to keep, defeated by re-running the thing F11 tells you to re-run. | `--verified-commit` carries the sha F11's verifier actually ran on; **any** other head is verified again before it may merge, whoever pushed it and whichever process. |
| **A MERGED PR was reported delivered with no identity check at all.** The terminal-state read ran *before* the identity check, so any merged PR in the repository could be reported as this run's delivery — reachable whenever `gh pr view <branch>` resolves a previously merged PR for a re-used slug. | Delivery is the one claim the whole pipeline rests on. | Identity split into `wrong_pr` (repository + head + base, no opinion on open-ness) and checked **first**, unconditionally. A drift test pins the ordering. |

Five mediums followed: no BEHIND/DIRTY re-check at the moment of merging (an unprotected
base does not force it, so a stale squash was reachable); case B resting on an untested
assumption about a bypass-capable token — fixed by **narrowing the authority**, §2; child
processes escaping the delivery budget by up to 90 minutes; `checks_observed` counting
rollup entries so an all-skipped rollup could claim "the host ran 3 check(s)"; and
`--delete-branch` doing local surgery inside the iterate worktree. Three lows, including a
false PASS on an **empty** canonical run id and a refusal that named a third party who was
never there. All fixed, each with a regression test; Stage 3 also listed seven mutations
the suite could not catch, and all seven now have one.

Stage 3 also returned a clean bill it is worth keeping: it could not defeat
`classify_arm_outcome`'s `None`-not-`False` chain, could not reach rung 3 under a campaign,
could not subvert `--match-head-commit` host-side, could not construct a false PASS on two
genuinely distinct run ids (NFC/NFD, NBSP, soft hyphen, BOM, word joiner, bidi isolates,
nested and lone backticks, long-prefix collisions all tried), and found no
branch-deleted-but-not-merged path.

**The external code review then found the narrowing had a second door.** `revise`, two
HIGH. One was a code-vs-spec divergence where the **spec** was stale (§2's case table still
promised case B a self-merge) — corrected there, not in the code. The other was real and
serious: the structural-marker path could still return `unavailable` when *both* facts read
permissively, so an error **string** alone could route a protected PR into self-merge —
exactly the hole the narrowing existed to close, reachable a different way. A marker can no
longer promote past a base that reads as `protected: true`. Three mediums with it:
`head_before` was read *after* `ensure_current` ran (so the comparison could never detect
the commit it exists to detect), the delivered result dropped `checks_passed` (re-opening
the skipped-is-not-evidence finding one layer up), and `Host.default` aliased rather than
**bound** its capability reader — the half-faked host the bundle was introduced to prevent.
Gemini's reply was truncated by the provider; its visible half raised that same binding
point, and it was treated as a finding rather than discarded.

## Confidence Calibration

- **Boundaries touched:** the GitHub host API (`gh pr view/merge`, two `gh api`
  reads) · the `statusCheckRollup` payload shape, now read by three consumers ·
  `subprocess` to two sibling scripts (`ensure_current.py`,
  `verify_iterate_finalization.py`) · `git push` · the `session_handoff.md` canon
  frontmatter + progress-block text format · two environment switches.

- **Empirical probes run:**
  1. **Is `protected` readable without admin?** `gh api repos/svenroth-ai/shipwright/branches/main`
     → `{"protected": true}`. **Yes** — and it covers rulesets *and* classic branch
     protection. This replaced the plan's weaker "no rulesets" discriminator.
  2. **Does `gh pr merge` support a conditional-head merge?** `gh pr merge --help`
     → `--match-head-commit SHA`. **Yes** — the pin is enforced host-side, not by my loop.
  3. **`allow_auto_merge` readable?** `gh api repos/svenroth-ai/shipwright` → `true`.
  4. **Who calls `watch_pr_delivery.py`?** Grepped every `.py/.md/.sh/.yml`: **only
     prose**. So `references/F11.md` *is* the entry point, and exit 6 has exactly one
     `case` block to reach.
  5. **Does any producer write a backticked Run ID?** `handoff_iterate.py:95` is the
     only writer and is bare; `git log --all -S` over both producers finds **no such
     commit, ever**; the runtime plugin-cache copy is identical. **The card's stated
     cause is false.**
  6. **Then what produced the observed warning?** Reverted canonicalization to the raw
     identity in-process and re-ran: reproduced the operator's exact sentence —
     `handoff was generated by iterate-…-name-the-blocker, not iterate-…-name-the-blocker`.
     Root cause confirmed as compare-raw / render-normalized.
  7. **Is `clip` safe to compare through?** No — it truncates at 120 chars. Probed by
     constructing two ids agreeing for 130 chars: `clip` collapses them. Hence a
     separate non-truncating `canonical_run_id`, with that collapse as a negative test.
  8. **Do the tests hold anything up?** Two negative controls, both run: reverting the
     canonicalization fails 1 test; disabling the "checks do not vanish" floor fails 1
     test in `shared/tests` **and** 1 in `integration-tests`.
  9. **Does it run on CI's Python?** CI does `uv python install 3.11`; local is 3.13.
     Re-ran all 114 affected tests under `--python 3.11`: green.
  10. **Does the old prose contract still hold?** The three F11 arm drift-tests failed
      after the move — correctly. Re-pointed at the code that now owns each property
      (flags, fail-soft, campaign defer) rather than deleted.

- **Test Completeness Ledger:** 46 behaviour rows over 56 acceptance criteria,
  **0 testable-but-untested.** Several rows deliberately cover a block of closely
  related criteria (the six arm-classification ACs are one row, the five host-call ACs
  another); `enumeration_basis` records the criterion count, not the row count, so the
  gate compares like with like.

  | # | Behaviour | Status | Evidence |
  |---|---|---|---|
  | 1 | A successful arm classifies `armed` | tested | `test_pr_delivery::test_a_successful_arm_is_armed` |
  | 2 | Auto-merge off ⇒ `unavailable` | tested | `…::test_auto_merge_switched_off_is_structurally_unavailable` |
  | 3 | Unprotected base ⇒ `unavailable` | tested | `…::test_an_unprotected_base_is_structurally_unavailable` |
  | 4 | Host refusal wording promotes when facts unreadable | tested | `…::test_the_hosts_own_refusal_is_enough_when_the_facts_cannot_be_read` |
  | 5 | Permissive facts + unknown error ⇒ `blocked` | tested | `…::test_a_permissive_picture_with_an_unknown_error_stays_blocked` |
  | 6 | Draft-PR refusal ⇒ transient | tested | `…::test_a_draft_pr_arm_failure_is_transient_not_structural` |
  | 7 | Unreadable picture never licenses a merge | tested | `…::test_an_unreadable_picture_with_an_unknown_error_never_licenses_a_merge` |
  | 8 | Every outcome names a reason | tested | `…::test_every_outcome_names_its_reason` |
  | 9 | Green + mergeable ⇒ `ready` | tested | `…::test_all_green_and_mergeable_is_green`, `test_watch_pr_delivery_ready::test_all_green_and_mergeable_becomes_ready_when_asked` |
  | 10 | Running / queued ⇒ `pending` | tested | `…::test_a_running_check_is_pending`, `…::test_a_queued_legacy_context_is_pending` |
  | 11 | Uncomputed mergeability ⇒ `pending` | tested | `…::test_an_uncomputed_merge_state_is_pending`, `…::test_a_missing_merge_state_is_pending_not_green` |
  | 12 | BLOCKED / DIRTY / DRAFT ⇒ `blocked` | tested | `test_pr_delivery::test_states_that_waiting_might_clear_are_blocked_never_green`, `…::test_a_conflicted_branch_is_refreshable_not_merely_blocked`, `…::test_an_unrecognised_merge_state_is_never_read_as_clear` |
  | 13 | BEHIND ⇒ `refresh_needed` | tested | `…::test_behind_is_its_own_answer_so_the_driver_can_refresh` |
  | 14 | Checks do not vanish (post-push floor) | tested | `…::test_checks_do_not_vanish`, `test_watch_pr_delivery_ready::test_checks_do_not_vanish_across_polls`, integration; **negative control run** |
  | 15 | Zero host checks ⇒ ready, count reported | tested | `…::test_a_host_that_runs_no_checks_is_green_and_says_how_many` |
  | 16 | Default path byte-identical (matrix) | tested | `test_watch_pr_delivery_ready::test_the_default_path_is_byte_for_byte_what_it_was`, `…::test_asking_for_ready_only_ever_reclassifies_a_would_be_pending` |
  | 17 | `ready` is never exit 0 | tested | `…::test_ready_is_never_exit_zero` |
  | 18 | Switch: default on / off / unparseable fails closed / campaign outranks | tested | `test_pr_delivery::test_self_merge_is_on_by_default`, `…::test_self_merge_can_be_switched_off`, `…::test_an_unusable_switch_value_fails_closed_and_names_itself`, `…::test_a_campaign_never_self_merges` |
  | 19 | No merger + no permission ⇒ exit 6 without waiting | tested | `test_deliver_pr::test_no_merger_and_no_permission_stops_at_once_without_waiting`, integration |
  | 20 | Identity refused before any mutation | tested | `…::test_a_pr_that_is_not_this_runs_is_refused_before_any_mutation`, `…::test_a_pr_targeting_the_wrong_base_is_refused` |
  | 21 | Merge pinned; moved head restarts, never merges | tested | `…::test_the_merge_is_pinned_to_the_verified_commit`, `…::test_a_head_that_moved_restarts_the_wait_instead_of_merging`, `…::test_a_head_that_keeps_moving_ends_pending_not_merged` |
  | 22 | Refresh ⇒ push ⇒ re-verify ⇒ wait again; red re-verify STOPS | tested | `…::test_a_refresh_pushes_reverifies_and_waits_again_before_merging`, `…::test_a_red_reverification_stops_delivery_and_merges_nothing`, `…::test_a_failed_refresh_stops_delivery` |
  | 23 | Merge failure / exit-0-but-not-MERGED ⇒ not delivered | tested | `…::test_a_host_refusal_of_the_merge_is_reported_not_swallowed`, `…::test_a_merge_that_exits_zero_but_did_not_merge_is_not_delivery` |
  | 24 | Freshness: whitespace/backticks pass, long ids and inner invisibles still differ, warning never self-refutes | tested | 10 tests in `test_handoff_freshness`; **negative control run** |
  | 25 | Identity is refused BEFORE the arm, not only before the merge | tested | `test_deliver_pr_self_merge::test_a_pr_that_is_not_this_runs_is_refused_before_any_mutation`, `…::test_an_unreadable_preflight_refuses_rather_than_arming_blind` |
  | 26 | A BEHIND branch triggers a refresh instead of waiting to timeout | tested | `test_watch_pr_delivery_ready::test_a_behind_branch_is_terminal_because_only_a_refresh_clears_it`, `test_deliver_pr_self_merge::test_a_behind_branch_triggers_a_refresh_instead_of_waiting_forever`, `…::test_a_host_that_insists_on_behind_with_nothing_to_integrate_ends_pending`, integration |
  | 27 | A gh failure while watching is exit 5, not a traceback | tested | `test_deliver_pr_self_merge::test_a_host_error_while_watching_is_exit_five_not_a_crash` |
  | 28 | A re-run on an already-terminal PR reports that state instead of refusing | tested | `test_deliver_pr_self_merge::test_a_pr_already_merged_is_reported_delivered_not_refused`, `…::test_a_pr_already_closed_unmerged_keeps_the_closed_verdict`, `…::test_a_pr_in_an_unrecognised_state_is_still_refused` |
  | 29 | Host calls: `protected` (not rulesets) is read; unreadable ⇒ `None` not `False`; re-verify carries the run id; integrate-then-push-only-if-integrated; `git -C` always | tested | 18 tests in `test_pr_delivery_host` |

  | 30 | The floor is a NAME set, not a count | tested | `test_pr_delivery::test_the_floor_is_a_name_set_not_a_count`, `test_watch_pr_delivery_ready::test_checks_do_not_vanish_across_polls` |
  | 31 | An empty rollup is not believed on the first look | tested | `test_pr_delivery::test_an_empty_rollup_is_not_believed_until_a_poll_has_passed`, `test_watch_pr_delivery_ready::test_the_first_poll_never_believes_an_empty_rollup` |
  | 32 | An unrecognised merge state is never read as clear | tested | `test_pr_delivery::test_an_unrecognised_merge_state_is_never_read_as_clear`, plus the two drift tests against the blocker probe's vocabulary |
  | 33 | A conflicted branch refreshes instead of polling to timeout | tested | `test_pr_delivery::test_a_conflicted_branch_is_refreshable_not_merely_blocked` |
  | 34 | The PR head must be the commit this run verified | tested | `test_deliver_pr::test_a_head_that_is_not_the_verified_commit_is_refused_not_pinned` |
  | 35 | A PR merged during the refresh is delivery, not a refusal | tested | `test_deliver_pr::test_a_pr_merged_during_the_refresh_is_delivery_not_a_refusal` |
  | 36 | Every host call pins the repository; identity checks it too | tested | `test_deliver_pr::test_every_gh_call_pins_the_repository`, `…::test_a_pr_in_another_repository_is_refused_even_with_matching_branches`, `test_pr_delivery_host::test_the_bundle_pins_the_repository_on_every_call` |
  | 37 | One delivery budget across attempts, not one per attempt | tested | `test_deliver_pr::test_the_delivery_budget_is_spent_once_not_once_per_attempt` |
  | 38 | Every child process is timed out; a timeout is a result, not an exception | tested | `test_pr_delivery_host::test_every_child_process_is_given_a_timeout`, `…::test_a_timeout_becomes_a_failed_result_not_an_exception`, `…::test_a_missing_binary_becomes_a_failed_result_not_an_exception` |
  | 39 | The host bundle cannot be half-faked | tested | `test_pr_delivery_host::test_the_default_host_binds_capability_to_its_own_reader`, `…::test_host_errors_covers_every_shape_an_ordinary_failure_takes` |
  | 40 | A null rollup entry does not cost the verdict | tested | `test_pr_delivery::test_a_null_rollup_entry_does_not_crash_the_verdict` |

  | 41 | A protected base is never self-merge-eligible, whatever the wording says | tested | `test_pr_delivery::test_auto_merge_off_on_a_PROTECTED_base_is_not_self_merge_eligible`, `…::test_permissive_facts_plus_a_structural_marker_stays_blocked_on_a_protected_base`, `…::test_a_structural_marker_still_carries_an_unprotected_or_unreadable_base`, integration `…::test_a_protected_base_whose_setting_is_off_is_reported_not_merged` |
  | 42 | A merge that landed despite a non-zero command exit is delivery | tested | `test_deliver_pr_hardening::test_a_merge_that_landed_despite_a_non_zero_exit_is_delivery` |
  | 43 | The self-merge never touches local refs; the remote ref is deleted after | tested | `test_deliver_pr_hardening::test_the_self_merge_never_deletes_the_local_branch` |
  | 44 | An unreadable local HEAD refuses instead of merging | tested | `test_deliver_pr_hardening::test_an_unreadable_local_head_refuses_instead_of_merging` |
  | 45 | The head that merges is verified as a COMMIT, across invocations | tested | `test_deliver_pr_hardening::test_a_head_verified_by_an_earlier_invocation_is_re_verified_here`, `…::test_the_commit_f11_verified_needs_no_second_verification` |
  | 46 | Up-to-dateness is re-read at the moment of merging | tested | `test_deliver_pr_hardening::test_a_base_that_moved_between_readiness_and_merge_refreshes_again` |

  Plus the closing-line behaviours (5 tests in `test_deliver_pr_summary`) and the composition
  (4 tests in `integration-tests/test_pr_delivery_ladder_integration.py`).
  **`untestable` rows: none.** Nothing in this diff needed a `reason_code` — the two
  host-shaped parts (which flags `gh` receives, whether the pin is honoured) are
  covered by asserting the argv we send and by delegating enforcement to
  `--match-head-commit`, and the honest limit is stated below rather than dressed up
  as coverage.

- **Confidence-pattern check:**
  - **Asymptote (depth).** The refusals are tested as thoroughly as the happy path —
    19 of the 40 driver tests assert that *nothing was merged or armed*. Two negative controls
    prove the two subtlest guards are load-bearing rather than decorative.
  - **Coverage (breadth).** All three host shapes are exercised: armed (case A),
    transient refusal, and structurally unavailable via *each* of the two facts
    independently (case B via `allow_auto_merge`, case C via `protected`).
  - **Integration composition.** `cross_component` machinery is touched — delivery now
    composes with the churn/merge resolver and the finalization verifier — so a
    `category:"integration"` test runs the **real** watcher and readiness against the
    real ladder, and its discriminating assertion is the poll *sequence*, which is the
    only thing that distinguishes "the floor held" from "it merged the first empty
    rollup it saw".
  - **What is NOT proven, stated plainly.** No test merges a real PR. The end-to-end
    claim rests on: the argv asserted here, `--match-head-commit` existing (probed),
    and `protected` / `allow_auto_merge` being readable (probed on this repo). The
    first live exercise of rung 3 will be the first unprotected repo — this repo is
    protected, so **this very PR takes rung 1 and cannot exercise rung 3.** That is a
    real limit of this iterate, not a coverage gap I can close from here, and it is why
    every refusal path fails closed rather than falling through.

## Review

Six passes, all recorded in
`.shipwright/planning/iterate/iterate-2026-07-31-f11-delivery-truth/reviews.json`.
**Every one of them found something the previous one had passed**, which is the whole
argument for running the cascade rather than picking a stage:

| Pass | Verdict | What it caught |
|---|---|---|
| **self** | 9/9 pass | — (the checklist; the real findings came from the others) |
| **plan** (external, GPT + Gemini) | gemini `approve`, openai `revise` — 3 HIGH | `[]`-rulesets would have demoted every classic-protection repo; `clip()` truncates, so comparing through it would trade the false WARN for a false **PASS**; a new tool plus prose wires nothing |
| **spec** (Stage 1) | **REJECT**, then PASS | `refresh_needed` computed and nothing acting on it; identity checked *after* the arm; a gh error crashing instead of exit 5; `pr_delivery_host.py` entirely untested while the ledger claimed otherwise |
| **code** (Stage 2) | 17 findings, 2 HIGH | the count-based floor merging an untested head, twice over; three test files over the size limit that would fail the post-merge audit; readiness failing OPEN on an unknown merge state; no subprocess timeouts; `--repo` missing from every mutating call |
| **doubt** (Stage 3) | 12 doubts, 4 HIGH | a **merged** PR reported NOT DELIVERED; an unreadable local HEAD failing open; a re-run merging a verifier-**rejected** commit; a merged PR reported delivered with no identity check |
| **external_code** (GPT; Gemini truncated) | `revise`, 2 HIGH | the narrowing had a second door through the marker path; `head_before` read too late; `checks_passed` dropped on the way out |

Nothing was declined. Two rounds changed the **shape** of the work — the module family
went from three files to five under review pressure — and one changed the **authority
granted**: a protected base is no longer self-merge-eligible, which is narrower than what
was approved, and is called out in the closing summary so the operator can revisit it.
