# Iterate Spec — events.jsonl ships via the iterate PR (worktree-committed)

- **Run ID:** `iterate-2026-05-29-events-jsonl-worktree-commit`
- **Intent:** BUG (audit-log / compliance-integrity)
- **Complexity:** medium (overrides classifier's keyword-only "trivial" — touches the
  foundational events-log SSoT resolver, is cross-cutting, and trips `touches_io_boundary`)
- **Spec impact:** NONE — no FR is added/modified/removed. This is tooling/compliance
  plumbing. `change_type=tooling`, justified below.
- **Risk flags:** `touches_io_boundary` (shipwright_events.jsonl is the IO boundary;
  JSON append + read round-trip). → Boundary Probe + round-trip test + Confidence
  Calibration are enforced.

## Problem (root cause, empirically reproduced)

In a worktree-based iterate, `finalize_iterate.py` (F5b) records the `work_completed`
event by calling `record_event.append_event` → `events_log.resolve_events_path()`, which
redirects the write to the **MAIN repo** via `git rev-parse --git-common-dir`. Reproduced
from the run worktree:

```
resolve_main_repo_root(worktree) = C:\01_Development\shipwright
resolve_events_path(worktree)    = C:\01_Development\shipwright\shipwright_events.jsonl   # MAIN tree
```

F6 commits inside the worktree with an explicit per-path `git add` list that **excludes**
`shipwright_events.jsonl`. Net: the event lands as an **uncommitted line in the main
tree**, never enters the iterate PR, and needs a manual `chore(events)` backfill (F7/F7b)
to persist. Because `events.jsonl` is **tracked** (`.gitignore` line 70:
`!/shipwright_events.jsonl`), that orphaned line shows as `M shipwright_events.jsonl` at
the start of essentially every session, and a `git reset --hard` silently wipes it
(incident 2026-05-22, recovery PR #70).

The main-tree redirect is *deliberate* — it was built to stop a worktree-local copy from
being discarded by `git worktree remove`. It is wired into four places:
`events_log.resolve_events_path`, the compliance parity copy
(`collectors/change_history.py::_resolve_events_path`), the leak-guard exemption
(`worktree_isolation._MAIN_TREE_WRITE_EXEMPT`), and the F7b seal
(`commit_event_followup.py`). The redirect is wrong for today's flow: the worktree commit
is shipped via the PR and merged to `main`, so the event would NOT be lost — it would ride
the PR like every other artifact.

## Chosen fix — Option A (scoped): events.jsonl is a per-tree, PR-committed artifact

Flip `resolve_events_path` (and its parity copy) so the event log resolves to
`project_root / EVENT_FILE` **literally**. In a plain checkout this is unchanged
(`resolve_main_repo_root == project_root`); only the worktree case changes — which is
exactly the bug. F6 then stages `shipwright_events.jsonl` and it ships in the PR.

**SHA-ordering decision (user-approved scope):** F6.5 `attach-commit` patches the commit
SHA into the event *after* F6 — under the new model that would re-dirty the committed
file. We therefore **skip the in-place SHA patch for the worktree flow** and ship the
event with `commit=""`. The commit↔run linkage is preserved by the `Run-ID:` commit footer
and the event's `adr_id == run_id`; all consumers already tolerate `commit=""` (they render
`—` / `(assigned post-merge)`). `attach_commit` is retained for legacy non-worktree callers.

`resolve_main_repo_root` is **left unchanged** — decision-drops (`write_decision_drop.py`,
`aggregate_decisions.py`) and the verifier's decision-drop dir lookup still resolve to the
main repo (those are gitignored staging, consumed on `main`).

### Explicitly OUT of scope (would push to large; documented as follow-ups)
- Changing whether `events.jsonl` is tracked (Option C).
- Reworking `attach_commit` beyond "skip in the worktree flow".
- Concurrent-iterate merge-conflict handling on the append-only log (low risk for
  sequential iterates — the normal case; noted as a known limitation).
