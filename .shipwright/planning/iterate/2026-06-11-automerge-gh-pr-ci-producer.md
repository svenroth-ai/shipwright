# Iterate Spec — `gh-pr-ci` producer (Automerge loop-closing)

- **Run ID:** `iterate-2026-06-11-automerge-gh-pr-ci-producer`
- **Intent:** FEATURE (new triage producer source) · **Complexity:** medium
- **Branch:** `iterate/automerge-gh-pr-ci-producer`
- **Governing spec:** `Spec/early-access-readiness-plan.md` §B4.5 → *Loop-Closing: failed Hard-Gates → Triage* (Phase 1, MUST ship before `gh pr merge --auto` activation)
- **Risk flags:** `touches_io_boundary` (gh JSON → action-unit → `triage.jsonl`)

## Problem

The `github_triage` producer surfaces failed CI only on the **default branch**
(`gh-ci:{workflow_id}`). When auto-merge is armed (`gh pr merge --auto`) and a
hard-gate goes red on the **open PR**, the PR sits "armed but waiting" and no
one notices until the next manual look. Without triage visibility, auto-merge is
silently broken. We close the loop: failed hard-gates on **open PRs** become a
`gh-pr-ci:{pr_number}` action-unit in the triage inbox.

## Scope guard

Ships the **producer only**. Does **not** activate `gh pr merge --auto`
(that is a later B4.5 step). No reviewer-tier / OpenRouter work here.

## Acceptance Criteria

- **AC-1 — Emit.** For each OPEN PR with ≥1 failing hard-gate check, emit ONE
  action-unit `gh-pr-ci:{pr_number}` (severity `high`, kind `bug`), whose
  `launchPayload` starts with `/shipwright-iterate --type bug` and contains the
  PR URL + the failing check names. Dedup key carries **no** head_sha / workflow
  id (operator action is "fix PR #N").
- **AC-2 — Failing set.** A check counts as failing iff `status == "completed"`
  AND `conclusion ∈ {failure, timed_out, startup_failure, cancelled,
  action_required}`. In-progress / queued / success / neutral / skipped never
  count. Names are de-duplicated and sorted (deterministic payload).
