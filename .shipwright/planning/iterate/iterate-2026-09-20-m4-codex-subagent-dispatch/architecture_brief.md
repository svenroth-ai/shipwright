# Architecture Brief: m4-codex-subagent-dispatch

## The problem

The Codex-driven review cascade (spec-reviewer, code-reviewer, doubt-reviewer)
has a model and a reasoning-effort policy stated in prose (AGENTS.md), but
nothing enforces it — the actual dispatch call has never passed a reasoning
effort setting, and there is no single, machine-readable place recording
which model/effort/sandbox each reviewer role runs under. A reader (or a
future reviewer of the review evidence) cannot verify from `reviews.json`
alone that three Codex-driven passes were genuinely separate invocations
under the stated policy, rather than one session's answer copied three ways.

## What already exists here

- `codex_review_transport.run_codex_review` — the actual `codex exec`
  dispatch call, one per review role.
- `record_review_pass.py` — the evidence file (`reviews.json`) each pass is
  recorded into.
- Codex CLI's own documented `.codex/agents/*.toml` custom-agent surface —
  real, but only usable from Codex's interactive TUI, not from `codex exec`
  (an upstream gap, verified empirically before this brief was written).

## What would newly, permanently exist

A generator script rendering one canonical Python role manifest to three
committed `.codex/agents/shipwright-*.toml` files (one per review role), plus
a drift test that must stay green going forward — any future edit to a
reviewer's prompt `.md` requires a regeneration commit or the drift test
fails. The `codex exec` dispatch call gains a `-c model_reasoning_effort=`
flag sourced from that same manifest. This is machinery the project keeps
running and keeps correct from now on: a contributor workflow step, a
generated-file pair to keep in sync, and a widened `reviews.json` evidence
contract (`transport_note` naming model/effort/sandbox).

## Options on the table

- **A:** Ship the generator + committed TOML files + drift test + the
  `model_reasoning_effort` argv change, as scoped.
- **B:** Skip the TOML generator entirely; only add `model_reasoning_effort`
  to the existing dispatch call, and prove distinctness with a fixture alone.
- **C:** Do nothing — leave the reasoning-effort policy as unenforced prose
  and `reviews.json` without a model/effort/sandbox evidence trail.

## Constraints that are not negotiable

- Named custom-agent dispatch from `codex exec` does not exist today (an
  upstream Codex CLI limitation, not a Shipwright choice) — whatever ships
  cannot claim to route dispatch through the TOML files.
- The repo's 300-line source-file cap and one-test-root-per-process rule.