- **Fully removing** the leak-guard `_MAIN_TREE_WRITE_EXEMPT` (fail-closed on any
  main-tree events write). AC2 is met by the resolver fix alone (the iterate no longer
  writes to main); removing the exemption risks false-positives against critical isolation
  infra, so this iterate only corrects its now-misleading comment.

## Acceptance criteria
- **AC1** — After a worktree iterate's F6 commit, `HEAD:shipwright_events.jsonl` (in the
  merged result) contains the `work_completed` event for that `run_id`.
- **AC2** — The main tree's `shipwright_events.jsonl` is clean (`git status` shows no `M`)
  after finalization — no orphaned uncommitted line.
- **AC3** — No separate `chore(events)` backfill commit is required for a normal worktree
  iterate.
- **AC4** — `verify_iterate_finalization.py` "events.jsonl has commit" check is tightened
  to assert the event is in a COMMIT (HEAD blob), not just the working copy — when the log
  is tracked. Gitignored/untracked repos keep working-copy-sufficient behavior (no regression).

## Affected files
**Code**
- `shared/scripts/lib/events_log.py` — `resolve_events_path` → literal; rewrite docstrings.
  `resolve_main_repo_root` unchanged.
- `plugins/shipwright-compliance/scripts/lib/collectors/change_history.py` —
  `_resolve_events_path` → literal; fix docstring.
- `shared/scripts/tools/record_event.py` — docstrings only (read_events / append_event /
  attach_commit_to_event no longer claim "main repo so it survives worktree remove").
- `shared/scripts/tools/verifiers/iterate_checks.py` — `check_events_has_commit` AC4
  committed-assertion (+ helper); docstring updates.
- `shared/scripts/lib/worktree_isolation.py` — correct the `_MAIN_TREE_WRITE_EXEMPT`
  comment (no behavior change).

**Docs / SKILL**
- `plugins/shipwright-iterate/skills/iterate/references/{F5b,F6,F6.5,F7,F7b}.md`
- `plugins/shipwright-iterate/skills/iterate/SKILL.md` (F-index one-liners + "Order matters" note)
- `docs/hooks-and-pipeline.md` (artifact write matrix: events.jsonl now per-tree, staged at F6)
- `docs/guide.md` (if it documents the finalization/events flow)

**Tests (TDD)**
- `shared/tests/test_events_log.py` — invert worktree resolution tests; repoint
  git-failure tests (resolve_events_path is now git-independent).
- `shared/tests/test_events_log_ssot.py` — update rationale prose (invariant unchanged).
- `integration-tests/test_events_log_parity.py` — invert worktree parity target
  (parity preserved: both → worktree-local).
- `plugins/shipwright-compliance/tests/test_data_collector.py` — invert
  `test_worktree_reads_main_repo_event_log` to the per-tree model.
- `shared/tests/test_verify_iterate_finalization.py` — new AC4 cases (committed vs
  working-copy-only vs gitignored).
- New: `append_event` from a worktree lands in the worktree copy, not main (round-trip /
  boundary probe).
- Regression guard (no change expected): `test_decision_drop_ssot.py`,
  `test_write_decision_drop.py`, `test_check_iterate_isolation.py`,
  `test_commit_event_followup.py` stay green (resolve_main_repo_root / leak-guard / F7b
  behavior unchanged).

## Known limitations & follow-ups (external-review-surfaced, 2026-05-29)
- **Merge conflicts on the append-only log.** events.jsonl is now a per-branch
  append-only artifact, so two concurrent iterate PRs conflict at EOF. Git inserts
  `<<<<<<<` markers, but the event readers are **corrupt-line-tolerant** (they skip
  non-JSON lines), so a bad merge degrades to *dropped* events, not a crashed parser.
  Recovery: `uv run shared/scripts/tools/validate_event_log.py --project-root .`.
  *Follow-up:* a pre-commit / CI "every line is valid JSON" guard on events.jsonl.
- **Abandoned-worktree events are no longer persisted.** Under the old main-tree
  model, an abandoned iterate's events survived in main. Now they live only in the
  discarded worktree. Acceptable: `work_completed` denotes *completed* work, and an
  abandoned iterate completed none — so losing its (never-emitted-as-complete) event
  is correct, not data loss. Documented so it isn't a surprise.
