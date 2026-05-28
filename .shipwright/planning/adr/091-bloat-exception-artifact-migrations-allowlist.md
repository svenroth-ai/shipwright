# ADR-091: Bloat exception — `shared/scripts/lib/artifact_migrations.py` raised to 592-LOC

<!-- Granting a bloat-baseline exception for the artifact-path-canon
     migration manifest. New `current` lands in shipwright_bloat_baseline.json
     with state="exception" and adr="ADR-091". -->

- **Status:** accepted
- **Date:** 2026-05-29
- **Re-Review-Date:** 2026-08-29 _(3 months — checkpoint to dedupe the four
  parallel ALLOWLIST blocks into a shared base list and retire this exception)_
- **Incident Reference:** iterate-2026-05-29-fix-path-canon-allowlist —
  `test_artifact_path_canon` went red on 41 legitimate references after
  Campaign A.defense + Campaign B (PRs #96/#99/#102 + A.foundation/defense)
  added new files and split allowlisted monoliths into packages without
  updating this manifest's ALLOWLIST.

## Context

`shared/scripts/lib/artifact_migrations.py` is the single source of truth for
the four artifact-directory migrations (`planning`, `designs`, `agent_docs`,
`compliance`) into `.shipwright/`. It carries `ARTIFACT_MIGRATIONS` (4 dicts of
regex + AST patterns) and `ALLOWLIST` (a dict of four lists of glob patterns
exempting files that legitimately reference a legacy-dirname token). It was
grandfathered at `current=567`.

This iterate had to add six allowlist entries to clear the lint after Campaign
A/B: `plugins/shipwright-iterate/tests/**` (×2, the one plugin test dir never
allowlisted), `shared/scripts/lib/phase_quality/**` (B3 split successor,
replaces the stale `phase_quality.py` line 1:1), `orchestrator_pkg/**` (B5),
`shared/contracts/**` (B8), `shared/glossary.md` (A.defense), and
`shipwright_bloat_baseline.json` (A.foundation; JSON has no inline-marker
syntax). The six entries plus terse per-entry provenance comments push the file
to 592 LOC. The six glob lines alone (zero comments) already exceed 567 — the
growth is arithmetically unavoidable for this fix.

## Ousterhout Argument

Honest framing: this is a **data manifest**, not a behaviour-deep module in the
classic sense — the depth is curated domain knowledge (which files legitimately
reference a legacy token, and why), not algorithm. The interface IS narrow:
`get_migration(name)`, `active_migrations()`, and two module-level constants
(`ARTIFACT_MIGRATIONS`, `ALLOWLIST`) consumed by `test_artifact_path_canon`, the
drift detector, and the artifact-drift hook. Splitting `ALLOWLIST` into its own
module would only move bytes — the consumers import both constants from one
place by design, and the per-entry Chesterton-fence comments must travel with
the data. The genuine structural debt is the ~30-entry duplication across the
four parallel ALLOWLIST blocks; that is the retirement target (see Decision),
not a same-iterate split.

## YAGNI Check

Every one of the six new entries exempts a file that exists **today** and
references a legacy-dirname token **today** — verified individually before
allowlisting (41 findings, all legitimate, zero real legacy-path bugs). None is
speculative. No responsibility was added to the file beyond the exemption data
the lint already consumes. Nothing here could be deleted with "some work" — the
entries are load-bearing for a green lint.

## Chesterton-Fence Check

The current four-block shape exists because the lint is parametrized per
migration and each migration scopes its own exemption set
(`ALLOWLIST.get(migration["name"], [])` in `_eligible_files`). That fence
stands for a documented reason — per-migration scoping prevents one migration's
exemption from silently exempting a file for a different migration. The fence is
kept. The *duplication within* the four blocks (identical framework-file /
self-adopted-record / JSON-capture entries) has no load-bearing reason and is
the documented retirement target.

## Decision

Grant `current = 592`, `state = "exception"`, `adr = "ADR-091"` for
`shared/scripts/lib/artifact_migrations.py` in `shipwright_bloat_baseline.json`,
in the same commit as the ALLOWLIST additions (the hook's sanctioned
remediation #3). Retirement plan: a future dedicated refactor iterate (by the
Re-Review-Date) extracts a `_COMMON_ALLOWLIST` shared base and rewrites each
migration's list as `[*_COMMON_ALLOWLIST, *<migration-specific>]`, which drops
the file well below 567 and lets the exception be retired.

## Consequences

Anyone editing this manifest now operates against the 592 limit; further
allowlist growth needs another deliberate bump (correct — keeps additions
visible). No downstream consumer changes: the public surface
(`get_migration`, `active_migrations`, the two constants) is unchanged. Cost if
the exception outlives 2026-08-29: the manifest keeps accreting per-entry
duplication, making the eventual dedupe slightly larger — bounded and benign.

## Rejected alternatives

- **Leave at 567 and split now.** Splitting `ALLOWLIST` into its own module is
  pure byte-moving (consumers import both constants together); it would not
  reduce total LOC, only fragment the manifest. Rejected — no real benefit,
  added import indirection.
- **Dedupe the four blocks in this iterate.** The behaviour-preserving dedupe
  (`_COMMON_ALLOWLIST`) is the right long-term fix but is a structural refactor
  with real regression risk (any matching-semantics drift silently re-breaks the
  lint), out of scope for a lint-drift bug fix. Deferred to the Re-Review with a
  concrete plan. Rejected for now on scope + risk grounds.
- **Loosen the `compliance/` regex / drop comments to fit 567.** Regex loosening
  globally weakens legacy-path detection (masks real bugs) — already rejected in
  the iterate ADR. Stripping all provenance comments to claw back ~25 lines would
  still not reach 567 (six glob lines alone exceed it) and would gut the
  Chesterton-fence documentation the file's own header mandates.
