# Iterate Spec: REQ-3 Phase 2 — content round, monorepo

- **Run ID:** iterate-2026-07-23-req3-phase2-content-mono
- **Type:** change
- **Complexity:** medium
- **Status:** planning
- **Campaign:** REQ-3 (`trg-eb19ada4`), Phase 2 of 4 — the content round (SPEC §5)
- **Source:** `Spec/design/2026-07-22-req3-campaign-SPEC.md`
- **Method under test:** `shared/requirement-elicitation.md` (built in Phase 1,
  iterate-2026-07-23-req3-elicitation-module). **Phase 2 IS its acceptance test**
  (campaign D13) — if the method proves mis-shaped here, we correct it here.

## Goal

Bring the monorepo's functional-requirement catalog to a state where every row
says, in business language, what the product does — and every row carries
acceptance criteria a test could be bound to. Fill the 7 requirements that carry
no criteria at all; verify the 9 that do against the real code for completeness
and correctness. Produce, as a by-product, the list of criteria that no test
proves — the input the autonomous test-backfill track needs.

This is the human content round. Phase 3 turns the result into mechanism
(AC identity, binding, the keystone gate); it cannot do so over criteria that
are missing or wrong.

## Scope decision (operator, 2026-07-23)

Opened from "fill the 7 empty" to **all 16 rows**. The operator's reasoning,
recorded because it changed the plan: *the existing criteria may themselves be
incomplete against the code.* A criterion that reads well but no longer matches
what the code does is worse than an absent one — Phase 3 would bind a test to a
false statement and the gate would defend it.

**Working rule for the 9 that already have criteria:** propose a change only
where (a) the code genuinely contradicts a criterion, or (b) a real guarantee
the capability makes is uncovered. No style rewrites of criteria that are
already correct — that is churn, and it costs merge conflicts on the one file
every parallel iterate touches.

## Method (the grill module, applied)

Per `shared/requirement-elicitation.md`:

1. **Facts are found, not asked (§3, §6).** Code scan first, per requirement:
   read the skill definition and its references — the authoritative statement of
   what each phase does — plus the scripts that carry the guarantees. Every
   question the code can answer is answered from the code.
2. **One question at a time, each with a recommendation (§2).** Only genuine
   decisions reach the operator, via `AskUserQuestion`, one per turn.
3. **Coverage checklist (§8)** per requirement: purpose · boundaries & edge
   cases · failure behaviour · glossary terms · rationale · out of scope. A
   dimension is answered or recorded `Basis: assumed`. Never silently blank.
4. **Confirm before acting (§9)** before the criteria are written.
5. **Output lands in our artifacts (§10)** — assertion-shaped `- (E) Given …
   when … then …` criteria under `shared/fr-authoring.md` rules, not a PRD.

## Acceptance Criteria

- [ ] AC1 — Given the monorepo requirements catalog, when this iterate finishes,
  then every live functional requirement carries at least one assertion-shaped
  acceptance criterion and none reads `TBD`. *(mechanical: TBD count = 0)*
- [ ] AC2 — Given the 9 requirements that already carried criteria, when each is
  checked against the code that implements it, then every divergence found is
  either corrected or recorded as a known gap, and no correct criterion is
  rewritten for style alone. *(diff review)*
- [ ] AC3 — Given the walk over every requirement, when it completes, then a
  by-product list names each acceptance criterion that no test proves, scoped to
  the whole catalog, in a form the test-backfill track can consume as work
  items. *(artifact exists, one row per unproven criterion)*
- [ ] AC4 — Given a capability the product ships but the catalog does not
  describe, when the completeness scan finds it, then it is raised as a
  mint-or-fold decision rather than silently left out. *(finding: `/shipwright-grade`)*
- [ ] AC5 — Given `Layers` cells, when this iterate finishes, then every cell is
  still the honest `(inferred)` form — this round establishes content, not
  verified coverage; promotion is Phase 3 and the bare form hard-fails without
  AC-bound tests. *(spec diff: no bare Layers cell introduced)*
- [ ] AC6 — Given the grill module is being acceptance-tested by this round,
  when the round finishes, then any point where the method proved mis-shaped is
  recorded, and either corrected in `shared/requirement-elicitation.md` in this
  same diff or written down as a Phase-4 follow-up. *(reflection section)*

## Spec Impact

- **Classification:** MODIFY (primary) — pending operator decision on one ADD.
- **MODIFY:** FR-01.03, .04, .05, .07, .08, .09, .12 — criteria authored where
  the block reads `TBD`. Plus corrections to any of FR-01.01, .02, .06, .10,
  .11, .13, .14, .15, .16 where the scan finds divergence from the code.
