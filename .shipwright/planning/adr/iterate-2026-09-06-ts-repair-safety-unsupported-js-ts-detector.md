# JS/TS-aware test-weakening detector for the main-repair safety gate

## Context

The main-repair safety gate (`check_repair_safety.py` → `lib/assertion_weakening.py`)
enforces FR-01.19 AC-6 ("a repair must never adjust a test until it's green") by
diffing before/after test files and refusing a repair that removes assertion
coverage or adds a skip/xfail mark. It parsed test files with Python's `ast`
module only. Any consumer repo whose tests are `.test.ts`/`.spec.ts` (Jest,
Vitest, Playwright) hit `unsupported_test_file` (blocking, fail-closed) on
*every* main-repair touching a test file — regardless of whether the change
actually weakened anything. Verified against leadwright's `e764f89` main
repair: it only ADDED assertion coverage for a previously-unhandled outcome
branch, no coverage removed, yet would have been blocked.

## Decision

Add a hand-written JS/TS test-declaration scanner (`_js_collect` and
supporting helpers in `assertion_weakening.py`) that recognizes
`describe`/`it`/`test`, `.skip`/`.only`/`.todo`/`.fixme` modifiers, `xdescribe`/
`xit`/`xtest` aliases, `.each` parametrize (parenthesized and tagged-template
forms), and counts `expect(...)`/`assert(...)`/member-style `assert.<method>(...)`
calls as assertions — without taking a real parser dependency. Dispatch in
`analyze_file` by extension: `.py` → existing `ast` path, `.test.ts`/`.spec.ts`/
`.test.js`/etc. → the new JS/TS path, anything else that merely *looks*
test-shaped → the existing blocking `unsupported_test_file` finding (unchanged
behavior for genuinely unsupported languages).

### Anonymous/duplicate test identity

A text scanner cannot recover a stable per-test AST identity across a diff.
Two problems compound: dynamically-named tests (`it(caseName, () => {...})`,
name not known statically) and duplicate literal names (`it('works', ...)`
appearing more than once, e.g. inside different `describe` blocks or via
copy-paste). The chosen design **pools** every test call sharing an identity
(its literal name, or a shared `_DYNAMIC_POOL_KEY` sentinel for dynamically-named
ones) into one `_Test` record per identity, tracking:

- `assertions` / `marks` as **multisets** (tuples, not sets) — a pooled group's
  marks/assertions can legitimately repeat across instances, and a `Counter`-
  based occurrence-count comparison (not set difference) is required to detect
  a genuinely NEW mark occurrence rather than a pre-existing repeated one.
- `instance_count` — how many source calls fed the pool; a decrease is reported
  (non-blocking `pooled_test_instance_lost`) since it's ambiguous whether the
  lost instance's coverage/marks moved onto a survivor.
- `instances` — per-call `(assertions, marks)` snapshots, enabling an exact-
  content-key match: a content signature occurring exactly once on both the
  before and after side of a pool is an unambiguous 1:1 match, and marks gained
  on that specific pair can be judged directly.
- `full_bijection` gate — a relocated-mark finding is only BLOCKING when the
  ENTIRE pool's content-signature `Counter` is unchanged (`before_counts ==
  after_counts`); otherwise it is only REPORTED (`pooled_mark_possibly_relocated`,
  non-blocking), because an unrelated edit elsewhere in the same pool makes the
  1:1 content match ambiguous rather than proof of relocation.

### Design philosophy

What is BLOCKED is unambiguous loss (a test disappeared with no survivor
absorbing its coverage; a genuinely isolated skip/xfail was added). What is only
REPORTED is anything the pooling model cannot disambiguate from a coincidence.
A false BLOCK is treated as strictly worse than a false negative here: a
wrongly-blocked repair is this file's entire reason for existing (the original
leadwright bug). This trade-off was tightened twice during review (round 9→10:
reverted a per-key "block on any match" rule that risked false blocks, in favor
of the full-pool bijection gate; round 10→11: relaxed "every count==1" to full
Counter equality, to avoid over-conservatism against harmless conserved
duplicates).

### Known residual (accepted, documented in the module docstring)

Two content-IDENTICAL instances in the same pool swapping a skip/xfail mark
between them defeats the exact-content-key matcher (their signatures are
indistinguishable) — the same class of residual the file already accepted for
its original Python-only design (two structurally identical tests swapping
state). Judged acceptable: detecting it would require true AST identity
tracking, which a regex/bracket-balancing scanner cannot provide, and the
failure mode is a false negative (an already-accepted risk class), not a false
block.

## Consequences

- Every future TS/JS-repo main-repair touching a test file gets a real
  weakening analysis instead of a blanket fail-closed block.
- `analyze_file`'s exemption for `.py` files that merely look test-shaped
  (`conftest.py`, `tests/__init__.py`) had to be explicitly re-added — it was
  silently dropped when the language dispatch was restructured for JS/TS
  support (caught by code-review, fixed with a regression test).
- `_JS_ASSERT_HEAD` now also matches member-style `assert.strictEqual(...)`/
  `assert.ok(...)` (Node `assert`/Chai), deliberately NOT `expect.<method>(...)`
  to avoid double-counting Jest/Vitest matcher factories like
  `expect.stringContaining(...)` as their own assertion.
- `check_repair_safety.py`'s "review" verdict message is now kind-aware
  (`assertion_changed` / `pooled_test_instance_lost` / `pooled_mark_possibly_relocated`
  each get their own explanation) instead of a message hardcoded to one kind.

## Rejected alternatives

- **Ordinal-keying** (match test N in before-file to test N in after-file by
  position): gameable by decoy reordering — inserting/removing an unrelated
  test earlier in the file shifts every later index and defeats the match.
  Rejected in favor of pooling by identity.
- **A real JS/TS parser dependency** (e.g. a tree-sitter or Babel-AST binding):
  would give exact per-test identity and eliminate the pooling residual, but
  adds a non-Python runtime dependency to a Python-only shared library used by
  every consumer repo regardless of language. Deferred — the pooling design's
  residual is a false negative on an already-narrow case, not a false block,
  which is the trade this file optimizes for.
- **An explicit opt-out path with human sign-off** (the bug report's fallback
  suggestion): rejected as the primary fix because it would leave every
  TS-repo main-repair either unenforced (opt-out granted blanket) or blocked
  exactly as before (opt-out required per-repair, same friction). A real
  detector removes the false block without weakening the gate's guarantee for
  genuine weakening.
