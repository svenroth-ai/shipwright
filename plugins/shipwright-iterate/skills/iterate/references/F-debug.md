# F-debug — Systematic Debugging (BUG-intent sub-skill)

> **When this fires:** Intent-classification returns `kind: bug-fix` (Path C).
> The iterate Kern routes BUG intent through this protocol **before** any fix
> attempt. It sits inside Path C Step 3 (Investigate & Reproduce) and feeds the
> failing-test step. See [path-c-bug.md](path-c-bug.md).

## Iron Law

**NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.**

A symptom patch that does not name the root cause is a regression waiting to
re-open. If you are reaching for an edit before you can state *why* the bug
happens — stop. The four phases below are mandatory and ordered; do not skip
ahead to a fix because one "looks obvious". The reviewer gate (below) rejects
any fix whose PR does not show the investigation that found the root cause.

The four phases produce, in order:

1. the exact error text and where it surfaces,
2. a reliable reproduction,
3. the change that introduced it (or proof it is not a regression),
4. the boundary at which good input becomes bad output.

Only then do you write the failing test and fix.

---

## Phase 1 — Read Error

Read the **entire** error, not the first line. The fix lives in the details
most people skip past.

- Capture the full message, exception type, and **complete** stack trace.
- Note the *exact* file:line the runtime blames — then read that code.
- Distinguish the **error site** (where it threw) from the **error source**
  (where the bad value came from). They are rarely the same place.
- Record the observed behavior vs. the expected behavior in one sentence each.
  If you cannot state the expected behavior precisely, you do not yet
  understand the bug — go find the spec / design / intended contract first.
- For UI bugs, read the browser console + network panel, not just the
  rendered DOM. For API bugs, read status code + payload, not just "it 500s".

**Output of Phase 1:** the verbatim error, the blamed file:line, and a
one-line symptom-vs-expected statement.

---

## Phase 2 — Reproduce

You cannot fix what you cannot trigger on demand.

- Build the **smallest** reliable reproduction: exact inputs, environment,
  and steps. A repro that fails "sometimes" means you have not isolated the
  trigger — keep narrowing.
- Prefer a reproduction you can run from the terminal or a test harness over
  one that needs manual clicking. Determinism beats convenience.
- If the bug is intermittent, hunt the hidden input: ordering, time, cache
  state, concurrency, environment variable, leftover state on disk.
- Confirm the repro fails **before** you touch any code. A repro you never
  saw fail proves nothing.

**Output of Phase 2:** a command or step-list that reproduces the bug 100% of
the time.

---

## Phase 3 — Recent Changes

Most bugs are regressions. Find the change that introduced the behavior before
theorizing about anything deeper.

- `git log --oneline -20` on the touched paths; read the diffs that look
  related to the error site/source.
- When the repro is deterministic, `git bisect` (or a manual binary search of
  recent commits) localizes the offending change fast — let it.
- Check dependency/config drift too: a lockfile bump, an `.env` change, a
  schema migration, a plugin-cache that did not sync. "Nothing changed in my
  code" is not the same as "nothing changed".
- If the behavior is genuinely *not* a regression (new code path, new input
  class), say so explicitly and move to Phase 4 — do not invent a regression.

**Output of Phase 3:** the commit/change that introduced the bug, or a stated,
justified conclusion that it is not a regression.

---

## Phase 4 — Component-Boundary Instrumentation

Find the precise boundary where correct input turns into incorrect output by
instrumenting the data flow — do not guess.

- Trace the value from its source to the error site. At each component
  boundary (function call, module edge, API call, serialization, store
  mutation) assert what you *expect* the value to be.
- Add temporary logging / asserts / breakpoints at those boundaries and run
  the repro. The boundary where "expected" first diverges from "actual" is the
  root cause's neighborhood.
- Narrow until you can point at a single line/expression and explain, in one
  sentence, the causal mechanism: "X happens because Y, which is wrong because
  Z."
- Remove the temporary instrumentation before committing (or convert a
  genuinely useful assertion into a permanent guard with a test).

**Output of Phase 4:** a one-sentence root-cause statement naming the exact
mechanism — the thing your failing test will pin.

---

## Hand-off to the Fix

With the root cause named:

1. **Write the failing test first.** It must fail for the *identified root
   cause*, not a side effect. If you cannot write a targeted failing test,
   your Phase 4 analysis is incomplete — go back.
2. Fix the **root cause**, minimal scope. Do not patch the symptom.
3. Re-run the repro and the new test → green. Run related tests → no
   regressions.
4. When the bug crossed a serialized boundary (`touches_io_boundary`), the fix
   is incomplete without a producer→file→consumer round-trip test that fails
   before and passes after — see [round-trip-tests.md](round-trip-tests.md).

**Circuit breaker:** if 3 fix attempts fail after writing the failing test,
STOP. The root cause is probably mis-identified, or the architecture is the
problem — re-run Phases 3–4 or escalate per
[mid-flight-escalation.md](mid-flight-escalation.md).

---

## Reviewer Gate (root-cause, not symptom)

At Self-Review and Full Code Review (and in the PR), the reviewer **rejects**
a BUG fix that:

- shows no evidence of the four-phase investigation (no root-cause statement),
- changes behavior at the **error site** while the **error source** is
  untouched (classic symptom patch),
- adds a guard/try-catch/null-check that hides the symptom without explaining
  why the bad value existed,
- ships without a test that fails for the named root cause.

A PASS requires a one-sentence root-cause statement and a test that pins it.

---

> Adapted from [obra/superpowers](https://github.com/obra/superpowers)
> `skills/systematic-debugging/SKILL.md` — the Iron Law and the four-phase
> structure. MIT, © Jesse Vincent. Patterns adapted to Shipwright's iterate
> BUG path; no verbatim text copied beyond the Iron Law phrasing.
