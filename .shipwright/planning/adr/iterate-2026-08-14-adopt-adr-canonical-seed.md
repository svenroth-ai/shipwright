# Adopt seeds its own canonical ADR folder; hollow retroactive ADRs fail closed

trg-50efc4c8: `/shipwright-adopt` minted its own "Adopted into Shipwright SDLC"
ADR and any retroactive ADRs only into `decision_log.md` — it never seeded
`.shipwright/planning/adr/`, the canonical ADR-spec folder every other plugin
writes to. Harvested third-party ADRs (`docs/adr/` etc.) stay exactly where the
maintainer put them — the fix is additive-only, never destructive to prior art.
Step E now seeds `.shipwright/planning/adr/` with adopt's own minted ADRs
(`lib/adr_seeding.py`) and best-effort refreshes `INDEX.md`
(`rebuild_adr_index.py`), and the `decision_log.md` "Imported decisions"
pointer sentence now names the canonical folder explicitly. A new soft check
(`soft_check_adr_seed_folder`) warns when the seed folder is empty or missing
its index, since seeding is best-effort by design and nothing else would
notice a silent degradation.

trg-6b59524b: a hollow retroactive ADR (missing `subject`/`sha`) rendered as
`### ADR-NNN: (no subject)` with an empty commit backtick, and adoption
reported success anyway. `_resolve_retroactive_adrs` now fails closed —
raising before `write_agent_docs` overwrites `architecture.md` /
`conventions.md` — preferring to derive `subject` from the commit when the
data exists rather than rejecting outright. `validate_adoption.py`'s density
check widened from counting ADR headings to per-field completeness.

Both write paths (the `decision_log.md` entry and the seeded spec file) were
made to agree on the same commit-fallback rendering (`unknown` vs. empty
backticks) after code review caught them diverging, which made the density
check flag its own output as hollow. A doubt-review pass found and closed five
further gaps: a filename-prefix regex that could manufacture a false
`ADR_OUTPUT_MAX_NUMBER` overflow from a foreign 4-digit-prefixed file; a
successful `INDEX.md` refresh never entering the gitignore-check's `written`
list; the new soft check above; a cross-check pinning adopt's duplicated
`ADR_SPEC_FOLDER` constant against `shared/scripts/lib/adr_index.py`'s; and the
plugin-local file-location loader for `hollow_adr_detection.py` gaining the
same missing-file/failed-exec guards `shared_loader.py` documents for the
`shared/`-tree case.

Rejected: importing `shared/scripts/lib/adr_index.py` directly from adopt's
`lib/` package — ADR-045's cross-plugin `lib` package collision rules out a
direct import, so `ADR_SPEC_FOLDER` is duplicated and pinned by a regex-based
test instead.
