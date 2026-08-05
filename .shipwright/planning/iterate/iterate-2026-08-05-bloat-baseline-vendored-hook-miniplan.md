# Mini-Plan: bloat-baseline-vendored-hook

- **Run ID:** iterate-2026-08-05-bloat-baseline-vendored-hook

## Files to create/modify

| File | Change type |
|---|---|
| `scripts/cache_tree_compare.py` | edit — trim `version_key` docstring |
| `shared/templates/hooks/ensure_shared_cache.py` | edit — trim `_version_key` comment (canonical vendoring source) |
| `plugins/{adopt,build,changelog,compliance,deploy,design,iterate,plan,project,run,security,test}/scripts/hooks/ensure_shared_cache.py` (12 files) | edit — byte-identical re-vendor from the canonical template |
| `shipwright_bloat_baseline.json` | edit — add 13 grandfathered entries (canonical template + 12 copies) |

## Work breakdown

1. Trim `version_key`'s docstring to essential content only, verify
   `wc -l` back at or under 300. — DONE (305→294).
2. Trim `_version_key`'s comment in the canonical hook template to
   essential content only. — DONE (325→321, still over 300: pre-existing
   debt, see Out of Scope).
3. Byte-copy the trimmed canonical template into all 12 plugin hook
   files, confirm `test_ensure_shared_cache_vendored.py` stays green.
   — DONE.
4. Add 13 entries to `shipwright_bloat_baseline.json` (`limit: 300,
   current: 321, state: grandfathered, adr: null`) for the canonical
   template + its 12 vendored copies. Appended at the end of the
   `entries` array rather than threaded into alphabetical position — no
   test enforces array order (`test_bloat_baseline.py`'s round-trip test
   compares *sorted* path sets, not literal array order), and manual
   13-point mid-array JSON surgery is a needless transcription-error risk
   for a purely additive, order-independent change. — DONE.
5. Re-run the full 138-test set (5 files the fixed bug touched + 2 bloat
   test files) — identical pass count to pre-trim. — DONE.
6. `ruff check` on all 14 touched `.py` files — clean. — DONE.
7. External LLM review (medium auto-trigger). — DONE, 2 rounds: round 1
   flagged an unreproducible runner cwd/path mismatch and a ledger count
   error (both fixed), round 2 requested a direct probe against the real
   Stop-hook entry point rather than trusting only the loader's unit
   tests (added, `WOULD PASS`); round 3 unanimous approve.
8. Full Code Review cascade (spec-reviewer → code-reviewer →
   doubt-reviewer). — DONE: spec-reviewer PASS, code-reviewer ACCEPT with
   2 low-severity citation-restoration suggestions (both applied,
   305→294→295 / 325→321→322, baseline `current` updated to 322 and
   12 copies re-vendored to match, all 138 tests + the direct probe
   re-verified green after the restore).
9. Finalization F0–F12. — PENDING.

## Test strategy

No new test is needed and none is written: this iterate changes zero
logic (comment/docstring density only) and adds rows to an already-tested
JSON schema (`bloat_baseline.py`'s loader and the Stop-hook's crossing
check are both already covered by `test_bloat_baseline.py` /
`test_bloat_defense_artifacts.py`, which read the real file this iterate
edits). The empirical proof is a before/after re-run of the exact same
138 tests showing an identical pass count — the trim provably changed
nothing observable.

## Alternative approach (considered, rejected)

**Alternative: split `shared/templates/hooks/ensure_shared_cache.py` into
multiple smaller modules** (e.g. separate the version-comparison helpers,
the walk/mirror logic, and the marketplace-resolution logic into sibling
files under `shared/templates/hooks/`).

**Rejected because:**
- The file is deliberately **stdlib-only** — it repairs the very
  `shared/` tree it would otherwise import from, so it cannot `import`
  sibling modules the normal way without first solving the exact
  chicken-and-egg problem this hook exists to solve.
- Splitting into vendored sibling files means **multiplying the
  vendoring surface 13x** (every new file needs the same byte-identity
  guarantee across all 12 plugins + the canonical template), for a
  hygiene-only motivation with no functional upside.
- The overage (317 lines pre-existing, 322 now) is modest — 22 lines
  over a 300-line *guideline*, not a hard architectural signal that the
  file is doing too many unrelated things. `grandfathered` registration
  is the proportionate response the repo's own baseline already uses
  131 times for exactly this shape of debt.
