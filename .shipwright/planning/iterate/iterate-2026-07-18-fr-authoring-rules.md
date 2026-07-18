# Iterate — FR-authoring rules: plain business language + capability altitude

**Run-ID:** `iterate-2026-07-18-fr-authoring-rules`
**Type:** CHANGE · **Complexity:** medium
**Closes triage:** `trg-44d23d63` (FR descriptions must be plain business
language) + `trg-8e840ca0` (FR taxonomy: capability-altitude minting,
mint-vs-fold gate, FR-hygiene lint) — both dismissed at F12, with the deferred
remainder re-filed as one new item.

Source analysis (webui repo): `Spec/design/2026-07-17-fr-business-language-plugin-spec.md`
and `Spec/design/2026-07-17-fr-taxonomy-regrouping.md`.

## Problem statement

Two FR-minting engines with incompatible philosophy produced specs that a
product owner cannot read or sign off:

- `/shipwright-adopt` mints **one FR per route** — so endpoints (`Health check
  (GET)`, `Pending tool_use list (GET)`) sit as siblings of real capabilities.
- `/shipwright-iterate` mints **one FR per unit of work**, with a *guessed*
  number and no altitude guidance — so change-deltas (`completes FR-01.37`,
  `Phase 2`) become their own requirements, and parallel iterates collide on
  the same number.
- Nothing lints FR prose, so implementation detail (file paths, ADR numbers,
  symbols) accumulates in descriptions unchecked.

Measured on the real webui spec before its cleanup: **92% of descriptions and
42% of names carried implementation detail**, across 66 rows that represented
only 29 actual capabilities.

Root cause is the *authoring guidance*, not the string assembly — FR text is
LLM-agent prose in all three plugins. Adopt's guidance actively contradicted the
goal ("nüchtern, technical", "describe what the code *does*").

## Design

One shared rulebook, cited by every surface that authors FR text, plus an
advisory detective check so drift is visible rather than silently merged.

| Change | File |
|---|---|
| **New SSoT rulebook** — plain language (the *reader test*), altitude, mint-vs-fold, numbering, name fence, where the "how" goes | `shared/fr-authoring.md` |
| **Adopt** — replaced the contradicting "nüchtern, technical / describe what the code does" leitplanke; `label`+`description` now follow the rulebook, with a worked ❌/✅ pair | `…adopt/references/step-b8-semantic-enrichment.md` |
| **Project** — plain-business rule + no-implementation-how fence on the Rupp/IREB template; "readable by a non-engineer" + "one requirement, one capability" writing guidelines | `…project/references/spec-generation.md` |
| **Iterate** — new **Step 1a MINT-vs-FOLD gate** before classification; deterministic numbering (next free `FR-{split}.NN` over live **and** removed rows); name fence; ADD no longer says "a new endpoint" | `…iterate/references/path-a-feature.md`, `path-b-change.md` |
| **Compliance** — new advisory **Group I — Requirement Hygiene** (I1 name fence · I2 description fence · I3 fold candidate · I4 duplicate FR ID) | `…compliance/scripts/audit/group_i.py` (+ registry, detector allowlists) |
| **Drift protection** — rulebook exists, retains its cited sections, is still cited by all four surfaces, and the old contradiction stays gone | `shared/tests/test_fr_authoring_refs.py` |

**Group I is advisory by contract** — every finding is LOW or MEDIUM, never
HIGH, and the detective audit does not gate a merge. Legacy specs are expected
to carry historical violations; the signal is "fix it when you next touch the
row". Blocking on a prose heuristic would be a false-green generator.

**Deliberately not reusing the shared FR parser.** `drift_parsers` and the RTM
collector are the authoritative readers feeding traceability, and they collapse
the table to one semantic body field. Hygiene needs Name and Description kept
apart, so `group_i` does its own header-driven scan. Nothing downstream consumes
it — a scanning mistake can only produce a wrong advisory line, never a
traceability defect. This is why traceability is provably unaffected.

## Scope

**Greenfield needs no `Area` column.** `/shipwright-project` already decomposes
into splits and the split is encoded in the FR ID (`FR-04.02` = split 04). The
`Area` column is a *brownfield repair* for adopt dumping everything into split
01. Documented in the rulebook §4 so it is not cargo-culted into greenfield.

### Deferred (re-filed as one new triage item at F12)

1. **Adopt's route→capability regrouping** — grouping routes under the
   capability they serve, the `Area` column, UI↔API dedup, HTTP-verb stripping.
   Real behaviour change in `generate_adoption_artifacts.py` (716 LOC) and
   `artifact_writer.py` (695 LOC), both grandfathered, with ~7 test files to
   re-baseline. Mixing a schema/behaviour migration into a prompt-rules change
   would produce one PR that is hard to review and impossible to roll back
   independently.
