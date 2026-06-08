# Iterate Spec — idle-main artifact hygiene (complete ADR-089 for two stragglers)

- **run_id:** `iterate-2026-06-09-idle-main-artifact-hygiene`
- **Intent:** change (framework infra) · **Complexity:** medium (classifier under-detected
  `trivial`/conf 0.6 — keyword-only, no path scan; locked **medium** for the AC-1 design
  decision + multi-file cross-cutting change + `touches_io_boundary` JSON-state markers +
  framework-wide blast radius to every adopted repo).
- **Risk flags:** `touches_io_boundary` (marker `bloat_pending.<sid>.json` + baseline JSON
  read/write; `hooks` behaviour; gitignore canon). → Boundary Probe + round-trip test +
  Confidence Calibration are mandatory.
- **Spec Impact:** NONE (framework producer/consumer behaviour; no product FR
  added/modified/removed → event `change_type=infra` + `none_reason`).
- **Anchor:** `trg-7640bd14` (kind=improvement, source=architecture). This iterate
  `expands_triage` it; dismissed at the end.
- **ADR grounding:** completes **ADR-089** (runtime/snapshot split for the agent-doc trio +
  finalize sandbox gate) + PR #78 (compliance-md single producer) for two producers that
  slipped through. Reuse, not reinvent.
- **Plan:** `.shipwright/planning/iterate/proposed-idle-main-artifact-hygiene.md`.

## Problem

