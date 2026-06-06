# Iterate: Architecture-drift detector + finalize gate

- **run_id:** `iterate-2026-06-06-arch-drift-detector`
- **Intent:** CHANGE (modify existing detective + finalize behavior)
- **Complexity:** medium (governance-sensitive: compliance gate behavior + a
  finalize verifier that runs on every iterate; spans 2 components)
- **Spec Impact:** MODIFY — changes the runtime behavior of the compliance
  Group F detective (F5) and adds a canon finalize gate to the iterate F11
  verifier. No user-facing FR; the contract change is recorded as an
  `architecture_impact=convention` entry in `architecture.md` (self-consistent
  with the new gate).
- **architecture_impact:** `convention` (changes how the arch-drift contract
  is *enforced* — from prose/dead-check to a live gate + content-reconciling
  detective). This iterate adds its OWN `architecture.md` entry.

## Problem (diagnosed this session)

`architecture.md` is silently drifting from the arch-impact decision-drops, and
the compliance detective never flags it:

1. **F5 detector is structurally blind** (`group_f.py::_check_f5`). It detects
   drift via `git log <marker>..HEAD -- .shipwright/agent_docs/decision-drops/`,
   but decision-drops are **gitignored** (`.gitignore:135`) → never committed →
   never appear in `git log`. With a `last-sync` marker present (stuck at
   `932e0d22`, 2026-05-21), `drift_set` is **always empty → permanent `pass`**.
2. **Scope gap:** F5 only considers `{component, data-flow}` — it ignores
   `convention` entirely (most missing drops are `convention`).
3. **The F2 finalize guard is dead + toothless:** `check_architecture_reviewed`
   (`iterate_checks.py:495`) is reachable only through `run_advisory_checks`,
   which has **zero callers anywhere** — it never runs. Even if it did, it was a
   non-blocking mtime heuristic that never checked run_id/impact and skipped
   `bug`/`fix`.

