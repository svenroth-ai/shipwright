# Mini-Plan — `iterate-2026-08-01-ci-card-deleted-workflow`

Spec: [`iterate-2026-08-01-ci-card-deleted-workflow.md`](iterate-2026-08-01-ci-card-deleted-workflow.md)

## Chosen approach

Carry the workflow lifecycle state across the `github_workflow_api` → `mappers`
boundary, where it was never fetched, and let the reducer drop runs whose
workflow the code host reports as `deleted`. The state is **read per failing
workflow**, never inferred from a listing.

| # | File | Change |
|---|---|---|
| 1 | `shared/scripts/github_workflow_api.py` (**new module**) | `fetch_workflow_state(workflow_id) -> str \| None` — one `actions/workflows/{id}` call; `None` on failure / 404 / malformed. Not added to `github_api.py`: that file is `grandfathered` at 321/300 in the bloat baseline, so the anti-ratchet hook would refuse the commit. `github_pr_api.py` is the precedent |
| 2 | `shared/scripts/github_triage/mappers.py` | `latest_failed_ci_runs(runs, *, workflow_state_fetcher=None)` + `_workflow_is_gone` predicate; policy constant `_GONE_WORKFLOW_STATES = {"deleted"}` beside the existing `_FAILED_CONCLUSIONS` |
| 3 | `shared/scripts/github_triage/consumer.py` | pass `github_workflow_api.fetch_workflow_state` into the reducer |
| 4 | `..._workflow_state.py` (reducer) + `test_github_workflow_api.py` (client) + `..._workflow_state_import.py` (end-to-end) | **new** (3 files) — AC1–AC11, 30 ledger rows; split by subject, each inside the 300-LOC budget |
| 5 | `shared/scripts/github_triage/__init__.py` | docstring only — record the CI filter in the package contract |
| 6 | `shared/tests/conftest.py` | stop unrelated consumer tests spawning a live `gh api` lookup. Folded into the sibling `_isolate_github_pr_api`, renamed `_isolate_live_gh_clients`: the two do the identical job for the identical reason, and merging them also kept the file inside its 320 baseline instead of ratcheting it |
| 7 | `.shipwright/agent_docs/architecture.md` | record the new client in the triage-producer inventory |

**Layering:** `github_workflow_api` returns the raw state string and makes no judgement;
`mappers` owns *which states count as gone*, next to the existing conclusion
policy. The API client stays a dumb client, and `mappers.py` keeps its "no I/O"
docstring property because the fetcher is injected — the same shape
`resolve.resolve_pr_ci(..., pr_state_fetcher=...)` already uses for the
identical problem.

**Ordering inside the reducer matters:** reduce to latest-failed-per-workflow
**first**, then look up state only for the survivors (AC9). Filtering earlier
would issue one API call per raw run — up to 100 per import.

**TDD order (Path C step 4 → 5):** write `test_drops_run_for_deleted_workflow`
first against the real run object, watch it fail, then implement 1 → 2 → 3.

## Why not the tidier variant

A single `actions/workflows?per_page=100` call inferring deletion from absence
is one call instead of N and was the first draft. The external plan review
rejected it: absence only means deletion if the listing is guaranteed to carry
every `disabled_*` state, which the probe never established — and its failure
direction is the dangerous one, suppressing actionable cards (AC3). Per-id also
turns out *cheaper* in the common case (zero calls on a healthy repo vs one
every import) and drops the `--paginate` concatenation trap, the truncation
branch, and the silent 100-workflow ceiling. Full reasoning in the spec's
"Why per-id, and not a workflow list".

## Blast radius

- **One production call site** (`consumer.py:76`). The reducer has no other
  caller anywhere in the monorepo — but note that the original grep behind this
  bullet excluded tests, and that is exactly where the consequence landed:
  Stage 1 found two existing suites driving this call site with no stub for the
  new client. Closed in `conftest.py`; recorded below.
- `latest_failed_ci_runs` is **re-exported public surface**
  (`github_triage.__init__.__all__`), so the new parameter is keyword-only with
  a default and every existing call keeps working (AC6).
- **The dangerous direction is over-filtering**, not under-filtering: dropping a
  live workflow's run silently hides real CI breakage. Every unknown — fetch
  failure, 404, malformed payload, raising fetcher, missing `workflow_id` —
  therefore resolves to *keep*, per workflow rather than globally (AC5).
- A failed lookup keeps the run, so its key stays in `current_keys` and the open
  card is **not** resolved — a fetch fault can never read as "finding cleared"
  (AC8), matching FR-01.14's "an import that failed closes nothing".
