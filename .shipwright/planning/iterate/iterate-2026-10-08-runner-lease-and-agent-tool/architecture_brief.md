# Architecture Brief — runner-lease-and-agent-tool

**Problem.** A campaign sub-iterate runner (a subagent) (1) cannot record its worktree in loop_state.json because its lease-touch command omits the fencing token, and (2) cannot run any internal review because it has no `Agent` tool, so plan_internal, architecture_internal and the spec/code/doubt cascade are recorded not_run and left to the orchestrator.

**Options.**
1. Do nothing: keep delegating the cascade to the orchestrator; document the lease failure.
2. Give the runner the `Agent` tool and have it spawn the reviewers itself (model=opus); keep the orchestrator cascade as a fallback; skip the orchestrator's re-review when the runner already recorded the passes completed.
3. Move the whole cascade permanently to the orchestrator and add the two internal arms there as well.
4. Write the unit's worktree at claim time in code (loop_claim) instead of fixing the runner's touch command.

**Permanent additions.** One new reference doc; a runner_settled handoff file in the orchestrator's per-unit run dir; one tools-list entry.
