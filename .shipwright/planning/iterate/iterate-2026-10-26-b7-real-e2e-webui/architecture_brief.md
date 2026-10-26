# Architecture Brief: operator-started real end-to-end check of the Brief-driven pipeline

## The problem
Every test of the Brief package pipeline runs without a real agent, so nobody knows whether a package turns into a working
chat-first app when a person drives it through the WebUI. A real run costs tokens and wall-clock time and varies from run to run.

## What already exists here
- A dry harness that validates a package and runs no model (CI).
- The WebUI repo's own isolated-stack Playwright harness, which fakes the plugin cache and the uv shim.
- The social engagement package, committed by an earlier unit.

## What would newly, permanently exist
A small Node project in this repo that an operator starts by hand, plus an answer key and a report template. It runs in no
pipeline; the operator keeps it working when the WebUI's page structure changes.

## Options on the table
- **A:** A Playwright project in this repo that drives a second WebUI instance as a user would and writes a screenshot report.
- **B:** A written manual procedure the operator follows by hand, with a checklist.
- **C:** Do nothing; rely on the dry harness and on the operator's ad hoc sessions.

## Constraints that are not negotiable
No model call in CI; no secret in the report or the repo; the WebUI repo is not changed to start.
