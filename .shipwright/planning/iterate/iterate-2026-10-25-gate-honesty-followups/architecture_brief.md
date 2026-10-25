# Architecture Brief: make the driven run's phase records say what really happened

## The problem

When the pipeline drives itself, three things leave no honest trace afterwards. A person can mark a stuck phase "skipped" and nothing records why. A phase that passed its checks looks exactly like one whose checks were never run, because the pass is only printed, never stored. And when a phase is retried after failing its checks, the earlier attempt's worker still holds a valid "I own this" ticket, so a late answer from that earlier attempt could still be accepted as the phase's result.

## What already exists here

- One record per phase in the run file (status, owner ticket, a counter bumped when a person releases a stuck phase, result, errors).
- The step that accepts a phase's result checks the ticket and the counter, runs the phase's checks, and writes an override record when a person waves a failing phase through.
- A tracked event log (phase started / completed / failed) and a separate per-run loop log.
- The release command for a stuck phase (re-run it, mark it failed, or skip it).

## What would newly, permanently exist

Two new fields on each phase record in the run file — the reason a phase was skipped, and a small summary of the check that let it finish (result, which id it was checked against, when, how many warnings). One new event kind, "phase skipped", in the tracked event log. Retrying a phase now changes its ticket counter, so only the newest attempt's answer is accepted. The orchestrator code that already owns the run file keeps all three correct; the run file's schema documents them.

## Options on the table

- **A:** Store the skip reason and the passed-check summary on the phase record; add a "phase skipped" event; change the existing ticket counter on every retry.
- **B:** As A, but fence retries with a second, separate random ticket instead of the existing counter.
- **C:** Put the passed-check summary in the existing override list (with a "passed" marker) rather than on the phase record.
- **D:** Only require a skip reason after the phase's checks have rejected it at least once.
- **E:** Do nothing.

## Constraints that are not negotiable

The run file is written only through the existing locked lifecycle helpers. A phase worker must never be able to complete, fail or override its own phase. Phase checks stay on for driven runs; nothing may switch them off at runtime.
