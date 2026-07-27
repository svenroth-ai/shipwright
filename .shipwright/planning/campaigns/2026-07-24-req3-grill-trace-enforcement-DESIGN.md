# Grill-trace enforcement — FR-01.16's Phase-4 work-unit

Decided 2026-07-24 (operator), during REQ-3 Phase 2. This is the **design**.
Owner requirement: **FR-01.16 — Guided requirement elicitation** (minted Phase 1
with `Layers: unit (inferred)`).

**Where the build lands — corrected 2026-07-26, during the `.16` walk.** This
document said "the enforcement campaign (Phase 3)", and Phase 3's item list runs
`P3.0`–`P3.10` with **no entry for it**: the design sat beside the plan rather
than inside it, and the autonomous campaign would have built every item except
this one. Two things then decided the home. Phase 3 is deliberately *pure
mechanics, fully autonomous* — everything that derives or approves content was
taken out of it — while the trace itself is produced **in a conversation with a
person**. And `REQ3.09` already rebuilds the elicitation surface that would have to
emit it. So producer and verifier land in one hand instead of two
phases: this is now item (2) of **`trg-e9fa7c49`** (REQ3.09, Phase 4).
That card owns the project surface, the shared module and the drift test; the
onboarding-side trigger is **not** its work — it belongs to `trg-1aa5a8ab`,
which owns onboarding's writers and handover. The two cards had described the
same mechanism in different words, which a collision check caught.

The campaign anchor was deliberately **not** touched: its id is what the campaign
view hangs on, and superseding an anchor mid-flight moves that id.

## The problem it solves

`shared/requirement-elicitation.md` is a **prompt-only guarantee**. Empirically
proven not to hold: three times in two days, with the module open and freshly
fixed, the agent slid back to reading-then-writing, drafting solo, asking 1–2
cosmetic questions, and capturing no glossary terms. **You cannot fix a
prompt-only guarantee with more prompt** — re: [[feedback_grill_module_execute_not_cite]].
The campaign's own thesis applies reflexively: bind the guarantee to a checkable
output + a gate.

## The mechanism

Reuse the pattern iterate already ships: a **required output section** + a
**finalization verifier** (mirror of iterate's Confidence-Calibration section +
the F11 `check_*` verifiers).

### The grill-trace (produced per elicitation session, per requirement)

A structured record the surface must write as it elicits — not after:

| Field | Content |
|---|---|
| `evidence` | what was actually read — code files (adopt/iterate) or interview turns (project). Proves "look it up" (§3/§6) happened, not prompt-reading. |
| `dimensions` | each of the seven (outcome/purpose/boundaries/failure/glossary/rationale/out-of-scope): `answered` \| `assumed:<reason>` \| `n/a:<reason>`. |
| `glossary_delta` | terms sharpened during elicitation and where each was recorded. |
| `confirmed_by` | the sign-off — the hand-off from the person's mental model to the recorded one (§9). |

### The gate (fails finalization, closed vocabulary)

- **Blank dimension** → STOP. Any dimension neither answered nor explicitly
  assumed/n-a.
- **Greenfield `assumed`** → STOP. In `/shipwright-project` any `assumed` at all
  is declining to ask (§8/§12 asymmetry). Adopt permits it **iff** a work item
  was raised.
- **Undefined term** → STOP. **A term used in the requirement text that is not in
  the glossary** (framework) or `CONTEXT.md` (domain). *This is the check that
  would have forced today's glossary additions automatically* — it turns the
  operator's manual catch into a mechanism, and it is the anti-term-drift lever
  ("sonst bringt der agent immer wieder andere terms").
- **Outcome without a fit criterion** → STOP. An outcome dimension answered with
  no yes/no measure (the Volere sharpening).

### Honesty guard (do not over-gate — campaign D7)

The gate checks the **trace is complete**, never adjudicates prose quality with
an LLM. "Did the agent grill *well*" stays `untestable` (no oracle); what is
gated is that every dimension left a trace and no term drifted. Pragmatic, not
audit-grade — matches the operator's "so umfassend wie nötig, nicht umfassender".

## Why this is the highest-value work-unit in the campaign

It is the gate on the gate-maker. Every other requirement in every future
project is only as good as the elicitation that produced it; this is the one
mechanism that makes the elicitation itself non-skippable — for the real
`/shipwright-project` a user runs, not just for a well-behaved agent.

## Scope note

Cross-cutting: FR-01.16 owns it, but it binds all three surfaces
(project/adopt/iterate). Build it once in `shared/`, wire the required section
into each surface, one verifier. Same shape as the existing
`test_requirement_elicitation_refs.py` drift guard, one level up (that guard pins
the *method doc*; this gate pins the *method's use*).
