# F-simplify — Behavior-Preserving Simplification (SIMPLIFY-mode sub-skill)

> **When this fires:** intent-classification returns `mode: "simplify"` (the
> CHANGE sub-mode raised by simplify vocabulary — `simplify` / `clean up` /
> `declutter` / `streamline` / `tidy`), OR any change/feature iterate the agent
> classifies as **Spec Impact = NONE** (a behavior-preserving refactor). The
> iterate Kern routes such work through this protocol. See [SKILL.md](../SKILL.md)
> "Path D: SIMPLIFY" and [path-b-change.md](path-b-change.md).

## Iron Law

**A SIMPLIFY THAT CHANGES OBSERVABLE BEHAVIOR IS A BUG, NOT A SIMPLIFICATION.**

Simplification reduces the cost of understanding code while leaving what it
*does* exactly as it was. The goal is a clearer program, **not** a shorter one —
*fewer lines is not the goal*. If a change makes the diff smaller but the code
harder to follow, or alters any observable result, it has failed. The wrap below
is mandatory and ordered: snapshot the green state **before** you touch anything,
simplify under the Five Principles, then verify the behavior is byte-for-byte
preserved. The reviewer gate (below) rejects a simplify that ships behavior drift
or that deletes test coverage to make the suite "pass".

The wrap produces, in order:

1. a stored green-state record (the suite passes before you start),
2. edits that satisfy the Five Principles + the Chesterton-Fence pre-flight,
3. a verified-equal green state (no test flips, no coverage removed).

---

## Phase 1 — Behavior-Snapshot (before any edit)

You cannot prove you preserved behavior without a baseline. Record one.

```bash
uv run "{plugin_root}/scripts/lib/behavior_snapshot.py" snapshot \
  --project-root "{project_root}" --run-id "{run_id}" \
  --test-cmd "<python> -m pytest" [--target <paths covering the code you will simplify>]
```

- The suite **must be green first.** `snapshot` REFUSES a red baseline (exit 2):
  there is no green state to preserve, so fix or pin the behavior first.
- Scope the snapshot to the tests that cover the code you will touch (`--target`),
  or the whole suite. Narrow scope = faster loop; the whole suite = strongest guard.
- The record (collected test node-id set + pass/fail counts + exit code + source
  LOC baseline) lands at the gitignored `.shipwright/runs/<run_id>/behavior_snapshot.json`.

**Output of Phase 1:** a stored green-state record. If the suite is not green,
STOP — you are not in a position to simplify yet.

---

## Phase 2 — Simplify under the Five Principles

> Adapted from addyosmani/agent-skills `code-simplification` (MIT, © Addy Osmani).

1. **Preserve Behavior.** Every observable output, side effect, error, and
   public signature stays identical. If you are tempted to "fix a little bug
   while here", STOP — that is a separate CHANGE/BUG iterate. Scope creep is how
   simplifications introduce regressions.
2. **Follow Conventions.** Match the surrounding code's naming, structure, and
   idioms. A simplification that imports a new style the file does not use trades
   one kind of friction for another. Read the neighbours first.
3. **Clarity over Cleverness.** Prefer the boring, obvious shape. A dense
   one-liner that needs a comment to decode is *not* simpler than three plain
   lines. Optimize for the next reader, not for line count.
4. **Maintain Balance.** Do not over-abstract. Collapsing two call-sites into a
   premature helper, or a factory with one caller, adds indirection that costs
   more than the duplication it removed (constitution Karpathy #2, Simplicity
   First). Add structure when the third caller arrives, not before.
5. **Scope to What Changed.** The diff should touch only the code being
   simplified. A simplify that reformats an entire file, re-sorts imports
   repo-wide, or renames across modules is a refactor wearing a simplify label —
   split it (constitution Karpathy #3, Surgical Changes).

### Chesterton-Fence pre-flight (before deleting or changing anything)

For **every** line, branch, guard, or piece of state you are about to remove or
rewrite, you must be able to state **why it exists**:

> "This `if not x: return` guards against the empty-payload case that FR-12's
> retry path can produce — so I keep it / replace it with an equivalent."

If you **cannot** explain why something is there, you do not yet understand it
well enough to remove it. Find out first (git blame, the test that pins it, the
ADR). "It looks unnecessary" is not a reason — it is the absence of one. Code you
do not understand is a fence you do not get to tear down yet.

---

## Phase 3 — Behavior-Verify (after the edit)

Re-run the snapshot's suite and diff against the stored green state:

```bash
uv run "{plugin_root}/scripts/lib/behavior_snapshot.py" verify \
  --project-root "{project_root}" --run-id "{run_id}"
```

`verify` exits **non-zero (STOP)** when any of these hold:

- **a test flipped green→red** — behavior changed in a covered path,
- **a previously-collected test disappeared** — coverage was removed (the classic
  "delete the failing test" anti-pattern),
- **the collected test count dropped**, or
- **source LOC dropped *together with* reduced coverage** (shrinking code by
  deleting its tests).

A clean green→green with intact coverage — even with a large LOC drop — exits 0.
That LOC drop *with preserved green coverage* is exactly the win you are after.

**Honest limit (read this).** The gate is only as strong as the suite's
coverage: behavior drift in an **un-covered** path cannot be detected by any
snapshot. That is *why* removed coverage is a hard reject, and why the Five
Principles + the Chesterton-Fence pre-flight are mandatory reasoning, not
decoration — they cover what the tests cannot. If you find the code you are
simplifying is under-tested, add the characterization test **first** (a normal
test-first step), re-snapshot, then simplify.

**Circuit breaker:** if `verify` rejects 3 times, STOP. Either the change is not
behavior-preserving (it is a CHANGE, re-classify it) or the code resists
simplification without a behavior shift — escalate per
[mid-flight-escalation.md](mid-flight-escalation.md).

---

## Reviewer Gate (behavior preserved, coverage intact)

At Self-Review and Full Code Review (and in the PR), the reviewer **rejects** a
simplify that:

- ships a `verify` REJECT (behavior drift or removed coverage) without a
  re-classification to CHANGE/BUG,
- weakens or deletes a test to make the suite green (constitution: "fix the code,
  not the test"),
- expands scope beyond the code being simplified (Surgical Changes),
- removes a guard/branch/state whose purpose the PR cannot state (Chesterton-Fence),
- trades clarity for fewer lines (a clever one-liner the reviewer must decode).

A PASS requires a green `verify` (behavior preserved, coverage intact) and a
one-line statement of what got clearer and why. **Spec Impact is NONE** by
definition — a behavior-preserving simplify changes no FR; record the one-line
NONE justification (FR-gate branch: `change_type = tooling`/`infra` only when the
simplified code is non-FR framework/tooling code).

---

> Adapted from [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)
> `skills/code-simplification/SKILL.md` — the Five Principles, the Chesterton-Fence
> check, and "fewer lines is not the goal". MIT, © Addy Osmani. Patterns adapted to
> Shipwright's iterate SIMPLIFY mode and paired with the executable
> `behavior_snapshot.py` gate; no verbatim text copied beyond the principle names.
