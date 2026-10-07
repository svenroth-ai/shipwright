# Architecture Brief: make finalization enforce what the whitepaper promises

## The problem
The framework's documentation claims that every change is tied to a requirement, every added test is bound to
the requirement it proves, every review is recorded, and every end-to-end check actually ran. Measured, only 6%
(monorepo) and 29% (WebUI) of tests carry a requirement tag, and most claimed gates are narrower than described
(they fire only when acceptance-criterion text changes, only at medium+ complexity, only on self-reported fields,
or only as agent-followed prose). A reader trusting the claims is misled; an operator relying on the gates has
holes in them.

## What already exists here
- Keystone AC gate: fires only when AC text changes in the spec diff.
- Cross-layer coverage gate: medium+ only, only for changed requirements.
- AC coverage ratchet: only newly minted unbound ACs.
- Backfill engine (test -> requirement mapping) and a completed backfill (last unit 2026-09-16).
- Review-record check (small+), test-completeness ledger (small+), surface verification (medium+),
  FR/requirement event gate (self-reported spec_impact), RTM 80% soft-block hook (plan-section metric).
- Campaign mode with dependency graph and parallel waves.

## What would newly, permanently exist
Roughly eight new or tightened finalization verifiers (test-tag binding on every changed test at every
complexity; 100-line review-cascade trigger; baseline-artifact freshness; reflection record; tighter
requirement gate; non-bypassable surface check; review record at trivial; requirement-coverage metric in the
80% hook) plus a closed-vocabulary exemption list. Each must be kept correct by every future iterate, and a
false positive blocks all future iterates.

## Options on the table
- **A:** Harden the product: new/tightened gates for each gap, executed as one parallel campaign.
- **B:** Harden only the test-tag gap (the one found in practice) and leave the other gaps as-is.
- **C:** Leave the gates, change the documentation to describe their actual reach.
- **D:** One generic "claims registry" verifier that reads a machine-readable list of promised behaviours and
  checks each one, instead of eight separate verifiers.

## Constraints that are not negotiable
Gates recompute from the git diff, not from self-reported fields. Infra failure fails closed. Existing
untagged tests must not be retroactively blocked. Files stay under the bloat caps.