2. **Unifying the greenfield and brownfield table shapes** — project emits
   `ID · Requirement · Priority · Layers`; adopt emits `ID · Name · Priority ·
   Description · Source · Layers`. Unifying ripples into the traceability
   parsers and belongs with (1).
3. **Stale doc line** — `adopt/references/feature-inference.md:109-110` claims
   "AST-inferred features are used only when no crawl data exists", which
   contradicts shipped behaviour (`generate_adoption_artifacts.py:342-360`
   unions AST-only routes). Found while scouting; out of scope here.
4. **Group I robustness follow-ups** (from the review round, all low): a spec
   that parses to zero rows is indistinguishable from an absent spec (a blind
   scanner reads as "nothing to audit"); `_column_map` returns a bare `None`
   for both "not a header" and "header I don't understand", so a second
   unrecognised table in one section reuses the previous mapping; a raw
   unescaped `|` inside a Description cell shifts later columns.
5. **Promote I1/I2 to blocking for NEW violations** via an FR-hygiene baseline
   (freeze existing, block new crossings), mirroring
   `shipwright_bloat_baseline.json`. This iterate ships the advisory half; the
   ratchet half needs a baseline file and its own drift protection.

## Spec Impact

- **Classification:** MODIFY
- **ADD:** none — this iterate is its own dogfood. Under the new §3 gate it is a
  **FOLD**: it changes how four existing capabilities behave, mints no new one.
- **MODIFY:** `FR-01.02` (/shipwright-project), `FR-01.10` (/shipwright-compliance),
  `FR-01.11` (/shipwright-iterate), `FR-01.13` (/shipwright-adopt)
- **REMOVE:** none

## Risk-flag note

`classify_complexity` reported `touches_auth`. **False positive** — the
classifier matches risk keywords against the *message prose*, and the substring
"auth" appears inside "FR-**auth**oring". No auth file is in the diff; the
`risk_detectors.py` diff-predicates are authoritative and F11 recomputes them.
Recorded in `shipwright_test_results.json.degraded[]`.

## Confidence Calibration (Step 7.5)

**Boundaries touched:** (a) agent-prompt → FR prose (an LLM-instruction boundary
— guarded by drift tests, not unit tests); (b) spec.md markdown table → hygiene
scanner (a *new* parse of an existing serialized format, in three column shapes);
(c) audit group registry → detector allowlists (two hardcoded letter sets).

**Empirical probes run (5):**

