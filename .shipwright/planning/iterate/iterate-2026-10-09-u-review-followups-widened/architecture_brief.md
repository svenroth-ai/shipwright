# Architecture brief: widened U0/U3/U4/U10 review follow-ups

**The change adds** one new module (`lib/review_capture_redact.py`), one new field on the F5c iterate entry (`risk_flags`), one new key on every external-review envelope (`capture: {run_id, at}`), and one new closed reason code (`stage-1-rejected`).

**The problem.** (1) A Stage-1 spec REJECT is recorded under a reason code that says "delegated". (2) A small run whose `plan.json` / `risk_recheck.json` are missing reads as "no risk flags". (3) A rebase-merged PR is size-measured by its last commit. (4) An `unavailable` review claim is backed by an envelope nothing ties to the run, and the stderr capture that ships in the run dir may carry URLs or tokens. (5) Several recorder rough edges (null marker reason on repair, `--force` blocked on a skipped row, post-hoc `reason_code` attach).

**Options for the durable-flags and provenance problems**
- A. Persist the data in the F5c entry / adapter envelope and make the gate treat absence as unknown.
- B. Leave the sidecar files as the only source and document "keep them".
- C. Have the writer (`append_iterate_entry`) compute and stamp the flags itself.
- D. Do nothing; keep the accepted limits.

**Options for redaction:** mask at record time; mask in the adapter before it prints; strip the stderr from the commit entirely.

**What would make this wrong:** a gate that turns "unknown" into "fired" for runs that legitimately have no sidecar; an envelope stamp the agent can hand-write; redaction patterns that miss a provider's secret shape.
