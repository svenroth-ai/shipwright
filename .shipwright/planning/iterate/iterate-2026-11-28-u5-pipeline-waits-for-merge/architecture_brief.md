# Architecture Brief: the pipeline can pause a phase until an outside event (release PR merged)

## The problem

A release started by the pipeline must wait until its release pull request is merged before it tags and finishes
(operator decision). Today a phase in the pipeline can only end "done" or "failed": "done" lets the run move straight
on to hosting and tags before the merge (after a squash merge the tag sits off the main line and the next release
cannot see it), "failed" stops the run as broken although nothing went wrong.

## What already exists here

- One conversation drives every phase: `single-session-next` picks and claims the next phase, a subagent runs it and
  returns a small result (`ok` true/false), `single-session-apply` completes or fails the phase and plans the next.
- A small loop-state file next to the run configuration holds the loop's own pointers; it already records one
  "waits for a person" marker (a phase whose checks failed past the retry limit), keyed to the phase task's version,
  which makes `single-session-next` answer `ask_human` instead of dispatching.
- `single-session-resume` prints a resume card and, confirmed, re-enters the loop; a re-dispatch of a claimed phase
  rotates its version.
- The run configuration's schema is read by a separate WebUI.

## What would newly, permanently exist

A third kind of phase result, "waiting for an outside event" (only reason today: the release pull request must be
merged, with its link). The loop records it in its loop-state file, answers "waiting" with the link and what to do
until the operator resumes, and then runs the same phase again. The run plugin's loop code and its tests keep it
correct; the changelog phase (next unit) is its only producer.

## Options on the table

- **A:** an optional waiting block on the phase result, held as a marker in the loop-state file; the phase task stays
  in progress; resume clears it and re-dispatches the same phase.
- **B:** a new phase status "waiting" in the run configuration (schema value).
- **C:** the changelog phase reports "done" after preparing the release, and a separate later step (outside the
  pipeline) tags after the merge.
- **D:** do nothing: pipeline releases keep tagging before the merge.

## Constraints that are not negotiable

- No new value in the run configuration schema without the operator (the WebUI reads it).
- Every current pipeline test stays green; the change stays inert until a phase emits the new result.
- A waiting phase must never be read as done (no hosting, run not complete) nor as failed.