- **`commit=""` on worktree-flow events.** Consumers tolerate it (render `—` /
  `(assigned post-merge)`); linkage is via the `Run-ID:` footer + `adr_id`.
  *Follow-up:* an optional post-merge GitHub Action could backfill the merge SHA into
  `main`'s events.jsonl to keep the log self-contained. The F11 check messaging
  ("events.jsonl has commit") could be renamed to "…is committed to HEAD" for clarity.
- **Leak-guard exemption fully retained** (comment-corrected only). *Follow-up:*
  remove the `_MAIN_TREE_WRITE_EXEMPT` EVENT_FILE entry to fail-closed on any
  main-tree events write during an iterate, once the legacy out-of-band F7/F7b path
  is confirmed unused in CI.

## Dogfood
This iterate runs in a worktree, so its OWN finalization (F5b→F6→F11) exercises the fix
end-to-end: the `work_completed` event for this run_id must land in the worktree copy, be
staged at F6, ship in the PR, and pass the tightened F11 verifier — with the main tree
staying clean.

## Confidence Calibration
- **Boundaries touched:** `shipwright_events.jsonl` (tracked JSONL append-only log);
  event-log path resolution (`events_log.resolve_events_path` + compliance parity
  `_resolve_events_path`); F11 verifier read of the committed HEAD blob (`git show`).
- **Empirical probes run:**
  - Reproduced root cause: `resolve_events_path(worktree)` → MAIN tree before fix
    (real linked worktree, not a mock). After fix → worktree-local
    (`test_worktree_resolves_to_worktree_local`, real `git worktree`).
  - Producer→consumer round-trip on a real worktree: `append_event` lands in the
    worktree copy, `read_events` reads it back, `attach_commit_to_event` patches in
    place; main tree never written (`TestWorktreeEventLogRoundTrip`,
    `test_boundary_roundtrip_worktree_producer_to_verifier`).
  - AC4 verifier on real git repos: tracked+uncommitted → FAIL; tracked+committed →
    PASS; untracked/gitignored → working-copy-sufficient (no regression). All on
    Windows (this session).
  - Parity preserved: shared resolver == compliance resolver, both → worktree-local
    (`test_events_log_parity.py`). Compliance reads the worktree copy even with a
    DECOY event in main (`test_worktree_reads_its_own_event_log`).
  - Non-regression of the retained primitive: `resolve_main_repo_root` unchanged →
    decision-drop SSoT + F7b seal tests stay green (`test_decision_drop_ssot.py`,
    `test_commit_event_followup.py`, `test_check_iterate_isolation.py`).
  - Full suites: shared/tests 2449 passed (1 pre-existing unrelated fail), compliance
    559 passed, integration 136 passed.
  - **Decisive probe (dogfood):** this iterate's own F5b records its `work_completed`
    event into THIS worktree's events.jsonl; F6 stages it; F11 verifier confirms it's
    committed; main tree stays clean. (Run live in finalization.)
- **Edge cases NOT probed + why acceptable:**
  - Nested-project layout (events.jsonl under a sub-path) for the AC4 `git show
    HEAD:<rel>` — used `ls-files --full-name` so a sub-path resolves correctly, but
    didn't build a nested fixture. Iterate worktrees are top-level and the log sits at
    the worktree root, so this path isn't exercised in practice. Low risk.
  - Concurrent-iterate merge conflict on the append-only log — NOT resolved by design
    (documented tradeoff). `iterate_history` + `CHANGELOG.md` were refactored to
    file-per-iterate / drop-dirs precisely to avoid this; events.jsonl is now the one
    per-branch append-only file. Acceptable for the normal sequential-iterate case;
    flagged as a known limitation + follow-up.
- **Confidence-pattern check (asymptote):** No yes-then-bug oscillation — the fix
  passed the full suites on the first complete run; every failure encountered was
  traced to pre-existing state (confirmed by re-running on the main tree), not the
  change. Residual uncertainty is concentrated in the live dogfood (F5b→F6→F11),
  which I run as the final confirming probe rather than asserting confidence abstractly.
