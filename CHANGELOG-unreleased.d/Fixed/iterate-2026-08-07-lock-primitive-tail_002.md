The run-orchestrator's phase-tasks lock now delegates to the shared bounded, reentrant file lock instead of its own unbounded, non-reentrant implementation.
