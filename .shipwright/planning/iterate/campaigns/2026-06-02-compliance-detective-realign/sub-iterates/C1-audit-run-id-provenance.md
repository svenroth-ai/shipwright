# C1 — Detective audit honors Run-ID provenance (B7 + Group E)

- **Type:** change (check-logic realign)
- **Complexity:** medium (two checks, two modules, shared helper opportunity)
- **Repo:** monorepo (`plugins/shipwright-compliance`)
- **Depends on:** —
- **Closes:** Group E of `trg-8747213b`; B7 of `trg-2bce4cc6`

## Problem

Two detective checks assume a pre-2026-05-29 linkage model:

- **B7** (`group_b._check_b7`, `git_log_scan.apply_retention_rules`) decides
  "commit has a matching event" purely via the event `commit` field. Since
  `iterate-2026-05-29-events-jsonl-worktree-commit`, `work_completed` events
  ship `commit:""` **by design** and link via the F6 commit's `Run-ID:` footer
  ↔ the event's `adr_id`. B7 never reads that footer → flags every new-flow
  iterate commit as "no matching event". **Verified:** `26ea506` carries
  `Run-ID: iterate-2026-06-02-campaigns-board-lane`; `evt-177f8389` has the
  matching `adr_id`; B7 still reports it uncovered.
- **Group E** (`audit_staleness.find_snapshot_commit`) finds the "last snapshot"
  via `git log --grep=Run-ID:`. `/shipwright-changelog` regenerates the tracked
  MDs and commits them as `chore(release):` **without** a `Run-ID:` trailer, so
  the audit compares on-disk (== HEAD) against the older iterate-finalize
  snapshot → perpetual "stale". **Verified:** `a0aa1e62` regenerated both MDs
  (`phase: changelog`, `run_id: changelog-v0.23.1-…`); triage detail names the
  stale snapshot `f75a0390`.

Both are the same conceptual gap: the audit's notion of *"who legitimately
produced this commit/snapshot"* is stuck on `Run-ID:`-trailer-only.

## Goal

Teach the detective audit to honor Run-ID provenance for **both** the
event↔commit link (B7) and the tracked-MD snapshot link (Group E), with a
commit-field / legacy fallback so out-of-band and pre-redesign data still match.

## Acceptance Criteria

- [ ] **AC-1 (B7 Run-ID match).** A commit whose `Run-ID:` footer equals some
      `work_completed` event's `adr_id` counts as covered, even when that
      event's `commit` field is empty. Full/prefix `commit`-field match retained
      as fallback for legacy/out-of-band events (e.g. the reopen event, which
      has a real SHA).
- [ ] **AC-2 (B7 stops false-flagging tracked iterate work).** Re-running the
      audit on the webui at `e3b1021`, `26ea506` (the FR-01.33 feature, whose
      event ships `commit:""` and links via Run-ID↔adr_id) is no longer
      "uncovered". **DECISION (2026-06-02, user):** do NOT add a *blanket*
      commit-type exclusion. B7 exists precisely to surface commits that bypassed
      the iterate flow; excluding `ci`/`docs`/`chore` by type would hide exactly
      that drift and neuter the check. **Sub-iterate B (folded into PR #142)**
      adds ONE narrow, principled recognition: a `chore(release)` commit
      (`da43aa4e`) is the changelog phase's tracked output — NOT drift — so Rule D
      in `git_log_scan.apply_retention_rules` excludes it, parallel to AC-3's
      Group E recognition. The 4 ci/docs hits (`d66ab550`/`71962052`/`48badb61`/
      `fff2b02d`) have neither a SHA nor a Run-ID match → they genuinely ran
      outside iterate. Those stay CORRECT findings (transient — age out at the
      next release tag) and are **fixed by recording events** in C4 (sub-iterate
      A), NOT suppressed and NOT via a `disabled_checks` mask.
- [ ] **AC-3 (Group E release snapshot).** `find_snapshot_commit` recognizes a
      changelog/release snapshot (the tracked MD's `canon_generated`+`phase:
      changelog` frontmatter, or a release-commit Run-ID trailer — pick one and
      document). A clean release commit no longer produces a Group E "stale".
- [ ] **AC-4 (no false-negative).** A genuinely hand-edited tracked MD (drift
      outside any recognized producer) is still flagged stale.

## Tests

- B7: event with `commit:""` + matching `adr_id`↔commit `Run-ID:` footer → covered.
- B7: legacy event with a real (full/abbrev) `commit` SHA → still covered (fallback).
- B7: chore/ci commit with neither event nor Run-ID match → still uncovered.
- Group E: tracked MD == a `chore(release)` snapshot → green (not stale).
- Group E: tracked MD hand-edited away from every recognized snapshot → stale.

## Risk / care

- Fail toward FLAGGING on ambiguity (a missed real drift is worse than a noisy
  one). The Run-ID match must be exact (`adr_id == footer run_id`), not prefix,
  to avoid cross-iterate false matches.
- Update `docs/hooks-and-pipeline.md` if the snapshot-provenance contract wording changes.
