# ADR: Split two test files that crossed the 300-line bloat gate post-merge

**Run:** iterate-2026-09-23-codextender-part-c-bloat-split

## Context

PR #791 (`codextender-monorepo-part-c`) merged before the session's Iron-Law
Stop-hook bloat check could run: `shared/tests/test_external_review_opus_leg.py`
grew to 361 lines and `integration-tests/test_external_review_driver_prose_contract.py`
grew to 339 lines while adding regression tests for the `ANTHROPIC_AUTH_TOKEN`
conditional-scrub fix and the driver-routing census. CI's own Bloat Check
passed (it only blocks ratcheting an already-baselined exception, not a
first-time crossing — `shared/glossary.md`'s Ratchet/Anti-Ratchet split), so
`main` stayed green — but the crossing is real technical debt the session's
own completion gate exists to catch before it gets forgotten.

## Decision

Split both files along their existing concern boundaries (each already had
`# --- <concern> ---` section comments marking the seam), verified
byte-identical against `origin/main` before editing so the split is a pure
move with zero risk of dropping a fix in transit:

- `test_external_review_opus_leg.py` (163 lines) keeps binary resolution
  (cwd-hijack guard, `.cmd`/`.bat` shim refusal), availability detection,
  `claude_cli_settings`, and `resolve_opus_route` tests.
- New `test_external_review_opus_leg_dispatch.py` (222 lines) takes
  `review_claude_cli`'s dispatch/retry/error-class/env-scrub tests — the
  larger, still-growing half (it holds both `ANTHROPIC_AUTH_TOKEN` regression
  tests from the merged PR).
- `test_external_review_driver_prose_contract.py` (274 lines) keeps the
  `--driver` coverage tests and the live-idiom extraction/execution tests.
- New `test_external_review_key_consistency_contract.py` (82 lines) takes the
  `reviews.openai`/`reviews.opus` key-consistency drift-protection tests —
  independent of the driver-block helpers, so it needed no shared fixtures.

No test logic changed — all 38 tests across the four files re-verified
passing after the split.

## Consequences

Both files are back under the 300-line ceiling with headroom to grow. No
behavior change; the split follows each original file's own section
boundaries rather than an arbitrary line cut, so each new file reads as a
coherent, independently-named concern.

## Review record

Mechanical repair (pure test-file reorganization, no production code
touched), verified via full re-run of all 38 tests plus the bloat pre-commit
gate. Code-reviewer: PASS, no defects found. Concretely verified: (1) test
count parity — 15 test functions / 18 collected items (2+3 parametrize
cases) in `test_external_review_opus_leg.py` plus 9 items in the new
`test_external_review_opus_leg_dispatch.py` = 27, matching pre-split; 5 plain
+ 1 four-case-parametrized test in `test_external_review_driver_prose_contract.py`
= 9 items plus 2 items in the new `test_external_review_key_consistency_contract.py`
= 11, matching pre-split; 38 total, no name collisions; (2) both new files'
imports/fixtures (`_LIB_DIR` sys.path shim, `_CONFIG`, `_FakeCompleted`,
`_json_ok`, `REPO_ROOT`/`PLUGINS_ROOT`, compiled regexes) are complete and
self-contained, cross-checked against every name each file actually uses;
(3) line-by-line read of both new files and the tails of both kept files
found no assertion/docstring drift — a verbatim relocation; (4) this ADR's
line counts and the sibling ADR's stale-path fix both checked accurate
against the files on disk. Spec-reviewer skipped — spec_impact=none, no
spec.md touched, no plan to review against. Doubt-reviewer skipped — no
migration, concurrency, cross-plugin import, or irreversible operation
present; risk criteria not met.
