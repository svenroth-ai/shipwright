# Iterate Spec: C.2 — ADR-bloat + Architecture-drift + CLAUDE.md-bloat detectors

- **Run ID:** iterate-2026-05-21-c2-architecture-and-adr-drift-detector
- **Type:** feature
- **Complexity:** small
- **Status:** draft

## Goal

Close the artifact-polish plan's Iterate C.2 by adding four detective-
only documentation-hygiene checks to the compliance audit's Group F
(structural-integrity, ADR-related):

1. **F4 ADR-bloat** — ADRs > 60 lines without a `spec_ref` link.
2. **F5 architecture drift** — `architecture.md` marker vs new
   `architecture_impact ∈ {component, data-flow}` decision-drops.
3. **F6 CLAUDE.md size** — CLAUDE.md > 200 lines.
4. **F7 CLAUDE.md iterate-annotation leak** — regex-counted inline
   `Iterate X.Y (ADR-NN)` references > 5.

These fire when the operator runs `/shipwright-compliance` (audit
mode), surfacing drift as fail-finding rows + mirrored triage items.

## Acceptance Criteria

- [ ] **AC-1** `group_f.run()` returns 7 findings instead of 3 — F1-F3
  (existing preventive-rerun structural checks) + F4-F7 (new
  detective-only doc-hygiene checks).

- [ ] **AC-2** F4 reads `.shipwright/agent_docs/decision_log.md`,
  parses compact-format ADRs (`### ADR-NNN:` headers + body lines),
  and flags ADRs with body > 60 lines AND no `**Details:**` link
  (indicating an unlinked `.shipwright/planning/adr/<NNN>-...md`
  spec file).

- [ ] **AC-3** F4 detail lists the heaviest 5 bloated ADRs sorted
  desc by line count; evidence carries the full list.

- [ ] **AC-4** F5 reads the `<!-- shipwright:architecture v=N
  last-sync=<sha> -->` marker from `architecture.md` and scans
  `.shipwright/agent_docs/decision-drops/*.json` for drops with
  `architecture_impact ∈ {component, data-flow}`. Drift conditions:
  - Marker missing + any arch-impact drops → fail (need first sync).
  - Marker present + drops added after the marker's commit (via
    `git log <marker_sha>..HEAD -- decision-drops/`) → fail.
  - All other states → pass / skip.

- [ ] **AC-5** F6 counts CLAUDE.md lines; fails if > 200.

- [ ] **AC-6** F7 regex-counts `Iterate [0-9A-Z][0-9A-Z.]*(\s*\(?ADR-[0-9]+\)?)?`
  in CLAUDE.md; fails if > 5.

- [ ] **AC-7** All four new checks are tagged
  `source=SOURCE_DETECTIVE_ONLY` (the existing F1-F3 stay
  `SOURCE_PREVENTIVE_RERUN`). Errors during any check produce
  `severity=HIGH status=fail` findings with the exception type in
  `detail`, never crashing the audit.

- [ ] **AC-8** When a check's source artifact is missing (CLAUDE.md
  absent, decision_log.md absent, decision-drops/ absent), the check
  returns `status=skip` with a clear `detail` — never crashes,
  never false-positives.

- [ ] **AC-9** Each check's `detail` includes a concrete fix hint
  pointing the operator at the right intervention (e.g. "refactor
  into `.shipwright/planning/adr/<NNN>-<slug>.md` and link via
  `--spec-ref`"). Audience-principle: every fail row tells the
  operator what to do next.

- [ ] **AC-10** The mirror-findings-to-triage path produces one
  `source="compliance"`, `kind="compliance"` triage item per failing
  F4/F5/F6/F7 with `dedup_key=<check_id>` (existing behavior of
  `audit_detector.mirror_findings_to_triage`).

## Out of scope

- **F4 verbose-format ADR parsing** — the verbose ADR format (`##
  ADR-NNN | date | section | Commit`) is no longer emitted by the
  decision-drop pipeline; only compact-format ADRs are eligible for
  bloat detection. Verbose ADRs are pre-A.3 historical and don't
  count toward the cap.

- **F5 retroactive drops scanning** — when git is unavailable (not a
  repo, no `git` on PATH), F5 skips rather than emitting a false
  positive. Tests cover the git-available path via subprocess + the
  marker-missing fast path.

- **F6/F7 configurable thresholds** — fixed at 200 lines / 5
  references per the plan B.4 spec. Configurable threshold deferred
  until an operator complains.

- **CLAUDE.md per-file checks for multi-CLAUDE.md repos** — the
  audit reads `project_root/CLAUDE.md` only. Subdir CLAUDE.md files
  are out of scope.

## Implementation Notes

- The four new checks each have a private helper
  (`_check_f4` / `_check_f5` / `_check_f6` / `_check_f7`) returning
  `(status, severity, detail, evidence)` — same shape as group_d's
  private helpers. A thin `_detective_finding` adapter wraps the
  helpers into `Finding` objects with `source=SOURCE_DETECTIVE_ONLY`.

- F5's git invocation uses `subprocess.run` with `timeout=10` so a
  hung git command can't stall the audit indefinitely.

- The `_ITERATE_REF_RE` regex is anchored at `Iterate ` followed by
  an alphanumeric+dot token, optionally followed by `(ADR-NN)` /
  `ADR-NN`. Matches "Iterate A.1 (ADR-048)", "Iterate B0",
  "Iterate B.2 — SBOM polish".

## Verification

- `uv run --extra dev pytest plugins/shipwright-compliance/tests/test_audit_groups_c_f.py
  -v` — 13 new tests across `TestF4AdrBloat`, `TestF5ArchDrift`,
  `TestF6F7ClaudeMdHygiene` (passing/failing/skipping paths for
  each).

- Full compliance suite: 424 passed (baseline 411 + 13 new).

- Full shared suite: 2141 maintained.
