# Architecture Brief: triage-dedup-recursion-guard

## The problem
A deeply-nested JSON value in a triage outbox line (or an events-log line)
makes `json.loads` raise `RecursionError`, which two existing best-effort parse
helpers do not catch. The exception propagates out of the triage log's
same-id-dedup step, crashing the caller that invoked it — for the triage side,
that caller runs inside the canonical file lock during automated worktree
setup, after the worktree directory has already been created on disk.

## What would newly, permanently exist
Nothing. This widens two existing exception-handler tuples (adds
`RecursionError`, in one case also `ValueError`) in two existing functions,
matching a pattern already shipped elsewhere in the same module family
(`lib/jsonl_records.py`, which already catches `RecursionError` at its own two
`json` parse call sites for the identical reason).
