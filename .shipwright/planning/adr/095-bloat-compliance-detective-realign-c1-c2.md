# ADR-095: Bloat exception — compliance detective-audit files raised for C1/C2 (Run-ID provenance + A5 invocation)

- **Status:** accepted
- **Date:** 2026-06-02
- **Re-Review-Date:** 2026-09-02 _(check whether the detective-audit check
  groups / their test suites should be split per-check, or the exception
  retired — candidate for the B/C bloat-cleanup campaigns)_
- **Incident Reference:** campaign `2026-06-02-compliance-detective-realign`
  (anchor triage `trg-5eb9b125`), sub-iterates **C1** (B7 `Run-ID:`↔`adr_id`
  linkage + Group E `chore(release)` snapshot recognition) and **C2** (A5
  invocation resilience: `group_a5` SKIP-not-FAIL on missing PyYAML +
  `uv run --with pyyaml` on the iterate/changelog Stop hooks). First crossing
  surfaced when the fixes + their regression tests pushed six already-oversize
  compliance-audit files past their baseline.

## Context

The detective audit drifted out of sync with two framework redesigns
(events.jsonl worktree-commit 2026-05-29; the changelog/release producer),
producing recurring false-positive compliance findings in both the monorepo
(Group E) and shipwright-webui (B7/A5.0). C1/C2 fix the root causes. The
growth, per file:

Source:
- `group_b.py` 529 → 545 (+16): B7 now also recognizes a commit covered via its
  `Run-ID:` footer ↔ an event's `adr_id` (the 2026-05-29 linkage), with the
  commit-field SHA match retained as fallback.
- `audit_staleness.py` 347 → 365 (+18): `find_snapshot_commit` now recognizes
  `chore(release)` snapshots (the changelog phase regenerates the tracked MDs
  without a `Run-ID:` trailer), via `--fixed-strings` + a second `--grep`.
- `group_a5.py` 598 → 608 (+10): a missing PyYAML degrades A5.0 to SKIP (env
  problem, not a compliance violation) instead of a phantom FAIL.

Tests:
- `test_audit_group_b.py` 622 → 676 (+54): two B7 Run-ID-linkage cases + a
  `commit_run_id` unit test.
- `test_audit_snapshot.py` 464 → 509 (+45): a `chore(release)` recognition case
  + a green-after-release staleness case (the `trg-8747213b` root cause).
- `test_audit_group_a5.py` 699 → 702 (+3): the pre-existing pyyaml-missing test
  updated from asserting FAIL to asserting SKIP (contract change, not weakening).

The `git_log_scan.py` helper that carries the new `commit_run_id` parser stayed
unbaselined at 216 LOC (room under the 300 limit), so the heaviest new logic did
NOT land in a baselined file.

## Ousterhout Argument

Each file is a **deep module**: a narrow interface over substantial behaviour.
`group_b.py`/`group_a5.py`/`audit_staleness.py` each expose one `run()` (or
`find_snapshot_commit`/`check_staleness`) over a cohesive group of detective
checks (B-group config↔event coherence; A5 security-workflow conformance;
Group E snapshot provenance). The test files are the matching per-group suites
with shared fixtures. Splitting any of them to dodge a +10…+54 increment would
scatter related checks/fixtures and expose the per-check internals the group
interface exists to encapsulate — making the audit harder to reason about, not
easier. The honest deep-module test holds.

## YAGNI Check

Every added line is needed **today**: each is part of a fix for a *live*,
reproduced false-positive (Group E re-flagging every release; B7 mis-flagging
real iterate commits in webui; A5.0 phantom-failing on non-Python adopt repos).
The regression tests assert exactly those behaviours. No speculative scope —
the deferred B7 commit-type-exclusion decision is explicitly NOT in these files.

## Chesterton-Fence Check

These files are large because the detective audit covers many independent drift
classes (groups A–H), each a cohesive sub-suite, with shared test fixtures
centralising git/event setup (DRY). git history shows group-by-group growth
under that same structure (e.g. iterate-2026-05-27 widened Group E's doc set;
ADR-090 already granted audit_staleness/test_audit_snapshot exceptions). The
fence stands for a documented reason; extending it for a real correctness fix is
consistent with it, not a violation.

## Decision

Raise the six entries to their post-change measurements (`state: exception`,
`adr: ADR-095`):

| File | new current |
|---|---|
| `plugins/shipwright-compliance/scripts/audit/group_b.py` | 545 |
| `plugins/shipwright-compliance/scripts/audit/audit_staleness.py` | 365 |
| `plugins/shipwright-compliance/scripts/audit/group_a5.py` | 608 |
| `plugins/shipwright-compliance/tests/test_audit_group_b.py` | 676 |
| `plugins/shipwright-compliance/tests/test_audit_snapshot.py` | 509 |
| `plugins/shipwright-compliance/tests/test_audit_group_a5.py` | 702 |

`audit_staleness.py` + `test_audit_snapshot.py` were already exception under
ADR-090; their `adr` is re-pointed to ADR-095 (the controlling reason for the
current measurement). Retire when the detective-audit groups / suites are split
per-check (tracked at the Re-Review-Date / the B/C bloat campaigns).

## Consequences

The six files now operate against the new limits; further additions must stay
within them or bump again with justification. No new file was promoted beyond
what the fix required, and the heaviest new logic landed in the unbaselined
`git_log_scan.py`. The C3/C4 sub-iterates of the same campaign will touch
`group_d.py` / `record_event.py` / `finalize_iterate.py` — out of scope here.

## Rejected alternatives

- **Split the check groups / test suites now** — disproportionate: these are
  pre-existing 500–700 LOC grandfathered/exception files; C1/C2 add small
  functional growth + required regression tests, not a structural problem.
  Splitting churns well-tested modules mid-fix and belongs to the dedicated
  bloat-cleanup campaigns, not a correctness iterate.
- **Trim comments to dodge the bump** — theatre: shaving explanatory "why"
  comments off 500–700 LOC files to hit an arbitrary number degrades clarity
  without addressing the (legitimate) growth. The conscious ADR + baseline
  update IS the check.
- **Skip the regression tests** — unacceptable: leaves the exact false-positives
  C1/C2 fix without coverage; a future change could silently reintroduce them.

---

## External Sources Acknowledged

The YAGNI Check + Chesterton-Fence Check headings follow the bloat-exception
template, adapted from obra/superpowers `writing-plans` (MIT © Jesse Vincent)
and addyosmani/agent-skills `code-simplification` (MIT © Addy Osmani). The
Incident-Reference field follows the pattern of multica-ai/multica `CLAUDE.md`
(Apache-2.0 modified-with-hosting-restriction — pattern reused, text not).
