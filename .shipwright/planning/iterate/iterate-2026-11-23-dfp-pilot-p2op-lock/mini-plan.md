# Mini-plan: stop-2 lock of the changelog pilot (P2-op)

Run: `iterate-2026-11-23-dfp-pilot-p2op-lock` · type change · complexity small (classifier + diff re-check; no risk flag) ·
Spec Impact NONE (test tooling and campaign docs; no product behaviour, no skill text change) · brief:
`.shipwright/planning/campaigns/2026-10-25-dfp-pilot-changelog-BRIEF.md` §5 P2-op.

## Deliverables (the acceptance list the reviewers check against)

1. **Generic lock writer** `shared/testkit/golden_lock.py` (stdlib only, ADR-044) with a CLI (`--plugin`, default
   `shipwright-changelog`, or `--golden-dir`; `--repo-root`, `--spec`, `--check`, `--repin`). Writes
   `golden.lock.json` = `{"version":1,"files":{relpath: sha256}}` over every `*.trace.json` under the golden dir, every
   file the freeze test's `REQUIRED` names (read from its source by AST, never imported) and `golden_trace.py`; hashes
   are `golden_trace.file_sha256` (CRLF read as LF). Writes the promise lock `promise.lock.json` next to it =
   `{"version":1,"promises":{"path::test": {"acs":[...], "hash":...}}}` for every test of every `test_promise_*.py`,
   via `promise_lock.lock_entry` with the spec's AC-Move-Map and the golden `conftest.py` (the same inputs
   `test_promises_meta.py` uses). Deterministic and byte-stable (sorted keys, indent 2, LF, trailing newline). Refuses
   to change an existing lock without `--repin`. Unit tests in `shared/tests/test_golden_driver_freeze.py` (catalogued
   infrastructure file); a check test in `test_trace_freeze.py` fails when the promise lock is stale
   (`promise_lock.lock_problems`).
2. **Pinned prose copy**: `SKILL.md` and `references/*.md` of the changelog skill copied byte-exact to
   `plugins/shipwright-changelog/tests/golden/pinned_prose/` (suffix `.pin`, see decision below); `coverage.py` (P8b)
   reads the pin (`pinned_skill_lines()`), `test_coverage_checks.py` uses it; the copies, the promise lock and the
   writer + its test file are added to `REQUIRED`.
3. **Retag** `test_trace_freeze.py`: module `pytestmark` `covers("FR-01.09/AC14")` -> `covers_none("tooling")` (the
   file is in `shared/config/infra_test_paths.json` at the merge-base, #1094). Other behaviour kept.
4. **Lock written last**: `golden.lock.json`, `promise.lock.json`, `approved_deltas.json` = `[]` (the full-run baseline
   found no trace change).
5. **Campaign docs**: FULLRUN-REPORT and SECOND-PASS copied in; BRIEF gets unit P4b, A2/A3/A6 into P3, A9/B1/B4 into
   P4, A7 deferred, B3/B5/B6/C3/C4 dropped, C1/C2/C5 kept, P2-op marked done; short notes in FINDINGS and LEARNINGS;
   one paragraph in `docs/hooks-and-pipeline.md` (the testkit section).

## Decisions

- **`.pin` suffix for the pinned copies** (content byte-exact, name not): a file named `SKILL.md` anywhere is a
  runtime prompt for the bloat gate (400-line limit; the changelog `SKILL.md` has 440 lines, an ADR exception for its
  live path only), so a copy would be a new unbaselined crossing (Group H1). Repository-wide prose scanners
  (`integration-tests/*` rglob `plugins/**/*.md`) would also read a copy as live skill text, and a later prose rule
  would then need an approved delta on a frozen copy. `.pin` keeps the copies inert. Alternative rejected: keep the
  names and add a bloat-baseline exception (needs an ADR number an iterate cannot assign).
- **`REQUIRED` stays a literal tuple** read by AST, so the writer serves any plugin without importing its test module.
- **The promise-lock check lives in `test_trace_freeze.py`**, not a new test file: a new file tagged
  `covers_none("tooling")` is refused unless it is in the infrastructure catalog at the merge-base.
- **`--repin`**: after the freeze a change is an approved delta; overwriting a lock is a decision, so it needs a flag.

## Out of scope

P3-P8; any change to the live skill prose or product scripts; CODEOWNERS / sensitive-path rules for the frozen files
(a residual risk already handed to the operator in `test_trace_freeze.py`'s docstring).
