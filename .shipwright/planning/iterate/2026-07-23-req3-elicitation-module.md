# Iterate Spec: REQ-3 Phase 1 — shared requirement-elicitation module

- **Run ID:** iterate-2026-07-23-req3-elicitation-module
- **Type:** feature
- **Complexity:** medium
- **Status:** implemented
- **Campaign:** REQ-3 (`trg-eb19ada4`), Phase 1 of 4 — the grill-Modul (SPEC §5, §6.5, D13)
- **Source:** `Spec/design/2026-07-22-req3-campaign-SPEC.md`

## Goal

Build the full, shared requirement-elicitation method in `shared/` — faithful to
Matt Pocock's `grilling` + `domain-modeling` + `grill-with-docs` skills, adapted
so the loop ends in **our** artifacts (an FR row + assertion-shaped ACs under
`fr-authoring.md`), not a PRD — plus the `CONTEXT.md` domain-glossary format as a
separate shared doc. Wire it into the three requirement-authoring surfaces
(project / adopt / iterate) as a binding citation, protected by a drift test.
This is the structural twin of the `shared/fr-authoring.md` iterate.

## Design decision (operator, 2026-07-23): centralize the coverage *guarantee*

The shared module owns three binding things, so that "grill enough, everywhere"
is a contract rather than an aspiration:

1. **The method** — the grilling discipline (one question at a time + a
   recommended answer, fact→look-it-up, glossary challenge, edge-case
   stress-tests, confirm-before-acting).
2. **A universal context-coverage checklist** — the dimensions every elicitation
   MUST cover: *purpose · boundaries & edge cases · failure behaviour · glossary
   terms · the Warum/rationale (M7) · explicit out-of-scope*. Elicitation is not
   "done" until every dimension is answered **or explicitly recorded
   `Basis: assumed`** (the vocabulary `fr-authoring.md` already defines). This is
   the centralized guarantee.
3. **A shared question bank** — concrete recommended questions per dimension, so
   every plugin grills with real depth for free.

Plugins keep **only** what is genuinely domain-specific and may *add to* the
checklist but never *skip* it — project (greenfield): split boundaries,
ordering, uncertainty mapping; adopt (brownfield): infer-from-code-first,
confirm-derived-requirements; iterate (change to a finished project):
scope-of-this-change, mint-vs-fold. Deep consolidation of those flows is the
Phase-4 follow-ups (this phase only cites the module, per the operator's
"Build + cite + drift-test" answer).

M7 (Rewritability) falls out for free: "the Warum" is a mandatory checklist
dimension, so the rationale is captured *at elicitation time*, not bolted on.

## Acceptance Criteria

- [x] AC1 — Given the three requirement-authoring plugins, when requirements are
  elicited, then all three are bound to **one** shared elicitation document
  rather than three divergent interview descriptions. *(drift test: file exists +
  all three surfaces cite it)*
- [x] AC2 — Given the shared method, when it is applied, then it carries a
  universal context-coverage checklist with a hard stop-condition: elicitation is
  not finished until every dimension is answered or recorded `Basis: assumed`.
  *(drift test: the checklist section + stop-condition wording are present)*
- [x] AC3 — Given the shared method, when read, then it carries the grilling
  discipline (one-question-at-a-time-with-recommendation, fact→look-up, glossary
  challenge, edge-case stress-tests, confirm-before-acting) and attributes Matt
  Pocock. *(drift test: named sections + attribution present)*
- [x] AC4 — Given the CONTEXT.md format, when documented, then it is a separate
  shared doc that explicitly distinguishes the target-project **domain** glossary
  (`CONTEXT.md`) from the framework vocabulary (`shared/glossary.md`). *(drift
  test: file exists + retains sections + states the distinction)*
