# Mini-plan: P2b1 - replay driver and scenarios S1-S9 (changelog pilot)

Complexity: medium. Test-support only: no skill, script or product code changes (the unchanged skill is the oracle).

## Goal
Deliver `driver_replay.py` (today's SKILL.md prose as per-step replay commands, each citing its line), the oracle,
scenarios S1, S1t, S2g/a/u, S3/S3b, S4, S5a/b, S6, S7a/b/c, S8, S9 under `plugins/shipwright-changelog/tests/golden/`, and
generated `*.trace.json`; green on the unchanged skill. Plus six hardening items for the P2a harness (gh stub local
checkout after merge, dummy GH_TOKEN and uv dirs, per-command short flags, body masking, freeze-checker note).

## Approach
1. Harness hardening first (test-first): stub `pr merge --delete-branch` leaves a checkout on the head on the merged base,
   per-command short-flag map, dummy GH token, uv cache dirs pass-through, mask PR title/body and body flags in the trace.
2. `replay_commands.py`: citation table (line + needle per command) and frozen copies of the three shell chains.
3. `driver_replay.py`: ReplayDriver over the driver interface; commands run through the scratch's explicit environment.
4. `oracle.py`: FR-01.09 AC checks that import nothing from the tools; `scenarios_*.py`; `verify()` compares the
   normalized trace with the committed file (`SHIPWRIGHT_GOLDEN_REGEN=1` rewrites).
5. Where the literal prose is refused (D21-D23: pathspec, tracked drop deletion, staged event leave a dirty tree for the
   release audit) the scenario records the refusal as today's behaviour and the findings file carries it.

## Tests
Scenario tests per layout (S1, S2: legacy and drops); citation tests; trace stable across two runs; harness tests.

## Alternative approach considered
Reading the prose's bash blocks live from SKILL.md instead of frozen copies - rejected: P5 rewrites the prose, so the
replay would drift with it.
