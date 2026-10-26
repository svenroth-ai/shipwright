# Architecture Brief: gate catalog learns "unattended"

## The problem
A Brief-package run is meant to finish with nobody present. Today a few design approvals always stop for a human, `autonomy` knows only guided and autonomous, and the gate catalog does not cover the test and changelog phases, so a run cannot tell which stops may be answered automatically and which must always reach a person.

## What already exists here
- shared/config/gate_catalog.json (+ generated .md): one policy per gate (auto-default / orchestrator-approve / hard-stop) and a constitution lock; validate_catalog in shared/scripts/lib/gate_policy.py ignores unknown keys.
- resolve_gate_policy.py resolves a gate for the run mode only.
- The `autonomy` value (guided / autonomous) is read in the run CLI, schema enum, config factory and about 25 phase prompts; phase_gate.py already treats `unattended` as a failing terminal with no human override.

## What would newly, permanently exist
An optional reviewed `unattended_answer` per gate in the catalog with a validator rule and a pinned denylist; the resolver reports it only when autonomy is `unattended` (it never unblocks a gate itself); catalog rows for the test and changelog phases; `unattended` accepted wherever `autonomous` is.

## Options on the table
- **A:** `unattended_answer` key on the existing catalog rows, validator + denylist test, resolver reports it, master applies it later.
- **B:** A second catalog file listing unattended answers.
- **C:** Hard-code the three design approvals in the master's code; no catalog change.
- **D:** Do nothing; unattended runs always escalate every orchestrator-approve gate.

## Constraints that are not negotiable
Constitution-locked and hard-stop gates always escalate; the denylist ids are fixed by the campaign brief; the catalog markdown is generated beside its JSON; COVERED_PHASES tuple and JSON change together.