- **ADD — decided, TWO not one** (recorded 2026-07-26, after an external review
  read this section against the diff and correctly called it out of date; the
  decisions were the operator's, this document had simply not been updated to
  carry them):
  - `FR-01.17` — **Independent re-check on the code host** (minted 2026-07-24).
    Not in the original plan. It surfaced while walking `.08`/`.09`: the
    guarantee that every proposed change is re-checked away from the author's
    machine was enforced in the workflows and described nowhere. Operator
    decided to mint it, so it took the next free number.
  - `FR-01.18` — **`/shipwright-grade`** (minted 2026-07-26). Still the ADD this
    document anticipated, at the next free number *after* `.17` rather than at
    `.17` itself. Deliberately taken **last** and grilled before minting, per
    the plan below.
- **REMOVE:** none.
- **`Basis` (pending decision):** the 7 filled rows are `Basis: code` today —
  derived from source, never confirmed by a human. Once the operator confirms
  them in this round, `interview` is the honest value. That is precisely the
  transition the grill module §6 exists to produce.

## Out of Scope

- The WebUI repo — an equal, separate track with its own iterate (campaign D6).
- All of Phase 3's mechanism: AC identity/IDs, manifest v4, tag grammar,
  binding, `Layers` promotion, the keystone gate.
- **Writing** the missing tests. This round only *names* them; the writing is
  the `REQ3-TB-MONO` backfill track (campaign §5, Phase 2.5).
- Quality requirements and constraints — the round is about functional
  requirements. **One deliberate exception, decided 2026-07-25:** `C-02` was
  added while walking `.13`. "Nothing is written into the project's own
  settings" turned out not to be a phase deliverable at all but a property of
  how the framework installs itself, so it belongs with the constraints rather
  than being duplicated into two requirements. Removing it from both without
  giving it a home would have lost a real guarantee.
- Re-grilling correct criteria for style.

## Affected Boundaries

No serialized producer/consumer pair is created or changed. The deliverables are
a markdown requirements catalog and a markdown by-product list.
`touches_io_boundary` does not fire.

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| n/a | n/a | n/a |

## Session log — resume here

**Day 1 (2026-07-23). The round was restarted once, deliberately.**

The first pass read `SKILL.md` prose instead of code, bulk-authored ~60 criteria,
and minted an FR ID — caught by the operator. Restarted properly. See
[[feedback_grill_module_execute_not_cite]].

### Done

- **FR-01.03 `/shipwright-plan`** — fully walked against real code. 9 criteria.
  1 of 7 original claims was enforced; 4 prompt-only; 1 uncheckable as written;
  description was factually wrong (review presented as inherent, is declinable).
- **FR-01.02 `/shipwright-project`** — partially walked. Duplicate "no prompt
  hook" guarantee resolved (removed from FR-01.01, which does not set projects
  up). Sentence-hygiene criterion split into its mechanical and judgement halves.
  **Not yet written: the outcome-axis criteria** (playback delivered, operator
  agreed the axis, criteria not yet in the file).
- **Glossary** — `split` and `section` defined; the "section" overload with
  release notes called out.
- **FR-01.07** — description corrected (drives fixes only inside a managed
  project). Verified in code.
- **The module itself** — 5 findings fixed + research-driven sharpenings, drift
  test extended from 28 to 32 assertions, mutation-probed (4 new assertions fail
  when reverted, pass when restored).
- **Evidence ledger** started: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
- **Research gap-check**: `…-content-mono-research.md` — no dimension missing.

**Day 2 (2026-07-24).** Four requirements walked; the round's architecture was
settled and two structural findings came out of it.

- **FR-01.02 `/shipwright-project`** finished — 14 criteria, rewritten on the
  outcome axis (what must exist in the catalogue, not how the interview runs).
- **FR-01.04 `/shipwright-design`** — 11 criteria. `linked_frs` found to be dead
  code (coverage + backflow have no data).
- **FR-01.05 `/shipwright-build`** — **trimmed 11 → 5.** The operator caught that
  most of what had been written was cross-cutting agent discipline, not build's
  output. **Architecture locked: FR = a phase's output (what) · constitution =
  cross-cutting discipline (how) · QR = how-well.** Discipline moved to the
  constitution (review cascade + browser-verify added there this round).
