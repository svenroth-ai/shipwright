# Constitution enforcement register — design sketch (REQ-3 Phase 3)

Filed 2026-07-24 during the Phase-2 content round
(`iterate-2026-07-23-req3-phase2-content-mono`), campaign `trg-eb19ada4`.
**Not built.** Sibling work unit to
`2026-07-24-req3-grill-trace-enforcement-DESIGN.md` — same class of problem.

## The problem (operator, 2026-07-24)

REQ-3 moves cross-cutting discipline OUT of per-phase functional requirements
and INTO `shared/constitution.md` — that is the locked architecture (FR = a
phase's output; constitution = cross-cutting discipline; QR = how well). The
move is right, but it exposes a gap:

> "how do we enforce things that we are now putting in the rulebook? it is not
> only one plugin but several … we need to have a clear list of the things that
> are in the constitution, if and where they need to be enforced."

Moving a rule from an FR to the constitution changes *where it is written*. It
does not create enforcement. And unlike an FR — which this campaign is binding
to tests, criterion by criterion — a constitution rule has **no owner, no
artifact, and no test identity**. It binds every plugin, so no single plugin's
suite is its home.

Worse, the document actively invites a false read: a `## Programmatic
Enforcement` section names **4 hooks** against roughly **40 rules**. A reader
sees a table headed "enforced by hooks" and generalises.

## The claim this buys (and the one it does not)

- **Does not**: make enforcement exist. You cannot enforce "Simplicity First".
- **Does**: make it impossible to add a rule to the rulebook without declaring
  whether, and by what, it is enforced. Prompt-only rules stay *visibly*
  prompt-only instead of being silently assumed mechanical.

Same move as the AC evidence ledger: the value is the honest split, not the
coverage number.

## Pattern to copy — it already works in this repo

`shared/config/gate_catalog.json` catalogues 47 interactive gates
(`id` · `phase` · `policy` · `constitution` · `fires` · `summary`);
`shared/config/gate_catalog.md` is **generated** from it by
`resolve_gate_policy.py --render-doc`; `shared/tests/test_gate_catalog.py` and
`test_gate_catalog_doc_sync.py` fail CI on drift. Three parts: machine-readable
catalogue, generated doc, drift test. Copy all three.

Copy the **placement** too: the render sits beside its JSON in `shared/config/`,
not under `docs/`. `docs/` holds hand-written instructions (CLAUDE.md "Where
documents live"), and a generated file kept in the tree belongs next to the
source it is generated from. So the register's render is
`shared/config/constitution_catalog.md`, not `docs/constitution-catalog.md`.
(The gate catalogue's render was moved there by
`iterate-2026-07-28-docs-placement-rule`.)

## Shape

`shared/config/constitution_catalog.json` — one entry per rule:

| Field | Meaning |
|---|---|
| `id` | stable slug, e.g. `always.tests-before-commit` |
| `tier` | `always` · `ask-first` · `never` · `pre-phase` · `escalation` |
| `text_hash` | hash of the bullet — changes when the rule is reworded |
| `binds` | which plugins the rule reaches (`*` for all) |
| `enforcement` | `hook` · `validator` · `test` · `prompt-only (mechanisable)` · `prompt-only (judgement)` · `unimplemented` |
| `mechanism` | the file that enforces it, or `""` |
| `note` | why, when enforcement is partial |

The `enforcement` vocabulary is deliberately the AC ledger's, so the two
registers read the same way and a rule that later becomes an FR (or vice versa)
keeps its classification.

## Drift test (the actual gate)

1. Every bullet in `constitution.md` has a catalogue entry — a NEW rule with no
   entry **fails CI**. This is the whole mechanism: it forces the author of a
   rule to answer "enforced how?" at the moment of writing.
2. Every catalogue entry still matches a bullet (`text_hash`) — a reworded or
   deleted rule surfaces instead of leaving a stale claim.
3. `docs/constitution-enforcement.md` equals the generated render.
4. Every `mechanism` path exists.

## Constraints

- **D7 binds.** A `prompt-only (judgement)` rule ("Simplicity First", "Surgical
  Changes") must **never** become an LLM-judged gate. Its honest ceiling is a
  drift test asserting the instruction is still present. The register's job is
  to record that ceiling, not to close it.
- The register is a **detective** artifact for classification and a
  **preventive** gate only on *declaration completeness* — never on the rule's
  own semantics.
- Anti-goal: a coverage percentage ("62 % of the constitution is enforced").
  That number would be gamed by reclassification and says nothing useful.

## Seeded rows (known at filing time)

| Rule | Enforcement | Mechanism |
|---|---|---|
| files ≤300/400 lines | `hook` | `bloat_gate_on_stop.py` (anti-ratchet) + advisory `check_file_size.py` |
| no `rm -rf`, no force-push to main, no `DROP DATABASE` | `hook` | `validate_command.sh` |
| no hardcoded secrets | `hook` | `check_secrets.sh` |
| `down.sql` for every `up.sql` | `hook` | `check_destructive_migration.sh` |
| skipping a test layer needs a reason | `validator` | `phase_validators.py::_validate_test` (unit/integration/smoke/e2e only — fidelity, performance, pgTAP-skip unchecked) |
| review cascade (spec → quality → adversarial) | `prompt-only (mechanisable)` | iterate's review-record gate is one implementation; build Step 6 is not gated |
| browser-verify on frontend change | `prompt-only (mechanisable)` | — |
| AskUserQuestion stop-after-call | `prompt-only (mechanisable)` | — |
| every AC tested at the falsifying layer (added 2026-07-24) | `unimplemented` | REQ-3 Phase 3 (criterion-level test identity, P3.1/P3.2) |
| Pre-Phase Principles 1–4 (Karpathy) | `prompt-only (judgement)` | drift test only — D7 |
| Conventional Commits | `prompt-only (mechanisable)` | — |
| test-layer blocking matrix | `validator` | `phase_validators.py::_validate_test` |

## Sequencing

Runs in Phase 3 next to grill-trace enforcement. Independent of the remaining
Phase-2 content walk — but every rule Phase 2 *adds* to the constitution (review
cascade, browser-verify, AC-layer rule) is seeded above so nothing added in the
interim lands unclassified.
