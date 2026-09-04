# Code Review Protocol

## Overview

After implementation, spawn the code-reviewer subagent to review the diff
against the section spec. The reviewer checks for bugs, security issues,
performance problems, and spec compliance.

## Steps

1. Generate diff. The path comes from `review_scratch.py resolve` (never a
   bare `/tmp/...` literal — bash and native Python resolve that to
   different files on Windows, see `code-review.md` Step 6b for the full
   rationale). `resolve` is a pure function of `(run_id, name)` — never carry
   this call's stdout across a separate Bash tool call; step 2 (and, later,
   `code-review.md`'s 6c cascade) each re-invoke it independently and land
   on the identical path. Build has no `run_id` of its own; `--run-id` is
   `$SHIPWRIGHT_SESSION_ID` (see `code-review.md`'s "Full review flow"
   step 1 for why that scopes safely, and why it's referenced as a real
   shell env var rather than interpolated text):
```bash
git diff HEAD > "$(uv run "{shared_root}/scripts/tools/review_scratch.py" resolve --run-id "$SHIPWRIGHT_SESSION_ID" --name shipwright-review-diff.txt)"
```

2. Spawn `code-reviewer` subagent with:
   - Section spec file path
   - Diff file path — re-resolve independently:
     `"$(uv run "{shared_root}/scripts/tools/review_scratch.py" resolve --run-id "$SHIPWRIGHT_SESSION_ID" --name shipwright-review-diff.txt)"`
   - `model=<review tier resolved at SKILL.md §G>` (omit when `inherit`) —
     see `code-review.md`'s "Model tier" note; the same value applies at
     every stage of this cascade

3. Receive structured review:
```json
{
  "section": "01-auth",
  "review": [
    {
      "severity": "high|medium|low",
      "category": "bug|security|performance|style|spec-gap",
      "file": "src/auth/login.ts",
      "line": 42,
      "finding": "Description",
      "suggestion": "How to fix"
    }
  ]
}
```

## Handling Results

### Autonomous mode
- **high + medium severity**: Fix immediately, no prompt
- **low severity**: Fix if trivial, otherwise log

### Guided mode (default)
- **high severity**: Must fix before commit
- **medium severity**: Present to user (Accept/Decline/Defer)
- **low severity**: Batch present ("3 style suggestions — accept all?")

## No Findings

If review returns no findings, proceed to commit.

## Cleanup

**Not here.** This protocol is always reached as Step 6b of `code-review.md`'s
larger Step 6 flow, which continues into 6c (the optional external cascade)
immediately after this subagent returns — 6c reuses the exact diff file this
step wrote. Cleaning it up here would delete it out from under 6c whenever
the cascade is enabled. The scratch diff is removed exactly once, at 6c's
own terminal step (`code-review.md` "Cascade flow" step 6), which runs
unconditionally regardless of whether the cascade itself fires.

If this step's code-reviewer subagent crashes or returns no parseable
review, 6c is never reached the intended way — the `SubagentStop` hook
`cleanup-review-scratch-on-code-reviewer-failure.py` is the failure-path
backstop for exactly that case (`hooks.json`; only acts when the subagent's
last reply is not a parseable review, a no-op on a normal completion).
