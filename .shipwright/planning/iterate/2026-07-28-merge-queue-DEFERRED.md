# Merge queue on main — DESIGNED, REVIEWED TWICE, DEFERRED (2026-07-28)

**Status: not built. Nothing was changed on GitHub, no workflow was touched.**
This file exists so the next attempt starts from what was established rather than
from scratch, and so the reasons for deferring are on the record.

Deferred in favour of a cheaper pair of changes that attack the *measured* cause
— see `HANDOVER-2026-07-29-main-selfheal-then-docs.md`.

## Why it was deferred

The queue was aimed at **BEHIND** (`strict_required_status_checks_policy: true`
makes every merge invalidate every other open PR). Measurement showed the churn
driving BEHIND is almost entirely generated documentation, which a merge queue
does nothing about:

```bash
git log --first-parent -40 --name-only --pretty=format: origin/main \
  | grep -v '^$' | sort | uniq -c | sort -rn | head -25
```

Ranks 1–18 are **all** derived artifacts (`shipwright_events.jsonl` 30,
`conventions.md` 24, `shipwright_test_results.json` 23, `triage.jsonl` 21, the
five `compliance/*` 16–18 each …). The first real source file is rank 22 with 3
changes.

Two external review rounds both returned `revise`, and the second raised a
finding that changed the risk picture of the part previously believed mechanical
(see "The credential finding" below). Codex, asked independently, reached the
same ordering: turn off the up-to-date requirement first, move derived artifacts
off PR branches second, add a post-merge lane third, revisit the queue fourth.

## Facts established (do not re-derive these)

**From GitHub's documentation:**

1. A merge queue **replaces** `strict_required_status_checks_policy`; the docs
   say it "provides the same benefits as Require branches to be up to date …
   but does not require a pull request author to update their branch". Enabling
   a queue means turning that setting off. So turning it off now is not work
   that a future queue would undo.
2. **A pull request must pass its required checks BEFORE it can be added to the
   queue.** This dissolves most of the `PR Review` design problem below: the
   queue's review is a re-check of the combination, not the only review.
3. Required checks are evaluated **on the merge group**, so any workflow without
   a `merge_group:` trigger reports nothing there and the entry blocks forever
   (`phantom`, in `lib/required_checks_drift.py` vocabulary).
4. One `required_status_checks` set serves both pull requests and merge groups —
   there is **no** per-merge-group granularity, so "drop `PR Review` for merge
   groups only" is not configurable.
5. GitHub creates a read-only merge-group branch **per PR in the queue**
   (`gh-readonly-queue/{base}/pr-{n}-{sha}`), and the `merge_group` event payload
   carries `head_sha` / `base_sha` directly — so nothing ever needs to parse the
   ref name. An early draft did, and both reviewers rejected it.

**From the host (`gh api repos/svenroth-ai/shipwright/rulesets/17548444`):**

The six required contexts, and their producers:

| Context | Produced by |
|---|---|
| `Python (lint + test)` | `ci.yml` |
| `Analyze (python)` | `codeql.yml` |
| `Analyze (javascript-typescript)` | `codeql.yml` |
| `Shipwright Security Scan` | `security.yml` |
| `Anti-ratchet + allowlist diff` | `bloat-check.yml` |
| `PR Review` | `pr-review-run.yml` — a **posted commit status**, not a job name |

`bypass_actors` is `RepositoryRole 5` (admin) with `bypass_mode: always`.

## The credential finding — the reason "mechanical" was wrong

A `merge_group` run executes the workflow file **as it exists in the merge-group
ref**, which contains the queued change, and — unlike a fork `pull_request` run —
**`merge_group` runs with secrets available**.

`security.yml` deliberately keeps `security-events: write` and
`pull-requests: write` at **top level** (its own comment forbids moving them
without first teaching the A5.3 compliance audit to read job-level scopes). So
adding `merge_group:` there would hand a queued change a write-scoped token out
of a file that change controls.

