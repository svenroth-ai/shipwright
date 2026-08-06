# Architecture Brief — template

The input to `external_review.py --mode architecture`, the one review pass that
asks whether a change should be built **at all** rather than whether the plan
for it is sound.

**Where it goes**

- iterate: `.shipwright/planning/iterate/<run_id>/architecture_brief.md`
- plan: `{planning_dir}/architecture_brief.md`

---

## The one rule that makes this pass worth running

**List the options. Do NOT give the reasons any of them were rejected.**

The mini-plan's `Alternative approach considered — rejected because X` (and the
plan's equivalent) must not be copied here, quoted here, or summarised here. A
reviewer who reads a rejection reason first will almost always confirm it; that
is the whole failure this pass routes around. Measured twice: the same two
models over the same change approve it when shown the plan and reject it when
shown a brief.

Two consequences, both intended:

- The reviewer may recommend something the author already discarded. **That is a
  result, not a defect.** The reconciliation happens afterwards, by the author,
  in the open — not by pre-loading the reviewer.
- **Keep it short.** Half a page is normal. Longer than a page means it has
  stopped being a brief and become the plan again.

Do **not** include the file list, the work breakdown, the test strategy, the
rejection rationale, or any code. Those belong to the plan review, which runs
separately over the plan itself.

---

## When the change adds nothing permanent

Most changes don't. Say so and stop — **the brief is three lines and you are
done**:

```markdown
# Architecture Brief: {short-description}

## The problem
{1-2 sentences, in outcome terms.}

## What would newly, permanently exist
Nothing. This changes machinery that already exists: {what, in one line}.
```

The reviewers confirm it in a sentence and the pass costs you nothing. This is
the deliberate design: the pass runs on every medium+ review rather than behind
a trigger the author sets, because a trigger the author sets fails first on
exactly the changes that most need the question asked — and a brief this short
is cheaper than the machinery a trigger would need.

---

## When something permanent IS being added

A *standing mechanism* is something the project must keep running, keep correct
and keep explaining from now on: a workflow, a credential, a scheduled job, a
new place data gets written, a new gate, a new service. Its cost is not the code
that creates it; it is every future change that has to reason about it.

```markdown
# Architecture Brief: {short-description}

## The problem

{2-4 sentences, in outcome terms. What goes wrong today, for whom, how often,
and how bad is it when it does. No solution vocabulary — if the sentence names a
mechanism, it is not the problem yet.}

## What already exists here

{The mechanisms already in this project that touch this area, one line each —
this is what tells the reviewer whether something existing could absorb it.}

## What would newly, permanently exist

{2-4 sentences: what it is, when it runs, what it writes or holds, and —
explicitly — who or what keeps it correct from now on.}

## Options on the table

- **A:** {one line}
- **B:** {one line}
- **C:** {one line — include "do nothing" whenever doing nothing is survivable}

{No reasons for or against. No marking of a preferred option.}

## Constraints that are not negotiable

{Only real ones — a regulatory rule, a platform limit, an interface something
else already depends on. "We already started building it" is not a constraint.
If there are none, write `none`.}
```

---

## After the review

Both reviewers end with `SHIPWRIGHT_VERDICT: approve|revise|reject`. `approve`
→ proceed. `revise` → integrate like any other finding. On a **`reject` from
either reviewer the run stops and asks the operator** — take the alternative,
keep the plan with the reason recorded, or rework and re-review. The
reconciliation against the plan's own rejection rationale is written down at
that point, which is where the withheld reasoning re-enters the record.
