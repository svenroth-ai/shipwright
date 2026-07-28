# Stage 2 — internal code-reviewer (`shipwright-build:code-reviewer`, Opus)

Ran after Stage 1 (`spec-reviewer`) returned **approve** and its two MEDIUM
findings were applied. Reviewed the full diff plus the post-change files, the F11
call site, `git_helpers.py`, `churn_merge.CHURN_ALLOWLIST`, the ruff ruleset and
the file-size limits.

**SHIPWRIGHT_VERDICT: revise** — 1 high, 3 medium, 6 low.

## What it verified as correct

`tokens_in_order`'s greedy two-pointer is a correct subsequence test.
`replacement_hunks` handles `\ No newline at end of file`, CRLF, a deleted
`---`/`@@`-prefixed content line, binary files, and outright add/delete. Both
cache keys are sound. `dropped` unions per merge, so a line reported by one merge
is never un-reported by another. Every new test except two would genuinely fail
against the pre-change code.

## Findings, and what each became

| # | Sev | Finding | Resolution |
|---|---|---|---|
| 1 | **high** | `still_carried_by_default` mapped a git FAILURE and a genuinely absent path onto the same `None`, and `None` silenced the ENTIRE path — so an unreadable file produced a green **pass** on a comparison that never happened, in a module that turns exactly that into a visible SKIP everywhere else. | Fixed. `tip_state` uses `ls-tree` to separate absence from failure; failures go to the `problems` channel. Later widened by external code review to all four read sides (`read_side`). |
| 2 | medium | Token containment proves the words survive, not the meaning; both docstrings claimed the question was "no longer open". | Fixed. The claim is narrowed in prose and the accepted case is pinned by `test_the_accepted_blind_spot_is_pinned_not_implied`. |
| 3 | medium | `tokens_in_order` and `replacement_hunks` — the two parsing surfaces where a mis-read becomes a suppressed finding — had no direct tests. Deleting the empty-needle guard would have kept the suite green. | Fixed. `test_silent_revert_filters.py` added (11 unit tests at the time). |
| 4 | medium | `merely_edited` re-split every replacement for every missing line; with `-U0` a wholesale rewrite is ONE hunk, so cost is quadratic on a large file and an F11 gate that hangs is a gate that gets switched off. | Fixed. Replacements tokenised once per hunk. |
| 5 | low | `merely_edited` returned the lines that were *not* merely edited — opposite polarity to its sibling, called back-to-back with identical shape. An inversion hazard on a safety gate. | Fixed. Renamed `unexplained_by_edit`. |
| 6 | low | `_file_lines` duplicated verbatim between the two modules; both feed the same comparison, so a divergence would silently change what "the same line" means. | Fixed. One definition, in `silent_revert_reading`. |
| 7 | low | `dropped_lines` rebound `default_branch`, but every operator-facing string still named the UNRESOLVED ref — so a block message could name a ref the comparison did not use. Given this run exists because an operator was handed findings they could not verify, not cosmetic. | Fixed. Resolved once in `check_no_silent_revert`, before the pre-flight, and used in the messages. |
| 8 | low | The AC1 fixture committed **conflict markers**: the assertion passed on text inside a `<<<<<<<` block, and a contributor with `merge.conflictStyle=diff3` would have seen it fail. | Fixed. Merge 2 resolved explicitly; `merge.conflictStyle` pinned in the fixture; a no-markers assertion added. |
| 9 | low | `test_deleting_a_file_..._does_not_raise` pinned nothing — its docstring described a crash the shipped code cannot have. | Fixed. Renamed and the docstring corrected to what it actually proves. |
| 10 | low | `significant_line` documented with a Sphinx `#:` attribute comment instead of a docstring. | Fixed. |
| 11 | low | `test-traceability.json` lists only the 16 pre-existing tests for this area. | Regenerated at F5b; verified after finalization. |
