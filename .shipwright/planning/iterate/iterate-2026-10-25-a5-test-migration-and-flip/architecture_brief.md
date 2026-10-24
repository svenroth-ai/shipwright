# Architecture Brief: turn the driven run's phase checks on by default

## The problem

When the pipeline drives itself, a phase's checks now exist in the step that marks the phase done, but they are switched off, so a phase that reports success with broken work still lets the run move on. Switching them on breaks about a dozen tests that complete phases with placeholder files no real check would accept, and the documentation says the checks are off.

## What already exists here

- The per-phase checks and canon checks, already run (and able to block) when the switch is on, with a capped retry, a per-autonomy outcome (ask the person / fail the phase) and a recorded override.
- A switch constant that turns those checks on or off for every driven run; tests can pass it per call.
- Each test file currently invents its own placeholder phase output.

## What would newly, permanently exist

The checks become always-on for driven runs. A small shared test helper that writes the smallest phase output the real checks accept, used by the test suites of the orchestrator plugin and the cross-plugin integration tests; the pipeline maintainers keep it in step with the checks whenever a check changes. One end-to-end test that plants a broken artifact and expects the run to stop.

## Options on the table

- **A:** Turn the checks on by default; migrate the tests to real minimal phase output through one shared helper; add the end-to-end test.
- **B:** Turn the checks on by default; tests that use placeholder output switch the checks off per call.
- **C:** Keep the default off and let each run opt in (configuration or flag).
- **D:** Do nothing.

## Constraints that are not negotiable

The test roots cannot share an imported package namespace (one test root per process; a shared `lib` package collides). The plugin must keep working in every installed layout (Claude plugin cache, its mirror, the Codex bundle, a checkout); a layout where the checks cannot load must fail closed, never pass silently.
