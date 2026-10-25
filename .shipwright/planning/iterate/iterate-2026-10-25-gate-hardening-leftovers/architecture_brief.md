# Architecture Brief: close the leftover gaps in the driven run's phase checks

## The problem

When the pipeline drives itself, three of its phase checks misbehave. A project built in more than one part is refused at the end of every part but the last, because the build tool files that part's finished work away before the check looks for it, so the check finds nothing and blocks a correct build. In a run where a person decides, the cap on how often a failing phase is retried only holds if the driver stops by itself; nothing refuses a fourth, fifth, sixth retry. And the code that tells "a person is no longer allowed to wave this through" apart from other failures does so by comparing a name as text.

## What already exists here

- The per-phase checks that run when a phase's result is applied, and the canon checks they call.
- The build tool's step that files a finished part away under its own key and clears the "current work" list.
- A per-run loop file that counts dispatches and check rejections of the current phase.
- The answers the driver's "what next" command can give (dispatch, complete, failed, needs validation).

## What would newly, permanently exist

One new answer from the "what next" command: "ask a person", given instead of a fifth dispatch once a guided run's failing phase is past its retry cap. The orchestrator code that already owns the loop file keeps it correct. One small new record in the loop file stores "this phase, at this attempt number, is waiting for a person" when a rejection reaches the cap. It goes stale by itself once the phase is retried afresh or finished. (Deriving the answer from the two existing counters alone was considered first, but they cannot tell a crash-resumed dispatch from one that reached the cap.) The build checks gain the ability to read a filed-away part, through one small reader that both check packages mirror.

## Options on the table

- **A:** The checks read the part being checked from where the build tool filed it; "what next" refuses to re-dispatch past the cap in a guided run, derived from the existing counters.
- **B:** As A, but store an explicit "waiting for a person" marker in the loop file.
- **C:** Move the build tool's filing step to the start of the next part, so the check still sees the work in the current list.
- **D:** Leave the retry cap to the driver's instructions and only document it.

## Constraints that are not negotiable

The run file is written only through the existing locked lifecycle helpers. The "what next" preview stays read-only. The build-checks file may not grow (it is over its size limit and grandfathered). A person's override must stay possible after the cap.
