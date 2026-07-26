# REQ-3 Phase 2 (monorepo) — Handover / Resume Prompt

Paste this into a fresh session to resume. Self-contained.

---

## What this is

REQ-3 **Phase 2, the content round** (campaign `trg-eb19ada4`), monorepo track.
Goal: give every functional requirement in `.shipwright/planning/01-adopted/spec.md`
acceptance criteria in business language — fill the empty ones, verify the rest
against the **real code**, and produce a by-product "AC evidence ledger" for the
autonomous test-backfill track (`REQ3-TB-MONO`).

**Working dir:** worktree `.worktrees/req3-phase2-content-mono` on branch
`iterate/req3-phase2-content-mono`, off `origin/main`. Run-id
`iterate-2026-07-23-req3-phase2-content-mono`. **Nothing pushed** — 7 WIP commits,
consolidated at finalization. `cd` into the worktree; use `git -C .`.

## Walk order — NON-NEGOTIABLE (added 2026-07-24 after two operator catches)

1. **The central criterion FIRST** — *what does this phase produce?* — written
   **before** the divergence table is opened. Six requirements were signed off
   without it: `.03` and `.06` had none at all, `.02` and `.05` only by
   implication, and `.07`/`.08` opened with edge cases. **Cause:** criteria
   derived from the divergence analysis inherit its bias — refusals and edge
   cases are what *stand out* when reading code; the core capability is so
   self-evident it never gets written.
2. Divergence table (enforced · prompt-only · contradicted).
3. Negative-space pass.
4. **At least two concrete failure scenarios put to the operator** (module §5).
   Three questions on `.08` found more than six walks of code-reading.
5. **Out-of-scope, explicitly** — the second systematic gap; only 3 of 17 have it.
6. Glossary terms — captured **and checked against existing entries** for
   collisions, not just appended.
7. §8 probe, then **show the criteria** before saying it is done.

Per new criterion, answer the enforcement question too (operator): if a test is
possible and missing, it goes in the enforcement list. Known finding: of eight
phase validators **exactly one** has a test, and `test_orchestrator.py` mocks
`validate_phase` wholesale.

## The method — READ THIS FIRST (the #1 recurring failure)

This round dogfoods `shared/requirement-elicitation.md` (the grill module). The
agent (me) slid back to shortcuts **three times**; the operator corrected each.
Do NOT repeat. Per requirement:

1. **Read the CODE, not the SKILL.md.** A SKILL.md is the *claim under test*, not
   evidence. Open `scripts/`, `lib/`, hooks, agent defs, tests. Sort each claim:
   **enforced** (code/hook) · **prompt-only** · **contradicted**. Split
   prompt-only into *mechanisable* vs *judgement* (D7: never an LLM-judged gate).
2. **Show the reading** — present the divergence table before writing criteria.
3. **Outcome axis** (module §8 finding 4): criteria state what must EXIST when the
   phase succeeds, with a **fit criterion** (yes/no measure) — not the workflow.
4. **Negative-space pass** (§8.1): "what should this guarantee that it doesn't?"
   Read each description-half; check the "must refuse" mirror. This found the
   biggest gaps every time.
5. **Grill one question at a time**, each with a recommendation, via
   `AskUserQuestion`. Facts → look up in code; only decisions → the operator.
6. **Capture glossary terms as you go** into `shared/glossary.md` (cap now 500).
   Skipping this is the clearest sign the grill is being cited, not run.
7. **Confirm (Abnahme) before moving on.** The operator answers "bist du
   confident?" with a PROBE, not a feeling — run the two-axis completeness check.

## Architecture decisions LOCKED (apply to all remaining)

- **The catalog DESCRIBES; triage carries the gap** (operator, 2026-07-24 —
  binding on every remaining walk). A negative-space finding becomes a **triage
  item**, never a criterion: the catalog states "what the product does", and
  writing an unbuilt promise into it turns the requirements list into a backlog.
  Keep the *true half* in the catalog where one exists, file the missing half
  (`triage_add.py --fr-id FR-01.xx`), and let a later iterate mint the criterion
  when it ships. Three cards filed this way for `.06`.