Idle `git status` on main is still not clean (verified live after PR #172). Two producers
leave untracked/uncommitted debris — the exact regression class ADR-089/PR #78 closed:

- **(a) phase-quality skill-compliance roll-ups.** `phase_quality/_dashboard_render.py`
  (driven by `regenerate_all_aggregates`, fired from the Stop-hook audit) regenerates 3 MDs —
  `skill-compliance-report.md` + `-dashboard.md` under `.shipwright/compliance/`, and
  `skill-compliance-findings.md` under `.shipwright/agent_docs/`. The per-finding JSON DIR
  `…/compliance/skill-compliance/` (`FINDING_DIR`) is ALREADY gitignored, but the 3 roll-ups
  sit in tracked-eligible homes → `??` noise on every Stop.
- **(b) bloat marker cwd-resolution.** `check_file_size.py` (PostToolUse writer) AND
  `bloat_gate_on_stop.py` (Stop reader) key the marker / baseline / re-measure off
  `Path.cwd()`. When a hook fires with cwd≠repo-root (sub-package test run, monorepo
  auto-descent), the marker is WRITTEN to `shared/.shipwright/locks/bloat_pending.*.json`
  — the root-anchored `/.shipwright/*` ignore misses it → `shared/.shipwright/` `??` noise.
  This is the very `cwd`-at-Stop antipattern ADR-089 hard-gated elsewhere.

## AC-1 decision (transient vs tracked-durable) — DECIDED: transient

Evidence (per the plan's "recover producer intent; do NOT guess"):
1. **Never tracked** — all 3 roll-ups are `??` in main; never committed.
2. **Not in `audit_staleness.DOC_REGISTRY`** — that registry holds the 5 compliance MDs +
   the 3 agent-doc trio (the tracked-durable single-producer set); no skill-compliance path.
3. **Added as Stop-hook infra** — commit `c9516f8f feat(phase-quality): Stop-hook audit
   infrastructure`; regenerated every Stop from the gitignored finding JSONs (derived cache).
4. **Consumed as LIVE state** — `skill-compliance-findings.md` → `capture_session_id.py`
   SessionStart injection banner; `skill-compliance-dashboard.md` → triage "Live view:"
   pointer (`_triage_bundle.DASHBOARD_REL`). No snapshot/iterate-boundary consumer.

⟹ **Transient.** Relocate all 3 INTO the already-gitignored `FINDING_DIR`
(`.shipwright/compliance/skill-compliance/{_report,_dashboard,_findings}.md`). Co-locates the
derived caches with their source JSONs under ONE existing gitignore rule. No `DOC_REGISTRY`
entry, no finalize-single-producer arm needed (they were never tracked-durable). Chosen over
scattering compliance rollups into the agent-doc-trio's `agent_docs/runtime/` (different
artifact family; would need a NEW canon entry).

## AC-2 decision — fix BOTH the writer and the reader (plan extension, documented)

The plan's AC-2 names only `bloat_gate_on_stop.py` (the reader). But the reader only READS;
the leak file is WRITTEN by `check_file_size.py` (the PostToolUse recorder), which has the
identical `Path.cwd()` bug. A reader-only fix is a band-aid — the writer would keep creating
`shared/.shipwright/locks/`. Coherent fix: resolve the **same canonical main-repo root** in
BOTH (writer + reader), via one shared fail-soft resolver, so marker/baseline/re-measure can
never disagree. Documented as an accepted deviation in the ADR.

## Design (reuse existing infra)

1. **`repo_root.main_repo_root_or(start, fallback=None)`** — fail-soft wrapper over
   `worktree_isolation.main_repo_root` (catches GitError/OSError/SubprocessError → returns
   `fallback or start`); advisory hooks must never brick. (Plan said "via `main_repo_root`
   (fail-soft)".) Lives in its OWN tiny module — NOT appended to the already-grandfathered
   `worktree_isolation.py` (448 LOC) — so the anti-ratchet bloat gate isn't tripped for a
   6-line helper (decided when the pre-commit gate blocked the in-module placement).
2. **`check_file_size.main()` + `bloat_gate_on_stop.main()`** — replace `cwd = Path.cwd()`
   with `root = main_repo_root_or(Path.cwd())`; pass `root` to marker/baseline/limit/guard.
   Helper signatures keep their explicit-path param (direct-call tests unaffected).
3. **`phase_quality/_constants.py`** — `REPORT_PATH`/`DASHBOARD_PATH`/`SUMMARY_PATH` → under
   `FINDING_DIR`. Consumers follow the constants: `capture_session_id.py` (SessionStart read),
   `_triage_bundle.DASHBOARD_REL` (← reference `DASHBOARD_PATH`, no re-declared literal),
   `_dashboard_render.py` docstrings.
4. **gitignore canon (AC-3)** — AC-1 needs no new entry (`skill-compliance/` already in the
   managed block + template). AC-2 adds a defensive non-anchored `**/.shipwright/locks/` to
   BOTH `.gitignore` and `shared/templates/shipwright-gitignore.template` (congruent block) so
   a stray nested locks dir can never leak; propagates to adopted repos (resolver is the real
   fix, this is belt-and-suspenders).
5. **Docs (AC-5)** — `docs/hooks-and-pipeline.md` artifact-write matrix + `docs/guide.md`
   path list + a `conventions.md` note generalising "marker/derived-cache producers resolve
   main_repo_root + write only to gitignored paths" (ADR-089 family).
6. **Cleanup** — remove the existing `shared/.shipwright/` + stale old-path skill-compliance
   MDs from the MAIN working tree (untracked derived debris; regenerated at the new path).

## Acceptance criteria

- **AC-1:** skill-compliance roll-ups relocated to gitignored `FINDING_DIR`; never `??` on
  idle main. Decision (transient) recorded above.
- **AC-2:** writer + reader resolve `main_repo_root` (fail-soft); no nested `.shipwright/locks/`
  leak; existing `shared/.shipwright/` removed.
- **AC-3:** the one new gitignore rule lives in the canon template (propagates to adopted repos).
- **AC-4:** empirical tests — non-root-cwd marker probe (real `git init` tmp repo: marker lands
  at ROOT) + git-status-clean-after-Stop for the 3 roll-ups + resolver fail-soft + regression
  guard (compliance set + agent-doc trio unaffected).
- **AC-5:** artifact-write matrix + guide + conventions updated.

## Out of scope

- D4 (WebUI launch-cards → tracked triage.jsonl), `trg-55516654`, WebUI repo.
- The historical `docs/migrations/.shipwright-agent_docs-relocation.md` record (past state).

## Confidence Calibration

- **Boundaries touched:** bloat marker `bloat_pending.<sid>.json` JSON read/write
  (writer `check_file_size` + reader `bloat_gate_on_stop`); `shipwright_bloat_baseline.json`
  read; git repo-root resolution (`worktree_isolation.main_repo_root`); gitignore canon
  template + framework `.gitignore` (adopt/self-heal propagation); SessionStart-injection
  contract (`capture_session_id` → `phase_quality.SUMMARY_PATH`); triage launchPayload
  pointer (`_triage_bundle.DASHBOARD_REL`); phase-quality roll-up producer paths.
- **Empirical probes run (real `git init` tmp repos + real subprocess hooks, no mocks):**
  - Writer fired from a sub-package cwd → marker lands at ROOT `.shipwright/locks/`, path
    recorded repo-relative (`shared/huge.py`); NO nested `shared/.shipwright/locks/`. ✔
  - Reader fired from a sub-package cwd → finds the ROOT marker + baseline → blocks a
    genuine crossing (current cwd-based code finds nothing → no block). ✔
  - `regenerate_all_aggregates` → 3 roll-ups under `skill-compliance/`; legacy
    tracked-eligible paths NOT written; `git status --porcelain -uall` clean (no
    `skill-compliance` entry) with the canon `.gitignore` installed. ✔
  - Defensive `**/.shipwright/locks/` actually ignores a stray nested marker (`-uall`). ✔
  - Resolver fail-soft: non-git dir → returns the fallback (advisory hooks never brick). ✔
  - Regression: `test_check_file_size_cross_repo`, `test_bloat_marker_worktree_aware`,
    `test_bloat_gate_on_stop`, `test_audit_phase_quality`, canon-path + gitignore-congruence
    suites all green (178 + 18 affected tests). ✔

- **Test Completeness Ledger** (principle: testable ⇒ tested; 0 testable-but-untested):

  | # | Behavior (AC) | Disposition | Evidence |
  |---|---|---|---|
  | 1 | `main_repo_root_or` resolves MAIN root from a subdir (AC-2) | tested | `test_main_repo_root_or_resolves_main_root_from_subdir` |
  | 2 | `main_repo_root_or` fail-soft → fallback on non-git/error (AC-2) | tested | `test_main_repo_root_or_falls_back_on_non_git` |
  | 3 | Writer: cwd≠root → marker at ROOT, repo-relative path (AC-2) | tested | `test_writer_subdir_cwd_writes_marker_to_repo_root` |
  | 4 | Reader: cwd≠root → reads ROOT marker + blocks (AC-2) | tested | `test_reader_subdir_cwd_reads_root_marker_and_blocks` |
  | 5 | Writer/reader unchanged in cwd=root + non-git tmp (AC-2 regression) | tested | `test_check_file_size_cross_repo`, `test_bloat_marker_worktree_aware`, `test_bloat_gate_on_stop` |
  | 6 | Roll-up constants live under `FINDING_DIR` (AC-1) | tested | `test_rollup_constants_live_under_finding_dir` |
  | 7 | Render writes 3 roll-ups under `FINDING_DIR`, not legacy paths (AC-1) | tested | `test_regenerate_writes_rollups_under_finding_dir` |
  | 8 | Roll-ups gitignored after render — idle-main clean (AC-1) | tested | `test_rollups_are_gitignored_after_render` |
  | 9 | SessionStart consumer reads from new `SUMMARY_PATH` (AC-1) | tested | `test_capture_session_id` (phase-quality block), `test_phase_quality_rollout` injection tests |
  | 10 | `DASHBOARD_REL` follows the relocated constant (AC-1) | tested | `test_phase_quality_triage_emit` (DASHBOARD_REL in detail/launchPayload) |
  | 11 | Defensive `**/.shipwright/locks/` in BOTH files + actually ignores nested (AC-2/AC-3) | tested | `test_nested_locks_rule_in_canon_template`, `..._in_framework_gitignore`, `test_nested_locks_dir_is_ignored_by_canon_block` |
  | 12 | Canon-path + gitignore-template congruence intact (AC-3 regression) | tested | `test_artifact_path_canon`, `test_gitignore_template_congruent` |

  No `untestable` rows. The `ImportError → return ""` fail-open in the consumer is a
  one-line defensive guard (mirrors the pre-existing untested fail-open guards in the same
  function); it is an implementation detail of behavior #9, not a separate AC behavior.

- **Confidence-pattern check:**
  - *Asymptote (depth):* root cause traced past the plan's literal AC-2 (which named only the
    reader) to the **writer** as the true leak author — proven by a real subprocess probe that
    the marker file lands at ROOT, not by assertion. AC-1 transient-vs-durable decided on 4
    independent evidence axes (never-tracked, not-in-DOC_REGISTRY, Stop-regenerated,
    live-consumer), not a guess.
  - *Coverage (breadth):* both producers (a)+(b); both sides of (b) writer+reader via a single
    shared resolver (can't drift); adopted-repo propagation (canon template + congruence);
    docs (matrix + guide + conventions); regression guards for the unchanged-cwd path and the
    compliance/agent-doc-trio sets. Out-of-scope D4 (WebUI, trg-55516654) explicitly excluded.
