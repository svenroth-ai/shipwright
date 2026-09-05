# Architecture Brief: review-scratch-path

## The problem

On Windows, the code-review pipeline's diff/units-list handoff between a
bash step and a `uv run` Python step silently reads the wrong file, because
Git-Bash and native Python resolve the same `/tmp/<name>` string to two
different physical locations. This has already produced one confusing
downstream failure in production (a schema error masking the real path
mismatch). It affects the internal code-reviewer, the external LLM review
cascade (build, iterate, campaign sub-iterates), and campaign init.

## What already exists here

- `shared/scripts/lib/host_resource_lease.py` — a hardened private-root
  primitive already used for cross-process host-resource leases, with
  Windows ACL / POSIX permission validation.
- The session-scratchpad convention (a Claude Code harness feature) that
  already solves this class of problem for ad-hoc agent work, but is not
  reachable from inside skill-instruction prose that must work the same way
  for every consumer (build, standalone iterate, campaign sub-iterate).

## What would newly, permanently exist

A small shared module (`shared/scripts/lib/review_scratch.py` + a thin CLI)
that resolves a run-scoped scratch path deterministically and cleans it up.
It writes to a private per-user directory outside the repo and outside the
OS's shared temp root. Every future skill or agent doc that hands a file
between a bash step and a Python step in this pipeline calls it instead of
writing a bare path.

## Options on the table

- **A:** A shared Python helper that both the bash write site and the
  Python read site call independently (each re-resolving from the same
  `run_id`/`name`), keyed to a hardened private root.
- **B:** Have each Python consumer (`external_review.py`,
  `autonomous_loop.py`) accept `--run-id`/`--name` directly and resolve the
  scratch path internally, so no path ever crosses the bash/python boundary
  as a string at all.
- **C:** Store the scratch file inside the repo, under a gitignored
  directory.
- **D:** Do nothing — leave the bare `/tmp/...` literals as they are.

## Constraints that are not negotiable

- The diff/units file can contain source code or secrets — it must not be
  world-readable, and must not be a candidate for accidental `git add`.
- The fix must work identically for a standalone iterate, a build session,
  and a campaign sub-iterate runner (three different skill/agent docs, no
  shared runtime state between them beyond the filesystem).