- **FR-01.06 `/shipwright-test`** — 1 → 13. The single existing criterion was an
  **overclaim** (promised proof of a round trip from a name-mention heuristic
  over hand-declared pairs) and was rewritten honestly; the undeclared-boundary
  flag was promoted to its own criterion.

**Two structural decisions, both binding on the remaining walks:**

1. **The catalog describes; triage carries the gap.** Three FR-01.06 criteria
   described things the product does *not* do. The operator rejected marking
   them ("dann wird die requirements liste zum backlog"). The rule now: a
   negative-space gap becomes a **triage item**, never a criterion; keep the
   *true half* in the catalog where one exists; a later iterate delivers it and
   mints the criterion **then**. Filed `trg-737d0449`, `trg-30fc1fc6`,
   `trg-3a4466e5`, all stamped `FR-01.06`.
2. **The rulebook needs an enforcement register.** Moving discipline into the
   constitution does not create enforcement, and its `## Programmatic
   Enforcement` table names 4 hooks against ~40 rules. Design filed as a Phase-3
   work unit: `…-req3-constitution-enforcement-register-DESIGN.md` — per-rule
   "enforced by what", copying the `gate_catalog.json` pattern; the gate is
   *declaration completeness*, D7 still binds.

**Where the test pyramid landed** (operator question): four homes, not one — the
layers + blocking matrix were already constitutional; "every AC tested at the
layer that can falsify it" became a constitution ALWAYS bullet; "which criteria
have no test" is compliance's report + Phase 3; coverage % is a QR.

**Asymmetry recorded for `.11`:** iterate's test-gate criteria promise
concurrency-correctness and infra-retry but no honest result — nothing says an
empty run, or a unit that could not start, is not a pass. Security has that
guarantee, test now has it, iterate does not.

**Triage visibility gap found (generic, not this round's):** an item filed from
inside an iterate worktree is invisible in the WebUI until its PR merges — the
WebUI reads the *main tree's* tracked ∪ outbox. Worked around by copying the
three cards (same ids) into main's gitignored outbox; the sweep's
origin-delivered GC cleans them once merged. Worth its own triage item —
deliberately not filed mid-round without an operator call.

### Next, in agreed pipeline order

`.07 security` (9 existing criteria — verify against code, do not assume
correct) → `.08 deploy` → `.09 changelog` → `.10 compliance` → `.01 run` →
`.11 iterate` (**same trim as build**; plus the honest-result asymmetry above) →
`.12 preview` → `.13 adopt` (**decide the 3 cross-cutting rows** — hook posture,
starting guidance, criteria obligation; the brownfield half of journey coverage
lands here too) → `.14/.15/.16` (verify) → `grade` (mint decision last, grill
first).

**The 6 blocks bulk-written on day 1 (`.04 .05 .07 .08 .09 .12`) are DRAFTS from
prose, not verified.** They must each get the FR-01.03 treatment before this
run finalizes. The ledger says so too.

### WebUI follow-ups (cross-repo — not built here)

- **External-review findings in the Mission view** (operator, 2026-07-24). The
  monorepo already logs external-review findings (`decision_log`, `external_review.py`
  output). FR-01.03's new "findings addressed or rejected-with-reason" criterion
  makes them first-class; the WebUI Mission surface should display them. WebUI-side
  work, its own iterate.

### Watch items

- Three guarantees now point at both project and adopt (hook posture, starting
  guidance, criteria obligation). If adopt needs all three, that is the evidence
  they want one cross-cutting row instead of three repetitions — decide at `.13`.
- `/shipwright-grade` has no requirement at all. Mint deferred until grilled; a
  memory note warns its requirement model may be too coarse for one row.
- `shared/tests/test_requirement_elicitation_refs.py` crossed 300 lines (326).
  Non-blocking, but a split is worth offering at finalization.
- Local `main` has unpushed triage-status appends that may bite `ensure_current`
  at F11.

## Confidence Calibration

- **Boundaries touched:** {to be completed before F0}
- **Empirical probes run:** {to be completed before F0}
- **Test Completeness Ledger:** {to be completed before F0}
- **Confidence-pattern check:** {to be completed before F0}

## Verification (medium+)

- **Surface:** none
- **Runner command:** `uv run pytest shared/tests/ -q` (catalog-contract and
  requirement-hygiene guards are the mechanical oracle for the spec edit)
- **Evidence path:** F0 test output → `shipwright_test_results.json`
- **Justification (surface=none):** a requirements-catalog content change has no
  startable user-facing surface; the catalog-contract test suite plus the
  compliance Group-I hygiene checks are the end-to-end oracle.
