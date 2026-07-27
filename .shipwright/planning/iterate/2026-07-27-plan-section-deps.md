# Iterate — a section can name what it presupposes, so the order becomes checkable

- **Run ID:** `iterate-2026-07-27-plan-section-deps`
- **Date:** 2026-07-27
- **Intent:** CHANGE · **Complexity:** medium · **Spec Impact:** NONE
- **Triage:** `trg-88f721be` (high, P1) — part 2 of 3
- **Evidence:** `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  → FR-01.03 row 5

## Why this is one of three

`trg-88f721be` covers three gaps in `/shipwright-plan`. Built as one change it
came to ~5,000 diff lines — past what the Tier-3 PR review gate can read, so it
truncated and failed closed and the change could not be reviewed at all. Rather
than override the gate with a label, it ships as three PRs the gate can read.
Part 1 (reviewer verdicts) is independent of this; part 3 (the remaining Step-9
gates) needs the parser this PR introduces.

**Spec Impact: NONE.** The acceptance criterion this satisfies was already
rewritten in the REQ-3 Phase 2 content round — FR-01.03 already says *"the
section names which others it presupposes, and the order they are numbered in
never places a prerequisite after the section that needs it — stating the
dependency is what makes the order something that can be checked rather than
merely intended."* This PR is the enforcement of an existing criterion, so no
`spec.md` changes.

## Problem

`section-index.md` promises "numbers represent execution order", and Step 9
lists "Dependency Order" among its verification gates. But `SECTION_MANIFEST`
was a flat list of `NN-slug` names: **dependencies were not expressible**, so
nothing could establish the promise and a section could be scheduled before the
one that produces what it needs. `check_section_id_validity` only checked that
the numbering was gap-free, which says nothing about whether the order is
*correct*.

The module's remedy for a promise with no oracle is to change the writing: make
the dependency declarable, and the order becomes something a check can read.

## Acceptance Criteria

**AC1 — a section can name what it presupposes.** A manifest line accepts
`NN-slug: dep-a, dep-b`. A bare `NN-slug` line means "no declared dependencies"
and parses exactly as before, so every manifest written before this stays valid.

**AC2 — the numbering is checked against the declarations.** A prerequisite
appearing *after* the section that names it fails. Every dependency must be a
complete canonical section id declared in the same manifest; an unknown id, a
self-dependency, a duplicate section id, a duplicate dependency token, an
interior empty token (`01-a, , 02-b`), and an id that does not match the section
grammar all fail. A single **trailing** comma is punctuation, not a missing
dependency, and is tolerated. Diagnostics name the offending manifest line.

**AC3 — a cycle cannot pass.** No separate graph walk: "every dependency is
earlier" cannot be satisfied by a cycle, so the ordering rule subsumes cycle
detection.

**AC4 — malformed manifests never report success.** `check-sections.py` fails
and prints the line-numbered parse errors; the entries that survived parsing do
not buy a pass.

**AC5 — one parser, two readers.** The plan plugin's own gate and the phase
verifier read the manifest through the same `lib/plan_manifest.py`, replacing
two private parsers that were drifting copies kept in sync by comment only.

**AC6 — the gate runs at phase completion.** `check_section_dependency_order`
is part of `run_plan_checks`, so `_validate_plan` blocks
`update-step --step plan --status complete` on it.

## Non-goals

- Requirement coverage, section→requirement trace, and section quality — part 3.
- Raising the PR review gate's size limit; filed separately.

## Affected Boundaries

| Boundary | Producer | Consumer |
|---|---|---|
| `SECTION_MANIFEST` in `plan.md` | `/shipwright-plan` Step 4 (agent) | `lib/plan_manifest.parse_manifest` → plugin `sections.py`, `check-sections.py`, `plan_checks.py`, `plan_gate_checks.py`, `setup-planning-session.py` |

Round-trip pair: the manifest is written by an agent and read by two
independent parsers' worth of callers — now one parser.

## Design decisions

**Why `:` as the separator.** It cannot occur inside a section id (the grammar
is two digits, `-`, then `[a-z0-9-]`), so a bare line stays unambiguous and no
existing manifest changes meaning.

**Why anchored id validation.** Section ids reach the filesystem as
`sections/<id>.md`. The grammar is anchored at both ends, so a traversal
payload (`../../etc/passwd`) is rejected at parse time rather than becoming a
path.

**Why "every dependency is earlier" rather than a topological sort.** The
manifest's numbering *is* the schedule; the question is whether it agrees with
the declarations, not whether some valid order exists. The simpler rule also
gives a better diagnostic — it names the pair that is wrong.

**Why only sections of this plan.** A dependency on something already built is
not an ordering constraint on this plan, and allowing it would make the check
unfalsifiable. Those belong in the section's `## Prerequisites` prose.

## Confidence Calibration

- **Boundaries touched:** `SECTION_MANIFEST` (see above).
- **Empirical probes run:**

  | Probe | Finding |
  |---|---|
  | Wrote a `plan.md` with declarations, read it back with the shared parser | `03-api: 01-auth, 02-db` → `{'03-api': ['01-auth','02-db']}`, no order errors |
  | Read the same file with the **plugin's** parser in a separate process | Identical sections and dependencies. Separate process on purpose: the two `lib` packages collide in one interpreter (ADR-044), which is how they run in production |
  | Ran `check-sections.py` against a duplicate id, an invalid dependency token, an interior empty token and a duplicate dependency | Each exits 1 with the line-numbered parse error — pinned as five CLI cases after an external reviewer read the `success` computation without the `is_valid` guard above it and reported a bypass three times running |
  | `plan_checks.py` line count vs its bloat baseline | 315 → 285: replacing its private parser with the shared one, and moving the finder into `plan_gate_checks`, shrank it below baseline rather than needing an exception |

- **Test Completeness Ledger:** machine-readable block in
  `shipwright_test_results.json.iterate_latest.test_completeness`; every
  behaviour `tested` or `untestable` with a closed-vocabulary reason code,
  **0 testable-but-untested**.

- **Confidence-pattern check.** *Asymptote:* the parser's failure modes were
  enumerated from the negative space (what a malformed declaration can look
  like) rather than from the happy path, which is where the interior-empty-token
  and traversal cases came from. *Coverage:* every AC has a test that fails if
  the behaviour regresses, at both the library and CLI level. *Integration:*
  `cross_component` did not fire — no hook, phase-validator entry point, merge
  resolver or campaign machinery is touched; the composition that matters is
  one manifest read by both parsers, probed above.

- **Degraded conditions:** none beyond the `touches_auth` message-keyword false
  positive noted in the run's part 1.

## Rollout / blast radius

This repo has no `plan.md` (it was adopted, not planned), so the new check
returns its "nothing to verify" pass here and all behaviour is exercised by
synthetic fixtures. For projects that run `/shipwright-plan`, a manifest that
declares no dependencies is unaffected: it promises nothing about order, so
there is nothing to contradict and no migration is owed.
