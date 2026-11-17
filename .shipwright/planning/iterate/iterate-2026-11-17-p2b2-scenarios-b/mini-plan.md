# Mini-plan: P2b2 - scenarios S10-S19, close-phase, coverage checks, seeded regressions (changelog pilot)

Complexity: medium. Test-support only: no skill, script or product code changes (the unchanged skill is the oracle).

## Goal
Finish the replay and its scenarios under `plugins/shipwright-changelog/tests/golden/`: the `close-phase` step
(`SKILL.md:386-414`), scenarios S10, S11a/b, S12a/b/c, S13, S14a/b/c, S15, S16a-f, S17a/b, S18a/b, S19 (plus S1d for
finding D21), their committed traces, the coverage checks P8a-c green on the unchanged skill, and three seeded
regressions caught by L2 cases (tag on `HEAD~1`, commit without pathspec, drops not deleted after the aggregation).
A full-chain comparison of the frozen Step 6, Step 7 and phase-complete blocks with the prose replaces the comparison
of the `uv run` lines only.

## Approach
1. Oracle first: each FR-01.09 AC gets an `@asserts` function; a scenario declares `Scenario.acs` and `verify` fails
   when the oracle never judged a declared AC. The P2b1 scenarios S1, S3-S9 move their literal asserts into the oracle.
2. Driver: `close-phase` (one shell, as the prose has it), `fallback-append`, `from_version`, an OS error as an exit-127
   result, a pipeline-aware version question. Citations in `replay_commands.py`.
3. Scenarios per module (`scenarios_assets`, `_branches`, `_refusals`, `_modes`); a refusal is judged by its kind.
   S13 drives the real orchestrator (`write-config`, `single-session-next` / `-apply`) and the real phase gate.
4. `coverage.py`: P8a against the inventory, P8b against the live prose (fenced blocks, conditionals), P8c against the spec.
5. `test_seeded_regressions.py`: the regression is swapped into the replay, the scenario that must notice is run.
6. Where today's prose is refused (D7, D21-D23, new D24-D26) the scenario records the refusal as today's behaviour.
7. Fold-ins from P2b1: stub warns when the local checkout cannot follow a merge, `collect(masked_status=...)`.

## Tests
One test per scenario and layout, the coverage checks with a red twin each, the seeded regressions, the stub and
trace-recorder additions in `shared/tests`.

## Alternative approach considered
One scenario module with every scenario in it - rejected: the 300-line cap and the review surface; one module per theme.
