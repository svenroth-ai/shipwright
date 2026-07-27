# Review log — iterate-2026-07-27-handoff-tally-and-gate-honesty

This iterate exists **because** of reviews: every defect it fixes was found by the
Stage-2 code review and Stage-3 doubt review of its predecessor
(`iterate-2026-07-27-phase-gate-override-evidence`, PR #438). Those two passes had
been closed `not_run` on the predecessor under a session rule barring subagents;
the user then asked for them explicitly, they ran against the merged commit, and
they found 13 + 8 findings that the external LLM reviews and the self-review had
all missed.

That is the single most useful fact in this log: **the substitution recorded on
the predecessor ("external_code + self-review + red-check covers it") was not
equivalent.** It is recorded here so the claim is not repeated.

---

## Inherited — Stage-2 code review (predecessor, `shipwright-build:code-reviewer`, opus)

13 findings. Those in scope here, all fixed:

| # | Finding | Fixed by |
|---|---|---|
| med | `needs_validation` survives a forced retry; the comment claims otherwise | R3 |
| med | `attempt: 0` rendered as "Currently dispatched" | R2 |
| low | critical-gate crash discards `validate_phase`'s findings | R8 |
| low | gate-error loses its traceback | R10 |
| low | inform notes duplicate, uncapped, into a tracked artifact | R9 |
| low | unhashable status → `TypeError` → handoff silently skipped | R7 |
| low | drift guard checks the direction its docstring disclaims | R6 |
| low | CLI/library asymmetry on the force-reason precondition | R11 |
| low | docs omit the standalone exclusion | docs |
| low | predecessor spec's Design section stale (50 vs 200, one module vs two, alias) | spec annotation |
| low | `record_validation_override` return value unused | **reverted** — see external review below |
| low | nothing surfaces `validation_overrides[]` to a person | out of scope (feature) |
| low | change-sizing: two concerns in one commit | retrospective, not actionable |

Explicitly **not** flagged by that reviewer after checking: split-loop record
persistence, `force_reason` rebind, lock-boundary state, backwards compatibility
of the new flag pairing, the `lib` namespace collision.

## Inherited — Stage-3 doubt review (predecessor, `shipwright-build:doubt-reviewer`, opus)

8 doubts, 1 high. In scope here:

| # | Doubt | Fixed by |
|---|---|---|
| **high** | `Finished: N of M` denominates against incrementally-materialised `phase_tasks` — a run 1-of-7 reads "1 of 2" while calling itself authoritative | **R1** |
| med | multi-split: `build` listed as finished AND interrupted; `failed` in no bullet | R5 |
| med | a step with no validator records `gate_result: "pass"` | R4 |
| med | corrupt config → silent standalone demotion → the whole guarantee switches off | **deferred, filed** |

Attacks that **held** (recorded as evidence for the predecessor): concurrent
writers cannot clobber the record; no reserialisation path drops the key; the new
flag pairing breaks no shipped caller; the lazy-import guard is not a tautology;
the markdown hardening is real.

---

## This iterate — external code review (openrouter)

`reviews_succeeded: 1` of 2. **gemini DEGRADED** — the provider reported the reply
was cut off (`finish_reason=length`); its one partial finding broke off mid-sentence
while describing the `_gate_error` message wording, which on inspection reads
correctly (`[gate-error] phase validation for 'project' raised RuntimeError: boom`).
Recorded as degraded, not as a pass. Second consecutive run where this leg failed.

**openai (gpt) — verdict `revise`**, 2 findings, both accepted:

| # | Finding | Disposition |
|---|---|---|
| medium (spec) | The code labels a task dispatched when `status == in_progress` OR `attempt >= 1`, but **AC2 said "only for `attempt >= 1`"**. Code and criterion disagree. | **AC corrected, code kept.** The task's own status is the stronger signal — `claim_phase_task` sets `in_progress` under CAS at dispatch time, while `attempt` is a retry counter that recovery resets. A lifecycle-recorded `in_progress` IS dispatched. Added `test_an_in_progress_task_is_dispatched_whatever_the_counter_says` so the rule is pinned rather than implied. Note this is the *same* plan/code divergence class that the predecessor's code review flagged — caught pre-merge this time. |
| low (regression) | `record_validation_override` had its `-> dict` return removed. | **Reverted.** The Stage-2 reviewer had suggested dropping it as unused surface; gpt is right that removing a return is a compatibility change with no defect behind it, and this is a **bug** iterate — that change fixed nothing. Out of scope, restored. |

## Deferred, deliberately

**The silent standalone demotion on a corrupt config** (doubt review, medium).
`_read_standalone_flag` returns `True` whenever `load_run_config` cannot parse the
file, so on a genuinely non-standalone run with an unreadable config: `--force`
needs no reason, writes no record, skips the gate entirely — and
`_load_or_bootstrap` can then atomically REPLACE the file, destroying
`phase_tasks`, `completed_steps` and the override log. `run_config_store.py`
already names this failure mode. It predates the predecessor, its blast radius is
every v1 caller rather than the override path, and fixing it means deciding what a
corrupt config should do to a run. Its own iterate — not smuggled into a bug fix.
