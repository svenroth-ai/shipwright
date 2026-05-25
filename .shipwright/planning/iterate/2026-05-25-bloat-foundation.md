# Iterate Spec: bloat-foundation

- **Run ID:** iterate-2026-05-25-bloat-foundation
- **Type:** feature
- **Complexity:** medium
- **Status:** draft
- **Campaign:** Bloat Cleanup Track A — Prevention (A.foundation = A1 + A2 + A3)
- **Source plan:** `.shipwright/planning/campaigns/2026-05-21-bloat-cleanup-A-prevention.md`

## Goal

Land the structural Loop-Gate that prevents bloat regrowth: extend the
PostToolUse `check_file_size.py` hook to detect runtime-prompt
overruns and Anti-Ratchet, add a new blocking Stop-hook
`bloat_gate_on_stop.py` with Superpowers Iron-Law-style error message
text, and register both hooks across every plugin's `hooks.json`.
Without A.foundation merged, every B/C cleanup iterate is unprotected
and bloat regrowth races the cleanup.

## Acceptance Criteria

- [ ] **AC-1 (A1 markdown classification).** `check_file_size.py` no
      longer pauschal-skips `.md` files; `_md_classification(path)`
      returns `runtime-prompt` for basename `SKILL.md`, `CLAUDE.md`,
      or paths matching `plugins/*/agents/*.md` / `shared/prompts/*.md`,
      and `doc` (= silently skipped) for everything else.
- [ ] **AC-2 (A1 per-filetype limit).** `_limit_for(path)` returns 400
      for `runtime-prompt`, 300 for source (`.py`, `.ts`, `.tsx`,
      `.js`, `.jsx`, including test files). Test-files no longer
      blanket-skipped; only inventoried.
- [ ] **AC-3 (A1 marker writer, session-scoped + atomic + TTL +
      read-modify-write).** Hook writes
      `.shipwright/locks/bloat_pending.<session_id>.json` via tmp+rename.
      Parent dir is created if missing (`mkdir -p`). `session_id`
      from `SHIPWRIGHT_SESSION_ID`; fallback literal `unknown` —
      collisions in the `unknown` bucket documented as a known
      degraded-mode (one test asserts last-write-wins for `unknown`).
      The marker file holds a **list** of entries (one per offending
      path); a second hook fire in the same session does a
      read-modify-write (load existing, upsert by `path`, atomic
      rename) — never blind-overwrites prior entries. Each entry
      carries `path`, `now`, `limit`, `classification`,
      `was_in_allowlist`, `delta` (`crossing` | `anti-ratchet`), `ts`
      (UTC ISO-8601). TTL 1h enforced by the Stop-Gate's reader, not
      the writer.
- [ ] **AC-4 (A2 Stop-Gate session-scoped, blocks on anti-ratchet).**
      `shared/scripts/hooks/bloat_gate_on_stop.py` (≤300 LOC — under
      the source-file limit this iterate enforces; the campaign's
      ≤200 aspirational target is missed by ~33 LOC because the
      Iron-Law message body is content-bearing and must remain
      operator-readable when the gate fires) reads
      **only** the current session's marker
      (`bloat_pending.<SHIPWRIGHT_SESSION_ID>.json`; falls back to
      `bloat_pending.unknown.json` when the env-var is absent — same
      degraded mode as the writer). It does **not** aggregate
      cross-session markers (resolves the AC-4-vs-Calibration-#5
      contradiction surfaced by both reviewers). For every entry
      within TTL, the gate **re-measures** the file's current line
      count and **skips** entries whose file is now at-or-under the
      limit (resolves the stale-violation TTL trap). Among surviving
      entries, any `anti-ratchet` triggers a block via
      `{"decision":"block","reason":"..."}` at the top level (Stop
      schema has no `additionalContext`; see ADR-042).
- [ ] **AC-5 (A2 Stop-Gate blocks new crossings).** Stop event with
      a `crossing` entry whose `path` is **not** in
      `shipwright_bloat_baseline.json::entries[*].path` → block.
