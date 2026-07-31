# External plan review — IT-7a

Two rounds, `shared/scripts/tools/external_review.py --mode iterate`, provider
`openrouter`. Both rounds returned `SHIPWRIGHT_VERDICT: revise` from the OpenAI
reviewer; the Gemini reviewer was cut off by the provider both times
(`finish_reason=length`), so `contradiction.requires_resolution` was raised on
both rounds for the same reason — only one reviewer answered.

## Round 1 — verdict `revise`

| # | Category | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | security | **high** | The marker only chose the *anchor*; candidates were then matched on `user.login`. Every workflow in a repository posts as the same `github-actions[bot]`, so the rule would dismiss any other workflow's `CHANGES_REQUESTED` — the risk option B was rejected for, reintroduced. | **Accepted.** Candidates must now carry the marker themselves. The cost — verdicts posted before this shipped can never be attributed — was measured rather than assumed (probe P5: zero open pull requests, so that backlog is empty) and recorded as AC7. |
| 2 | approach | medium | "The newest marked bot review" is not necessarily *this* invocation's review; a concurrent run can post between the state post and the list call. | **Accepted.** The marker carries a per-run 128-bit nonce, so the anchor is this invocation's own review. |
| 3 | dependency | medium | `PUT …/dismissals` requires a `message`; a wrapper that omits it fails every time and parks the feature in its best-effort failure path. | **Accepted**, and settled empirically rather than from docs — probe **P6**. |
| 4 | edge-case | low | `submitted_at <` is a weak ordering guard at GitHub's timestamp precision; ties would be mishandled. | **Accepted.** The timestamp comparison was dropped entirely in favour of anchoring on the commit. |
| 5 | risk | low | Orchestration-level tests needed for listing failure, one refusal among several, malformed output, and `block` never listing. | **Accepted.** All four exist. |

## Round 2 — verdict `revise`

| # | Category | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | edge-case | **high** | The head guard is not atomic with the dismissals; the head can move between selection and mutation. | **Accepted in part.** The head is re-confirmed once after selection and before the first dismissal. The irreducible residual (a force-push inside the loop, and the T0→T1 window) is recorded in §6 rather than claimed closed. |
| 2 | dependency | medium | `event=DISMISS` is not part of the documented request; depending on undocumented acceptance is unnecessary. | **Accepted.** Probe P6 confirmed it is accepted but inert; it is not sent, and a test pins its absence. |
| 3 | security | medium | Matching `MARKER_PREFIX` as a substring is weaker than matching a structured token. | **Accepted**, and taken further after Stage 2: the match is a whole-token `fullmatch` on the body's **last line**. |
| 4 | edge-case | medium | The selection result should be structured, with categorised skip counts, or AC7's required diagnostic can be omitted while the safety behaviour is correct. | **Accepted, trimmed.** `StaleSelection.skipped` carries per-category counts (`human`, `unmarked`, `other_identity`, `current_commit`, `unreadable`), rendered by `_describe`. |
| 5 | risk | medium | "Best effort" needs containment at the whole call boundary, not only around individual dismissals. | **Accepted.** The orchestrator never raises, and the caller wraps it again. |
| 6 | approach | low | Read-after-write visibility: a just-posted review may not be listable yet; that benign no-op should be logged distinctly. | **Accepted.** "this run's own review is not visible on the pull request yet" is its own reason string. |

## Gemini

Round 1 produced one finding before truncation, and it was the decisive one:

> Using `submitted_at < anchor.submitted_at` to determine staleness incorrectly
> assumes execution order matches commit history. If a slow review run on an
> older commit finishes after a fast review run on a newer commit, the older
> commit's post-time will be newer, causing its orchestrator to […] dismiss the
> newer commit's valid failure.

**Accepted** — this is why the design anchors on a commit rather than on
wall-clock at all. Round 2's Gemini reply was truncated before its second
finding; its first was an advisory preference for `gh --jq` over
`json.raw_decode`, declined with a reason now recorded in `_decode_pages`'
docstring (`--paginate` applies the filter per page, so `--jq` returns NDJSON
that still needs reassembling).

**Degraded status recorded:** the Gemini leg answered partially in both rounds.
It is reported as `degraded`, not as agreement.
