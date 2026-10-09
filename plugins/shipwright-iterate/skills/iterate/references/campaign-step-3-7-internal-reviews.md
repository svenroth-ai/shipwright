## Steps 3.5 + 3.7 — the runner's own internal reviews (runner contract)

The body of `agents/sub-iterate-runner.md`'s internal-arm and cascade spawns, extracted so the
runner stays under its line ceiling. The runner carries the `Agent` tool (a subagent with
`Agent` in its tools list can spawn child subagents — verified 2026-10-01), so it spawns the
reviewers a standalone iterate would spawn. Where this file and `iteration-planning.md` /
`iteration-reviews.md` disagree on the *review itself*, those files win; this one owns only what
differs in a campaign unit. **Claude Code and Codextender only** — Codex Light is out of scope.
Cost: up to five reviewer runs per unit (two arms + three cascade stages).

## Rules for every spawn

- **`model=<tier>`, passed explicitly** — `review_tier` for the cascade, `plan_review_tier` for the two
  arms, both from the runner's brief (the orchestrator resolved them once; never re-resolve). Omit
  `model=` only when the tier is `inherit` (the Agent tool has no `inherit` literal). Record each row
  with `--model-tier <that tier>`. Never fall back to a hard-coded tier: a silent default can be a far
  more expensive model, and a hard-coded one overrides the operator's choice.
- **State the run id in plain text** in every spawn prompt: `This review is part of iterate run
  {run_id}.` The `SubagentStop` salvage hook can only find it in the subagent's own transcript.
- **Record the instant the reply returns**, before any other reasoning or the next spawn: write the
  reply to its canonical payload file under `.shipwright/planning/iterate/{run_id}/` and call
  `record_review_pass.py record` (shapes: `iteration-reviews.md` → *Recording each review pass*).
- **Spawn only these five `subagent_type`s** — `architecture-internal-reviewer`, `opus-plan-reviewer`,
  `spec-reviewer`, `code-reviewer`, `doubt-reviewer` — never `sub-iterate-runner`, `section-builder`,
  `browser-fixer` or `general-purpose` (no recursion or fan-out; the CLAUDE.md grant covers reviewers only).
  Cap re-review at 2 rounds per stage; on exhaustion record `not_run --reason-code delegated-to-orchestrator`.
- **Never `completed` for a pass whose subagent did not return.** "Completed by substitution"
  claims a pass that did not run.

## Step 3.5 — internal arms (medium+ effective complexity)

Before the external calls, whichever Branch A/B/C applies:

1. `shipwright-plan:architecture-internal-reviewer` over the architecture brief + the sanitized
   spec copy — never the plan or mini-plan. Procedure: `iteration-planning.md` Step 4 item 0b.
2. `shipwright-plan:opus-plan-reviewer` over the sub-iterate spec + mini-plan. Item 0.

A campaign unit has no iterate spec: write each `## Internal … Review` outcome into the F3
decision-drop, as the external architecture review does. Record `plan_internal` /
`architecture_internal` `completed` with `--recorded-by {reviewer} --model-tier {plan_review_tier}` (no payload
file). A `reject` from `architecture-internal-reviewer` HALTS THE UNIT exactly like the external
reject (`campaign-step-3-5-plan-review.md`).

Below medium: `not_applicable --reason-code complexity-below-threshold`.

## Step 3.7 — the cascade

`spec-reviewer` (Stage 1, HARD-GATE) → `code-reviewer` (Stage 2) → `doubt-reviewer` (Stage 3,
conditional) over the merge-base diff, as `SKILL.md` Step 8. A Stage-1 REJECT blocks Stage 2: fix
the diff and re-review. Record `spec`, `code` (`--from code-reviewer`) and `doubt` `completed`
(`doubt` is `not_applicable --reason-code diff-below-threshold` when Stage 3 did not apply), and set
`reviews.code.status: "completed"` in the result JSON.

**Hand the reply over, or the findings are lost.** Each `completed` cascade row names its adapter AND the
canonical reply file: `--from spec-reviewer|code-reviewer|doubt-reviewer --payload-file
"{project_root}/.shipwright/planning/iterate/{run_id}/{spec|code|doubt}_review_reply.json"`. `--recorded-by`
alone satisfies the evidence check but records `findings_count: 0` whatever the reviewer reported (a smoke
campaign recorded one low finding as 0); the recorder now prints a `warning` for that shape.

**Record the pair 3f-bis can verify.** Every `completed` `spec`/`code`/`doubt` call carries
`--verdict pass --reviewed-commit "$reviewed"` -- the HEAD the reviewed diff was taken at, captured
(`reviewed=$(git -C "{project_root}" rev-parse HEAD)`) BEFORE the spawn, never at record time (commit the code first, as Step 3.7's `git diff HEAD~1` already assumes). Code you change
after a review is code that review never saw: re-review it, or accept that 3f-bis will.

**A REJECT is never recorded `completed`** (the Stage-1 payload drops the verdict, so a `completed`
REJECT reads as a PASS). Record `spec not_run --reason-code stage-1-rejected --disposition
"Stage-1 REJECTED: {citations}"`, fix the diff, re-review, then re-record `completed` with `--force` once
it PASSes (or leave the `not_run` row on cap exhaustion). A Stage-2 high finding must be fixed before F6.

**Enforced, not just asked.** The `runner_spawn_guard.py` PreToolUse hook denies any `Agent` spawn from a
runner (recognised by the payload's `agent_type`, not by env) outside the five types, and a 4th spawn of one
type (first review + 2 re-reviews). `SHIPWRIGHT_RUNNER_SPAWN_GUARD=off` is the user's lever, not yours.

**Known limits (disclosed, not solved here).** The guard is cooperative, like the worktree gate; it does not
choose the model;
the spec/code/doubt reviewers live in `shipwright-build`, so a consumer without it takes the fallback. The
`SubagentStop` salvage hook finds the unit worktree through `loop_state.json`, so it backstops a campaign reply too. The `*_review_reply.json` files
are the runner's own evidence (F6 stages the run dir); 3f-bis writes its own copies to the same names and
commits only `reviews.json`.

## Fallback — when a spawn cannot happen

The `Agent` tool unavailable at runtime, erroring, or denied. Do not stop the unit:

- the two arms: `not_run --reason-code no-spawn-site`, disposition naming the failure. The
  orchestrator has no internal-arm spawn site, so these are never promoted;
- `spec` / `code` / `doubt`: `not_run --reason-code delegated-to-orchestrator` (commands:
  `iteration-reviews.md` → *Campaign sub-iterate rows*), `reviews.code.status:
  "delegated_to_orchestrator"`. The orchestrator's `campaign-mode.md` **3f-bis** runs the cascade
  before the merge and promotes those rows with `--force`. 3f-bis ALSO
  runs for a unit whose runner spawned the cascade whenever its own trigger fires: the runner's rows are
  its own attestation, so they never replace that gate (it re-promotes them with `--force`). Below
  3f-bis's trigger the runner's rows stand, as `not_run` rows always did. Above it, `3f-bis` skips its
  re-review only when `review_attested.py` confirms the pair above (verdict `pass`, a `reviewed_commit`
  that is an ancestor of the head it merges, and nothing but `.shipwright/` / `CHANGELOG-unreleased.d/`
  changed since); a legacy row, a missing field or later code takes the cascade as before.