- No schema, no migration, no artifact shape, no hook, no workflow file.
  `.shipwright/triage.jsonl` gains no field; existing cards are unaffected
  except that a stale `gh-ci:{deleted}` one now auto-dismisses through the
  existing `resolve_stale` sweep.
- API cost: **zero** extra calls when no workflow is failing; one per distinct
  failing workflow otherwise (import is throttled by `state.is_due`).

## Verification

`uv run --extra dev pytest shared/tests/test_github_triage_workflow_state.py shared/tests/test_github_workflow_api.py shared/tests/test_github_triage_workflow_state_import.py shared/tests/test_github_triage.py shared/tests/test_github_triage_action_units.py shared/tests/test_github_triage_pr_ci.py -q`
plus the full `shared/tests` root at F0, and the real-run repro re-run against
the patched reducer to confirm the incident no longer reproduces.

## Revised after the review cascade

**Stage 1 (spec-reviewer) — REJECT, then fixed and re-run.** It confirmed the
critical safety property by audit (`_workflow_is_gone` has exactly one `True`
exit; every unknown path keeps the run) and all 11 ACs, then blocked on three
findings:

- **MED-1, a real defect this change introduced.** Wiring a live fetcher into
  `import_findings` meant two *existing* tests
  (`test_github_triage_action_units.py:313` and `:367`) would spawn a real
  `gh api` subprocess against whatever repo the cwd resolved to — the exact
  hazard `conftest.py`'s `_isolate_github_pr_api` was written to close for the
  sibling client. It did not turn the suite red (workflow id `1` 404s → `None`
  → keep), which is precisely why it needed catching before it became a flake.
  Fixed with autouse isolation defaulting to the fail-open value, so every
  pre-existing expectation stays byte-identical. The new unit suite binds the
  real function at import time instead of being stubbed, since it is the suite
  that tests the client.
- **MED-2 —** the delivered producer (`github_workflow_api.py`) diverged from
  the one this plan named (`github_api.py`), recorded nowhere but the code. The
  code's choice stands (anti-ratchet makes the literal instruction unlandable);
  the spec, this plan and `architecture.md` now say so.
- **MED-3 —** the recorded verification command omitted the file that is the
  sole evidence for AC7/AC8/AC10. Corrected.

LOW-1/2/3 also folded in: the AC7 test now asserts `reason="githubResolved"`
(not merely `dismissed`), and the case-insensitive match plus the reducer's own
id guard are pinned by ledger rows 22-23 instead of being incidental.

**Stage 2 (code-reviewer) — REQUEST_CHANGES, then APPROVE.** It found that this
diff pushed `consumer.py` from exactly 300 to 303 with no baseline entry — a
*new crossing*, which `bloat_gate_on_stop.py` blocks, not merely a post-merge
detective finding as CLAUDE.md's wording had led me to assume. Fixed in the
code rather than by buying a baseline exemption: the readable call site was
restored and `ci_units`' five-line conditional became one line
(`ci_runs or []`, behaviourally identical since both `None` and `[]` mean "no
units"; the distinction that matters lives in `fetch_succeeded`). It also killed
a `# noqa: E501` whose justification was false twice over — E501 is not in the
ruff `select` list, and the file was over budget anyway.

**Stage 3 (doubt-reviewer) — 4 advisory doubts, all answered.** Two accepted
(a stderr diagnostic so premise-drift is visible; `_MAX_STATE_LOOKUPS = 20` so
an uncapped lookup phase cannot starve the hook budget and kill the whole
import), one declined with reasoning (the `githubResolved` label — the
"should this have been deleted?" question is owned by the CI-supply-chain
gate), one accepted (`raising=False` dropped from the isolation stubs). Full
dispositions in the spec.

**External CODE review — `revise`, then `approve` ("ship as-is").** Two real
findings, both accepted: the client did not contain a raising transport (its
contract promises `None`, and a direct caller does not inherit the reducer's
guard), and the lookup cap counted *runs* rather than *lookups*, so a batch of
malformed ids could exhaust the budget having fetched nothing and hide a
genuinely deleted workflow behind them. gemini's "stderr is spam" was partly
taken: silencing the `None` case would silence exactly the drift D1 exists to
surface, so the line stays but now names transport-fault vs drifted-payload.

**Net effect of the cascade.** Every stage changed the code. The plan review
replaced the whole detection strategy; Stage 1 caught a live-API leak into two
existing suites; Stage 2 caught a bloat crossing that would have blocked the
Stop gate; Stage 3 bought an observability line and a lookup cap; the external
code review fixed an escaping exception and a mis-counted budget. None of it
was cosmetic.