- [ ] **AC-6 (A2 Stop-Gate Iron-Law error message).** Block-reason
      body adapts the Superpowers
      `verification-before-completion` SKILL.md text (MIT,
      © Jesse Vincent — [obra/superpowers](https://github.com/obra/superpowers))
      to the bloat domain: Iron-Law rule line, Red-Flags table, and
      Rationalization-Prevention table. Attribution + license in the
      module docstring.
- [ ] **AC-7 (A2 no-baseline / malformed baseline pass-through —
      fail-open).** If `shipwright_bloat_baseline.json` is absent,
      empty, malformed (JSON decode error), or contains a non-list
      `entries`, Stop-Gate exits 0 with `{"hookEventName":"Stop"}`
      (no decision, no reason) AND writes a one-line diagnostic
      to stderr (Claude Code surfaces hook stderr — keeps the
      failure visible without bricking the agent). Same fail-open
      treatment for malformed marker files. Covers fresh repos,
      pre-adopt state, and rebase-corruption (Gemini HIGH #4).
- [ ] **AC-8 (A2 grandfathered crossings pass — path
      normalization).** Stop event with a `crossing` entry whose
      `path` **is** in the baseline (any `state`) → no block. Path
      comparison is done after centralized normalization
      (`bloat_baseline.normalize_path(p)` = `Path(p).as_posix()`
      with case-normalization on Windows), so producer + consumer
      cannot drift on separator / case (resolves OpenAI MEDIUM
      #6). The same normalization runs at scan time when entries
      are first written.
- [ ] **AC-9 (shared bloat_baseline.py).**
      `shared/scripts/lib/bloat_baseline.py` exposes
      `scan(project_root) -> list[Entry]` (Phase-0 / Adopt) and
      `load(project_root) -> BaselineDoc | None` (Stop-Gate),
      reused by both consumers. Single producer for the entry
      schema.
- [ ] **AC-10 (Adopt sequence — baseline-first).**
      `plugins/shipwright-adopt/scripts/lib/baseline_generator.py`
      wraps `bloat_baseline.scan()` and writes
      `shipwright_bloat_baseline.json` atomically (tmp+rename). It
      is invoked as the **first artifact-writing step** of
      `/shipwright-adopt`, BEFORE
      `generate_adoption_artifacts.py` writes any over-limit file
      that Adopt itself authors (CLAUDE.md, decision_log.md,
      architecture.md, SKILL.md backups). Since plugin hooks
      already ship registered (per A3, not installed by Adopt),
      the order that matters is "baseline file exists before the
      first Stop event of the Adopt session" — verified by a unit
      test that asserts baseline-write precedes the
      `generate_adoption_artifacts` import / call in the Adopt
      flow. Concrete wiring: `plugins/shipwright-adopt/skills/
      adopt/SKILL.md` Step A (pre-flight) gains a single early
      invocation of `baseline_generator.py`, documented as
      "Schritt A.0 — Baseline".
- [ ] **AC-11 (Adopt SKILL.md minimal addition).** Adopt
      `SKILL.md` carries one new step "Schritt A.0 — Baseline
      generieren" before the existing Step A pre-flight scan
      output is consumed (≤15 LOC delta; reads + writes only —
      no UI-flow change). Existing Step A content stays
      unchanged.
- [ ] **AC-12 (A3 hook-registry across all plugins).** Every
      `plugins/*/hooks/hooks.json` carries both the PostToolUse
      `check_file_size.py` entry (`Write|Edit` matcher) and the
      Stop `bloat_gate_on_stop.py` entry. Verified by a meta-test
      that walks every plugin's hooks.json.
- [ ] **AC-13 (Probe-iterate smoke — 350-LOC file blocks).** End-
      to-end smoke: simulate a hook session that creates a new
      350-LOC `.py` file; Stop-Gate reads the resulting marker and
      returns `decision=block`.
- [ ] **AC-14 (Anti-Ratchet smoke).** Smoke: baseline lists
      `foo.py` at `current=400`; PostToolUse hook fires with file
      now at `current=410` (path already in baseline); marker
      carries `delta=anti-ratchet`; Stop-Gate blocks.
- [ ] **AC-15 (No-Baseline smoke).** Smoke: temporarily rename
      `shipwright_bloat_baseline.json`; Stop-Gate exits 0, no
      block.
- [ ] **AC-16 (All existing hook tests stay green).**
      `uv run pytest shared/tests/test_hooks.py -v` (and the
      plugin-side hook test suites) pass without modification of
      their assertions; only additive tests in this iterate.

## Spec Impact

This iterate adds enforcement infrastructure used by every future
SDLC phase; it doesn't introduce a user-visible app feature. The
project is a library / SDLC tooling monorepo (scope=library), and
the FR table covers tool/skill obligations.

- **Classification:** modify (one existing FR), add (one new FR)
- **ADD** (new FR): `FR-A.10 — Bloat Prevention Loop-Gate` (one row
  covering A1 + A2 + A3: PostToolUse marker, Stop-Gate block,
  per-plugin hook registry).
- **MODIFY** (existing FR): the existing `check_file_size`-related
  FR (if any in spec.md; otherwise the broader "300-LOC rule"
  reference) is updated to point to the new classification +
  marker writer.
- **REMOVE:** none.
- **NONE justification:** n/a — see ADD above.

## Out of Scope

- A4 / A5 (code-reviewer subagent prompts, Compliance-Audit
  Group G) — separate `A.review` iterate.
- A6 / A7 / A8 (Pre-Commit, CI workflow, ADR-template, glossary)
  — separate `A.defense` iterate.
- Phase-0 baseline inventory for this monorepo — the helper is
  built here, but actually running it to populate
  `shipwright_bloat_baseline.json` is a separate operation. The
  Stop-Gate's no-baseline-pass behavior (AC-7) covers the
  intermediate state.
- WebUI side of bloat enforcement (`shipwright-webui` is a
  separate repo; it gets Pre-Commit + CI only, in `A.defense`).
- Cleanup tracks B and C (touching the actual oversize files).
- Migrating existing oversize SKILL.md files (B1 work).

## Design Notes

n/a — this iterate ships no UI surface.

## Affected Boundaries

The hook system has two producer/consumer boundaries — both flagged
`touches_io_boundary` and gated by the Boundary Probe sub-step
(SKILL.md Path A Step 6a) plus a producer→file→consumer round-trip
test.

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `check_file_size.py:_write_marker` | `bloat_gate_on_stop.py:_load_markers` | per-session JSON marker (`.shipwright/locks/bloat_pending.<session_id>.json`) |
| `bloat_baseline.py:scan` → `<project_root>/shipwright_bloat_baseline.json` | `bloat_gate_on_stop.py:_load_baseline` | baseline JSON (schema in Spec §4.2) |

Both formats are machine-only (producer + consumer are both Python
code in this repo). The operator-input boundary categories (POSIX
`export` prefix, inline `# comment`, quoted `#`) are N/A — the
boundaries are pure JSON in machine-managed dirs. The round-trip
test (producer→disk→consumer) is mandatory and covered by AC-13 /
AC-14.

## Confidence Calibration

- **Boundaries touched:** the two rows in "Affected Boundaries"
  above — the per-session marker file and the baseline JSON.
- **Empirical probes run** (all → real test, no "looks correct"):
  1. **Marker round-trip** — PostToolUse subprocess writes a real
     marker via `_write_marker_entry`; Stop-Gate subprocess
     re-reads it via `_load_marker` and decision is asserted.
     Covered by `test_marker_written_for_crossing` +
     `test_blocks_on_new_crossing_outside_baseline` + chain.
     **No finding.**
  2. **Baseline round-trip (schema contract)** —
     `test_round_trip_scan_write_load_match` in
     `test_bloat_baseline.py`: `scan` writes → `load` reads back
     → set-equal on `path` keys. **No finding.**
  3. **TTL filter** —
     `test_ttl_filter_skips_old_markers` seeds a marker with
     `ts="2020-01-01T00:00:00Z"` and asserts no block. Producer
     ts format (`YYYY-MM-DDTHH:MM:SSZ`) round-trips through
     `_parse_ts`. **No finding.**
  4. **Read-modify-write under multi-edit** —
     `test_marker_read_modify_write_preserves_other_paths`:
     two sequential producer fires for distinct paths;
     both survive in the marker list. **Finding earlier:**
     Gemini HIGH #1 flagged blind-overwrite risk in the
     plan; resolved before code by upserting on `path`.
     Re-probe confirms the fix.
  5. **Session scoping (parallel worktrees)** —
     `test_session_scoping_ignores_other_session_marker`:
     two `bloat_pending.<sid>.json` files exist; Stop-Gate
     reads only its own. **Finding earlier:** Gemini HIGH #3
     / OpenAI HIGH #1 flagged the AC-4-vs-Calibration-#5
     contradiction; AC-4 rewritten to "session-scoped" and
     gate implements `_marker_path(cwd, _session_id())`.
     Re-probe confirms.
  6. **Path normalization (Windows ↔ POSIX)** —
     `test_path_normalization_grandfathers_backslash_baseline`:
     baseline written with `sub\legacy.py`; marker uses
     `sub/legacy.py`; Stop-Gate normalizes both via
     `bb.normalize_path` and grandfathers the entry. **No
     finding.**
  7. **Malformed JSON fail-open** —
     `test_malformed_baseline_pass_silent_with_stderr` and
     `test_malformed_marker_pass_silent` — both write
     `"{not valid"`; Stop-Gate exits 0, prints stderr
     diagnostic, doesn't block. **Finding earlier:** Gemini
     HIGH #4 (rebase-corruption crash) — addressed by
     `_bb.load` returning `None` on JSON errors and the gate
     pass-silently path. Re-probe confirms.
  8. **Missing `SHIPWRIGHT_SESSION_ID`** —
     `test_marker_unknown_session_when_env_absent` (producer)
     +`test_session_scoping_unknown_fallback` (consumer) —
     both pin the `unknown` bucket. **No finding.**
  9. **Stale violation (file fixed between PostToolUse and Stop)** —
     `test_stale_marker_skipped_when_file_under_limit`:
     marker recorded `now=320` but the file is now 150 LOC at
     decision time; Stop-Gate re-measures and skips the entry.
     **Finding earlier:** Gemini HIGH #2 (1-hour stale-trap);
     addressed by `_re_measure_oversize`. Re-probe confirms.
 10. **Hook output schema compliance (Stop event, ADR-042)** —
     `test_block_output_uses_top_level_decision_not_additional_context`
     asserts the block payload places `decision` at the top
     level and never inside `hookSpecificOutput.additionalContext`.
     The broader `test_hook_output_schema_compliance.py`
     subprocess-runs all 113 hooks under realistic stdin and
     all 12 new bloat_gate registrations pass. **No finding.**

- **Edge cases NOT probed + why acceptable:**
  - POSIX `export` prefix / inline `# comment` / quoted `#` — N/A.
    Both formats are JSON in `.shipwright/locks/` and at the
    project root; producer + consumer are both Python code in
    this repo (no operator hand-editing).
  - UTF-8 BOM on JSON files — N/A. Writers use
    `encoding="utf-8"` (no BOM), readers don't strip BOM; if a
    BOM ever appeared `json.JSONDecodeError` would route through
    fail-open. Acceptable.
  - Concurrent two-writer race on the same session marker —
    not probed at runtime; the read-modify-write is not
    file-locked. Same-session producers are sequential in
    Claude Code's PostToolUse pipeline (one tool call at a
    time), so this is not an active risk. Documented for
    future drift protection if PostToolUse ever becomes
    concurrent.

- **Confidence-pattern check:** I did not say "are you confident?"
  to myself at any point during this iterate. Three of the ten
  probes (4, 5, 7, 9) returned findings *in the plan* — caught by
  external review BEFORE code was written; all fixes are now
  test-asserted. No yes-then-bug pattern fired in this run, so
  no extra probe is owed.

## Self-Review

1. **Spec compliance** — all 16 ACs map to a code path + test:
   AC-1/2 → `bloat_baseline.{classify_md,limit_for}` + 24 tests in
   `test_bloat_baseline.py`. AC-3 → `check_file_size._write_marker_entry`
   + 7 new tests in `test_hooks.py::TestCheckFileSize`. AC-4/5/6/7/8 →
   `bloat_gate_on_stop` + 15 tests. AC-9 → `bloat_baseline` (single
   producer for schema + classification). AC-10/11 → `baseline_generator`
   + 6 tests + Adopt SKILL.md Step A.0. AC-12 → meta-test (49 cases).
   AC-13/14/15 → covered by gate tests. AC-16 → 2388 shared + 290
   adopt + 113 schema tests all green.
2. **Error handling** — fail-open at every boundary: marker decode
   error, baseline decode error, baseline absent, marker absent,
   missing-file at re-measure, malformed TTL string, missing env-var.
   PostToolUse marker write wrapped in `OSError` swallow so the
   advisory hook never breaks the tool flow.
3. **Security** — block-reason body is a static module-level constant;
   offender data interpolated via formatted string (no shell, no eval,
   no template-string injection surface). Path normalization happens
   before any filesystem comparison. No secrets, no DROP-class SQL,
   no `--no-verify` bypass.
4. **Test quality** — every test asserts on observable outcomes
   (decision payload, marker file contents on disk, baseline file
   contents). Producer→file→consumer round-trip is real (subprocess
   writes, subprocess re-reads), not a stubbed in-memory shape. The
   meta-test parametrizes across every plugin so a future new plugin
   that forgets either hook fails CI.
5. **Naming** — three modules + one wrapper, all carrying `bloat_`
   prefix where they live in shared, matching the campaign glossary.
6. **Files under limit** —
   `bloat_baseline.py` 276 / `check_file_size.py` 293 /
   `bloat_gate_on_stop.py` 233 / `baseline_generator.py` 74 /
   `test_bloat_baseline.py` 281 / `test_bloat_gate_on_stop.py` 286 /
   `test_hook_registry_bloat.py` 108. The gate file overshoots the
   campaign's aspirational ≤200 LOC by 33 lines (Iron-Law message
   body is content-bearing) — under the structural 300 limit this
   iterate enforces. Documented in AC-4 + ADR.
7. **Affected Boundaries** — both producer/consumer pairs (marker
   file, baseline file) carry round-trip tests. The shared
   `bloat_baseline` library is the single producer for the schema
   and classification — `check_file_size.py`'s `_md_classification`
   / `_limit_for` are thin delegating wrappers.

## Verification (medium+)

- **Surface:** cli
- **Runner command:**
  ```
  uv run pytest shared/tests/test_hooks.py
    shared/tests/test_bloat_baseline.py
    shared/tests/test_bloat_gate_on_stop.py
    plugins/shipwright-adopt/tests/test_baseline_generator.py
    shared/tests/test_hook_registry_bloat.py
    --color=no -v
  ```
  (executed via a wrapper that handles per-plugin pytest sessions
  if conftest collision arises — see conventions.md learning on
  conftest collisions and `--color=no` requirement for the F0.5
  EXIT_ZERO_TESTS trap.)
- **Evidence path:** `.shipwright/runs/iterate-2026-05-25-bloat-foundation/surface_verification.log`
- **Justification (only if surface=none):** n/a — this iterate
  ships real CLI / Python code with tests.
