# ADR-116 — A passing Tier-3 review retracts its own superseded verdicts

- **Run ID:** `iterate-2026-07-31-it7a-pr-review-stale-verdict`
- **Anchor:** `trg-fc173418` (IT-7), member 7a
- **Status:** accepted
- **Architecture impact:** component (a new write surface)

## Context

A Tier-3 review that fails closed posts a GitHub `CHANGES_REQUESTED` review.
Two GitHub behaviours then combine badly:

1. A later `COMMENTED` review from the same reviewer does **not** retract an
   earlier `CHANGES_REQUESTED` one.
2. `dismiss_stale_reviews_on_push` — enabled on this repository's
   `main-protection` ruleset — clears **approvals** only.

So the change-request survives every subsequent commit and every subsequent
clean review. The pull request sits at `reviewDecision: CHANGES_REQUESTED` and
`mergeStateStatus: BLOCKED` with all six required checks green and zero open
review threads, and **nothing on the pull request names the blocker**. The
symptom is silence.

Measured on PR #446 (live API, 2026-07-31): five verdicts stamped `bdd788a1`,
`720f0de8`, `75e538c1`, `2ea75602`, `1086cf4e` survived six later `COMMENTED`
reviews on newer commits. It merged only after a manual dismiss.

## Decision

On a **passing** verdict, the reviewer dismisses its own superseded
change-requests via `PUT /repos/{repo}/pulls/{n}/reviews/{id}/dismissals`.

Ownership is **proven, never inferred**. A review is a candidate only if all of:

- its body's **last line** is a whole `<!-- shipwright-pr-review:{32 hex} -->`
  token (positional, `fullmatch`);
- `user.type == "Bot"`;
- its `user.login` equals that of the **anchor** — the review carrying *this
  run's* 128-bit nonce;
- its `commit_id` differs from the anchor's;
- and its state is still `CHANGES_REQUESTED`.

Nothing is cleared at all unless **the commit this run read, the pull request's
current head, and the anchor's own `commit_id` are the same commit** — and the
head is re-confirmed once more immediately before the first dismissal.

Every part of this is best-effort. The required check keeps the value the
*review* earned; a housekeeping failure is reported and then dropped.

## Rationale

Four weaker rules were rejected, each on evidence rather than taste.

**Posting `APPROVED` on success** would retract the change-request for free.
Rejected: `required_approving_review_count` is 0 *today*, so the moment it is
raised the gate bot's approval would satisfy a human-review requirement. That
trades a stuck merge for a control downgrade.

**Dismissing by author login alone.** Rejected in external review (high): every
workflow in a repository posts as the same `github-actions[bot]`, so this
sweeps up other workflows' change-requests.

**Matching the marker anywhere in the body.** Rejected in code review (medium):
a summarising bot under that same shared login could inherit ownership by
echoing PR-authored text — and the review body *is* model output over an
attacker-controlled diff. Hence the positional, whole-token rule, and hence
`stamp_review_body` stripping any marker-shaped text before adding its own.

**Treating `commit_id` as "the commit that was reviewed".** Rejected in code
review (medium), and this was the sharpest finding of the run: GitHub stamps
`commit_id` at **submission** time. A run that reviewed X while the head
advanced to Z is stamped Z, would have passed a two-term guard, and would have
retracted a live verdict about the intermediate commit Y. The reviewed SHA is
therefore read before the diff is fetched and threaded in from the caller — an
ordering now pinned by a test that was verified by mutation.

**Comparing `submitted_at`.** Rejected: execution order is not commit order (a
slow run on an old commit can land after a fast run on a new one), and ties at
GitHub's one-second precision would silently no-op. Anchoring on a commit makes
the comparison unnecessary.

## Consequences

- Verdicts posted **before** this shipped carry no marker and can never be
  attributed, so they are never cleared. That price was measured, not assumed:
  zero open pull requests at the time of writing, so the backlog is empty.
- Two extra `gh` reads on the passing path (reviews list + head), one head
  re-confirmation that is skipped when there is nothing to dismiss, and one
  `PUT` per stale verdict.
- The reviewer now holds a **write** surface on the reviews API. It is exercised
  only under the proof chain above, and never on a `block`, truncated,
  nothing-reviewed or unknown-decision run.
- Idempotent by construction: a cleared review reads `DISMISSED`, so a re-run
  selects nothing.

### Deliberately left open, and why

| Gap | Why not here |
|---|---|
| The workflow's `needs_review == false` success path still leaves a stale verdict standing | Needs a step in `.github/workflows/pr-review-run.yml`; that tree is reserved for anchor IT-9 |
| `reviewed_sha` is *fresh* rather than *exact* — a force-push X → Y → X straddling the run defeats it | The exact fix is passing the workflow's trusted `github.event.workflow_run.head_sha` in as `--head-sha`; same workflow tree, same owner. The merge decision is protected meanwhile: the required `PR Review` status is per commit SHA and the workflow re-checks the head against that trusted field before posting it |
| The vendored `pr_review` in `shipwright-webui` needs the same change | Different repository; cannot ship in this pull request |

## Shape

Two modules, split at the seam between deciding and doing:
`pr_review_dismiss_select.py` holds the whole ownership rule with no I/O
(the safety surface, readable on its own); `pr_review_dismiss.py` makes the
`gh` calls and reports. `pr_review_gh.py` gained three thin wrappers. The
split happened because the single module reached the 300-line guideline
during review hardening — shaving the reasoning would have cost more than it
saved, and a bloat exception on a file created in the same diff would have
been a fiction.

## Evidence

Six probes, all live rather than reasoned:

| Probe | What it settled |
|---|---|
| P1 | PR #446's eleven real review objects — the failure, and the field shapes |
| P2 | Ruleset 17548444: `dismissal_restriction.enabled = false` (permitted), `dismiss_stale_reviews_on_push` covers approvals only (why pushing did not help) |
| P3 | A dismissed review reads `DISMISSED` — idempotency without bookkeeping |
| P4 | `gh 2.92` merges paginated arrays; older releases concatenate them |
| P5 | Zero open pull requests — the unmarked backlog is empty |
| P6 | Three real `PUT …/dismissals` responses against an already-dismissed review: `message` is required and checked first; `event=DISMISS` is accepted but inert, so it is not sent |

Full acceptance criteria, options table and the 27-row Test Completeness Ledger:
`.shipwright/planning/iterate/iterate-2026-07-31-it7a-pr-review-stale-verdict.md`.
