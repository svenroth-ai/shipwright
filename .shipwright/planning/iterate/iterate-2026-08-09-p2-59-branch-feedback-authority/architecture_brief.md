# Architecture Brief: branch feedback and lifecycle authority

## The problem

An in-flight branch can currently treat its own incomplete compliance state as the default branch's operator backlog. This causes release-owned document drift to create noise and lets a branch dismiss main-owned findings.

## What already exists here

The audit detector returns structured group coverage; the Stop hook runs it; delivery verifies a pull request; release verifies its stamped evidence commit.

## What would newly, permanently exist

A lifecycle authority boundary will decide whether detected findings are local diagnostics or may update the global backlog. It will also preserve the audit target independently from the backlog-writing tree.

## Options on the table

- **A:** One shared lifecycle authority runner used by Stop, delivery, and release.
- **B:** Three lifecycle-specific hooks with separate coverage and triage checks.
- **C:** Keep the existing Stop hook and suppress Group E only.

## Constraints that are not negotiable

Delivery must audit the delivered PR merge commit; merge scope excludes Group E; release is the sole authoritative scope for all A-I groups.