1. **Real-spec discrimination (the decisive probe).** Ran the detectors over the
   actual webui `spec.md` before and after its human cleanup (PR #287):
   **before** 66 rows / 42% dirty names / 92% dirty descriptions / 4 fold
   candidates → **after** 29 rows / **0% / 0% / 0**. The detectors track exactly
   what humans judged to be the fix, with **zero false positives** on 29
   hand-cleaned rows. Also confirms the scanner parses both 6-column shapes and
   that 66→29 matches the design spec's predicted outcome.
2. **Dogfood on this monorepo.** 15 FR rows → I1/I3/I4 pass, I2 flags exactly 3
   rows that genuinely name files. Proportionate signal, not noise.
3. **Mutation probe on the drift guard.** Removed `shared/fr-authoring.md` →
   7 targeted failures; restored → 12 pass. The guard demonstrably fires.
4. **Group-registry blast radius.** Adding Group I surfaced 12 failures across
   6 files from two hardcoded `{A..H}` allowlists and one hardcoded count — all
   found by the existing drift tests, all reconciled; suite returned to green
   at 1144 (baseline 1119 + 25 new).
5. **Runtime reachability.** Verified `update-marketplace.sh` syncs `shared/`
   into `cache/shipwright/shared/` and that `constitution.md` resolves there —
   so `shared/fr-authoring.md` will actually reach the agents rather than being
   a dev-repo-only no-op (the CLAUDE.md silent-no-op failure class).
6. **Re-validation after the review round.** Probe 1 re-run against the
   hardened detectors (PascalCase added, fold verbs completed, `Phase N of`
   tightened): **before** 66 rows / 45% dirty names / 93% dirty descriptions —
   *more* sensitive than the first pass (28→30 names, 61→62 descriptions) —
   while **after** stayed at **0 / 0 / 0**. Strictly better detection with no
   new false positives, which is the property that mattered.

### Review round (Step 8 — internal code-reviewer + external GPT-5.4 + Gemini 3.1 Pro)

All three reviewers found real defects; every must-fix was fixed and re-probed.

| Source | Sev | Finding | Resolution |
|---|---|---|---|
| internal | **HIGH** | `audit_compliance_on_stop.py` `_EXPECTED_GROUPS` was still `{A..H}` — a *third* hardcoded group set. Group I could fail while `coverage_ok()` still reported "full coverage" and the backlog item was dismissed: the exact false-dismiss class the F20 comment exists to prevent, repeated one letter later. | Added `"I"` + reconciled the three `A-H` strings and both test pins. |
| gemini | med | I4 was blind to live-vs-retired ID collisions, contradicting §4 ("counting both live and removed rows"). | `FrRow.retired` + `scan_fr_rows(include_retired=True)`; I4 now sees retired rows, prose checks still never lint them. |
| gpt-5.4 | med | `_FOLD_RE` missed `fixes` / `polishes`, which §3 explicitly lists — the detector did not match its own rule. | Verbs completed; a test now asserts every verb the rulebook names. |
| gpt-5.4 | low | PascalCase symbols (`TaskService`) evaded the fence. | `_PASCAL_RE` added, with a Title-Case negative test so ordinary prose is safe. |
| internal | med | I1 reported `pass` on greenfield specs that have no Name column — a false green over names never examined, and the original test baked it in. | I1 now `skip`s with an explicit reason; tests split into the greenfield-skip and adopt-pass cases. |
| internal | med | The advisory contract held only because nothing calls `run_audit` — `status="fail"` feeds `any_fail`, flipping the audit exit code and dashboard verdict on any repo with legacy FR prose. | I1/I2/I3 no longer emit `fail`; counts ride in `detail`. I4 still fails (objective defect). Guaranteed by `test_prose_checks_never_flip_the_audit_verdict`. |
| internal | med | `Phase N of` false-positives on domain prose ("phase 2 of the application form"). | Now requires a nearby FR reference; negative test added. |
| internal | med | Group I undocumented in `guide.md` and the compliance `SKILL.md` (CLAUDE.md mandates the guide check). | Both updated to 9 groups (A–I). |
| internal | low | The rulebook routed endpoint detail to an `Interfaces` note that exists in no template or parser. | Retargeted to `architecture.md` + acceptance criteria, both of which exist. |
| internal | low | The drift guard pinned only the two removed strings; a reword would pass. | Added positive assertions (rule text + worked pair present, MINT/FOLD gate present). |

**CI round (CodeQL, PR #395) — one HIGH in this diff's own new code.**
`py/redos` at `group_i_detectors.py`: `_FILE_PATH_RE` was
`[\w./-]*\w\.(ext)`, and `\w` is a subset of `[\w./-]`, so a long word-char run
that never reaches an extension has exponentially many parses and backtracks
without terminating. The detectors scan arbitrary requirement prose — and adopt
reverse-engineers that prose from a foreign repo — so a hung matcher would wedge
the whole compliance audit. **Root-fixed, not suppressed:** the pattern is now
anchored on the extension (`\w\.(ext)` — one literal dot, no leading quantifier,
linear), and the same overlap class was removed from `_PASCAL_RE` (inner
`[a-zA-Z]*` → `[a-z]*`, giving each uppercase-started run exactly one parse).
Pinned by `test_detectors_are_linear_on_pathological_input`; accuracy re-probed
against the real webui spec and unchanged (45%/93% dirty vs 0%/0% clean).
A second CodeQL alert — MEDIUM `non-literal-import` in
`shared/scripts/tools/verifiers/_layer_coverage_regen.py` — is **pre-existing**
and outside this diff.

Two findings were accepted rather than fixed, recorded here so the choice is
visible: the `_NOT_SYMBOLS` allowlist remains a judgement list (narrowing the
regex as suggested would stop catching `taskId`/`runId`, which are exactly the
symbols probe 1 shows dominate real specs), and `name_violations` /
`description_violations` stay as separate named wrappers because they document
intent at the call site. Three lower-value items are deferred to the new triage
item (§Deferred): distinguishing a parse failure from an empty project, the
unknown-header sentinel, and the raw-unescaped-pipe column shift.

**Test Completeness Ledger** — every behaviour this diff introduces:

| # | Behaviour | Disposition | Evidence |
|---|---|---|---|
| 1 | Name fence flags HTTP verb / ADR / iterate slug / file path / snake_case symbol | tested | `test_name_flags_*` (5 tests) |
| 2 | Clean capability name produces no finding | tested | `test_clean_capability_name_is_silent` |
| 3 | Description fence flags file path + camelCase symbol | tested | `test_description_flags_*` |
| 4 | Plain prose with a parenthetical gloss passes | tested | `test_description_allows_plain_prose_with_gloss` |
| 5 | Platform words (`iOS`, `iPadOS`) are not treated as code symbols | tested | `test_platform_names_are_not_code_symbols` |
| 6 | Fold candidates detected (`completes/replaces FR-x`, `Phase N of`) | tested | `test_fold_candidate_*` (3 tests) |
| 7 | Ordinary description is not a fold candidate | tested | `test_ordinary_description_is_not_a_fold_candidate` |
| 8 | Header-driven scan reads greenfield / adopt / Area column shapes | tested | `test_scan_greenfield…`, `test_scan_adopt…`, `test_scan_tolerates_area_column` |
| 9 | `### Removed Requirements` rows are not linted | tested | `test_scan_skips_removed_requirements` |
| 10 | `Source` column (legitimate file paths) is never linted | tested | `test_scan_adopt_splits_name_and_description` (desc asserted, Source excluded) |
| 11 | Clean spec passes all four checks | tested | `test_clean_spec_passes_every_check` |
| 12 | Duplicate FR ID within a split is reported | tested | `test_duplicate_fr_id_is_reported` |
| 13 | Absent spec SKIPs rather than fails | tested | `test_no_spec_skips_rather_than_fails` |
| 14 | Advisory contract: group I, detective-only, never HIGH | tested | `test_every_finding_is_detective_only_and_advisory` |
| 15 | Preview capped at 5 IDs but true count reported | tested | `test_findings_cap_the_preview_but_report_the_true_count` |
| 16 | Group I registered and runs in the default set | tested | `test_audit_detector.py`, `test_audit_group_b.py`, `test_audit_groups_a_d.py` (updated pins) |
| 16a | Group I is inside the Stop-hook full-coverage gate (no false dismiss) | tested | `test_audit_compliance_on_stop.py` (pins updated to A–I) |
| 16b | PascalCase symbols flagged; Title-Case prose is not | tested | `test_description_flags_pascal_case_symbol`, `test_capitalised_prose_is_not_a_pascal_symbol` |
| 16c | Every fold verb the rulebook names is detected | tested | `test_fold_candidate_covers_every_verb_the_rulebook_lists` |
| 16d | "Phase N of" in domain prose is not a fold candidate | tested | `test_domain_phase_prose_is_not_a_fold_candidate` |
| 16e | I1 skips (not passes) when the spec shape has no Name column | tested | `test_clean_greenfield_spec_is_clean` |
| 16f | I1 genuinely passes on a clean spec that HAS a Name column | tested | `test_clean_adopt_spec_passes_the_name_fence` |
| 16g | Prose checks never emit `fail` → never flip the audit verdict | tested | `test_prose_checks_never_flip_the_audit_verdict` |
| 16h | Reuse of a retired FR number is caught | tested | `test_retired_fr_number_must_not_be_reused` |
| 16i | Retired rows are never linted for prose | tested | `test_retired_rows_are_not_linted_for_prose` |
| 16j | Adopt states the plain-language rule positively (not just absence of the old one) | tested | `test_adopt_positively_states_the_plain_language_rule` |
| 16k | Both iterate paths still carry the MINT-vs-FOLD gate | tested | `test_iterate_paths_carry_the_mint_vs_fold_gate` |
| 17 | Rulebook exists, non-empty, retains its cited sections | tested | `test_rulebook_exists…`, `test_rulebook_retains_cited_sections` (6 params) |
| 18 | All four FR-authoring surfaces still cite the rulebook | tested | `test_fr_authoring_surface_cites_the_rulebook` (4 params) |
| 19 | Adopt's contradicting guidance stays removed | tested | `test_adopt_no_longer_carries_the_contradicting_guidance` |
| 20 | Agents actually *write better FRs* given the new prompts | untestable | `requires-manual-visual-judgment` — LLM prose quality has no deterministic oracle. Mitigated structurally: Group I measures the *output* (probe 1 shows it discriminates correctly), so drift is detected even though the instruction itself cannot be unit-tested. |

0 testable-but-untested. 30 tested, 1 `untestable` with a closed-vocabulary
reason code.

**Confidence-pattern check.** *Asymptote (depth):* two consecutive clean probe
rounds after the last fix (the registry-allowlist round) — probes 1–3 and 5 ran
clean against the final code. *Coverage (breadth):* all three FR table shapes in
the wild, both table sections (live + removed), both authoring directions (mint
+ fold), and both ends of the drift guard (forward: file exists; reverse: still
cited). *Integration composition:* `cross_component` not flagged — this diff
touches no merge/churn resolver, hook, phase validator, or campaign machinery.
