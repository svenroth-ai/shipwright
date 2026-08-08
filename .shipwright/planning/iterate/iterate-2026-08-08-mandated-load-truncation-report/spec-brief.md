# Spec brief — iterate-2026-08-08-mandated-load-truncation-report

**Source:** TC3.2 (trg-c0d83dce). Small complexity (per Stage-1
classify_complexity.py: `small`, confidence 0.6, no risk flags) — no formal
iterate spec file (skipped at this complexity per the Phase Matrix). This
brief is the reviewable substitute, scoped in chat with the operator.

## Delivers TC3.2, not TC3.2a
TC3.2a (trg-8865b01e) — switching the four `decision_log.md` mandated readers
to index-first — is **already delivered** by commit `bf2efc95` (PR #608,
`iterate-2026-08-08-index-readers-adr-lock`) and is dismissed separately.
This run must not re-touch that wording; it only adds the truncation-report
half TC3.2 itself asks for, over the ONE remaining concrete instance TC3.2a's
fix did not cover: the `.shipwright/planning/*/spec.md` "read completely"
mandate (`context-loading.md` item 7, `step-1-interview.md`'s Extension-scope
list) — which has no ready-made index to dodge the cap with, so the honest
fix is an explicit coverage declaration, not a workaround.

## Acceptance Criteria

- **AC1.** A small shared helper (`shared/scripts/lib/mandated_load_coverage.py`
  + a thin CLI, `shared/scripts/tools/check_mandated_load_coverage.py`)
  reports, for a set of mandated-load file paths, each file's line count
  against the single-`Read`-call cap (2,000 lines) and an aggregate
  `any_exceeds_cap` flag. It does not read file *content*, does not decide
  what to do about an oversized file, and adds no persistence or schema —
  "a check, not an architecture" (TC3.2's own scoping words).
- **AC2.** The check is wired into the `.shipwright/planning/*/spec.md`
  "read completely" instruction in both
  `plugins/shipwright-iterate/skills/iterate/references/context-loading.md`
  (item 7) and
  `plugins/shipwright-project/skills/project/references/step-1-interview.md`
  (Extension-scope list) — replacing the blind promise with: run the check,
  then either read every line (offset/limit across multiple `Read` calls for
  a file over cap) or explicitly declare a partial read ("read K of N lines
  of {path} — not fully read") instead of proceeding silently.
- **AC3.** `decision_log.md`'s wording in either file is untouched — that is
  TC3.2a's surface, already fixed, and re-litigating it here would conflict
  with the operator's explicit instruction.
- **AC4.** Tests cover: within-cap, over-cap, the exact-cap boundary, a
  missing file (reported, not a crash), the aggregate flag across several
  files, a custom `--cap-lines`, and the CLI's `--glob` / `--path` / no-match
  behavior.
- **AC5.** No new persisted artifact, config key, or schema — the CLI prints
  a JSON report consumed inline by the invoking skill step; nothing writes
  it to disk.