- **Read the new card's id back — never assume it.** `triage_add.py` prints the
  id in its JSON; piping it to `tail -1` shows only the closing brace. An
  assumed id cost a real card this round: the supersede note, the ledger and the
  outbox mirror all pointed at an id that did not exist, so the replacement never
  reached the main tree and the Command Center silently lost the card. Capture it
  (`json.load(...)['id']`) and verify from the MAIN tree afterwards.
- **Search the open board BEFORE filing (operator, 2026-07-25) — and read the
  status from the MAIN tree, not from the worktree.** A worktree's triage log
  only carries the status events on *this branch*; anything dismissed on main
  after the branch point still reads `triage` here. Verified the hard way: two
  items were cited as live adjacencies and are in fact **dismissed**
  (`trg-92c0c36b`, `trg-6e8121e7`) — the operator spotted it because neither
  appears in the Command Center. Resolve status with `read_all_items(<main
  repo root>)`, or merge `origin/main` into the worktree first. Anything this
  campaign touches that is already a *live* triage item must not become a
  second card.
- **The re-verification flags this round produces are NOT noise** (operator,
  2026-07-25). Touching the requirements file marks its FRs behaviour-touched
  and unreconciled, and this round will do that ~11 times. That is the
  *worklist*, not a defect: the triage cards plus the enforcement list exist so
  it can be cleared in one sweep, run alongside the WebUI track before the rest
  of this campaign. Do **not** add a criterion distinguishing text-change from
  behaviour-change to work around it.
- **One work unit per plugin, not one card per finding.** The ledger IS the
  enforcement list — every criterion, always. Triage carries only *decided*
  changes, as one action-unit per plugin. Filing per finding turns the board
  into a mirror of the ledger.
- **Every `prompt-only` row states whether a check is possible** —
  `(mechanisable)` or `(judgement)`. A bare `prompt-only` sends the autonomous
  enforcement run hunting for oracles that cannot exist (D7). Current split:
  36 mechanisable / 6 judgement.
- **A rule moved into the constitution still needs an enforcement declaration.**
  Design filed: `campaigns/2026-07-24-req3-constitution-enforcement-register-DESIGN.md`
  (Phase 3). Seed any rule this round adds into its table so nothing lands
  unclassified.

- **FR = what a phase's OUTPUT must be; constitution = cross-cutting agent
  DISCIPLINE (the how); QR = measurable how-well.** Do NOT duplicate discipline
  (TDD, review cascade, tests-green, conventional commits, no-secret, down.sql,
  destructive-confirm, browser-verify) into per-phase FRs — it lives in
  `shared/constitution.md`, hook-enforced. Memory: `project_fr_vs_constitution_boundary`.
- **The constitution reaches clients via the plugin** (single source, read by
  each skill's First-Actions "Read and follow shared/constitution.md"; verified
  project/build/iterate). No per-client copy → nothing drifts.
- **Grill-trace enforcement** is FR-01.16's Phase-3 work-unit — design at
  `.shipwright/planning/campaigns/2026-07-24-req3-grill-trace-enforcement-DESIGN.md`.
  The module is prompt-only; you can't fix a prompt-only guarantee with more
  prompt — it needs a produced trace + a completeness gate (incl. an
  undefined-term check that auto-forces glossary capture).
- **Glossary vocab:** `split` (planning unit) ≠ `section` (buildable chunk);
  "section" is overloaded (release-notes). Cap raised 300→500.

## Done (signed off) — 9 of 17 (see the ledger for per-criterion status)

