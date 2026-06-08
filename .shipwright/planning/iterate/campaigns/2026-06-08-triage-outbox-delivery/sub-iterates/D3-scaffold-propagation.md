# Sub-Iterate: D3 — Explicit propagation of the outbox path into adopted repos + tests + docs

## Scope

Scaffold the outbox + `.gitignore` entry into adopted repos EXPLICITLY (adopt step + iterate self-heal in setup_iterate_worktree), like the `.gitattributes` union driver — do NOT assume 'shared/ change = deployed' (Codex Q6). Tests for the propagation path. Docs: `docs/hooks-and-pipeline.md` (artifact-write matrix — producers now write the outbox), `shared/glossary.md` (Outbox term), guide if user-facing.

## Acceptance Criteria

- [ ] adopt scaffolds the `triage.outbox.jsonl` gitignore entry into a fresh repo
- [ ] iterate self-heal ensures the gitignore entry exists in a managed repo on next setup
- [ ] hooks-and-pipeline.md artifact-write matrix updated (producers -> outbox)
- [ ] glossary defines Outbox

## Review Cascade Remediation (post-D3, 2026-06-08)

A follow-up review cascade on the merged D3 branch surfaced 1 MED + 3 LOW (no
HIGH). The reviewer CONCEDED the core design (self-heal as a guarded `chore`
commit, single-sourced merge in `gitignore_canon.plan_merge`, the step-4.6 wiring)
is sound — these are targeted hardenings + a missing-seam test, NOT a redesign.
All accepted-and-fixed with EMPIRICAL tests (real git / worktrees / outbox / the
real in-process `setup_iterate_worktree.setup` — no mocks for git).

| FIX | Sev | Finding | Disposition |
|-----|-----|---------|-------------|
| MED-1 | med | The self-heal↔sweep STAGED-STATE seam was untested: the existing wiring test seeds NO outbox, so the combined path (step 4.6 commits `.gitignore`, then step 5 must still find a clean index and fold a NON-EMPTY outbox) had no coverage — a future regression that left `.gitignore` staged would false-skip the sweep silently. | accepted-and-FIXED: new `test_gitignore_selfheal_then_outbox_sweep_both_commit` (in `test_setup_iterate_worktree.py`) seeds a managed repo on `origin/main` with a tracked `triage.jsonl` (schema header) + union `.gitattributes`, a `.gitignore` MISSING the canon block, AND a NON-EMPTY outbox (one valid append line); runs the REAL in-process `setup(...)`; asserts the branch HEAD chain contains BOTH the gitignore self-heal `chore` AND a `chore(triage): sweep 1 outbox append(s)` commit, `git status --porcelain` is clean, and the swept line is present in the branch's tracked `triage.jsonl`. Locks the seam against regression. |
| LOW-1 | low | A `skipped` sweep (e.g. `reason=staged_changes` from a self-heal that left `.gitignore` staged) was SILENT in `setup_iterate_worktree` — only `invalid`/`error` reached stderr — so a self-heal-induced staged residue would silently defer delivery. | accepted-and-FIXED: setup now surfaces `skipped` sweeps to stderr (and into the `warnings` payload) alongside `invalid`/`error`; a one-line note in `gitignore_selfheal._restore` documents the suppressed-`reset` → possible-stale-stage → fail-safe-re-sweep chain (mirrors the gitattributes rationale). |
| LOW-2 | low | Steps 4.5/4.6 called both self-heals inside a tuple literal in a loop, which reads as lazy and discarded all non-error heal results (no observability parity with the sweep). | accepted-and-FIXED: explicit `ga = self_heal_gitattributes(...)` then `gi = self_heal_gitignore(...)` on separate lines (gitattributes-then-gitignore order preserved); any non-`no_change` heal status (`committed`/`skipped`/`error`) is appended to the returned `warnings` list so operators get the same observability the sweep already had. Behavior otherwise identical. |
| LOW-3 | low | `gitignore_selfheal` read `.gitignore` with strict UTF-8, so a non-UTF-8 file raised `UnicodeDecodeError` — a `ValueError` NOT caught by `setup.main`'s `(GitError, OSError)` handler → crashes setup, violating the never-raises fail-soft contract. | accepted-and-FIXED: read with `errors="replace"` in `gitignore_selfheal` AND the analogous read in `gitattributes_union` (kept congruent); two new tests (`test_non_utf8_gitignore_does_not_raise`, `test_non_utf8_gitattributes_does_not_raise`) write a genuinely-undecodable byte and assert the self-heal returns a structured `committed` result without raising. |

Doc-consistency note: this cascade also added the missing `## Architecture
Updates` bullet for `iterate-2026-06-08-outbox-delivery-d3` (the D3 decision-drop
declared `architecture_impact=convention` but `architecture.md` lacked the matching
entry — a pre-existing red on the D3 branch surfaced by
`test_every_arch_impact_drop_has_architecture_md_entry`).

Module-size note: every changed source file stays at/under the 300-LOC guideline
(`gitattributes_union.py` 300, `setup_iterate_worktree.py` 300,
`gitignore_selfheal.py` 208) — no new bloat-baseline crossing; the hardening
comments were compressed to hold the line.