- **AC-3 — Symmetry (the MED-#1 lesson).** If `fetch_open_prs()` returns `None`
  (fetch failed) OR **any** per-PR check-runs fetch returns `None`, the entire
  PR-CI source is treated as a failed fetch this run: **no emit, no resolve**
  (`by_source["gh-pr-ci:"] == None`). A network blip must never mass-resolve.
- **AC-4 — Differentiated auto-resolve.** When the PR-CI fetch fully succeeded,
  an open `gh-pr-ci:{n}` item is dismissed when its PR left the failing set:
  - PR still open, no failing check → `reason="prChecksResolved"`
  - PR no longer open, merged → `reason="prMerged"`
  - PR no longer open, not merged → `reason="prClosed"` (also the fallback when
    the per-PR state fetch fails — the PR is provably gone from the open set)
- **AC-5 — Idempotent / frozen payload.** A second import with the same failing
  PR appends no duplicate; the first `launchPayload` is preserved.
- **AC-6 — Round-trip (touches_io_boundary).** A `gh-pr-ci` action-unit emitted
  by the consumer survives the write→read round-trip through `triage.jsonl`
  (`dedupKey`, `launchPayload`, `severity`, `kind` intact).
- **AC-7 — Docs + telemetry.** `docs/guide.md` action-units table and
  `docs/hooks-and-pipeline.md` SessionStart-producer prose name the new source;
  `import_findings` returns `by_source["gh-pr-ci:"]` (emit count | `None`).

## Design (placement decisions — confirmed with user)

- **New module `shared/scripts/github_pr_api.py`** (NOT `github_api.py`, which is
  already 392 LOC / grandfathered — adding there trips the anti-ratchet hard
  gate). Reuses `github_api._gh_api` for identical None-on-failure semantics.
  - `fetch_open_prs()` → `repos/{owner}/{repo}/pulls?state=open` (`None`/`[]`/list)
  - `fetch_pr_check_runs(head_sha)` → `commits/{sha}/check-runs` → `check_runs`
  - `fetch_pr_state(pr_number)` → `pulls/{n}` → `{state, merged}` (resolve only)
  - `_failing_check_names(check_runs)` → pure, sorted-unique failing names
  - `open_prs_with_failed_checks(prs)` → reduce to enriched PRs with ≥1 failing
    check; returns `None` if any per-PR fetch was `None` (symmetry).
- **`github_triage/producer.py`** — `PREFIX_PR_CI = "gh-pr-ci:"`; add to
  `_OWNED_PREFIXES`.
- **`github_triage/mappers.py`** — `pr_ci_action_unit(pr_info, *, owner_repo)`
  pure builder (owner_repo optional; dedup key is PR-number-based).
- **`github_triage/resolve.py`** — `resolve_pr_ci(...)` differentiated resolver
  (injected `pr_state_fetcher`). PREFIX_PR_CI is deliberately **excluded** from
  the generic `resolve_stale` resolvable set so resolution routes only here.
- **`github_triage/pr_ci.py`** (NEW) — `import_pr_ci_findings(project_root,
  owner_repo, *, append_fn)` consumer-side orchestration, so `consumer.py` stays
  ≤300 LOC (it's at 283; the new wiring is ~8 lines).
- **`github_triage/consumer.py`** — wire `import_pr_ci_findings` into
  `import_findings`; fold its counts into `appended`/`resolved`/`by_source`.
- **`github_triage/__init__.py`** — re-export `PREFIX_PR_CI`, `pr_ci_action_unit`.
- **`shared/tests/conftest.py`** — autouse fixture neutralises the live PR
  fetchers by default (existing consumer tests stay hermetic; gh substitutes
  `{owner}/{repo}` from cwd, so an un-stubbed fetch would hit the real repo).

## Confidence Calibration
- **Boundaries touched:** gh REST JSON (`pulls?state=open`,
  `commits/{sha}/check-runs?filter=latest`, `pulls/{n}`) → action-unit dict →
  `triage.jsonl` append/read.
- **Empirical probes run (all asserted in `test_github_triage_pr_ci.py`, 26 tests):**
  - fetch parsing: `_gh_api` → list/None for `fetch_open_prs`; object→`check_runs`
    extraction + **truncation guard** (`len < total_count → None`); `fetch_pr_state`
    field extraction → finding: None-on-failure contract holds on every leg.
  - query safety: `check-runs` request carries `filter=latest`, `pulls` carries
    `state=open` → finding: no superseded re-run can linger as a stale failure.
  - failing-set: 5 non-passing terminal conclusions counted; success/neutral/
    skipped/in-progress/queued excluded; names sorted+deduped+sanitised → finding:
    deterministic payload, control chars stripped.
  - symmetry: `prs=None` and any per-PR `None` both poison the whole sweep (emit
    AND resolve) → finding: a blip yields `by_source=None`, existing item untouched.
  - differentiated resolve: prChecksResolved / prMerged / prClosed; unfetchable
    state keeps the item open → finding: no false `prClosed` guess.
  - round-trip: emitted unit survives write→read through `triage.jsonl` intact.
  - wiring: `import_findings` provably calls `github_pr_api.fetch_open_prs`
    (hermetic autouse stub can't hide a broken wire).
- **Test Completeness Ledger:** see the machine-readable `test_completeness` block
  in `shipwright_test_results.json` (`iterate_latest`). Every AC + refinement →
  `tested` with the citing test; **0 testable-but-untested**. Two rows were
  un-tested at first pass (real `fetch_pr_state`, `filter=latest` query) and
  converted to `tested` rather than excused.
- **Confidence-pattern check:** asymptote (depth) — symmetry + truncation + resolve
  edge cases each have a dedicated test, not just the happy path. Coverage (breadth)
  — every public function in `github_pr_api` + `pr_ci_action_unit` + `resolve_pr_ci`
  + the consumer wiring is exercised; the only un-unit-tested seam is the live `gh`
  subprocess inside `github_api._gh_api` (reused, already covered) — `untestable`
  reason `requires-external-nondeterministic-service`, mocked at the `_gh_api` seam.