Result: the test `shared/tests/test_architecture_md_reflects_arch_impact.py`
fails locally on **5** arch-impact drops missing from `architecture.md`
(a5-gate-behavioral-probe, b7-exclude-nonfunctional, bloat-marker-worktree-aware,
fr-linkage-lifecycle, scanner-degraded-marker) while the detective stays green —
**no triage item is ever produced.** scanner-degraded-marker (#157) is fresh
drift that merged this morning — the bug recurring live.

## Acceptance Criteria (assertion-shaped)

- **AC-1 (F5 content oracle):** Given a drops dir containing a drop with
  `architecture_impact ∈ {component, data-flow, convention}` whose `run_id` is
  absent from `architecture.md`, `_check_f5` returns `status="fail"` and the
  evidence lists that drop. Given all such run_ids present, it returns `"pass"`.
- **AC-2 (convention counted):** A `convention`-impact drop missing from
  `architecture.md` triggers an F5 `fail` (regression vs the old
  `{component,data-flow}`-only set).
- **AC-3 (worktree-aware + CI-safe):** F5 resolves the drops dir via the
  main-repo resolver (works from a worktree); when the drops dir is absent
  (clean checkout / CI), it returns `"skip"` (stays born-green in CI). Corrupt
  drop JSON still yields a `fail` finding.
- **AC-4 (git-log path retired):** `_check_f5` no longer shells out to
  `git log <marker>..HEAD`; the adopt-side marker producer
  (`artifact_writer.render_architecture_marker`) is untouched.
- **AC-5 (live F11 gate):** A new `check_architecture_documented(project_root,
  run_id)` is wired into `verify_iterate_finalization.py`. For a run whose
  decision-drop declares `architecture_impact ∈ {component,data-flow,convention}`
  and whose `run_id` is absent from `architecture.md`, it returns a canon
  `fail`. When the drop is absent or `impact=none`, it returns pass/n-a.
- **AC-6 (dead code removed):** The unreachable `run_advisory_checks` +
  `check_architecture_reviewed` (and any sibling reachable only through them) are
  removed, or repurposed into the live gate; no test regresses.
- **AC-7 (data remediation):** The 5 missing `architecture.md` entries are
  back-filled (accurate one-liners sourced from each drop), so both the existing
  drift test AND the new F5 pass on the real repo.
- **AC-8 (detective surfaces drift):** With a synthetic missing entry, the F5
  `fail` flows through `triage_bundle` into a `compliance:backlog` item
  (verified via the existing bundle path, not re-implemented).

## Affected Boundaries

- `plugins/shipwright-compliance/scripts/audit/group_f.py` — `_check_f5` rewrite
  (reads decision-drop JSON + architecture.md text → `touches_io_boundary`).
- `shared/scripts/tools/verifiers/iterate_checks.py` — new live gate; remove
  dead advisory wrapper.
- `shared/scripts/tools/verify_iterate_finalization.py` — wire the new gate.
- `.shipwright/agent_docs/architecture.md` — back-fill 5 entries + this run's.
- Tests: `plugins/shipwright-compliance/tests/` (F5), `shared/tests/`
  (verifier), synthetic tmp_path fixtures only.
- Docs: `docs/hooks-and-pipeline.md` (F5 behavior + new F11 gate).

## Mini-Plan

**Primary approach:** Replace F5's git-history oracle with the *content
reconciliation* oracle the existing test already uses (run_id ∈ architecture.md
over the real drop set, main-repo-resolved, including `convention`), and convert
the dead/prose F2 step into a *live canon F11 gate* mirroring
`check_spec_impact_recorded`. Back-fill the 5 orphaned entries so the repo is
clean. This is minimal, reuses the proven test oracle, and the F11 gate prevents
recurrence at the source.

**Alternative considered (rejected):** *Keep the marker + fix the git-log path*
(e.g. diff drop content by reading the marker's committed architecture.md blob).
Rejected: the inputs (decision-drops) are gitignored, so any git-history-based
oracle is fundamentally comparing against data that never enters history — it
would need the drops force-tracked, which contradicts the staging-only design
([[decision_drops_gitignored]]). Content reconciliation needs no git at all and
matches the test's already-correct definition.

**Blocking-vs-advisory decision (AC-5):** the new F11 gate is **canon/blocking**,
not a warning. Rationale: prose + a dead check already failed (5 real drifts,
incl. one this morning); the constitution/learnings favor "convert a load-bearing
prose step into a gate." Escape hatch: an over-flagged drop can be downgraded to
`architecture_impact=none`, or the entry added — both are one-line fixes the
failure message names.

## Confidence Calibration
- **Boundaries touched:** decision-drop JSON reader (`touches_io_boundary`),
  `architecture.md` text, the F11 verifier registry (`run_all_checks`), the F5
  detective registry.
- **Empirical probes run:**
  - F5 on the real repo BEFORE back-fill → `fail`, listed all 5 missing drops
    (proved the detector now *sees* the drift it was blind to).
  - F5 on the real repo AFTER back-fill → `pass` ("all 9 arch-impact drops
    documented"); existing `test_architecture_md_reflects_arch_impact` flipped
    RED→GREEN.
  - Word-boundary match: `iter-r1` NOT satisfied by documented
    `iter-r1-extended` (helper + gate tests).
  - CI-safety: drops dir absent → F5 `skip` (born-green in clean checkout).
  - My own run's F11 gate simulated with a synthetic `convention` drop →
    `pass` (the pre-added architecture.md entry satisfies it).
  - Dead-code removal: full-repo `ruff check .` green (no dangling import of
    `check_architecture_reviewed`); all importers updated.
- **Test Completeness Ledger:**
  | AC | Disposition | Evidence |
  |----|-------------|----------|
  | AC-1 F5 fail/pass | tested | `test_undocumented_component_drop_fails`, `test_documented_component_drop_passes` |
  | AC-2 convention counted | tested | `test_convention_impact_now_counted` |
  | AC-3 worktree-resolve + CI-skip + corrupt | tested | `test_absent_drops_dir_skips`, `TestF5CorruptDrops`, helper `test_scan_drops_*`; real-repo probe for resolution |
  | AC-4 git-log path retired | tested | `subprocess` import removed (ruff F811/F401 clean); tests need no git |
  | AC-5 live F11 canon gate | tested | 8 `check_architecture_documented` tests (incl. severity=error) + wired into `run_all_checks` |
  | AC-6 dead code removed | tested | full-repo ruff green; `test_verify_iterate_finalization` + `test_verifiers_dual_mode` updated, green |
  | AC-7 data remediation | tested | drift test passes; F5 real-repo "9 documented" |
  | AC-8 detective → triage item | covered-by-existing-test | F5 fail is tested; `triage_bundle` mirrors ALL `status=="fail"` findings generically (unchanged; its own tests cover the bundle path) |
  0 testable-but-untested behaviors.
- **Confidence-pattern check:** asymptote — marginal probes (prefix-collision,
  CI-skip, my-own-gate, real-repo before/after) each returned no new finding →
  stop. Coverage — detector (F5) + finalize gate (F11) + shared oracle + data
  remediation + docs all exercised; ~3,875 tests green, ruff green.

## External Review (gpt-5.4 + gemini-3.1-pro via OpenRouter, 1 round — incorporated)

Refinements folded into the design from the review:

- **Shared reconciliation helper** (`shared/scripts/lib/architecture_doc.py`):
  one module owns drop enumeration + run_id↔architecture.md matching; F5, the
  F11 gate, and tests all call it (prevents the detective and finalizer drifting
  apart). [OpenAI#2 / Gemini#4]
- **Robust run_id match** — `(?<![\w-])<run_id>(?![\w-])`, not bare substring, so
  a prefix run_id can't satisfy a longer one. [OpenAI#1 / Gemini#2]
- **Case-insensitive `architecture_impact`**; only the 4 canonical values
  recognized; an unknown non-empty value is surfaced as an F5 finding, not
  silently skipped. [OpenAI#4 / Gemini#3]
- **F11 robustness** — a current-run drop that exists but is corrupt / missing
  `architecture_impact` → canon fail (don't fail-open on the blocking gate).
  [OpenAI#5]
- **architecture.md missing/unreadable** → F5 fail / F11 canon fail. [OpenAI#10]
- **Back-fill format** mirrors the existing `## Architecture Updates` bullet
  shape exactly; one regression test parses the real doc shape. [OpenAI#7]
- **Bounded dead-code removal** — remove ONLY the provably-unreachable
  `run_advisory_checks` + the superseded `check_architecture_reviewed`; leave
  sibling checks untouched (over-broad deletion flagged as scope creep).
  [OpenAI#9 / Gemini-low]
- **Actionable failure messages** naming `architecture.md` + the `run_id`.
  [Gemini#5]
- **Authoring guidance** — F2/F3 reference + `hooks-and-pipeline.md` note that
  `architecture_impact ∈ {component,data-flow,convention}` now requires a
  matching entry before finalize passes. [OpenAI#8]

**Accepted limitation (documented, not fixed here):** decision-drops are
gitignored, so F5 in a clean CI checkout `skip`s — F5 is a local/worktree
detective, and the **F11 gate is the authoritative prevention layer**. A
CI-side backstop would require force-tracking drops (contradicts the
staging-only design); noted as a possible follow-up. [OpenAI#3 / Gemini#1]

## Out of scope
- No change to the adopt-side architecture marker producer.
- No force-tracking of decision-drops (they remain gitignored staging).
- No re-design of triage bundling (reuse existing path).
- No CI-side arch-drift backstop (follow-up; see accepted limitation).
