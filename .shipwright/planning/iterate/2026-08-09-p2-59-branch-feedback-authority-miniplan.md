# Mini-plan: branch feedback and lifecycle authority

- **Run ID:** `iterate-2026-08-09-p2-59-branch-feedback-authority`

1. Add a small shared lifecycle authority module that defines scopes, expected versus not-applicable group coverage, exact-tree resolution, and guarded backlog mirroring. Test the distinction between `not_applicable` and `missing` directly.
2. Route the compliance Stop hook through branch-feedback authority. It will still print local audit diagnostics but cannot write global triage.
3. Integrate merge authority into delivery after the tool has verified `DELIVERED`; resolve the merge SHA from the delivered PR and audit a detached exact-SHA tree, while targeting the global default-tree backlog.
4. Add release authority after the existing stage/commit/verify contract, without changing the seven-document producer.
5. Cover branch E drift, branch non-E failures, incomplete merge coverage, merge A-D/F-I refresh, full release convergence, and the 5 → 13 → 5 regression. Update lifecycle docs.

## Alternative considered

Use three independent hooks that each duplicate coverage and triage logic. Rejected because the authority matrix would drift across lifecycle paths; one shared runner keeps the distinction between detection target, backlog target, and scope testable.
