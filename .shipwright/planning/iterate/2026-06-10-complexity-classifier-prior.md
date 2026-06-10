# Iterate Spec — history-calibrated complexity prior + broadened scope vocabulary

- **run_id:** `iterate-2026-06-10-complexity-classifier-prior`
- **Intent:** change (framework infra) · **Complexity:** medium (framework classifier
  touching every adopted repo's iterate entry point; new producer/consumer boundary
  — plugin reader of the shared F5c writer's entries; SKILL.md prose + tests).
- **Risk flags:** `touches_io_boundary` (new JSON consumer of
  `.shipwright/agent_docs/iterates/*.json`, written by `append_iterate_entry.py`) →
  Boundary Probe + round-trip test + Confidence Calibration mandatory.
- **Spec Impact:** NONE (framework behaviour; no product FR added/modified/removed →
  event `change_type=infra` + `none_reason`).
- **Anchor:** `trg-35e6701e` (kind=improvement, source=iterate-analysis). This iterate
  `expands_triage` it; dismissed at the end.
- **Approval:** user confirmed both parts in-session 2026-06-10 ("yes. go") after the
  empirical analysis and the vocabulary discussion.

## Problem (empirical)

45 Stage-1 classifier outputs from sessions 2026-05-10..2026-06-10 vs 50 finalized runs
(F5c entries): Stage 1 returns **trivial 64%** of the time (scope-keyword fall-through in
33/45), but only **14%** of runs finalize trivial (small 44%, medium 42%). The Stage-2
Repo Scout bumps nearly every run — Stage 1 carries near-zero signal in this repo.
Root causes:
1. `estimate_scope()` vocabulary is hard-coded for end-user web apps (`spinner`,
   `dashboard`, `new page`) — never matches monorepo/CLI/API vocabulary → falls through.
2. The fall-through default is `"trivial"` (lowest rung) instead of the project's
   observed distribution.
3. No feedback loop, although every F5c entry records the run's final complexity.
4. Side effect: a trivial estimate selects the *Quick* repo scout, shallowing the very
   stage meant to correct the estimate.

## Fix (two complementary parts)

**Part 1 — history-calibrated prior.** When no scope keyword matches and F5c history
exists, the fall-through default becomes the median final complexity of the last 20
entries instead of `"trivial"`.

**Part 2 — broadened scope vocabulary.** Extend the keyword sets with cross-domain
*scope-signal* patterns (structure verbs + nouns for CLI / API / backend /
library-plugin / data / infra stacks), not just more web-UI nouns. Keywords stay the
per-prompt signal; the prior only replaces the *no-match* default.

Precedence: **keyword match > history prior > trivial default.** Risk floors unchanged.

## Acceptance Criteria

- **AC-1 (prior):** With `--project-root` given, no scope-keyword match, and ≥3 valid
  entries under `.shipwright/agent_docs/iterates/`: estimate = median complexity of the
  last ≤20 entries (sorted by `date`, `run_id` tiebreak — mirrors shared `sort_key`),
  upper-clamped to `medium` (the prior alone never routes to the large escape hatch).
  `signals.prior_source = "history"`, plus `signals.history_prior` and
  `signals.history_n`. Invalid/quarantine entries are skipped, never crash.
- **AC-2 (cold start / compat):** <3 entries, missing dir, or no `--project-root` →
  exact current behaviour (`trivial`, `prior_source = "default"`). Keyword match →
  `prior_source = "keyword"`, history not consulted. `estimate_scope()` keeps its
  public signature and trivial-on-no-match return (existing importers unaffected).
- **AC-3 (vocabulary):** keyword sets move to new `complexity_vocabulary.py`
  (re-exported from `classify_complexity` for compat) and are broadened with anchored,
  scope-signaling entries. All existing scope/test expectations still pass.
- **AC-4 (corpus golden test):** a fixture of real prompts harvested from the session
  transcripts (hand-joined to their runs' final complexity) lives in
  `tests/fixtures/complexity_corpus.json`; a golden test asserts the new classifier's
  estimate per row (history-less, vocabulary-only path) and pins the known
  false-positive guards. On this corpus the under-classification rate must drop vs the
  recorded old estimates (asserted with hard numbers in the test).
- **AC-5 (round-trip / boundary):** a round-trip test writes entries via the REAL shared
  writer (`append_iterate_entry`) into a tmp project root and asserts the plugin reader
  computes the expected prior — pins the path + field contract across the
  plugin/shared boundary. ImportError of the shared writer hard-fails in CI
  (silent-skip rule).
- **AC-6 (surface):** SKILL.md Step E command gains `--project-root "{project_root}"`;
  Step E/F prose documents `prior_source` and prints it in the Planned Run Summary.
- **AC-7 (bloat discipline):** `classify_complexity.py` net LOC ≤ 382 (grandfathered
  anti-ratchet), `test_classify_complexity.py` ≤ 318 (untouched); each new module and
  test file < 300 LOC.

## Mini-Plan

1. Harvest corpus: extract `--message` args + Stage-1 results from transcripts; join to
   F5c finals by date; hand-verify rows; write fixture.
2. Tests (red): `test_complexity_history.py` (prior unit + round-trip AC-1/2/5),
   `test_complexity_corpus.py` (AC-3/4 golden + false-positive guards).
3. Implement: `complexity_history.py` (reader + median), `complexity_vocabulary.py`
   (moved + broadened sets), `classify_complexity.py` integration (prior hook, signals,
   `--project-root`), green.
4. SKILL.md Step E/F + guide check; bloat/LOC verify; full suite; finalization.

**Alternative considered (rejected):** per-project vocabulary config generated at
adopt/project time — precise but adds a maintained artifact and leaves the default bias
unfixed for cold starts; revisit only if the prior + broadened vocabulary still
under-classify in practice. Also rejected: always-thorough repo scout (taxes genuinely
trivial fixes), keyword-only broadening (leaves root cause #2 unfixed).

## Confidence Calibration
- **Boundaries touched:** (1) plugin reader ↔ shared F5c writer
  (`.shipwright/agent_docs/iterates/*.json` — path/field/sort contract, no
  runtime import); (2) classify() output surface (`signals` consumed by SKILL
  Step E + sub-iterate-runner); (3) re-export surface for existing importers
  (tests, shared/contracts scope note verified: `estimate_scope` NOT in the
  contract); (4) CLI arg surface (`--project-root` new, optional).
- **Empirical probes run:** (a) transcript harvest — 45 real Stage-1 outputs:
  64% trivial vs 14% of runs finalizing trivial (the motivating gap);
  (b) live CLI probe on THIS repo post-change: fall-through prompt →
  `estimate small, prior_source history, n=20` (exit 0); (c) corpus metric on
  26 verified real rows: old 18 under / 1 over → new 11 under / 0 over;
  (d) round-trip via the REAL shared writer (25 jumbled entries → correct
  window median); (e) standalone `spec_from_file_location` load without
  sys.path prep (the test_record_event.py pattern) → self-bootstrap works.
- **Test Completeness Ledger:**

  | Behavior | Disposition |
  |---|---|
  | Median (odd/even-lower-middle), window=20, clamp≤medium, min-entries=3 | tested (`TestLoadHistoryPrior`, 9 tests) |
  | Invalid-entry skips: bad complexity, bad JSON, non-dict, missing/non-string/unparseable date, oversized file, `_quarantine/` subdir, valid-first-then-window | tested (6 tests incl. review-HIGH null-date) |
  | Sort determinism: (date, run_id) tiebreak at window cutoff, glob-order independence | tested (`test_run_id_tiebreak_decides_window_cutoff`) |
  | classify precedence keyword > history > default + new signals shape | tested (`TestClassifyPrecedence`, 6 tests) |
  | Risk-floor interplay (floor lifts prior; floor doesn't cap prior) | tested (2 tests) |
  | Backward compat: no `project_root` → old estimate + old signal keys | tested (precedence + CLI tests) |
  | CLI `--project-root` end-to-end (subprocess) | tested (`TestCli`, 2 tests) |
  | Writer→reader contract via real `append_iterate_entry` + real field entry shape | tested (`TestRoundTripWithRealWriter`, 2 tests) |
  | Sibling-module deployment + standalone import self-bootstrap | tested (`TestStandaloneLoading`, 2 tests) |
  | Matcher: alnum boundaries (underscore=separator), plural s/es, no arbitrary inflection, phrase anchoring | tested (guards: renew-commander, research, consolidated, underscore-filename, plurals ×2) |
  | Vocabulary golden on 29 real prompts + under-classification metric ceilings | tested (`TestVocabularyGolden`, `TestUnderClassificationMetric`) |
  | New/changed keyword intents (new command, add support for, systemic, producer-consumer, breaking change, new module→medium, typo, bump) | tested (`TestIntendedNewKeywords`, 9 tests) |
  | SKILL.md / sub-iterate-runner / guide prose edits | covered-by-existing-test (skill drift suite green: completeness matrix, phase matrix, risk-taxonomy consistency, references-link — 341/341) |

  0 testable-but-untested behaviors.
- **Confidence-pattern check:** depth/asymptote — the last probes (standalone
  load, tiebreak mutation analysis) produced no new failures, only
  confirmations; breadth/coverage — all four touched boundaries carry at
  least one empirical probe AND one pinned test; the riskiest assumption
  (writer/reader contract drift) is double-covered (round-trip + real field
  entry fixture).
