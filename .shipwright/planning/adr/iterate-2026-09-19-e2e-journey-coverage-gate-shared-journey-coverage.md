# Shared per-journey E2E coverage oracle

**Run-ID:** `iterate-2026-09-19-e2e-journey-coverage-gate`

## Context

FR-01.06 #6b was deferred because its per-journey matcher lived only in the test plugin, while the authoritative shared test verifier cannot import plugin-private code under ADR-045. The coarse floor counted any `*.spec.ts`, allowing an unrelated spec to satisfy a plan with multiple journeys.

## Decision

Relocate the reusable plan parser, journey matcher, and text sanitizer to `shared/scripts/lib/`; keep the test-plugin modules as compatibility shims. The shared verifier now calls the shared matcher for every declared journey instead of performing a bare file-existence check.

## Consequences

Greenfield projects block when a planned journey has no matching local E2E spec. A canonical `### Flow N:` heading without a title also fails closed, while a genuinely empty User Flows section remains skipped. Brownfield gaps remain non-blocking warnings at verification time, while the test phase's producer creates one durable follow-up per uncovered journey, including when no specs exist. The established `project_facts.is_adopted_project` classification is the sole greenfield/brownfield source; existing imported plans therefore become backlog work rather than a new block. Tests pin matching, unreadable-input, malformed headings, path-containment, compatibility-shim, and zero-spec follow-up behavior.

## Rejected

Importing `plugins/shipwright-test/scripts/lib` from the shared verifier would violate ADR-045. Retaining the existence floor would preserve the known false-positive path where one arbitrary spec satisfies all planned journeys.
