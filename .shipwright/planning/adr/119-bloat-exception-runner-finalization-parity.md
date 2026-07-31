# ADR-119: Bloat exception — `plugins/shipwright-iterate/agents/sub-iterate-runner.md` raised to 497-LOC

- **Status:** accepted
- **Date:** 2026-07-31
- **Re-Review-Date:** 2026-10-31
- **Incident Reference:** `iterate-2026-07-31-it7b-campaign-cascade`
  (anchor trg-fc173418, member 7b). The limit was crossed by adding the four
  finalization phases the contract was missing — F0.5, F2 (`architecture.md`),
  F3a and F5.

## Context

`sub-iterate-runner.md` is the **runtime prompt** for the subagent a campaign
spawns per sub-iterate. It is not source; it is the text the agent is given.

It sat at 479 lines against a 400-line runtime-prompt cap, `grandfathered`.
Investigating IT-7b (the review cascade never running in campaign mode) surfaced
a second instance of the same defect: the contract **re-enumerates** the
finalization phases rather than deriving them from SKILL.md's index, and that
duplicate list had silently fallen four phases behind.

| Phase | Standalone | Runner (before) |
|---|---|---|
| F0.5 E2E gate | mandatory medium+ | absent |
| F2 `architecture.md` | on structural impact | absent — the label `F2` was reused for Browser Verify |
| F3a Reflection | mandatory | absent |
| F5 `iterate_latest` | mandatory small+ | absent — the producer the ledger + surface gates read |

The F2 case is the instructive one: the *label* was present, so any token-level
check reported F2 as covered while `architecture.md` was never written by any
sub-iterate of any campaign. Measured against the pre-change file, a token-set
drift test reports F0.5, F3a and F5 missing — never F2. The guard is therefore
a SUBJECT pin per phase (each bullet must name its reference or producer), not
a phase-number pin; F4 proved the same point independently, having instructed
every sub-iterate to append to `CHANGELOG.md` where `references/F4.md` forbids
it in as many words.

Adding the missing phases plus the collision note costs **+18 lines**
(479 → 497).

**F5 was found by the Stage-2 review, while this ADR was in draft.** It had
first been classified *excluded* here, on the reasoning that
`shipwright_test_results.json` is a derived snapshot F11 rewinds to HEAD — a
mechanism trg-ad29a709 had already closed
(`RESTORABLE_SNAPSHOTS = DERIVED_SNAPSHOTS - {TEST_RESULTS}`). F5 is in fact the
PRODUCER of the `iterate_latest` block that both
`check_test_completeness_ledger` and the F0.5 `surface_verification` gate read,
so a small+ sub-iterate was failing its own F6-verify for want of it. A wrong
exclusion reason is no safer than a missing phase; that is why every entry in
`RUNNER_EXCLUDED` now carries one that can be checked.

## Ousterhout Argument

The module is deep. Its **interface** is genuinely narrow: five input
parameters in, one `result.json` out. Its **implementation** is genuinely
substantial: the whole iterate lifecycle, executed autonomously with no human
in the loop.

The size is load-bearing for a reason specific to runtime prompts: **a
subagent's system prompt is the only text guaranteed to be loaded.** Anything
moved behind a pointer is read only if the agent chooses to read it. For the
*exact commands* of a step that is acceptable — the agent reads them when it
executes that step, and failure is loud and immediate. For *the existence of a
mandatory step* it is not: an agent that never follows the pointer never learns
the step exists, and the omission is silent.

That is not hypothetical. It is precisely the defect this ADR's incident fixes
— four mandatory phases absent from the enumeration, unnoticed across every
campaign that has run. So the list of **what must happen** belongs in the
prompt; only **how exactly** may be delegated to `references/*.md`. The file
already follows that division, and the change extends it rather than breaking
it.

Splitting the enumeration out would therefore not encapsulate an internal — it
would demote a guaranteed load into a best-effort one, reintroducing the exact
failure mode being repaired.

## YAGNI Check

Walking the file's responsibilities, today:

- **Steps 1–3.8 (build, reviews, calibration)** — needed today; ADR-029 exists
  because campaigns A/B/C/D shipped without them.
- **Step 4 finalization list** — needed today, and *incomplete* until this
  change. This is the only responsibility that grew.
- **Step 5–6 (push, result)** — needed today; the orchestrator parses the
  result at loop step 3e.
- **Output / result-JSON contract** — needed today; pinned by
  `test_sub_iterate_runner_contract.py` and consumed by `campaign_progress.py`.
