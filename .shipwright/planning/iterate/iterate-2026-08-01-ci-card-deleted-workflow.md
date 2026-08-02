# Iterate — the CI importer files cards only for workflows the repo still has

- **Run-ID:** `iterate-2026-08-01-ci-card-deleted-workflow`
- **Intent:** BUG (Path C) — the triage importer emits an unfixable high card
- **Complexity:** medium (locked; `prior_source: keyword`, confidence 0.70)
- **Risk flags:** none (all four diff-driven detectors are path-based; this
  diff touches none of their patterns — re-checked against the real diff
  before finalization)
- **Found in:** triage `trg-6c9e32e4`, while triaging `trg-9b1a1286`
- **Status:** implemented

## Spec Impact

- **Classification:** `none`
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **Affected FRs:** FR-01.14 (Triage Inbox)
- **NONE justification:** FR-01.14 already states the guarantee this fix
  restores — *"one entry is created per **action the operator can take**"*. A
  card for a workflow that no longer exists is not an action anyone can take,
  so the spec was already right and the code failed to honour it. Restoring an
  AC the spec states correctly is the textbook `none` case for a BUG iterate
  (`path-c-bug.md` Step 2). No FR row changes; no new AC is minted, because an
  AC restating "the entry must be actionable" would duplicate the existing one.

## Symptom vs expected (F-debug Phase 1)

- **Observed:** `trg-9b1a1286` — a **P1 / high** triage card,
  `[ci] Probe refresh-token bypass failing on main`, dedup key
  `gh-ci:322548704`, whose `launchPayload` is `/shipwright-iterate --type bug`
  pointing at
  `https://github.com/svenroth-ai/shipwright/actions/workflows/322548704`.
- **Expected:** no card at all. Workflow `322548704`
  (`.github/workflows/probe-token-bypass.yml`) has **`state: "deleted"`** on
  GitHub — the file is not on the default branch. Nobody can fix it, re-run it,
  or make it green. The card is unactionable by construction.
- **Error site:** `shared/scripts/github_triage/mappers.py:145`
  (`latest_failed_ci_runs` returns the run) → `mappers.py:100`
  (`ci_action_unit` mints the high card).
- **Error source:** `shared/scripts/github_api.py:229`
  (`fetch_workflow_runs`) — the payload it returns has no workflow-state field
  at all, so the reducer never had the information it needed.

## Reproduction (F-debug Phase 2)

Deterministic, and built from the **real** run behind the real card rather than
a synthetic fixture — `gh api repos/svenroth-ai/shipwright/actions/runs/30404435116`
verbatim, fed through the two production functions:

```
Boundary 1  fetch_workflow_runs -> latest_failed_ci_runs
            'state' in run payload? False        <-- never crosses
Boundary 2  latest_failed_ci_runs               kept [322548704, 259825683]
Boundary 3  ci_action_unit                      severity=high  key=gh-ci:322548704
                                                "[ci] Probe refresh-token bypass failing on main"
```

The emitted title and dedup key are **identical** to the card recorded in
`.shipwright/triage.jsonl:1186`, which confirms the repro reproduces the actual
incident and not merely something adjacent to it.

## Recent changes (F-debug Phase 3) — NOT a regression

`git log -S latest_failed_ci_runs --reverse` → introduced in `ff51a8cc`
("feat(triage): import GitHub findings into the triage inbox"), moved by
`74d4cf04` (the 7-file package split) and neighboured by `f9cf3624` (gh-pr-ci).
The reducer has consulted `conclusion` alone **since the day it was written**.
Stated explicitly per F-debug Phase 3: this is not a regression — the workflow
lifecycle dimension was never modelled, so no commit "broke" it.

## Root cause (F-debug Phase 4)

> `latest_failed_ci_runs` decides that a workflow needs triage from
> `run.conclusion` alone, and its only input — the `actions/runs` payload —
> carries no workflow `state` field whatsoever; lifecycle state lives on a
> **different endpoint** (`actions/workflows`) that the importer never calls.
> A run belonging to a deleted workflow is therefore indistinguishable from one
> belonging to a live workflow, and mints a high-severity `gh-ci:{workflow_id}`
> action-unit pointing at a workflow page that no longer exists.

The boundary at which good input becomes bad output is **boundary 1**, the
`github_api` → `mappers` edge — the state is *absent at the fetch*, not lost in
the reduce. That is why the fix cannot live inside the reducer alone.

