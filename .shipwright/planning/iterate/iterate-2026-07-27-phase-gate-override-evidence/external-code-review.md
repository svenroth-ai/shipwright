# External code review — iterate-2026-07-27-phase-gate-override-evidence

Mode: `code` · Provider: openrouter · `success: true`, `reviews_succeeded: 2`.
Diff reviewed: the staged diff excluding `.shipwright/planning/iterate/` (2120 lines).

**Leg status: 1 usable, 1 DEGRADED.** The gemini leg returned a degenerate
generation — an unterminated fragment of its own reasoning
(`` ` where is `config["status"]` updated when moving to the next step? … ``) with no
findings and no verdict. It is recorded as degraded rather than as a clean pass;
the substantive review below is gpt's alone.

---

## openai (gpt)

**C1 — medium — regression.** `shared/scripts/tools/generate_session_handoff.py:28`.
The diff removes `_current_iterate_progress` without the compatibility re-export the
mini-plan specified. Updating this repo's own test imports does not protect an
external caller importing `tools.generate_session_handoff._current_iterate_progress`.
*Suggestion:* add `_current_iterate_progress = render_iterate_progress` plus a
compatibility test.

**C2 — low — spec.** `validation_record.py:57`. `MAX_VALIDATION_OVERRIDES = 200`,
while the mini-plan states a cap of 50 matching `append_iterate_entry.py`.
*Suggestion:* set it to 50 and adjust the retention test.

**Verdict:** ship-with-fixes. "The core acceptance criteria for always-running forced
validation, evidence recording, and pipeline handoff rendering appear implemented and
substantively tested."

---

## Disposition

Both findings have the same root cause, and it is a real one: **the mini-plan was not
updated after the plan-review dispositions were applied**, so the reviewer was
comparing the diff against a stale plan. Fixed by correcting the plan, not the code —
in both cases the code is what the *reviewed and disposed* design called for.

| # | Verdict | Reasoning |
|---|---|---|
| C2 | **plan corrected, code unchanged** | 200 is not a drift from 50 — it is the disposition of plan-review finding **O6**, which objected that a small silent cap discards the only durable evidence distinguishing "passed" from "waved through". The eviction counter (`validation_overrides_dropped`) was added in the same disposition so truncation is never silent. The mini-plan still said 50; it now records the revision and the reason. |
| C1 | **rejected, plan corrected** | The alias was in the first draft and was dropped deliberately during build. `_current_iterate_progress` is a **private** symbol (leading underscore) in a `tools/` script, not a public contract; `grep -rn` across the repo returns only the defining module and one in-repo test file. A permanent alias for a private helper with no callers is precisely the dead compatibility surface plan-review finding **O10** objected to, and adding a test asserting the alias exists would make the dead surface load-bearing. The plan now records the reversal and the grep that justifies it. |

No code change resulted from this review. The mini-plan changed so that plan and diff
agree — which is the defect the review actually found.