- [x] AC5 — Given a rename or delete of either shared doc, or a surface dropping
  its citation, when the suite runs, then a drift-protection test fails in both
  directions (forward: files exist & retain cited sections; reverse: all three
  surfaces cite the module) — mirroring `test_fr_authoring_refs.py`. *(mutation
  probe: remove file → test fails; restore → passes)*
- [x] AC6 — Given the shared elicitation capability, when this iterate finishes,
  then it is recorded once as a new cross-cutting requirement `FR-01.16` (Guided
  requirement elicitation) with acceptance criteria for the method, the glossary
  challenge + edge-case stress-test, the rationale/CONTEXT.md capture, and the
  coverage stop-condition. FR-01.02/11/13 are unchanged. *(spec.md diff)*

> **AC shape.** These are structural/assertion-shaped: the drift test is the
> mechanical oracle. The one thing with no deterministic oracle — "does the agent
> actually grill well given the prompt" — is `untestable`
> (`requires-manual-visual-judgment`), mitigated structurally the same way
> fr-authoring was: the completeness checklist + `Basis: assumed` stop-condition
> make *coverage* the measurable output, not prose quality.

## Spec Impact

- **Classification:** ADD (operator decision, 2026-07-23 — MINT over FOLD)
- **ADD:** `FR-01.16` (cross-cutting) — "Guided requirement elicitation", the
  shared coverage-guaranteed elicitation capability. Sibling of FR-01.14 (Triage
  Inbox) / FR-01.15 (Cross-repo output contract); next free number in group 01.
  `Basis: interview`, `Layers: unit (inferred)` (Phase 1 does not yet enforce —
  the completeness gate is Phase 3). Goes to F7 `--new-frs FR-01.16`.
- **MODIFY:** none — FR-01.02/11/13 stay unchanged; they *cite* the module
  (wiring), but the capability lives once, in FR-01.16.
- **REMOVE:** none
- **Why MINT, not FOLD, and not a Quality Requirement (operator decision):**
  - *vs FOLD.* fr-authoring refined how existing FR prose *reads* (a constraint
    on an output that already existed). This introduces a genuinely new
    **cross-cutting guarantee that none of FR-01.02/11/13 owns**: each of those
    owns "gather requirements *at my surface*"; none promises the **uniform
    coverage stop-condition** — *no requirement, anywhere, is settled while a
    context dimension is silently blank*. That guarantee spans all three surfaces
    and belongs to no single one, exactly as FR-01.14 (Triage Inbox) / FR-01.15
    (Cross-repo contract) are cross-cutting rows rather than folds.
  - *vs Quality Requirement.* A QR is *how well* another function performs
    (CI-passing, latency). This is a **capability the product provides** — it
    *does* guided, coverage-checked elicitation, with observable behaviour (the
    grilling interaction and the visible `Basis: assumed` marks). Functional, not
    a quality attribute of another function.
  - *Altitude test passes:* a product owner reads it as a guarantee the product
    makes. `Basis: interview` + `Layers: unit (inferred)` keep the row honest —
    it does **not** overclaim an enforced guarantee.
  - *Phase-1 posture (acknowledged):* in Phase 1 the guarantee is **bound by
    prompt only** — the three surfaces are instructed to follow it; nothing yet
    *audits* that the six dimensions were walked. Phase 3 (the completeness gate)
    adds the enforcement. `(inferred)` is the honest cell for that gap, the same
    deliberate honest-but-unverified posture as the campaign intends.
  - Recorded as the F3 ADR (hard-to-reverse: FR IDs are permanent).

## Out of Scope

- Rewriting the three plugins' interview **flows** — that is the Phase-4
  Adopt/Project follow-ups ("Verbreitung/einbauen"). This phase cites the module.
- Any compliance/CI **gate** enforcing elicitation completeness — Phase 3.
- Phase 2 content work (requirement-by-requirement grilling of the two repos).
- The seam-heuristic / test-backfill (Phase 2.5) and its `to-spec` source.
- The `webui` repo (equal track, its own iterate).

## Design Notes

