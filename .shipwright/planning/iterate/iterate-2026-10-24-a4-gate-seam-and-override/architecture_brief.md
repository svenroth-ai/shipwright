# Architecture Brief: real phase gates in the driven pipeline run (seam, rejection, override)

## The problem

When the pipeline drives itself phase by phase, nothing checks that a phase actually produced valid work before the next one starts: a phase can report success with broken or empty artifacts and the run moves on. The same checks exist and run on the older manual path, but there they can be waved through only with a recorded reason; in the driven path there is neither a check nor a way to record that a person decided to go ahead anyway. Turning the checks on also needs an answer to "what happens when a phase fails them", which today is undefined: a rejection simply exits and the same phase is re-run forever.

## What already exists here

- Eight per-phase validators plus canon verifiers, already used by the manual (`update-step`) path, which turns a crashing check into a blocking finding and records overrides with a reason in the run config.
- The driven loop: a "next" command that claims and dispatches a phase, a subagent that runs it, and an "apply" command that validates the result shape, checks claimed files exist, and completes the phase task under a lock with a version check.
- A per-run loop pointer file with a dispatch counter (`attempt`) that is reset when the loop moves on.
- An autonomy setting (guided / autonomous) and a recovery command for failed phase tasks.

## What would newly, permanently exist

A gate step inside "apply" that runs the phase's validators before a phase is marked done, switched off by default in this change and switched on in the next one. When it fails, the phase is not completed and the master re-runs it with the list of findings, up to a fixed number of retries, then either asks the person (guided) or marks the phase failed (autonomous). A person can complete a phase over failed checks with a mandatory reason, which is recorded in the run config next to the completion. The pipeline maintainers keep it correct; the retry cap and the per-autonomy outcomes become part of the master's documented behaviour.

## Options on the table

- **A:** Gate in "apply" behind a switch (off now, on next), rejection leaves the task in progress, master retries with the findings, retry cap on the existing counter, per-autonomy terminal, override flag on "apply" that records and completes in one locked write.
- **B:** Run the validators in "apply" report-only (record findings, never block), and leave blocking and overrides to a later change.
- **C:** Let the phase subagent run its own validators and refuse to report success; no change to "apply".
- **D:** Do nothing; keep the validators on the manual path only.

## Constraints that are not negotiable

The phase-runner result contract and the apply exit codes are consumed by the master skill and tests; a stale or duplicate apply must keep its existing answer. Every phase-task state change must go through the existing lifecycle module (documented invariant). Overriding a phase gate is an ASK FIRST action in the project constitution: it needs a human decision and a recorded reason.
