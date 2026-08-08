# ADR Spec-Folder Number Collision Report

- **Run ID:** iterate-2026-08-08-index-readers-adr-lock
- **Measured:** 2026-08-08, `main` at PR #605 (`b7615e64`) — regenerate via
  `uv run shared/scripts/tools/rebuild_adr_collision_baseline.py --project-root .`
- **Filed here, not under `.shipwright/planning/adr/`**, because that folder
  is rendered verbatim into the committed `INDEX.md` — a report there would
  become a pseudo-ADR entry (Opus plan-review finding 6).
- **No file listed below is renamed by this run** (explicit operator
  instruction — a wrong rename is worse than a known collision). This report
  is informational; resolution, if any, is the operator's call.

## Why this exists, and why it stops here

`.shipwright/planning/adr/<NNN>-slug.md`'s `<NNN>` was, until this run,
guessed by unaided agent judgment at branch time — no coordination between
parallel iterates sharing a base. Going forward, new spec files are named
`<run_id_sanitized>-<slug>.md` (F3.md), which structurally cannot collide.
That fix is forward-only: it does not touch any file that already exists.
The 15 files below are the accumulated result of the old convention.

## What a bare `ADR-NNN` citation means today

`.shipwright/planning/adr/<NNN>-slug.md`'s number and
`decision_log.md`'s own fold-assigned `ADR-NNN` are — and always were —
**two independent numbering identities** (confirmed by reading
`aggregate_decisions.py`: it renders whatever `spec_ref` filename a drop
carries, verbatim, and never reconciles it against the number it assigns to
the short entry). A colliding spec-folder number does **not** mean two
`decision_log.md` entries share a number — `decision_log.md` itself has no
duplicates. It means two long-form spec files happen to share a filename
prefix. `lib/adr_index.py`'s freeform-rendering fallback already displays
both rows correctly (`test_duplicate_numbers_both_appear`,
`shared/tests/test_adr_index.py`) — the collision is a filename-identity
problem, not a rendering bug and not data loss.

## The 15 files, by colliding number

Citation counts are `git grep -c "ADR-<NNN>\b" -- '*.md'`, **excluding**
matches inside the colliding files themselves (their own self-reference).
"Citing files" lists every OTHER file that mentions the bare number — this
is what a rename would have to touch.

### ADR-097 — 2 files, 6 citations across 5 files

- `097-bloat-b7-rule-e-test-growth.md`
- `097-bloat-exception-oss-backend-gitleaks-report-path.md`

Cited in: `.shipwright/agent_docs/architecture.md`,
`.shipwright/agent_docs/conventions.md`, `decision_log.md`,
`decision_log_index.md`, `.shipwright/planning/adr/INDEX.md`.

### ADR-120 — 2 files, 16 citations across 8 files

- `120-coverage-gates-ask-the-diff.md`
- `120-the-cache-check-reads-the-index-not-the-disk.md`

Cited in: `.shipwright/agent_docs/conventions.md`, `decision_log.md`,
`decision_log_index.md`, `.shipwright/planning/adr/INDEX.md`, two
`iterate-2026-08-01-cache-heal-per-plugin*` planning files, a
`CHANGELOG-unreleased.d` entry, and `docs/hooks-and-pipeline.md`. The widest
cross-reference spread of the six — the most a rename would have to touch.

### ADR-125 — 2 files, 5 citations across 4 files

- `125-bloat-exception-risk-recheck-recording-registration.md`
- `125-iterate-timings-derived-parent-synthesis.md`

Cited in: `.shipwright/agent_docs/conventions.md`, `decision_log.md`,
`decision_log_index.md`, `.shipwright/planning/adr/INDEX.md`.

### ADR-126 — 2 files, 7 citations across 5 files

- `126-context-cost-meter.md`
- `126-test-phase-attribution.md`

Cited in: `.shipwright/agent_docs/conventions.md`, `decision_log.md`,
`decision_log_index.md`, `.shipwright/planning/adr/INDEX.md`, and a
`2026-06-12-hook-resolver-canon.md` planning note.

### ADR-127 — 5 files, 25 citations across 10 files

- `127-agent-model-tiers-per-role-tiers.md`
- `127-bloat-exception-atomic-write-none-winerror-retry.md`
- `127-decision-log-drops-index.md`
- `127-events-context-backfill-keys.md`
- `127-run-id-lifecycle-fixes.md`

Cited in: `decision_log.md`, `decision_log_index.md`,
`.shipwright/planning/adr/INDEX.md`, both `128-*` colliding files
(cross-referencing 127 by number), and four `iterate-2026-08-07`/
`iterate-2026-08-08` planning files. **Five files on one number** — the
worst collision by file count, and the most citations of the six.

### ADR-128 — 2 files, 5 citations across 4 files

- `128-coverage-envelope-not-applicable-missing-split.md`
- `128-track-decision-drops.md`

Cited in: `.shipwright/agent_docs/conventions.md`, `decision_log.md`,
`decision_log_index.md`, `.shipwright/planning/adr/INDEX.md`. The most
recent collision — both files landed via #604/#605, the two PRs merged
immediately before this run branched.

## What a rename would break

Every number above is cited from `decision_log.md`, `decision_log_index.md`,
and `.shipwright/planning/adr/INDEX.md` at minimum — those three are
regenerated/appended-to by tooling, not hand-edited, so a rename would need
to either regenerate them (safe, mechanical) or hand-patch stale references
(error-prone). ADR-120, ADR-126, and ADR-127 are additionally cited from
hand-written planning notes and, for ADR-120, `docs/hooks-and-pipeline.md` —
those are prose files a rename tool would not touch automatically, so a
rename risks leaving a dangling cross-reference exactly where a human reader
would trust it least. ADR-127 is also self-referenced from within the two
`128-*` files (one collision citing another) — untangling that pair without
breaking the citation requires reading both files' content, not a
mechanical string-replace.

## Proposed resolution (operator's call — not applied in this run)

Two honest options, neither applied here:

1. **Leave as-is.** The freeform-fallback rendering already displays every
   row correctly and the anti-ratchet drift guard (`shared/tests/
   test_adr_index_no_duplicate_numbers.py`) now pins exactly these 15 files
   so none of them can silently multiply. Cost: a bare `ADR-NNN` citation
   remains ambiguous between up to 5 files for these 6 numbers specifically.
2. **Rename deliberately, one number at a time**, starting with ADR-097 (the
   fewest cross-references) and ending with ADR-127 (the most, and the one
   with an internal cross-reference to untangle first). Each rename should
   follow the SAME convention this run establishes for new files
   (`<run_id_sanitized>-<slug>.md` — but note the ORIGINAL `run_id` that
   produced each file is not recoverable from the file alone, so a
   descriptive slug substitute would be the practical choice), update the
   three tooling-owned files by regenerating (`rebuild_adr_index.py`), and
   hand-fix the prose citations listed above.

This run does neither — reporting the count and the risk is the full scope
of AC6.
