# Architecture brief: record what a change promises before it is built

Problem: the agent that builds a feature or change also decides, after the fact, whether it needs a written promise (acceptance criterion). Eleven changes passed with none because the author labelled them bug, tooling or no-spec.

Options (no reasons given):
1. Do nothing; keep the existing after-the-build warnings.
2. Prose only: tell the agent in the FEATURE and CHANGE paths to write the promise first.
3. Prose plus a small script that applies a fixed ask-or-decide table (existing promise changed, no owning requirement, text that describes mechanism, request that leaves open what users see) and freezes the text with a hash in the plan stub; an iterate-local advisory check reads the stub.
4. A blocking check on every pull request.

Constraint: no new PR check; under an unattended run a question stops that unit and never auto-approves.
