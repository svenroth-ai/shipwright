# REQ-3 Phase 2 — brief for the WebUI track

Written 2026-07-25 from the monorepo track, campaign `trg-eb19ada4`. Paste into
the session that runs the same exercise in `shipwright-webui`.

The monorepo track walked nine requirements before this was written. Everything
below is a lesson **paid for** there — each one was found by the operator
catching the agent, not by the agent noticing. Read it before starting, not
after.

## Read this first: one hard dependency

The method itself lives in `shared/requirement-elicitation.md`, and its most
important section (**§0, the running order**) was added by the monorepo round
and is **not merged yet**. A WebUI session starting before that PR merges *and*
`bash scripts/update-marketplace.sh` runs will load the **old** module — the one
this round demonstrated does not work. Check §0 exists before relying on it; if
it does not, this brief carries the same content.

## The walk order — the single most valuable thing here

1. **Central criterion FIRST** — *what does this phase produce?* — written before
   any code is read. Six of eight monorepo requirements were signed off without
   it. The cause is structural, not carelessness: criteria derived from reading
   code inherit the reading's bias. **Refusals and edge cases are what stand
   out; the core capability is too obvious to write down.** A requirement whose
   first criterion is a refusal or an edge case is the signature of this failure.
2. Read the **code**, never the `SKILL.md` — a skill file is the claim under
   test, not evidence.
3. Show the **divergence table** (enforced · prompt-only · contradicted) before
   writing anything.
4. **Negative-space pass** — what should it guarantee that it doesn't?
5. **At least two concrete failure scenarios put to the operator.** Not
   optional, not answered by you. Three scenarios on one requirement found more
   than six full code-reading walks had.
6. **Out-of-scope explicitly** — what will this *not* do?
7. **Glossary: capture and check against existing entries.** Appending blind
   introduced a real ambiguity in the monorepo round.
8. **Probe, then show the criteria** — and probe whether each statement is
   **true**, not only whether a dimension is covered. That check caught a
   criterion that read perfectly and was factually wrong.

## Conventions the two tracks must share

- **The catalog DESCRIBES what the product does.** A gap found by the
  negative-space pass becomes a **triage item**, never a criterion. Keep the
  *true half* in the catalog where one exists; a later iterate ships the rest and
  mints the criterion then. Otherwise the requirements list becomes a backlog.
- **FR = a phase's output (what) · constitution = cross-cutting discipline (how)
  · QR = how well.** Do not duplicate discipline into per-phase requirements.
### Two lists, two scopes — keep them from becoming one

This is the part most easily got wrong, so it is spelled out.

| | **Enforcement list** (the ledger) | **Triage cards** |
|---|---|---|
| Holds | **every** criterion, with its status | only **decided changes to behaviour** |
| Work it implies | write the missing test · build the check for a mechanisable row · drift-test a judgement row | change the product |
| Consumed by | the enforcement / test-backfill run | an iterate |
| Granularity | one row per criterion | one card per **unit of work** |

**They must not duplicate.** A card never says "write a test" or "build the
check for this prompt-only criterion" — that work is already carried, per
criterion, by the ledger. Worked example from the monorepo: the largest single
enforcement item found there was *seven of eight phase validators have no test*,
and it correctly has **no card at all**.

**Where they touch, deliberately:** an `unimplemented` row names its card. The
lifecycle is sequential, not overlapping — the card ships the behaviour, the row
then becomes `enforced, untested`, and only then does the enforcement list owe a
test. If you find yourself writing the same sentence in both places, one of them
is wrong.

**One card per unit of work — and the unit is the MECHANISM, not the plugin.**
Start from one card per plugin, but bundle when one mechanism serves several
call sites: the monorepo ended up merging its design card and its build card
because both needed the *same* missing mechanism (declare a requirement impact,
then check that a requirements file was touched) — two plugins, one build. It
also merged a critical defect with the adjacent improvements in the same phase,
because all of them need the same file and the same live environment to verify
against. Per-plugin optimises the board; per-mechanism optimises doing it in one
pass, and the second is what matters when the work is actually picked up.
- **Every `prompt-only` row says whether a check is possible** —
  `(mechanisable)` or `(judgement)`. A bare `prompt-only` sends the autonomous
  enforcement run hunting for oracles that cannot exist (campaign decision D7:
  an LLM may adjudicate a mechanically raised flag, never raise one). The
  monorepo split came out **36 mechanisable / 6 judgement** — expect the
  buildable share to dominate.
- **Presence vs quality inside one criterion:** "recorded **with reasoning**" is
  mechanisable for *recorded* and judgement for *with reasoning*. Build the check
  for the half that has an oracle.

## Produce the same by-product

An **AC evidence ledger** for the WebUI, mirroring
`.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`:
one row per criterion, status from the shared vocabulary, so the autonomous
test-backfill track can consume both tracks the same way. Use the same status
words — a second vocabulary would defeat the purpose.

## WebUI-specific landmines

- **Naming is pinned:** **Command Center** is the product-facing name (users,
  docs, the requirements catalog); **WebUI** is the repository and codebase
  (code, commits, contracts, internal notes). One product, two registers. Do not
  invent a third — "companion app" was exactly that mistake.
- **The WebUI vendors its own copies** of the pull-request review and
  anti-ratchet gates. A monorepo fix does **not** reach them; they need their own
  iterate. Expect the same for anything shared.
- **The cross-repo output contract (`FR-01.15` in the monorepo)** binds both
  sides: the payloads the Command Center renders are versioned contracts. A shape
  change needs a version bump and a new fixture. Whatever the WebUI track writes
  about rendering must agree with the monorepo's producer-side criteria.
- **Triage filed from inside an iterate worktree is invisible** in the Command
  Center until its PR merges — the view reads the main tree's tracked log plus
  its ignored outbox. To make an item visible immediately, copy the same line
  (same id) into the main tree's outbox; the sweep's origin-delivered collection
  removes the copy once merged.

## What the monorepo track already decided — do not re-litigate

- The constitution is the single home for cross-cutting discipline, and it
  reaches every project through the plugin, not through per-project copies.
- A constitution rule still needs an enforcement declaration; a register for that
  is designed and filed as Phase-3 work
  (`2026-07-24-req3-constitution-enforcement-register-DESIGN.md`).
- Grill-trace enforcement — a produced trace plus a completeness gate — is the
  actual fix for the method being instruction-only. More prose is not.

## What to expect, based on the monorepo's yield

Nine requirements produced **two critical defects**, both of the same shape: a
safety net that reports success while doing nothing, in a branch **no test
covered**. Both were found by reading code that a skill file described
differently. In both cases the tests covered the paths that work.

Assume the WebUI has the same class of defect and look for it deliberately:
**the untested branch of anything that writes, deletes or restores.**
