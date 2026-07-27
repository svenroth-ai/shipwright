# Iterate — the Step-9 gates stop being instructions and become code

- **Run ID:** `iterate-2026-07-27-plan-step9-gates`
- **Date:** 2026-07-27
- **Intent:** CHANGE · **Complexity:** medium · **Spec Impact:** NONE
- **Triage:** `trg-88f721be` (high, P1) — part 3 of 3, closes it
- **Evidence:** `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  → FR-01.03 rows 2, 3, 3b, 4, 9

## Why this is one of three

`trg-88f721be` covers three gaps in `/shipwright-plan`. Built as one change it
came to ~5,000 diff lines — past what the Tier-3 PR review gate can read, so it
truncated and **failed closed**: the change could not be reviewed at all. Rather
than override the gate with a `skip-pr-review` label, it shipped as three PRs
the gate can read. Parts 1 (#456, reviewer verdicts) and 2 (#457, section
dependencies) are merged; this closes the item.

The split worked on its own terms: PR Review passed on both, so nothing was
waved through.

**Spec Impact: NONE.** All five criteria this enforces are already in FR-01.03
from the REQ-3 Phase 2 content round — every requirement lands in a section,
every section traces back to one, each section says what it is for with two
steps and a test strategy, a section is self-contained, and the review route is
on record before dividing begins. This is the enforcement of existing criteria.

## Problem

`SKILL.md` Step 9 lists seven "verification gates (**all must pass**)". Four
existed only as instructions to the agent:

- **no FR coverage check.** `check_fr_orphans_in_plan` looks only *outward* — a
  cited FR must exist in the spec. Nothing established that every requirement
  was covered.
- **no section→requirement trace.** A section recorded no requirement link at
  all, so a plan could quietly add work nobody asked for — which the
  constitution forbids in prose (YAGNI) and nothing enforced. This is also what
  made coverage uncheckable: there was no link data in either direction.
- **no section-quality check.** Zero code anywhere in the plugin.
- **the in-session review gate was prose.** Step 6 opened with "Read the
  marker. If missing, STOP" — an instruction, not a command.

## Acceptance Criteria

**AC1 — every requirement lands in at least one section.** Linkage is read from
one explicit `Requirements:` line in the section file, never a prose scan for
`FR-NN.NN`. A live FR in the split's `spec.md` that no section declares fails.

**AC2 — every section traces back to a requirement.** A section whose
`Requirements:` field is absent or empty, or which names only ids that are not
live FRs of its split, fails.

**AC3 — requirement ids are parsed, not mined.** Each comma-separated token
must match the canonical FR-ID grammar **in full**. `FR-01.01x` and
`not-FR-02.02-example` are reported as linkage errors, not credited as
`FR-01.01` — an unanchored search would let a typo in the one machine-readable
field satisfy both coverage directions.

**AC4 — every section states purpose, ≥2 steps, and how it is tested.** The
accepted headings are a defined closed set, and the section-writer prompt plus
the `section-splitting.md` template emit them. A failure names the missing part
and the heading it expected.

**AC5 — the in-session gates are runnable.** `check-plan-gates.py
--gate review|sections|all` exits non-zero when a gate fails, so Step 6's "STOP"
and Step 9's checklist are commands.

**AC6 — the gates run at phase completion.** All four are in `run_plan_checks`,
so `_validate_plan` blocks `update-step --step plan --status complete` on them.

**AC7 — a plan written before the formats is flagged, not stranded.** Adoption
is decided **per split, from the presence of the field** — a section that writes
`Requirements:` and leaves it empty has adopted the format and failed it, which
is not the same as a plan that predates it. A split showing no sign of a format
warns (`strict_exempt`, naming the migration) instead of failing. The
in-session gate is strict regardless: a plan being written today complies.

## Non-goals

- Raising the PR review gate's own size limit — the reason this work needed
  splitting at all. Noted for follow-up rather than bundled in.
- Registering the new checks in the compliance Group C adapter
  (`audit_adapters.REQUIRED_SYMBOLS`): that registry is a curated iterate-12
  subset with a pinned count, and the plan **phase validator** is the
  enforcement point for the plan phase. Deliberate boundary.

## Affected Boundaries

| Boundary | Producer | Consumer |
|---|---|---|
| section `.md` files (`Requirements:` + headings) | `section-writer` subagent / hand-authored | `lib/plan_section_quality`, `plan_gate_checks`, `check-plan-gates.py`, `/shipwright-build` |
| `external_review_state.json` | `mark-review-state.py` (part 1) | `check-plan-gates.py --gate review` joins `W5` + the resume gate on `evaluate_review_state` |

## Design decisions

**Why one explicit `Requirements:` field.** A prose scan would count an id named
in an example, a rationale, or a retired-history note as coverage, and would
teach authors to sprinkle ids to satisfy the gate. One field, parsed in one
place, also gives `/shipwright-build` the same linkage the gate uses.

**Why anchored token parsing.** The repo has been bitten by the same shape
before — a tag regex that let `@FR-01.03x` expose a valid `@FR-01.03` prefix.
The field is machine-readable or it is an error, with no middle ground that
quietly counts as coverage.

**Why adoption is per split, not per section.** Deciding per section would let
one unrecognised file in an otherwise modern split hide as "legacy". As soon as
one section adopts, the split is held to it.

**Why the in-session gate is strict where the verifier is lenient.** The
verifier walks every split, including ones written months ago, so leniency is
what keeps it from stranding them. The in-session gate reads the plan being
written now, which has no excuse.

## Confidence Calibration

- **Boundaries touched:** section `.md` files; the review marker (read-only
  here, via the shared evaluator from part 1).
- **Empirical probes run:**

  | Probe | Finding |
  |---|---|
  | Ran the FR-token parser against `FR-01.01x, not-FR-02.02-example, FR-01.03` | Reproduced the over-match before fixing: the first two were credited as live ids. Now `('FR-01.03',)` with the other two reported as linkage errors |
  | Drove both gate CLIs (`--gate review`, `--gate sections`) as subprocesses against a seeded split | Each blocks on its own failure and exits 0 on a clean plan; `--gate` runs only what was asked for |
  | Seeded one failure per gate through the real `run_plan_checks` | All four block phase completion individually; a clean plan trips none of them (the complement, so a gate failing unconditionally cannot satisfy the set) |
  | `plan_checks.py` line count vs its bloat baseline | 315 → 295: the four gates live in `plan_gate_checks.py`, so registering them shrank the file rather than ratcheting it |

- **Test Completeness Ledger:** machine-readable block in
  `shipwright_test_results.json.iterate_latest.test_completeness`; every
  behaviour `tested` or `untestable` with a closed-vocabulary reason code,
  **0 testable-but-untested**.

- **Confidence-pattern check.** *Asymptote:* the linkage parser's failure mode
  (a token *containing* an id) was found by an external reviewer, not by the
  happy path — and it is the second time this repo has hit that exact shape, so
  the depth here came from recognising a known class rather than from more
  thinking. *Coverage:* every AC has a test that fails if the behaviour
  regresses, at library, CLI and phase-validator level. *Integration:* the
  composition that matters is "the gate the SKILL tells you to run is the gate
  that blocks completion" — covered by
  `test_verifiers_plan_gates_wiring.py`, which drives the real
  `run_plan_checks` per gate rather than the checks in isolation.

- **Degraded conditions:** none new. (The `touches_auth` message-keyword false
  positive noted in part 1 applies to the whole work unit.)

## Rollout / blast radius

This repo has no `plan.md`, so all four gates return their "nothing to verify"
pass here and the behaviour is exercised by synthetic fixtures. For projects
running `/shipwright-plan`, a split that never adopted either format warns with
a migration hint rather than failing; one that has adopted is held to it.
