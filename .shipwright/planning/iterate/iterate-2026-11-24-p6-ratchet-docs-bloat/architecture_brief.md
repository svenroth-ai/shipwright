# Architecture Brief: prompt-mechanics ratchet for converted skills

## The problem
The changelog skill's SKILL.md was converted so its mechanics run in code. Nothing stops a later edit from putting chained shell commands or new shell commands back into the prose. The prose file is frozen by golden locks, so an escape marker inside it would itself need an approved delta.

## What would newly, permanently exist
- A checker script and a registry file listing converted skills, their allowed commands and a capped list of exact escape blocks.
- One more gate step in the CI required job and in the local pre-push mirror.

## Options
1. Registry-held allowlist and escapes, checked by one script (the proposed change).
2. An inline marker comment in the prose to excuse a block, ratcheted by count.
3. A test inside the existing skill test root that scans the prose, with no new gate.
4. Do nothing: rely on code review of prose edits.
