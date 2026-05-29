# ADR-092: Bloat exception — events-jsonl-worktree-commit verifier + test growth

<!-- Grants a bloat-baseline exception for the files grown by
     iterate-2026-05-29-events-jsonl-worktree-commit. Referenced from
     shipwright_bloat_baseline.json (state="exception", adr="ADR-092"). -->

- **Status:** accepted
- **Date:** 2026-05-29
- **Re-Review-Date:** 2026-08-29 _(3 months out — reviewer checks whether
  `iterate_checks.py` can be split into a `verifiers/iterate/` package and
  whether the grown test suites can shed any now-redundant cases)_
- **Incident Reference:** iterate-2026-05-29-events-jsonl-worktree-commit —
  making `shipwright_events.jsonl` a per-tree, PR-committed artifact (the AC4
  committed-event assertion + the test inversions/additions for the per-tree
  model crossed six already-grandfathered baselines).

## Context

The iterate flipped the event-log resolver to per-tree and added a fail-closed
F11 check that a *tracked* event log's `work_completed` event is in the
committed HEAD blob (not just the working copy). Six files that were ALREADY
grandfathered over the 300-LOC limit grew past their `current` baselines:

| Path | baseline → new | Δ | kind |
|---|---|---|---|
| `shared/scripts/tools/verifiers/iterate_checks.py` | 803 → 881 | +78 | production (AC4 logic) |
| `shared/tests/test_verify_iterate_finalization.py` | 1143 → 1196 | +53 | test coverage |
| `shared/tests/test_record_event.py` | 450 → 501 | +51 | test coverage |
| `plugins/shipwright-compliance/tests/test_data_collector.py` | 1214 → 1224 | +10 | test coverage |
| `shared/scripts/tools/tests/test_record_event.py` | 783 → 791 | +8 | test coverage |
| `plugins/shipwright-compliance/tests/test_rtm_generator.py` | 534 → 535 | +1 | test coverage |

Two other files grown by the iterate (`worktree_isolation.py`,
`record_event.py`) were prose-only and were trimmed back UNDER baseline — no
exception needed for them (remediation #1, preferred).

## Ousterhout Argument

`iterate_checks.py` is a **deep module**: its public interface is narrow —
`run_all_checks(project_root, run_id, commit)` and
`run_cross_artifact_checks(...)` — behind which sits the substantial,
cohesive family of iterate-finalization invariants (events-has-commit, ADR
present, changelog drop, spec-impact, surface-verification, dashboard/handoff
freshness). AC4 added ONE more fail-closed check plus two private helpers
(`_event_committed_in_head`, `_committed_blob_has_event`). Splitting the file
by line count would scatter a single conceptual unit ("what F11 verifies")
across files and expose the private `git show`/`_find_work_event_*` helpers
that are intentionally encapsulated. The interface stays narrow; the body grew
because the contract it enforces grew.

The five test files are not modules — the deep-module test doesn't apply. Their
size tracks the **surface under test**: the per-tree model changed how the
resolver, the producer (`record_event`), the verifier, and the compliance
collectors behave, so the suites that pin those behaviors grew by exactly the
new/changed cases (inverted worktree assertions, AC4 tracked/uncommitted/
untracked branches, a worktree producer→verifier round-trip boundary probe,
and a decoy-event "reads its own log" case). The growth is new coverage, not
duplication.

## YAGNI Check

- `iterate_checks.py` +78: the AC4 committed-assertion is needed **today** — it
  is the structural guard that makes this very iterate's fix enforceable (F6
  forgetting to stage events.jsonl must fail closed). Not speculative.
- Test growth: every added case maps to a behavior this iterate changed. None
  is "might need next quarter" — they pin the per-tree model that ships now.
  Removing any would leave a changed branch unverified.

## Chesterton-Fence Check

The six files are grandfathered, not freshly bloated — their large size
predates this iterate (established by Campaign B test-evidence work and the
F11-verifier accretion). Git history shows the verifier and these suites have
grown by deliberate per-iterate accretion, each addition pinned by tests. The
fence (one cohesive iterate-verifier module + its co-located suites) stands for
a documented reason: single-source the F11 contract and its evidence. The
exception holds; the re-review will reconsider a `verifiers/iterate/` split.

## Decision

Bump `current` to the measured values in the table above; set each entry's
`state="exception"`, `adr="ADR-092"`. Retirement plan: at Re-Review (2026-08-29)
evaluate splitting `iterate_checks.py` into a `verifiers/iterate/` package
(events/spec-impact/surface families) — which would also let the test suites
split along the same seam.

## Consequences

Anyone editing these six files now operates against the raised limits. The
anti-ratchet gate (state-agnostic) passes because `measured == current`. The
Group H detective audit will record the exception (adr-linked). If the
exception outlives the Re-Review-Date without a split, the files keep
accreting against an ever-higher ceiling — the re-review is the backstop.

## Rejected alternatives

- **Leave at old limit and split now.** Splitting `iterate_checks.py` mid
  bug-fix iterate would balloon a contained medium iterate into a refactor
  (the user explicitly scoped this as a contained fix, escalating to a plan if
  it grew). Deferred to the re-review with a concrete seam noted.
- **Trim the tests to fit.** Removing test cases to dodge the gate is the exact
  rationalization the anti-ratchet block refuses ("tests don't count — they
  count"). The added cases each verify a changed branch; deleting them would
  ship the per-tree model under-verified.
- **Shallow refactor (extract helpers to a new file).** Moving
  `_event_committed_in_head` out would just relocate LOC and create a new
  cross-file import for one check — net complexity up, not down.

---

## External Sources Acknowledged

YAGNI Check + Chesterton-Fence Check headings adapted from obra/superpowers
`writing-plans` (MIT © Jesse Vincent) and addyosmani/agent-skills
`code-simplification` (MIT © Addy Osmani). Incident-Reference field follows the
pattern of the per-decision incident-reference convention in multica-ai/multica
`CLAUDE.md` (Apache-2.0 modified-with-hosting-restriction — pattern reusable).