Empirically verified (not inferred from docs):

- `actions/runs` run objects expose 38 keys; **`state` is not among them**.
- `actions/workflows/322548704` → `{"state": "deleted"}` — the per-id endpoint
  serves deleted workflows, explicitly and authoritatively.
- `actions/workflows/259825683` → `{"state": "active"}`.
- `actions/workflows/999999999` → HTTP 404 → `_gh_api` returns `None`.

## The fix

Carry the missing dimension across boundary 1, and let the reducer use it.

1. **`github_workflow_api.fetch_workflow_state(workflow_id)`** (new module) →
   `str | None`: the lifecycle state of ONE workflow, straight from
   `actions/workflows/{id}`. `None` whenever the state cannot be established
   (fetch failed, 404, malformed payload).

   **Why a new module rather than `github_api.py`.** `github_api.py` is
   recorded in `shipwright_bloat_baseline.json` at `current: 321, limit: 300,
   state: grandfathered`, so the anti-ratchet pre-commit hook refuses any commit
   that grows it — the obvious home is literally unlandable. `github_pr_api.py`
   is the established precedent for exactly this situation: a focused sibling
   client that reuses `github_api._gh_api` as its transport. The split is also
   honest on its own terms — `fetch_workflow_runs` reports what a workflow's
   runs *did*, this reports what the workflow *is*, and conflating the two is
   the bug being fixed.
2. **`mappers.latest_failed_ci_runs(runs, *, workflow_state_fetcher=None)`**:
   after reducing to the latest failed run per workflow, drops any whose
   workflow reports `deleted`. `workflow_state_fetcher=None` ⇒ no filtering
   (unchanged behavior), so the public re-exported signature stays
   backwards-compatible.
3. **`consumer.import_findings`** passes `github_workflow_api.fetch_workflow_state`.

The injected-fetcher shape is not invented here — it mirrors
`resolve.resolve_pr_ci(..., pr_state_fetcher=...)`, which solves the identical
problem (a pure-ish module needing one authoritative live lookup per item).
`mappers.py` keeps its "no I/O" property: it calls a callable the consumer
supplies, and the tests inject a fake.

### Why per-id, and not a workflow list

The first draft of this fix fetched `actions/workflows?per_page=100` once and
inferred deletion from **absence** from that list. The external plan review
(openai, `revise`, finding 1) caught that this rests on an unverified premise:
absence only means deletion if the list is *guaranteed* to include every
`disabled_*` workflow, and the probe behind it observed a repo whose workflows
were all `active`. Had GitHub omitted any disabled state, the rule would have
suppressed **actionable** cards — precisely the failure AC3 forbids, and the
most dangerous direction this change can fail in.

Verifying the premise would have meant disabling a live workflow on the
operator's repository. Removing the premise was better, and asking each failing
workflow for its own state does exactly that — the state is then **read, never
inferred**.

It is also *cheaper*, which inverts the original reasoning. The list costs one
API call on **every** import even when nothing is failing; per-id costs **zero**
on a healthy repo, and one call per *distinct workflow with a failing latest
run* otherwise — typically 0, rarely more than 3. And it dissolves three further
problems the list approach carried:

- **No pagination trap.** `actions/workflows` is object-shaped
  (`{total_count, workflows}`), and `gh api --paginate` on an object endpoint
  emits *concatenated* JSON objects — verified: `json.loads` raises
  `Extra data: line 1 column 964`. A `paginate=True` there would have made the
  fetch silently always fail: fail-open, filter never active, bug not fixed,
  and every mocked unit test still green.
