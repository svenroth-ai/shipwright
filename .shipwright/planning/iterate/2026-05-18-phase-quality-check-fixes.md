# Iterate Spec: phase-quality-check-fixes

- **Run ID:** iterate-2026-05-18-phase-quality-check-fixes
- **Type:** change
- **Complexity:** medium
- **Status:** implemented

## Goal

Eliminate three false-negative classes in the phase-quality auditor: the
C1/C5 canon checks (`shared/scripts/tools/verifiers/common.py`) and the S1
spec reader (`shared/scripts/lib/spec_parser.py`) predate three conventions
that shipwright-adopt, shipwright-iterate and shipwright-changelog already
emit. All changes are check-side (compliance-layer) and retroactive — no
skill changes, no per-project backfill. Mirrors the existing
`check_c4_decision_log_has_phase_adr` `if phase == "iterate"` decision-drop
special-case.

## Acceptance Criteria

- [x] **AC-1 (C5 drop-directory awareness):** When the inline
  `## [Unreleased]` → `### <category>` sub-section is missing OR has 0
  bullets, `check_c5_changelog_unreleased_has_phase_entry` also counts
  `*.md` files (excluding `.gitkeep`) under
  `<project_root>/CHANGELOG-unreleased.d/` recursively (any category —
  category-agnostic). ≥1 drop file → PASS. Given a CHANGELOG with an empty
  `### Added` and a drop file at `CHANGELOG-unreleased.d/Fixed/x_001.md`,
  `check_c5(...,"iterate","Added")` returns `ok is True`.
- [x] **AC-2 (C5 unchanged when inline present):** When the inline category
  sub-section has ≥1 bullet, C5 still PASSes via the inline path without
  consulting the drop directory (existing behaviour preserved). When
  neither inline bullets nor any drop file exist, C5 still FAILs.
- [x] **AC-3 (S1 spec-path fallback):** When `.shipwright/agent_docs/spec.md`
  is missing, `read_top_level_spec` falls back to
  `glob('.shipwright/planning/*/spec.md')`, sorts the matches
  deterministically, and returns the text of the first match. Given a repo
  with no `agent_docs/spec.md` and a populated
  `.shipwright/planning/01-adopted/spec.md`, `read_top_level_spec(root)`
  returns that file's content (not `None`).
- [x] **AC-4 (S1 no fallback when canonical present):** When
  `.shipwright/agent_docs/spec.md` exists, `read_top_level_spec` returns it
  unchanged — the planning glob is not consulted. When neither exists,
  `read_top_level_spec` returns `None`.
- [x] **AC-5 (C1 iterate evidence):** For `phase == "iterate"`, before
  failing, `check_c1_phase_event_recorded` accepts EITHER a `work_completed`
  event with `source == "iterate"` in `shipwright_events.jsonl` OR ≥1
  pending decision-drop `*.json` (non-`_`-prefixed) under
  `.shipwright/agent_docs/decision-drops/` (mirrors C4). Either → `ok is True`.
- [x] **AC-6 (C1 phase_history evidence, any phase):** For ANY phase,
  before failing, `check_c1_phase_event_recorded` accepts a
  `phase_history[<phase>]` entry in `shipwright_run_config.json` whose
  `outcome` is terminal — `{adopted, adopted-skipped, completed, tagged}`.
  ≥1 such entry → `ok is True`. This fallback runs even when
  `shipwright_events.jsonl` is empty or absent (adopted projects record no
  events).
- [x] **AC-7 (C1 still fails on no evidence):** With no `phase_completed`
  event, no iterate evidence, and no terminal `phase_history` entry, C1
  still returns `ok is False`. Existing C1 tests continue to pass.
- [x] **AC-8 (tests):** New/extended tests in
  `shared/tests/test_verifiers_common.py` (C5 drop-dir, C1 iterate
  work_completed, C1 iterate decision-drop, C1 phase_history any-phase, C1
  phase_history with empty event log, C1 still-fails) and
  `shared/tests/test_spec_checks.py` (`read_top_level_spec` planning
  fallback PASS, canonical-wins, neither-exists). All `shared/tests/` green.
- [x] **AC-9 (docs):** C1 + C5 docstrings updated to describe the new
  fallbacks; `docs/hooks-and-pipeline.md` § "Minimum Phase Completion Canon"
  updated to document drop-directory awareness (C5) and iterate/adopt
  evidence (C1).

## Spec Impact

- **Classification:** none
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** Check-side correctness fix to three detective
  phase-quality audit checks. The checks are extended to recognise
  conventions already emitted by shipwright-adopt / -iterate / -changelog
  (drop-directory changelog, adopted spec path at
  `.shipwright/planning/*/spec.md`, `work_completed` / `phase_history`
  completion evidence). No functional requirement is added, modified or
  removed — the auditor's contract ("verify phase-completion canon") is
  unchanged; only its false-negative rate against existing, correctly-shaped
  artifacts is corrected. FR-01.10 (`/shipwright-compliance`) and FR-01.11
  (`/shipwright-iterate`) describe user-facing slash commands; the Stop-hook
  phase-quality auditor is internal infrastructure with no FR of its own.

