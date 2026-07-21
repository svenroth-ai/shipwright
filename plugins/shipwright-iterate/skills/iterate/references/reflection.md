# Reflection Protocol

After completing work, reflect on what was learned during implementation.

## Questions to consider

1. **New patterns**: Did you discover a reusable approach, naming convention, or architectural pattern that should be documented?
2. **Gotchas**: Did you encounter unexpected behavior (API quirks, framework limitations, migration pitfalls) that future sessions should know about?
3. **Corrections**: Was an existing convention wrong, incomplete, or misleading? Should it be updated?
4. **Tool/infra insights**: Did you learn something about the build system, deployment, or test infrastructure that isn't documented?

## Actions (only if learnings exist — do not force entries)

`conventions.md` is always-loaded Layer-1 context, so every entry costs tokens on
every future run. Detail lives ONCE in the ADR (decision-drop ≤500 chars/field +
the `.shipwright/planning/adr/` spec folder); the `conventions.md` entry is a
one-line pointer. The ≤600-char rule is enforced **repo-agnostically** (this
monorepo AND every adopted repo): the F11 verifier `check_agent_doc_budget` STOPs
finalize on an over-budget NEW entry, and `shared/scripts/tools/check_agent_doc_budget.py`
(SSoT `lib.agent_doc_budget`) runs the same check by hand. Learnings are a
**date-lead one-liner, NOT a bold paragraph** (format below); the gate reads the
date from a bare `(YYYY-MM-DD)` OR the run-id slug, so a bold-lead entry no longer
slips the budget.

### For decisions (pattern chosen, convention corrected)
Record the ADR as the **F3 decision-DROP** (`write_decision_drop.py`, keyed by
`run_id`) with `--architecture-impact convention` — **not** `write_decision_log.py`.
An iterate never appends to `decision_log.md` directly (two parallel worktrees would
collide on the ADR number; the F11 verifier `check_iterate_no_direct_decision_log`
fails the run if the commit touches it). Add the matching **one-line** pointer under
`conventions.md ## Convention Updates` at **F2** (routing per `references/F2.md`); the
`ADR-NNN` is assigned at `/shipwright-changelog` release. Put the substance in the ADR
fields / `--spec-ref`, not in the bullet.

### For observations (gotchas, framework quirks, infra insights)
Append ONE compact line to `.shipwright/agent_docs/conventions.md` under
`## Learnings` — a single rule + an optional pointer, not a paragraph:
```
- ({YYYY-MM-DD}) {phase} — {one-line rule/gotcha}. [→ ADR-NNN / run_id]
```
If the learning won't fit one line, it is a **decision**: write an ADR (above)
and leave a one-line pointer here.

### For follow-ups — triage is for "later", NOT for tracking "now"

The triage backlog logs **genuine deferred follow-ups** discovered along the way —
work that is real but out of scope for *this* iterate. It is **not** a tracker for
the work you are doing right now: the **board / events log** (the `work_completed`
event F5b records, the iterate PR, the spec's acceptance criteria) owns "now".

Do **not** file a triage item to:
- track this iterate's own change or a step you are about to do / just did (e.g. "remember
  to sync the plugin cache", "this iterate still needs X") — that is current work; do it,
  or put it on the board (spec AC / TodoWrite), not in the backlog;
- mirror a gate failure that already STOPped the run (the STOP is the signal);
- restate a finding a background detective producer already emits (drift, compliance,
  phase-quality, sbom, security, performance) — those auto-append; don't duplicate them.

Only `triage_add` a follow-up when it is a **distinct, deferrable** item a future session
would otherwise lose. When in doubt, it belongs on the board, not in triage.

### For cross-project insights (only in main-conversation Skills, not in subagents)
Save a Claude Code feedback or project memory if the learning applies beyond this project.

If no learnings: skip. Do not create empty or boilerplate entries.