- **No truncation logic**, and no 100-workflow ceiling above which the fix
  would quietly stop working (gemini's finding).
- **No map to validate entry-by-entry** (openai finding 2) — there is a single
  `state` string, and anything unexpected about it resolves to `None` ⇒ keep.

### Two deliberate design decisions

- **`disabled_*` workflows keep emitting.** `disabled_manually`,
  `disabled_inactivity` and `disabled_fork` all mean *the file is still on the
  default branch* — an operator can re-enable and fix it. Only `deleted` is
  unfixable, and only `deleted` is what the card reported. Filtering disabled
  workflows would suppress real, actionable failures. With per-id lookup this
  is now enforced by reading the state, not by trusting a listing.
- **Unknown state fails OPEN, never closed.** A failed fetch, a 404, a
  malformed payload, a raising fetcher, or a run with no `workflow_id` all
  **keep** the run. Fail-closed would mean *real CI failures stop being
  surfaced*, which is far worse than re-showing one stale card. Fail-open is
  also per-workflow here, so one flaky lookup cannot disable the whole filter.

## Loop-closing — the already-open card resolves itself

No extra code. `PREFIX_CI` is already in `resolvable_prefixes` whenever the
runs fetch succeeds, so once the deleted workflow's key leaves `current_keys`,
`resolve.resolve_stale` dismisses any open `gh-ci:{deleted}` item with
`reason="githubResolved"`. The fix closes existing bad cards, not just future
ones.

## Out of scope

- **`main_health.py` is NOT affected** — verified, not assumed. It filters
  against the pinned `MONITORED_WORKFLOWS` allowlist
  (`shared/scripts/lib/main_health.py:120`, `if name not in known: continue`),
  so an ad-hoc probe workflow never enters its verdict. No change needed there.
- **`gh-pr-ci:` cards** — keyed by PR number with their own differentiated
  resolve path; a deleted workflow cannot mint one.
- Any change to `ci_action_unit`'s payload, severity, or dedup key.
- Retro-dismissing `trg-9b1a1286` by hand — it already self-resolved when the
  run aged out of the 100-run window.

## Acceptance Criteria

- **AC1** — Given a failed run whose workflow reports `state: "deleted"`, when
  the reducer runs with a state fetcher, then that run is dropped and no
  `gh-ci:` action-unit is minted for it.
- **AC2** — Given `fetch_workflow_state` is called for a workflow, when the
  API answers, then the state is **read from `actions/workflows/{id}`** rather
  than inferred from any listing — a deleted workflow is identified by what the
  host says about it, not by its absence from a collection.
- **AC3** — Given a failed run whose workflow is `active` or any `disabled_*`
  state, when the reducer runs, then the run is **kept** and still mints its
  card — a disabled workflow's file still exists and is still fixable.
- **AC4** — Given the state cannot be established — fetch failure, HTTP 404,
  malformed payload, a fetcher that raises, or a run carrying no
  `workflow_id` — when the reducer runs, then the run is kept. Fail-open, so
  no API fault can suppress real CI failures.
- **AC5** — Given the state lookup fails for one workflow, when the reducer
  runs, then the *other* workflows are still filtered normally — fail-open is
  per-workflow, never global.
- **AC6** — Given the existing single-argument call
  `latest_failed_ci_runs(runs)`, when it is called, then behavior is unchanged
  — the public re-exported signature stays backwards-compatible.
- **AC7** — Given an open `gh-ci:{deleted}` card and a successful import that
  now filters the deleted workflow, when the resolve sweep runs, then the card
  is auto-dismissed with `reason="githubResolved"`.
- **AC8** — Given the state lookup fails, when the import runs, then the open
  `gh-ci:` card is **not** resolved — a fetch fault must never be read as
  "the finding cleared" (mirrors FR-01.14's "an import that failed closes
  nothing").
- **AC9** — Given a state lookup is needed, when the reducer runs, then it is
  performed only for workflows whose **latest** run failed — never once per
  raw run, and never for workflows that are green.
- **AC10** — Given the workflow-**runs** fetch itself failed (`None`), when the
  import runs, then `PREFIX_CI` is not resolvable and **no** `gh-ci:` card is
  closed — the pre-existing gate this change must not weaken.
- **AC11** — Given any payload that is not a mapping carrying a non-empty
  string `state`, or a `workflow_id` that is not an integer, when
  `fetch_workflow_state` runs, then it returns `None` without constructing a
  request from unvalidated input.

## Findings folded in from the external plan review

Round 1 returned `revise` (openai; gemini truncated). Round 2 returned
`approve` / `approve`. Dispositions:

| # | Finding | Disposition |
|---|---|---|
| openai-1 | `PREFIX_CI` resolvability must stay tied to a successful runs fetch, else an upstream failure could close every CI card | **Accepted** → AC10 + ledger row 18. The gate already exists (`if fetch_succeeded["runs"]`); the test pins it so this change cannot erode it. |
| openai-2 | `fetch_workflow_state` must validate: mapping + non-empty string `state` | **Accepted** → AC11. Mapper policy stays narrow: only exactly `"deleted"` drops. |
| openai-3 | Contain exceptions in both the helper and the per-fetcher call; no cache needed | **Accepted** — `try/except` inside the reducer loop; reduction already guarantees ≤1 lookup per surviving workflow. |
| openai-4 | Confirm token scope reaches `actions/workflows/{id}` | **Accepted** — verified live against this repo with the importer's own `gh` identity (probes 2, 3). Fail-open covers a permission-denied deployment. |
| openai-5 | Treat `workflow_id` as an integer before building the endpoint | **Accepted** → AC11. `_gh_api` is already non-shell (argv list, no `shell=True`), so this is hygiene rather than an injection fix. |
| gemini-1 | Treat HTTP 404 as `deleted` rather than fail-open | **Declined — see below.** |
| gemini-2 | Ensure the `try/except` sits inside the loop so a raising fetcher cannot abort the import | **Accepted** → AC4 + ledger row 8. |

## Findings folded in from the external CODE review

Round 1: openai `revise`, gemini `approve`. Round 2: openai `approve`
("ship as-is"), gemini degraded (truncated reply, no verdict — recorded in
`degraded[]`). Both round-1 findings accepted:

- **openai medium** — `fetch_workflow_state` did not contain exceptions from
  `_gh_api`, so a transport that raised would escape a public helper whose
  documented contract is "`None` whenever the state cannot be established".
  The reducer happened to catch it, but a direct caller would not. Now
  contained in the client, with the exception type in the diagnostic (row 29).
- **openai low** — the lookup cap was consuming *runs* rather than *lookups*,
  so 20 malformed-id runs could exhaust the budget having fetched nothing and
  leave a genuinely deleted workflow unexamined behind them — re-opening the
  original bug for a case the cap was never meant to touch. The counter now
  increments only immediately before the fetcher is invoked (row 30).
- **gemini low** — stderr on every failure is spam. *Partly taken:* silencing
  the `data is None` case would silence exactly the hard-delete/permission
  drift D1 exists to surface, so the line stays; instead it now names whether
  the cause was a transport fault or a drifted payload shape, which is what
  made the two indistinguishable in the first place. Volume is bounded by the
  cap (≤20 lines) and the import throttle.

## Findings folded in from the review cascade (Stage 3)

The doubt-reviewer could not break the filter — it failed to construct any
live-workflow suppression, cwd/id mismatch, permission-edge suppression, AC10
erosion, permanently-lost finding, or a broken implementation the tests would
pass. Four advisory doubts, all answered:

| # | Doubt | Disposition |
|---|---|---|
| D1 | Premise-drift is undetectable: `None` reads as "keep" but is indistinguishable from "alive", so if GitHub ever stopped tombstoning, the filter would become a permanent no-op with no signal | **Accepted.** `fetch_workflow_state` now writes one stderr line whenever it cannot establish a state — the id always comes from a run in this same repo, so failing to resolve it is anomalous, never routine. Pinned both ways (rows 26-27). `mappers.py` stays I/O-free; its silent `except` branch is now documented as reachable only by an injected fake. |
| D2 | Uncapped serial `gh` subprocesses run *ahead of* the other four feeds on a hook with no timeout; exceeding the budget kills the import before **any** finding of any class is written — worst exactly when main is broadly red | **Accepted, reversing my earlier decline.** The decline had argued a cap adds "a silent partial-filtering mode"; the reviewer's observation that a *budget* is fail-open (unknown ⇒ keep) defeats that, since fail-open is the design's own posture everywhere else. `_MAX_STATE_LOOKUPS = 20`; beyond it runs are kept unexamined, i.e. the cap degrades to pre-fix behaviour for the tail rather than suppressing. Row 28. |
| D3 | `reason="githubResolved"` reads as good news, and `triage_gc` compacts that reason away — so a red workflow *deleted* from main vanishes silently, and `main_health` only covers the four `MONITORED_WORKFLOWS` | **Declined, with reasoning.** "Unactionable" and "resolved" are deliberately the same outcome here: once the file is off the default branch there is nothing the operator can do *about that workflow*, which is this change's whole premise. The distinct concern — *should* that file have been deleted — is already owned by a different gate: `touches_ci_supplychain` fires on `.github/workflows/**` and `risk_detectors.py` documents that "a DELETED security workflow must trigger just like an edited one". Minting a new reason token would also require adding it to `triage_gc.MACHINE_REASONS`, or the item becomes uncompactable churn. |
| D4 | `raising=False` on the isolation stubs means a rename creates a dead attribute while the real client stays live | **Accepted.** Dropped from all four `setattr` calls, so a rename now fails loudly. (Deliberately *kept* on the three `monkeypatch.delenv` calls in the sibling fixture, where it is load-bearing — `delenv` raises `KeyError` when the var is unset.) |

### Why gemini-1 is declined

The suggestion is to read a 404 from `actions/workflows/{id}` as authoritative
absence and drop the run. It rests on the premise that a deleted workflow may
404 — but the premise is false here, and acting on it is unsafe:

1. **Deleted workflows do not 404 — they are tombstoned.** Probe 2 fetched the
   actual deleted workflow behind this incident and got HTTP 200 with
   `{"state": "deleted"}`. The 404 branch is therefore not the deletion signal;
   the explicit state is, and the fix already reads it.
2. **GitHub returns 404, not 403, for resources a token may not see.** So a
   token lacking `actions:read` would 404 on *every* workflow — and treating
   404 as deleted would then silently suppress **every** CI card in the repo.
   That is the exact catastrophic over-filtering direction the whole design is
   built to avoid, and it intersects openai-4's permission concern.
3. `_gh_api` collapses all failures to `None` and exposes no HTTP status, so
   honouring the suggestion would mean widening a client shared by many
   callers — real cost, to buy a branch that is unreachable in practice and
   dangerous when reached.

If GitHub ever does start hard-deleting workflows, the symptom is the *original*
bug (one stale card), not a new one — recoverable, and strictly preferable to
blanking the CI feed on a permissions edge.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `github_workflow_api.fetch_workflow_state` | `mappers.latest_failed_ci_runs` | in-process `str \| None` (injected callable) |

No **serialized** boundary is touched — the new value is an in-process string
returned by an injected callable; it is never written to disk, never parsed
from a file, and never crosses a process edge. `touches_io_boundary` therefore
does not fire (verified: all four detectors in `risk_detectors.py` are
path-based, and this diff matches none of their patterns). No Boundary Probe /
round-trip test is owed.

## Confidence Calibration

- **Boundaries touched:** the in-process `github_workflow_api` → `mappers` edge above.
  No serialized format, no file, no schema.

- **Empirical probes run:**
  1. `gh api actions/runs?per_page=1 --jq 'keys'` → 38 keys, **no `state`**.
     Confirms the reducer could not have consulted state — the root cause is at
     the fetch, not the reduce.
  2. `gh api actions/workflows/322548704` → `{"state": "deleted"}`. Confirms
     the card's workflow really is deleted, so the report is accurate.
  3. `gh api actions/workflows/259825683` → `{"state": "active"}`, and
     `.../999999999` → HTTP 404 ⇒ `_gh_api` returns `None`. Establishes that
     the per-id endpoint answers authoritatively for live, deleted, and
     nonexistent ids alike — the signal the final design reads.
  4. **Repro against the real run object** (`runs/30404435116`) → emitted title
     and dedup key byte-identical to `triage.jsonl:1186`. The repro reproduces
     the actual incident.
  5. **Pagination shape probe** → `--paginate` on the object-shaped
     `actions/workflows` endpoint yields concatenated JSON; `json.loads` raises
     `Extra data: line 1 column 964`. This probe killed `paginate=True`, which
     would have silently disabled the entire fix behind green tests.
  6. `--paginate --slurp` probe → parses (gh 2.92, 4 pages, all 7 ids).
     Recorded as a rejected alternative; costs a `gh` version floor.
  7. `main_health.py:120` read directly → pinned `MONITORED_WORKFLOWS`
     allowlist. Scope boundary verified rather than assumed.
  8. `gh api actions/workflows?per_page=100` → 7 workflows, all `active`.
     **This probe is why the design changed:** it could not establish that
     `disabled_*` workflows appear in the listing, so absence-from-list was an
     unsound deletion signal (openai finding 1). Recorded as a *falsified*
     premise, not a supporting one.
  9. **Post-fix run against the LIVE API, no mocks** — the same real run objects
     routed through the production fetcher: `322548704 -> 'deleted'`,
     `259825683 -> 'active'`; reducer keeps only the live one; exactly one
     lookup per failing workflow. The reported incident no longer reproduces in
     production, not merely against a fake. Re-run after the review cascade's
     edits, unchanged.
  10. `bash scripts/hooks/pre-commit` → exit 0, empty output. Run because the
     Stage-2 reviewer found this diff had pushed `consumer.py` to 303 against a
     300 limit with no baseline entry — a **new crossing**, which
     `bloat_gate_on_stop.py` blocks, not merely a post-merge detective finding
     as I had assumed from CLAUDE.md's wording. `consumer.py` and `conftest.py`
     now sit at exactly 300 and 320.

- **Test Completeness Ledger:** below.

- **Confidence-pattern check:**
  - *Asymptote (depth):* yes, twice — and both times the extra probe overturned
    something. Probe 5 fired after the design already read as obviously correct
    and invalidated `paginate=True`; then the external review invalidated the
    absence-inference premise that probe 8 had only *appeared* to support. Each
    was answered with a further probe (6, then 3) rather than a re-reading. The
    generalisable lesson: every state claim here is now API-verified, and the
    one claim that was inferred rather than read is exactly the one that broke.
  - *Coverage (breadth):* every ledger row below is `tested`; 0
    untested-testable behaviors.

### Test Completeness Ledger

| # | Testable behavior | Disposition | Evidence / reason_code |
|---|---|---|---|
| 1 | Run whose workflow reports `deleted` is dropped (AC1) | tested | `test_drops_run_for_deleted_workflow` |
| 2 | State is read from `actions/workflows/{id}`, not a listing (AC2) | tested | `test_github_workflow_api.py::test_fetch_workflow_state_reads_the_per_id_endpoint` |
| 3 | `active` workflow still emits (AC3) | tested | `test_keeps_run_for_active_workflow` |
| 4 | Each `disabled_*` state still emits (AC3) | tested | `test_keeps_run_for_disabled_workflow` (parametrized ×3) |
| 5 | `workflow_state_fetcher=None` ⇒ no filtering (AC4, AC6) | tested | `test_no_fetcher_keeps_every_failed_run` |
| 6 | Run without `workflow_id` is kept, fetcher not called (AC4) | tested | `test_run_without_workflow_id_is_kept` |
| 7 | Fetcher returning `None` ⇒ run kept (AC4) | tested | `test_unknown_state_keeps_run` |
| 8 | Fetcher that raises ⇒ run kept, no propagation (AC4) | tested | `test_raising_fetcher_keeps_run` |
| 9 | 404 / malformed payload ⇒ `fetch_workflow_state` returns `None` (AC4) | tested | `test_github_workflow_api.py::test_fetch_workflow_state_returns_none_on_bad_payload` (parametrized) |
| 10 | One failed lookup does not disable filtering for others (AC5) | tested | `test_one_failed_lookup_does_not_disable_other_filtering` |
| 11 | Existing single-arg call unchanged (AC6) | tested | `test_latest_failed_ci_runs_picks_latest_per_workflow` (existing, unmodified) |
| 12 | Deleted workflow does NOT reach the triage store end-to-end (AC1) | tested | `test_import_files_no_card_for_deleted_workflow` |
| 13 | Live workflow's failed run still cards in that same import (AC3) | tested | `test_import_files_no_card_for_deleted_workflow` (asserts the live key IS present) |
| 14 | Open `gh-ci:{deleted}` card auto-dismisses (AC7) | tested | `test_import_resolves_open_card_for_deleted_workflow` |
| 15 | A failed state lookup does NOT resolve the open card (AC8) | tested | `test_failed_state_lookup_does_not_resolve_card` |
| 16 | Lookup happens only for latest-failed workflows, once each (AC9) | tested | `test_state_is_fetched_only_for_latest_failed_workflows` |
| 17 | `fetch_workflow_state` does not pass `paginate=True` (AC2) | tested | `test_github_workflow_api.py::test_fetch_workflow_state_reads_the_per_id_endpoint` (asserts the call kwargs) |
| 18 | A failed **runs** fetch closes no `gh-ci:` card (AC10) | tested | `test_failed_runs_fetch_resolves_no_ci_cards` |
| 19 | Non-integer `workflow_id` ⇒ `None`, no request built (AC11) | tested | `test_github_workflow_api.py::test_fetch_workflow_state_rejects_non_integer_id` |
| 20 | Non-mapping / empty-`state` payload ⇒ `None` (AC11) | tested | `test_github_workflow_api.py::test_fetch_workflow_state_returns_none_on_bad_payload` (parametrized) |
| 21 | The dismissal carries `reason="githubResolved"`, not merely a dismissed status (AC7) | tested | `test_import_resolves_open_card_for_deleted_workflow` (asserts `statusReason`) |
| 22 | The `deleted` match is case-insensitive (widens the literal, in the safe direction) | tested | `test_gone_state_match_is_case_insensitive` (parametrized ×3) |
| 23 | The REDUCER's own id guard keeps a run whose `workflow_id` is a bool/str/float (AC4) | tested | `test_reducer_keeps_run_whose_workflow_id_is_not_an_integer` (parametrized ×5) |
| 24 | Under conftest's default isolation alone, no live `gh api` workflow-state lookup is made, and both failed runs still card | tested | `test_default_fixture_prevents_a_live_workflow_state_lookup` (asserts on the `_gh_api` transport) |
| 25 | `ci_units` is unchanged by the `ci_runs or []` collapse for all three inputs (`None` / `[]` / populated) | tested | `test_failed_runs_fetch_resolves_no_ci_cards` (None), `test_import_files_no_card_for_deleted_workflow` (populated), `test_github_triage_action_units.py::…owner_repo_none` (empty) |
| 26 | An unresolvable state is reported to stderr, so premise-drift is visible (D1) | tested | `test_github_workflow_api.py::test_unresolvable_state_is_reported_to_stderr` |
| 27 | The normal (resolved) path stays silent, so the diagnostic is not noise (D1) | tested | `test_github_workflow_api.py::test_resolved_state_is_silent` |
| 28 | Lookups are capped at 20, and the over-cap tail is KEPT, never dropped (D2) | tested | `test_state_lookups_are_capped_and_the_tail_is_kept` |
| 29 | A transport that RAISES is contained in the client itself, not only at the call site | tested | `test_github_workflow_api.py::test_transport_exception_is_contained` |
| 30 | Runs that cannot be looked up spend no lookup budget, so they cannot hide a deleted workflow behind them | tested | `test_unlookupable_runs_do_not_spend_the_lookup_budget` |

Rows 16 and 17 exist because their failure modes are invisible to every other
row. A reducer that looked up state for *every raw run* would still pass rows
1–15 while multiplying API calls; and a fetch built with `paginate=True` returns
`None`, silently disabling the filter, while all the mocked rows stay green.

## Alternatives considered

- **One `actions/workflows` list call, inferring deletion from absence.**
  This was the first draft, and the external plan review rejected it: absence
  only implies deletion if the listing is guaranteed to contain every
  `disabled_*` workflow, which probe 8 could not establish. Its failure
  direction is the dangerous one — suppressing actionable cards. It also
  carried the `--paginate` concatenation trap, truncation handling, and a
  silent 100-workflow ceiling, and cost one API call on every import versus
  zero on a healthy repo.
- **List first, per-id lookup only for absent ids** (hybrid). Rejected as
  strictly more machinery than per-id alone for a saving that only materialises
  when many *distinct* workflows fail at once — an already-catastrophic state in
  which three extra API calls are irrelevant.
- **Filter inside `ci_action_unit` instead of the reducer.** Rejected: the
  reducer's output is what `current_keys` is built from, so filtering later
  would emit nothing but *also* leave the key in the current set, defeating the
  auto-resolve loop-closing above.
- **Drop the run when the workflow file is missing from the working tree.**
  Rejected: the importer runs against `origin`'s state and a local checkout may
  be on any branch; the code host's own lifecycle state is the authority.
- **Gate CI emission on the state fetch succeeding** (fail-closed, mirroring
  `both_security_feeds_ok`). Rejected: that rule exists because a partial
  security fetch would freeze a payload *claiming* "0 alerts" — a falsehood.
  Here the un-filtered card is still true for every live workflow; only the
  deleted case is wrong. Fail-closed would trade one stale card for total
  blindness to real CI breakage during any API blip.

## Verification (medium+)

- **Surface:** `cli`
- **Runner command:**
  `uv run --extra dev pytest shared/tests/test_github_triage_workflow_state.py shared/tests/test_github_workflow_api.py shared/tests/test_github_triage_workflow_state_import.py shared/tests/test_github_triage.py shared/tests/test_github_triage_action_units.py shared/tests/test_github_triage_pr_ci.py -q`
- **Evidence path:** `.shipwright/compliance/evidence/`
- **Justification (surface=none):** n/a — the importer is a CLI-invoked
  producer and is executed directly.
