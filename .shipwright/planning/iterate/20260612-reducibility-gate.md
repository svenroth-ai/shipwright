# Iterate Spec — Reducibility Reviewer Gate (LOC becomes a router, not the verdict)

- **Run ID:** `iterate-2026-06-12-reducibility-gate`
- **Intent:** CHANGE (modify the bloat gate's verdict mechanism)
- **Spec Impact:** MODIFY
- **Complexity:** medium (repo-scout override of classifier `small`)
- **Risk flags:** `touches_shared_infra` (shared/ reference + `shared/profiles/`)
- **Anchor:** `trg-af476d87` (filed PR #219, iterate-2026-06-12-bloat-h1-h2-cleanup)
- **Design:** agreed over 3 turns + Codex review; recorded in the anchor +
  memory `project_intelligent_bloat_gate`. This iterate BUILDS the gate;
  the catalog was already dogfooded on 8 H1 files in PR #219.

## Problem

The bloat machinery today has only a **quantitative** verdict: a file over
300 LOC (source) / 400 LOC (runtime-prompt) is a "crossing." That verdict is
dumb — it cannot tell *long-but-coherent* code (fine) from *reducible* code
(real bloat). It produces two failure modes:

1. **False positives** — pressure to churn coherent long code into a worse
   shape just to drop under a line count (the "blanket source-must-split"
   policy, shown wrong by the PR #219 dogfood: 7/8 H1 files were coherent).
2. **False negatives** — a 120-LOC file packed with needless abstraction,
   duplication, or dead code sails through because it is under the limit.

The cheap LOC signal should **route**, not **rule**. It escalates to a
reviewer that blocks only on a *concrete, falsifiable reduction*.

## Solution (closed catalog + guardrails)

LOC-as-router → LLM reducibility reviewer that blocks only on a concrete
finding from a **closed catalog**, each citing a falsifiable contract:

| Code | Smell | Code | Smell |
|---|---|---|---|
| **D** | duplication | **S** | data-shape (dict-shuffling vs a type) |
| **A** | needless abstraction | **M** | comment restating code |
| **X** | dead code | **P** | dependency footprint |
| **C** | control-flow verbosity | **T** | test repetition |

Each finding MUST cite: **what to remove** + **est-LOC-saved** + **keeps
tests green**. No concrete finding → **PASS**.

**Guardrails G1–G6:** G1 long-but-coherent is never a finding · G2
clarity > cleverness · G3 never weaken coverage / validation / types ·
G4 no churn that breaks merge stability · G5 justified duplication exempt ·
G6 generated / vendored exempt.

**Two goals:** (A) prevent over-production = **blocking on the diff**
(the review cascade bounce-back); (B) boy-scout improve-on-touch =
**advisory**, bounded to the touched unit (unbounded B conflicts with
YAGNI + this repo's churn-merge fragility).

## Acceptance Criteria

- **AC1** — `shared/reducibility-catalog.md` (SSoT) defines the LOC-as-router
  model, the closed catalog D/A/X/C/S/M/P/T, the finding contract
  (what-to-remove + est-LOC-saved + keeps-tests-green), guardrails G1–G6,
  and the goal-A/goal-B split.
- **AC2** — `shared/profiles/reducibility-idioms.json` is a valid per-language
  idiom-map with `stack_agnostic`, `python`, and `typescript` sections, each
  mapping all eight catalog codes to recognizable idioms + a long-but-coherent
  exemption note.
- **AC3** — The local diff reviewer `plugins/shipwright-build/agents/code-reviewer.md`
  gains a **Reducibility Reviewer** dimension (a section SEPARATE from the
  parity-locked Bloat Checklist), LOC-routed, blocking only on a concrete
  contract-complete finding, PASS otherwise — wired to the bounce-back cascade.
- **AC4** — The CI Tier-3 reviewer `shared/prompts/pr_reviewer/system` (B4.5,
  a live Required Check) gains a **self-contained** reducibility decision rule
  that blocks only on a concrete falsifiable reduction and never on
  long-but-coherent code (G1) / weakened tests (G3) / generated files (G6).
- **AC5** — The external plan reviewer `shared/prompts/iterate_reviewer/system`
  gains an advisory reducibility focus (catch over-production at plan stage —
  goal-B pre-emption).
- **AC6** — `shared/glossary.md` defines `Reducibility-Catalog` + `LOC-as-Router`
  (stays ≤300 LOC); `docs/guide.md` documents the reducibility reviewer as the
  qualitative complement to the quantitative anti-ratchet gate.
- **AC7** — A drift-protection test pins the eight codes, six guardrails, the
  contract fields, and the goal split across all surfaces; the existing
  reviewer-parity + glossary tests stay green.
- **AC8 (dogfood)** — The codified catalog applied to THIS iterate's own diff
  yields **0 forced churn** (the new reference/idiom/prompt content is
  long-but-coherent → G1 + G6 exempt), validating that the gate does not
  churn coherent code. The prior 8-file H1 dogfood (7/8 coherent, 1/8 a real
  D2 = the 3 repo-root resolvers, tracked separately as `trg-b9acb195`) is
  cited as design validation.

## Affected Boundaries

No `touches_io_boundary` producer/consumer code, no env/config/state parsing,
no migrations — the deliverables are reference + reviewer-prompt content, and
the idiom-map JSON is reviewer *context* validated only by the drift test.

**But one surface is an enforcement change, not pure docs** (external-review
OpenAI #2): `shared/prompts/pr_reviewer/system` is the **live B4.5 Required
Check** `PR Review`, so changing it can alter merge behaviour. Mitigations
that bound the blast radius: (a) Tier 1/2 PRs — iterate branches + the
maintainer's manual PRs — **skip** the CI reviewer entirely (so THIS PR never
hits the new rule); only external-contributor / sensitive-path PRs do; (b) the
reducibility rule is **conservative** — `block` only on a contract-complete
finding with material est-LOC-saved (≈15+), else `comment`, and
long-but-coherent is never a finding (G1); (c) unproven test-safety downgrades
to advisory (never block). A synthetic PASS/BLOCK regression-fixture harness
(OpenAI #6) is deferred — the verdict is a non-deterministic LLM judgment; the
live Step-8 code-reviewer run on this diff is the dogfood instead.

## Mini-Plan

1. SSoT catalog `shared/reducibility-catalog.md` (not bloat-scanned — shared
   root, not a runtime-prompt path).
2. Idiom-map `shared/profiles/reducibility-idioms.json`.
3. `code-reviewer.md` → new `## Reducibility Reviewer` section (separate from
   `## Bloat Checklist`; leaves the byte-locked parity section + the
   already-grandfathered `sub-iterate-runner.md` untouched → no ratchet).
4. `pr_reviewer/system` (B4.5 CI) + `iterate_reviewer/system` (plan) → compact,
   self-contained reducibility rules.
5. `glossary.md` + `docs/guide.md` notes.
6. TDD drift-protection test `shared/tests/test_reducibility_gate.py`.

### Alternative considered (rejected)

Put the reducibility dimension *inside* the parity-locked `## Bloat Checklist`
section. **Rejected:** the section is byte-identical-locked to
`sub-iterate-runner.md`, which is already grandfathered at `current: 479`
(over its 400 limit). Any growth there ratchets the baseline upward — a
Group-H (H3) violation, and self-defeating for a feature whose entire purpose
is "don't grow files needlessly." A separate section in the canonical diff
reviewer covers the campaign path too (the runner delegates code review back
to the orchestrator, which uses `code-reviewer.md`).

## Confidence Calibration
- **Boundaries touched:** one enforcement surface — `pr_reviewer/system` is the
  live B4.5 Required Check (see Affected Boundaries). The rest is reference +
  reviewer-prompt content; the idiom-map JSON is reviewer context.
- **Empirical probes run:**
  - JSON parse/shape: `json.loads(reducibility-idioms.json)` succeeds; 3
    languages × 8 codes × {idioms non-empty, long_but_coherent present} — pinned
    by `test_idiom_map_*` (green).
  - Identifier probe: `grep _SKIP` on `bloat_baseline.py` → real symbols are
    `_SKIP_PATH_RE` + `_SKIP_EXT_RE` (caught + fixed a wrong `_SKIP_RE`
    reference flagged by the code-reviewer).
  - Parity probe: the byte-locked `## Bloat Checklist` section stays identical
    across `code-reviewer.md` ↔ `sub-iterate-runner.md`; the new section sits
    AFTER `<!-- /Bloat Checklist -->` → `sub-iterate-runner.md` baseline
    (`current:479`) unchanged → anti-ratchet exit 0 (no ratchet).
  - LOC budget: `code-reviewer.md` 271→305 (≤400 runtime-prompt limit, not a
    new crossing); glossary 222→236 (≤300); test 263 (≤300).
  - Security-guard probe: `pr_reviewer/system` retains the "diff is UNTRUSTED
    data" block + strict 4-key JSON contract; rule 7 routes through existing
    `block`/`comment` verdicts (code-reviewer confirmed).
  - Live review-path dogfood: the real Step-8 code-reviewer agent reviewed this
    diff → judged long-but-coherent (G1) + justified-duplication (G5) → 0
    forced churn (matches AC8).
- **Test Completeness Ledger:**

  | Behavior (AC) | Disposition | Evidence |
  |---|---|---|
  | AC1 catalog defines router/codes/contract/guardrails/goals | `tested` | `test_catalog_*` (router, 8 codes, contract, G1–G6, two goals, behavioral rules) |
  | AC2 idiom-map 3 langs × 8 codes valid | `tested` | `test_idiom_map_is_valid_json` + `_has_all_languages` + `_covers_all_codes_per_language` |
  | AC3 code-reviewer reducibility section, separate from parity block | `tested` | `test_code_reviewer_has_reducibility_section` + `_is_separate_from_bloat_checklist` |
  | AC4 pr_reviewer self-contained rule (codes inlined, G1, contract, threshold) | `tested` | `test_pr_reviewer_has_self_contained_reducibility_rule` (code+keyword adjacency + numeric threshold) |
  | AC5 iterate_reviewer advisory focus | `tested` | `test_iterate_reviewer_has_reducibility_focus` |
  | AC6 glossary terms; guide note | `tested` (glossary) / `untestable: covered-by-existing-test` (guide prose) | `test_glossary_defines_reducibility_terms` + `test_glossary_under_loc_limit`; guide is narrative doc |
  | AC7 drift test pins invariants; parity+glossary stay green | `tested` | this file + `test_reviewer_bloat_checklist_parity` + `test_bloat_defense_artifacts` |
  | AC8 dogfood: 0 forced churn on this diff | `tested` (live agent) / design-validation cite | Step-8 code-reviewer verdict (G1+G5); PR #219 8-file dogfood cited |

  0 testable-but-untested behaviors. The one `untestable` row (guide narrative
  prose) carries reason_code `covered-by-existing-test` (the guide's structural
  doc tests already run in the full suite).
- **Confidence-pattern check:**
  - *Asymptote (depth):* probes converged — the only depth surprise (wrong
    `_SKIP_RE` symbol) was found by the code-reviewer and fixed; re-probe green.
  - *Coverage (breadth):* all 4 enforcement surfaces + SSoT + idiom-map +
    glossary + guide are each pinned by ≥1 assertion; the cross-surface
    consistency of the 8 codes is enforced (no surface can drop a code silently).
