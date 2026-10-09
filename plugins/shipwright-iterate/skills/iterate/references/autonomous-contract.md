# Autonomous contract (`--autonomous`)

An `--autonomous` iterate is **done only when its PR is MERGED with green required checks (F11 delivery) and F12 has printed its summary.** Nothing before that is a result.

## What counts as a contract violation

- A closing summary, status report or "should I continue?" before F12 — including right after a green build or a green F0.
- Skipping a phase the Phase Matrix (SKILL.md §6) requires for the run's complexity: Mini-Plan, plan review, the review cascade (Step 8), F0–F5c, F6, F11.
- Ending the turn to "wait" without a pending background task you can name.

Ending a turn while a background task you started (F0 suite, delivery watch) is still running is fine **only** if you resume when its notification arrives.

## Phase checklist (create it at the first action)

Right after the worktree exists, create one task per phase with `TaskCreate` (or `TodoWrite` when that is the available tool), in this order, and close each as you finish it — open tasks are what keeps the remaining work visible after a long build:

`Scout` · `Mini-Plan` (small FEATURE / medium+) · `Plan review` (medium+) · `Build (TDD)` · `Self-review` · `Review cascade (spec → code → doubt → external)` · `F0 / F0.5` · `F1–F5c` · `F6 commit` · `F11 push + PR + delivery MERGED` · `F12`.

Drop the rows the Phase Matrix marks `skip` for the run's complexity, and say so in the planned run summary.

## The only legitimate early stop: a recorded hard blocker

When you truly cannot proceed (delivery exit 8 non-converging, the merge needs an admin override, a decision only the operator can take, an external outage, a missing credential, a run the operator abandoned), record it **before** you stop:

```bash
uv run "{shared_root}/scripts/tools/record_hard_blocker.py" --project-root "{project_root}" \
  --run-id "{run_id}" --reason-code <non-converging-delivery|admin-merge-required|operator-only-decision|external-outage|credential-missing|abandoned-by-operator> \
  --detail "<one sentence: what blocks, what the operator must do>"
```

The F12 summary must name the recorded blocker (`code: detail`) so a self-release is visible in review; the hook also prints it to stderr when it lets the Stop through.

## Enforcement

The `iterate_stop_guard.py` Stop hook blocks every Stop of an `--autonomous` iterate whose run pointer is still live (`deliver_pr.py` retires it at MERGED/CLOSED) and names the next unfinished phase in the block reason. It lets a Stop through only after a recorded hard blocker, once its PR is MERGED out of band (below), or when the counters run out (3 consecutive blocks without a tool call in between, 40 per run). Interactive iterates are never blocked.

A run whose PR is already MERGED (merged by auto-merge or by hand, so `deliver_pr.py` never retired the pointer) is released: before blocking, the guard asks `gh pr list --head <branch> --state all` once per 2 minutes (8 s timeout; a `gh` failure counts as not merged) and records `delivered` in its state. Only a PR merged after the run started counts (a reused branch name must not release a new run); `SHIPWRIGHT_ITERATE_STOP_GUARD_GH=0` skips the call. A pointer whose worktree directory is gone never blocks; a stale pointer of an abandoned run or a long CI wait is bounded by the 40-per-run cap. Operator escape in a live session: interrupt with Esc, or have the agent record `abandoned-by-operator`; `SHIPWRIGHT_ITERATE_STOP_GUARD=0` is a launch-time kill switch (the hook inherits the environment Claude Code started with). A run pointer older than 48 h is ignored, and a session-less pointer (setup ran without `$SHIPWRIGHT_SESSION_ID`) is matched by the run id the transcript names. Autonomy is read from the LATEST iterate invocation in the transcript, so an interactive iterate started later in the same session is not held to this contract. If another Stop hook (bloat gate) also blocks, both reasons reach the agent; each is independent.