| FR | Phase | Criteria | Note |
|---|---|---|---|
| FR-01.02 | project | 14 | outcome axis; strict greenfield AC obligation; dimension-trace; `assumed` banned greenfield; context-glossary |
| FR-01.03 | plan | 12 | walked + 3 revisit gaps (findings-resolved, self-contained sections, E2E journeys); kept all 12 |
| FR-01.04 | design | 11 | outcome axis; flows + approval gates (enforced) + no-production-code boundary; **linked_frs is dead code** (coverage + backflow have no data) |
| FR-01.05 | build | 5 | **trimmed** — discipline moved to constitution; kept: needs-a-section, spec-match (no-skip), mockup-match, tests-prove, one-section-one-branch |
| FR-01.06 | test | 14 | day-1 criterion was an **overclaim** — rewritten; undeclared-boundary flag promoted to its own criterion; blocking matrix deliberately NOT restated (constitution's) |
| FR-01.07 | security | 12 | folded in prompt-injection + SARIF (shipped, undescribed); criterion 1 also once asserted coverage that had been routed to triage — corrected |
| FR-01.08 | deploy | 11 | **critical defect** `trg-7c6de478` (revert ignores the version, reports success); central + out-of-scope added; 2 constitution rows trimmed |
| FR-01.09 | changelog | 9 | **critical defect** `trg-6690d175` (writer destroys an unrecognised history file); criterion 4 was factually WRONG pre-1.0 |
| FR-01.17 | host re-check | 5 | **minted** — `Basis: interview`; count pins live in THREE test files |

`.02` also got its central criterion late (2026-07-24), as did `.03`/`.05`/`.06`.
FR-01.10, .11, .14, .15, .16 already carry ACs — verify against code, do not
assume correct. FR-01.16 was Phase-1 minted.

## Remaining — three requirements, then the mint decision

All are **non-phase** requirements: they describe cross-cutting capabilities
rather than a pipeline step. Walk each with the order above.

- **`.14` Triage Inbox** (14 criteria) — collects findings from local checks and
  the code host's scans into one per-project buffer; each recorded once, each
  either promoted into real work or dismissed. Best-populated of the three; the
  walk is verification, not minting.
- **`.15` Cross-repo output contract** (**2 criteria** — under-specified) — the
  two payloads the Command Center renders field-for-field are **versioned output
  contracts**: a breaking change obliges the consumer to refuse, an additive one
  leaves it working. Expect a missing central criterion.
- **`.16` Guided requirement elicitation** (5 criteria) — the grill module
  itself, minted in Phase 1. **The requirement this whole round runs under**, so
  walk it against what actually happened here: §0 (the running order), the
  two-scenario minimum and the glossary trigger were all added *because this
  round proved the module insufficient*. Its criteria should now say so.
- Then **`/shipwright-grade`**: a shipped, marketplace-published capability with
  **no requirement at all**. Mint decision **last**, and grill before minting — a
  memory note warns its requirement model may be too coarse for one row.

## Finalization owed (do not discover these at F11)

- **doc-sync**: the constitution gained rules this round (the AC-layer rule, the
  authoritative-state rule) → `docs/guide.md` Ch 7.5 needs matching lines.
- **ADR**: the FR-vs-constitution boundary is the round's one hard-to-reverse
  architectural choice and exists in no ADR. F5c wants the field.
- **plugin-cache sync**: `shared/` changed (constitution, glossary, elicitation
  module) → **post-merge only**: `git push` → PR merged → `update-marketplace.sh`
  → `check_plugin_cache_sync.py --strict`.
- **bloat**: `shared/requirement-elicitation.md` is 409/400 — a *new* crossing
  (advisory), operator decided to leave it. Recorded in the ledger so the
  post-merge audit does not re-litigate it.

## State at the 2026-07-25 pause

- **Walked: 14 of 18** — `.01`–`.13` plus `.17` (minted this round). Remaining:
  `.14` `.15` `.16` + the grade decision.
- **Catalog grew from ~90 criteria to ~150**, and the round found **two critical
  defects**, both the same shape: a safety net reporting success while doing
  nothing, in a branch **no test covered**.
- **Enforcement list complete** — catalog criteria == ledger rows for every
  walked requirement, **zero** unclassified `prompt-only`. Roughly: 49 `enforced`
  · 12 `enforced, untested` · 38 `mechanisable` · 6 `judgement` · 23
  `unimplemented` · 4 `no-oracle` · 4 contradicted.
- **13 triage cards**, one per area, each naming the files it owns so they run in
  parallel. Verified from the MAIN tree:
  `trg-74b945bc` **CRITICAL** hosting · `trg-6690d175` **CRITICAL** changelog ·
  `trg-3f4d6b57` orchestrator · `trg-88f721be` plan · `trg-e9e5188e` requirement
  write-back loop · `trg-12b4cf3f` test · `trg-15a43b6b` security ·
  `trg-4d5b6a56` artifact stamping · `trg-10597d50` change-workflow race warning ·
  `trg-1aa5a8ab` onboarding · `trg-2f9865fb` host checks (**owns every workflow
  file**) · `trg-a8110d84` project · `trg-a1fd8125` compliance.
  **Every earlier id in this document's history is superseded** — resolve status
  from the main tree before acting on any of them.
- **Biggest single enforcement target**: 7 of 8 phase validators have no test,
  and `test_orchestrator.py` mocks `validate_phase` wholesale. Deliberately **no
  card** — that is enforcement-list work.
- **Cross-pollination worth reusing**: the change workflow's F0 runner already
  solves what the test phase gets wrong — it **proves** execution with a report
  file that exists iff pytest ran, where `.06` merely checks a number in a record
  it wrote itself. Copy, do not reinvent (`trg-12b4cf3f`).

## Key artifacts

- Spec (the catalog): `.shipwright/planning/01-adopted/spec.md`
- Iterate spec + session log: `.shipwright/planning/iterate/2026-07-23-req3-phase2-content-mono.md`
- **AC evidence ledger** (the by-product for REQ3-TB-MONO): `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
- Research (RE standards gap-check): `.shipwright/planning/iterate/2026-07-23-req3-phase2-content-mono-research.md`
- Grill-trace enforcement design: `.shipwright/planning/campaigns/2026-07-24-req3-grill-trace-enforcement-DESIGN.md`
- Campaign SPEC: `Spec/design/2026-07-22-req3-campaign-SPEC.md`

## Open findings / finalization owed (in the ledger's "Findings" section)

- **doc-sync owed:** constitution changed (review-cascade + browser-verify ALWAYS
  bullets) → check `docs/guide.md` Ch 7.5 before finalizing (CLAUDE.md rule).
- Bloat/file-size → a Quality Requirement (later QR pass), not an FR.
- External-code-review SKILL-vs-code drift (build 6c "opt-in" vs helper default True) — verify + reconcile.
- Client CLAUDE.md doesn't reference the constitution (robustness; adopt/project).
- **WebUI sister track — brief WRITTEN 2026-07-25:**
  `campaigns/2026-07-25-req3-phase2-webui-BRIEF.md`. Carries the walk order,
  the shared status vocabulary (so both ledgers feed one backfill track), the
  catalog-vs-triage rule, the Command Center/WebUI naming split, and the
  WebUI landmines: vendored gates, the cross-repo contract, and worktree-filed
  triage staying invisible until merge. Plus the hard dependency — the module
  fix only reaches another repo after this PR merges + marketplace sync.
  Still owed separately: the external-review-findings Mission display.

## Landmines

- Contract tests scan **criteria text** for filenames/symbols — no `CONTEXT.md`,
  no `.py`, no paths in an (E) line. Use "context glossary" / "a plain glossary".
- After any spec edit run `integration-tests/test_requirements_catalog_contract.py`
  + `_parsers.py` + `test_fr_table_shape_convergence.py`.
- Minting a new FR trips hardcoded 16-count pins (test_fr_table_shape_convergence,
  _parsers, _contract) — extend to the true set with per-FR Basis/Layers/priority
  pinned, never loosen. Keep `Layers: (inferred)` (bare form hard-fails).
- `check_security_scan` hook false-blocks Bash commands containing "deploy" —
  reword.
- Local `main` has unpushed triage-status appends → may bite `ensure_current` at
  F11 (git-checkout the stray, re-run).
- **Post-merge only** (NOT mid-flight): `shared/glossary.md` + constitution are
  plugin-side → after the PR merges, `bash scripts/update-marketplace.sh` +
  `check_plugin_cache_sync.py --strict`.
