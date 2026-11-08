# Architecture brief: check the built code against the promise recorded before the build

Problem: a run records the promise (acceptance criterion) it makes before building, but nothing afterwards checks that the finished code keeps it. The reviewer today reads the spec and the diff, never the recorded promises.

Options (no reasons given):
1. Do nothing; rely on the existing reviewers and tests.
2. Prose only: tell the existing spec-reviewer to also read the recorded promises.
3. Code builds a claims file from the record; the shared spec-reviewer takes it as an optional third input and answers per promise; a warning-only F11 check reports the answers and says visibly when no such review ran.
4. As option 3, but a divergence refuses the finished change.

Constraint: no new PR check; the reviewer is shared with another skill and must behave exactly as before without the input; an AI verdict is evidence for a person, not proof, so nothing blocks in this phase.