- **`## Bloat Checklist`** — needed today and **cannot be removed**: see the
  fence check below.

Nothing here is speculative scope. No responsibility failed the test, so
nothing was deleted before writing this exception.

## Chesterton-Fence Check

The current shape is documented, not accidental:

1. **The `## Bloat Checklist` section (~96 lines) is byte-identical-pinned** to
   `plugins/shipwright-build/agents/code-reviewer.md` by
   `shared/tests/test_reviewer_bloat_checklist_parity.py` (Campaign A.review,
   with the extraction boundary set by external review — Gemini #3, OpenAI
   #7/#8). The fence has a reason: both reviewer prompts must carry the
   verbatim text *and* the MIT attribution for Karpathy/Osmani. Extracting it
   to a shared include would break the parity invariant, drop the attribution
   from the loaded prompt, and reach into a second plugin. **Fence stands.**
2. **The nearest prior split was of the TESTS, not this file.**
   `iterate-2026-07-20-runner-finalization-integrity` moved the finalization
   tests into their own module so additions would not ratchet the sibling test
   file. Stated plainly because an earlier draft of this ADR cited it as "the
   file has already been split once" — subject and evidence were different
   artifacts, and the sentence was doing load-bearing work (Stage-3 doubt). The
   prompt itself has never been split; the argument for not splitting it now is
   the Ousterhout one above, not a precedent.
3. **The `F2` label collision** was *not* a documented fence — no design note
   defended it. That one was torn down rather than exception-allowed: Browser
   Verify no longer carries an F-number.

## Decision

Raise `current` for `plugins/shipwright-iterate/agents/sub-iterate-runner.md`
from **479 to 497**, `state: "exception"`, `adr: "ADR-119"`, in the same commit
as the change that crosses it.

**Retirement plan.** The exception is retired by removing the *duplication*,
not by trimming prose: the runner should derive its finalization list from
SKILL.md instead of restating it. That needs a loader able to inline shared
prose into an agent prompt at spawn time. That premise is ASSERTED, not
probed — `shared/prompts/` already holds cross-plugin prompt text and
`scripts/update-marketplace.sh` already runs a compose/sync step over the
plugin cache, so a generation step (SKILL.md index → the Step-4 block, checked
by the drift test) may well be buildable. The re-review must MEASURE this
rather than repeat the assumption (Stage-3 doubt).

Until then the duplication is mandatory and drift protection
substitutes for deduplication:
`test_sub_iterate_runner_finalization.py` now pins BOTH directions — every
required phase is present, and every phase SKILL.md defines is classified
required-or-excluded-with-a-reason, so a phase added upstream cannot be
silently ignored again. The re-review on 2026-10-31 should ask whether that
loader exists yet.

## Consequences

- The runner prompt may grow to 497 lines before the anti-ratchet blocks.
  It is **not** a licence to keep growing: the next crossing needs its own ADR.
- `shared/tests/test_reviewer_bloat_checklist_parity.py` is unaffected — the
  pinned section is untouched by this change.
- A campaign sub-iterate now runs F0.5, so a medium+ sub-iterate touching a web
  surface must produce a `surface_verification` block. Runs that previously
  passed F6-verify by never claiming a surface will now be asked for one — that
  is the intended tightening, not a regression.
- If the exception outlives 2026-10-31, the cost is that the prompt keeps two
  copies of a phase list whose divergence is caught by tests but never
  prevented by construction.

## Rejected alternatives

- **Leave it at 479 and split now.** The only section large enough to matter is
  the Bloat Checklist, and splitting it breaks a deliberate byte-identical
  parity invariant across two plugins plus its MIT attribution. Splitting the
  *step contract* instead is worse: it converts guaranteed-loaded text into a
  best-effort pointer, which is the failure mode being repaired.
- **Shallow refactor — compress the prose.** Attempted. Tightening the newly
  added bullets recovered exactly one line (493 → 492, before F5 took it to
  497). The phases cannot be named, gated and pointed at their references in
  zero lines.
- **Drop the incident lessons to buy space** (e.g. the F5c note recording that
  its omission lost `iterates/<run_id>.json` for 3 of 4 sub-iterates). Rejected:
  those notes are why the steps survive contact with an autonomous agent.
- **Leave the phases out and file them instead** (three of them, at the time —
  F5 had not yet been found). This was the initial
  plan and was rejected by the operator on the correct ground: a campaign
  sub-iterate that skips the E2E gate, reflection and `architecture.md` is not
  congruent with a standalone one, and deferring means touching the same
  grandfathered file twice.
