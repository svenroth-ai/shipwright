# Mini-Plan — P4.1 glossary generator

Run-ID: iterate-2026-09-09-p4-1-glossary-generator
Campaign: req3-09-p4-grill-glossary (sub-iterate P4.1)
Complexity: small (Step 2 classifier); effective complexity: small
(Step 3.4 diff-driven re-check — carries `touches_migrations` from Stage-1,
no diff-driven detector fired; diff 578 LOC triggers plan review + code
review cascade regardless of complexity tier)

## 1. Files to create/modify

- **New:** `shared/scripts/tools/write_context_term.py` — the CONTEXT.md
  producer. Follows `shared/context-format.md`'s schema (Language /
  Relationships / Flagged ambiguities), writes/updates a single sharpened
  `Language` term, idempotent.
- **New:** `shared/tests/test_write_context_term.py` — unit tests (direct
  function calls) + subprocess tests exercising the exact CLI invocation
  shape the interview protocol wires in (the "wired path").
- **Edit:** `plugins/shipwright-project/skills/project/references/interview-protocol.md`
  — add a "Capturing sharpened terms — write CONTEXT.md as you go" section
  instructing the producer be called during the turn a term is sharpened
  (`shared/requirement-elicitation.md` §4/§7), not batched at end-of-interview.
- **Edit:** `shared/tests/test_requirement_elicitation_refs.py` — drift test
  pinning that `interview-protocol.md` cites `write_context_term.py` and
  describes the "during the turn" (not batched) requirement — the only test
  possible for a prompt-only instruction (elicitation §6's
  enforced/prompt-only/contradicted table).

`plugins/shipwright-adopt/**` is explicitly out of scope (owned by a
different triage item) and is not touched.

## 3. Component hierarchy

N/A — no UI surface.

## 4. Data model changes

None. `CONTEXT.md` is a plain markdown file in the target project, not a
database or schema artifact.

## 5. Test strategy

- Unit tests on `upsert_term`/`find_context_file` (creation, append,
  update-in-place, idempotency, preservation of hand-written content in the
  other two sections) — `shared/tests/test_write_context_term.py`.
- Subprocess tests invoking the script exactly as the wired
  `interview-protocol.md` instruction shape does, asserting the produced
  file matches `shared/context-format.md`'s documented shape (AC3).
- A second sharpened term through the same wired CLI path, asserting no
  corruption/duplication of the first (AC4).
- Drift test (`test_requirement_elicitation_refs.py`) pinning the wiring
  citation itself, since the instruction to call the producer is
  prompt-only and cannot be behaviorally tested any other way.
- No E2E/browser surface — this is a backend script + doc change only.

## Known limitations / explicitly out of scope

- Only `Language`-section (term) writes are implemented — `Relationships`
  and `Flagged ambiguities` sections are preserved verbatim but not written
  by this tool. The sub-iterate's scope and ACs are about capturing a
  *sharpened term*, which is a `Language` entry; ambiguity-resolution
  writes are a natural follow-up, not blocked by anything here (the
  section headers already exist in every file this tool creates).
- Multi-domain `CONTEXT-MAP.md` layout (`shared/context-format.md` §4) is
  out of scope — single-domain `<project_root>/CONTEXT.md` only.