Mitigating this is real work (per-job least privilege, `persist-credentials:
false`, a permissions regression test for merge-group-capable workflows) and it
collides with a documented landmine. It is not a blocker, but it is not
mechanical either.

Note fact 2 above cuts the other way and softens this: a PR editing
`.github/workflows/**` is a Tier-3a sensitive path, so it cannot reach the queue
without a mandatory review having already read that edit.

## The `PR Review` problem, and the shape that solves it

`PR Review` is a two-stage pair protecting FR-01.17 (E)5 (pinned by
`shared/tests/test_workflow_token_permissions.py`): stage 1 (`pr-review.yml`) runs
on `pull_request`, holds **no** credentials, reads an attacker-influenced diff;
stage 2 (`pr-review-run.yml`) runs on `workflow_run` — therefore from the
**default branch's** copy of the file, which a contributor cannot edit — holds
the credentials and posts the status. Stage 2 trusts nothing stage 1 produced.

A merge group breaks both halves: no `pull_request` event fires, and stage 2
resolves its subject by requiring exactly one open PR whose head is the event
SHA, which a merge-group commit never is.

**The shape that preserves (E)5** (designed, not built): give stage 1 a
`merge_group:` trigger — it stays credential-free and its only load-bearing
effect is *completing*, which triggers stage 2 from the default branch as
before. Fix stage 1's `concurrency` key, which is
`pr-review-${{ github.event.pull_request.number }}` and renders empty on a merge
group, so every merge group would share one group and cancel-in-progress would
have them cancel each other.

Given fact 2, the merge-group side may be able to be far simpler than the full
re-review that was designed — the PR-level review has provably already passed.
Settle that before building.

## What the two external review rounds found

**Round 1** (openai `revise`; gemini truncated by the provider):

- **high, both** — do not derive the merge-group base from the queue ref name.
  A batched group's ref does not carry a single `pr-{n}`, and the SHA there
  identifies the entry rather than the base. Superseded by fact 5: the payload
  carries `base_sha`.
- **high** — a partial/truncated compare must fail the gate, never review a
  partial range.
- **high** — every failure path must post a status; an opaque permanent
  `pending` is not acceptable.
- **medium** — a `merge_group:` trigger is necessary but *not sufficient* for a
  context to report; the job producing it can still be event-gated, and a
  `workflow_run` stage depends on the upstream workflow name resolving.
- **medium** — `origin/main` may not be in a shallow clone; verify the base
  object exists before using it.
- **medium** — run a pre-arm capability checklist before touching the ruleset.
- **low** — live verification needs an explicit timeout and expected producer
  identity, not just "the context appeared".

**Round 2** (openai `revise`; gemini truncated again):

- **high** — the credential finding above.
- **high** — a raw compare diff does not itself reveal whether GitHub truncated
  the result; completeness must be established from the JSON compare metadata
  first.
- **medium** — an empty-but-complete comparison (a genuinely no-op entry) must
  be distinguishable from an incomplete response, or the live probe rolls itself
  back for an expected condition.
- **medium** — `pr-review.yml` being credential-free on `merge_group` is not
  automatic; assert `permissions` explicitly for the new trigger too.

## If it is picked up again

1. Settle the remaining semantics **empirically** in a throwaway repo — arm a
   queue, push two PRs, print `toJson(github.event.merge_group)`, `github.ref`,
   and `git rev-list --parents`. Codex flagged commit topology as undocumented;
   do not design around an assumed first-parent ordering.
2. Do the credential audit of every merge-group-capable workflow first.
3. Re-read this file's fact 2 before rebuilding the review path — it may make
   most of the designed machinery unnecessary.
4. `shared/scripts/lib/required_checks_drift.py` gaining a `queue_phantom`
   direction (a required context whose producer cannot fire on a merge group)
   remains a good idea independent of the queue, and would have caught the
   whole problem class before anything was armed.