## Out of Scope

- The shipwright-iterate / shipwright-adopt / shipwright-changelog **skills**
  stay unchanged — this is check-side only.
- No per-project backfill — the fix is retroactively correct against
  existing artifacts.
- `spec_checks.py` S1 finding strings (`S1_NAME`, evidence text) — the S1
  fix is scoped to the `read_top_level_spec` reader; the finding wording
  staying slightly `agent_docs`-centric is acceptable and out of scope.
- The SessionStart phase-quality hook printing 13× (one per plugin) — noted
  as a separate optional follow-up; a future iterate could give it a single
  owner (shipwright-compliance). Not done here.

## Design Notes

n/a — no UI surface. Pure Python check-side change to two shared modules.

## Affected Boundaries

All three changes add **new consumers** of existing, stable producers — no
serialized format is changed. The risk is consumer-vs-producer shape drift,
probed in Confidence Calibration below.

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `write_changelog_drop.py` → `CHANGELOG-unreleased.d/<cat>/<run_id>_NNN.md` | `check_c5_changelog_unreleased_has_phase_entry` (new glob path) | filesystem (`*.md` drop files) |
| shipwright-adopt / `append_phase_history.py` → `shipwright_run_config.json::phase_history` | `check_c1_phase_event_recorded` (new fallback) | JSON |
| `record_event.py` → `shipwright_events.jsonl` `work_completed` lines | `check_c1_phase_event_recorded` (new `work_completed`/`source` scan) | JSONL |
| `write_decision_drop.py` → `.shipwright/agent_docs/decision-drops/*.json` | `check_c1_phase_event_recorded` (new, mirrors C4) | filesystem (`*.json` drops) |
| shipwright-adopt / -project → `.shipwright/planning/<NN-split>/spec.md` | `read_top_level_spec` (new glob fallback) | filesystem (`spec.md`) |

## Confidence Calibration

Probe script + evidence:
`.shipwright/runs/iterate-2026-05-18-phase-quality-check-fixes/probe.py`
(14 probes, all PASS).

- **Boundaries touched:** the 5 producer/consumer pairs in the table above.
- **Empirical probes run:**
  1. *C1 ↔ real adopted `phase_history` (round-trip):* `check_c1` run
     against this repo's real `shipwright_run_config.json` for
     project/plan/build/test/changelog — all PASS. `C1[test]` PASSes
     specifically via `outcome='adopted-skipped'` (confirms the operator
     decision was load-bearing). Finding: none.
  2. *C1[iterate] ↔ real event log:* PASSes via a real
     `work_completed[source=iterate]` event. Finding: none.
  3. *C5 ↔ real `CHANGELOG-unreleased.d/`:* 4 real `*.md` drop files,
     6 `.gitkeep` files present — count returns 4 (`.gitkeep` correctly
     excluded). `C5[iterate/Added]`, `C5[build/Added]`,
     `C5[deploy/Changed]` all PASS off the same drops (category-agnostic
     confirmed — the 4 drops live in `Added/` + `Fixed/`). The repo's
     `## [Unreleased]` has no `### Added` sub-section, so the fallback
     path is genuinely exercised. Finding: none.
  4. *S1 ↔ real adopted spec layout (round-trip):* no
     `agent_docs/spec.md`; `read_top_level_spec` returns the 11 119-char
     `.shipwright/planning/01-adopted/spec.md`; `check_s1_top_level_spec`
     PASSes. Finding: none.
  5. *Malformed / edge inputs:* `phase_history` as a list, a non-dict
     `phase_history` entry, malformed run-config JSON, a planning split
     with no `spec.md`, a stray non-dir planning entry — all handled
     gracefully (FAIL/None, no crash). Finding: none.
- **Edge cases NOT probed + why acceptable:** operator-input categories
  from `references/boundary-probes.md` (POSIX `export` prefix, inline
  `# comment`, quoted `#`) are N/A — every format read here
  (`shipwright_run_config.json`, `shipwright_events.jsonl`, decision-drop
  `*.json`, changelog drop `*.md`, `spec.md`) is machine-written and never
  hand-edited at the byte level by an operator. No serialized format is
  *changed* by this iterate — only new readers are added — so producer
  round-trips (probes 1-4) plus malformed-input probes (probe 5) cover
  the real drift surface.
- **Confidence-pattern check:** no "are you confident?"-style question
  produced a yes-then-finding in this run; the C1-`adopted-skipped`
  question was resolved by the operator *before* implementation, not
  papered over. Stopping rule satisfied: the last probe (5e) returned no
  finding, all applicable categories are covered, no yes-then-bug fired.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run --with pytest --with pytest-mock pytest
  shared/tests/test_verifiers_common.py shared/tests/test_spec_checks.py -q
  --color=no` (full `shared/tests/` suite also run at F0).
- **Evidence path:** `.shipwright/runs/iterate-2026-05-18-phase-quality-check-fixes/`
- **Justification (only if surface=none):** n/a — cli surface exists.