No UI. Deliverables are two `shared/*.md` reference docs (Tier-2 markdown), a
pytest drift guard, three one-line citations, three appended spec ACs. Follows
the `fr-authoring.md` house style: binding-statement header, numbered sections,
plain language, attribution footer.

## Affected Boundaries

No serialized-format producer/consumer pair is created or changed — the
deliverables are prose docs + a test that reads them. `touches_io_boundary` does
not fire.

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| n/a | n/a | n/a |

n/a — this iterate touches no serialized I/O boundary; the drift test reads
markdown as text, not as a parsed format contract.

## Confidence Calibration

- **Boundaries touched:** one — agent-prompt → elicitation method (an
  LLM-instruction boundary, guarded by a drift test, not a unit test), identical
  in kind to the fr-authoring change.
- **Empirical probes run:**
  1. Mutation probe (both directions). The drift guard was first run with the
     two shared docs AND the three citations ABSENT → **25 failures** (22 forward:
     missing files / sections / attribution / stop-condition / coverage
     dimensions; 3 reverse: missing citations). After authoring the docs + adding
     the citations → **25/25 pass**. The guard demonstrably fires in both
     directions and is not vacuous.
  2. Blast-radius probe. Minting FR-01.16 tripped exactly the hardcoded FR-count
     pins in three integration guards (15→16). Each was extended to the true set
     with FR-01.16's *real* Basis (`interview`) and layers (`unit`) pinned per-FR
     — not loosened. All 23 catalog-contract checks green; RTM regenerated to
     carry `#fr-0116` and the deep-link resolver passes end-to-end.
  3. Full `shared/tests` suite green after the new test + FR mint:
     **4946 passed, 15 skipped, 0 failed** (338s).
  4. Runtime reachability. `shared/` is synced into `cache/shipwright/shared/`
     by `update-marketplace.sh` (CLAUDE.md; fr-authoring probe 5), so the module
     reaches the agents rather than being a dev-repo-only no-op. Verified at F11
     post-push via `check_plugin_cache_sync.py --strict`.
- **Test Completeness Ledger:** (see F5 `iterate_latest.test_completeness`)

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | Both shared docs exist and are non-empty | tested | drift test |
  | 2 | Each doc retains its cited sections (forward drift) | tested | drift test (parametrized) |
  | 3 | All three interview surfaces cite the module (reverse drift) | tested | drift test (parametrized) |
  | 4 | `context-format.md` states the CONTEXT.md-vs-glossary.md distinction | tested | drift test |
  | 5 | Matt Pocock attribution present | tested | drift test |
  | 6 | The coverage checklist + `Basis: assumed` stop-condition are present | tested | drift test |
  | 7 | Agent actually elicits full context given the prompt | untestable | requires-manual-visual-judgment — no deterministic oracle for prompt-following; mitigated: the checklist makes *coverage* the measured output, dogfooded in Phase 2 |

  0 testable-but-untested.

- **Confidence-pattern check.** Asymptote (depth): the drift guard ran clean
  after the final doc + citation edits, and the full shared suite is green — no
  "yes-then-a-finding" oscillation. Coverage (breadth): both drift directions +
  attribution + the CONTEXT.md/glossary.md distinction + the coverage
  stop-condition + the six checklist dimensions are pinned; every ledger row is
  `tested`/`untestable`, 0 testable-but-untested. Integration composition:
  `cross_component` not flagged (no merge/churn/hook/phase-validator/campaign
  machinery touched).

## Verification (medium+)

- **Surface:** none
- **Runner command:** `uv run pytest shared/tests/test_requirement_elicitation_refs.py -v`
  (the drift guard is the mechanical verification; run inside F0's full suite)
- **Evidence path:** F0 test output → `shipwright_test_results.json`
- **Justification (surface=none):** a framework prompt-docs + drift-test change
  has no startable user-facing web/cli/api surface; the pytest drift suite is the
  end-to-end oracle.
