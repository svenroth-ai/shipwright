# Bloat exception addendum — `plugins/shipwright-iterate/agents/sub-iterate-runner.md` raised to 528-LOC

<!-- Named by run_id per `_template-bloat-exception.md`; `shipwright_bloat_baseline.json`'s
     entry for this file is set to `"state": "exception", "adr": "ADR-pending:
     .shipwright/planning/adr/iterate-2026-09-23-r5a-wave-build-flip-sub-iterate-runner-bloat-exception.md"`.
     Addendum to the existing R2 exception on this file (512, itself already
     raised from 400) — not a fresh Ousterhout/YAGNI/Chesterton-Fence writeup,
     since the argument for the file staying whole is unchanged from R2's own. -->

- **Status:** accepted
- **Date:** 2026-09-23
- **Re-Review-Date:** 2026-12-23
- **Incident Reference:** `iterate-2026-09-23-r5a-wave-build-flip` — external
  code review (both `glm` and `openai` legs, verdict `revise`) found the
  first version of this sub-iterate's runner-contract edit had two real gaps:
  (1) the new Step 1.0.5 claim-promotion call was unconditional, breaking a
  standalone-shaped dispatch (no `state_path`/`unit_id`/`attempt_id` — the
  exact shape THIS sub-iterate's own dispatch used, since it predates its own
  flip landing); (2) Step 6's result-path prose omitted the `a{attempt}`
  attempt-scoping component the sub-iterate spec's own acceptance criteria
  name explicitly.

## Decision

Raise `current` for
`plugins/shipwright-iterate/agents/sub-iterate-runner.md` from **512 to 528**
(+12 lines round 1: a guard clause on 1.0.5, a two-branch path rule on
Step 6; +4 lines round 2: item 0's own isolation check was ALSO
unconditional — the same bug openai's round-1 review named for 1.0.5 alone —
fixed the same way, plus a one-line canonical-presence-check callout so all
three steps branch on the same `unit_id` field), `state: "exception"`, `adr`
updated to this file, in the same commit as the fix.

## Consequences

- Both fixes are load-bearing correctness fixes, not narration: without (1),
  every future sub-iterate dispatched under the OLD (pre-R5a) orchestrator
  prose — which cannot pass `unit_id`/`attempt_id`/`state_path` because it
  has not been re-read yet — would hard-fail at Step 1.0.5 before ever
  reaching its own build. Without (2), a superseded prior attempt's
  `result.json` and the current attempt's could alias at the same path.
- No new test file; `shared/tests/test_r2_worktree_capability_prose.py` and
  `plugins/shipwright-iterate/tests/test_sub_iterate_runner_step_3_4.py`
  already assert this file's shape and bloat ceiling — the ceiling assertion
  reads the baseline directly, so only the baseline needed updating, not the
  test.

## Rejected alternatives

- **Compress the Input block further to net back to 512.** Rejected: the
  Input block is already maximally compressed from this same sub-iterate's
  earlier round (three bullets merged into one to hold 512 in the first
  place); further compression would drop information a re-entering session
  needs, trading a real correctness fix for a cosmetic line count.
