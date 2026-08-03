# Mini-plan: preserve complete test evidence per run

- **Run ID:** `iterate-2026-08-03-preserve-test-evidence`
- **Spec:** `.shipwright/planning/iterate/2026-08-03-preserve-test-evidence.md`

## Files and work breakdown

1. Add failing tests for exact-byte capture, attribution failures, immutable retry behavior, and transaction ordering around the F5c summary.
2. Implement a narrow shared primitive that reads candidate bytes once, rejects ambiguous/unsafe JSON attribution, and installs an immutable sibling without overwriting different bytes.
3. Wire evidence-first then summary ordering into `append_iterate_entry.py` under the existing F5c lock; cover artifact-only, summary-only, both-present, collision, and injected write-failure states. Extend bundle tests to prove F5b never runs after an F5c failure.
4. Update the real F6 staging selection, derived-snapshot/F11 integrity checks, F5c/F6/sub-iterate-runner prose, and pipeline documentation. Prove the sibling ships and the mutable root does not.
5. Keep the one-time backfill procedural and run-scoped: use explicit commit/path candidates plus sibling worktree candidates that are demonstrably dirty relative to their own HEAD; join to durable summaries, refuse collisions, and write a deterministic manifest with source and decision reasons.
6. Run the one-time backfill before any worktree cleanup; verify each recovered artifact byte-for-byte against its source and run ID against its durable summary. Treat an unavailable required source as unavailable evidence, never a substitute.
7. Run focused tests, boundary probes, full F0 suite, local CI-only guards, review cascade, external code review, and normal F0–F12 delivery.

## Test strategy

- Unit: validation states, exact bytes, collision behavior, manifest decisions.
- Integration: real temp Git repository/worktree/blob candidates and `append_iterate_entry` transaction behavior.
- CLI surface: invoke F5c/F11 against temporary projects; the backfill is a one-time operator procedure using the same validator, not a persistent command or scanner.
- Security/integrity: duplicate JSON keys, invalid UTF-8, symlink candidates/targets, canonical run IDs, exact whitespace/newline preservation, and existing secret gates.
- Full suite: one pytest root per process plus pinned Ruff and `verify_local.py`.

## Alternative considered

Embedding the complete snapshot inside `<run_id>.json` was rejected: the existing entry has a 64 KiB read bound, is a compact 50-run recency record, and consumers rely on its current summary shape. A sibling artifact preserves exact bytes without silently changing that contract.

The existing `finalize_bundle.py` already runs F5c before F5b and stops on a
non-zero F5c result; this change pins that behavior with a regression test rather
than manufacturing an unnecessary orchestrator edit.
