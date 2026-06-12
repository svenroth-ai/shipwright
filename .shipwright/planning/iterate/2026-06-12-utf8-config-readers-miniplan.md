# Mini-Plan — iterate-2026-06-12-utf8-config-readers (WP8 / F24+F25)

## Problem
WP8 of the 2026-06-10 deep audit. Two cp1252-vs-UTF-8 defects on the Windows
dev platform:

- **F24 (MED):** config readers do `json.loads(path.read_text())` with no
  `encoding=`. The canonical writer (`lib/config.py`) emits FR titles /
  project descriptions with `ensure_ascii=False` (raw non-ASCII), so a
  non-English project (CJK / Cyrillic FR titles or description) crashes
  iterate F1 / the `suggest_iterate` UserPromptSubmit hook with
  `UnicodeDecodeError` on Windows. Affected: `artifact_sync.detect_drift`,
  `suggest_iterate.main`, `classify_complexity.detect_cross_split`,
  `classify_intent._find_affected_frs`. (`lib/config.py` is already correct —
  pinned with a regression test.)
- **F25 (MED):** `surface_verification.run_with_retries` runs the F0.5 runner
  with `text=True` and no `encoding=`. Runner output is UTF-8 (vitest's `❯` =
  U+276F contains cp1252-undefined byte 0x9D; pytest quotes this repo's
  em-dash docstrings). The cp1252 decode raises in the subprocess reader
  thread → F0.5 false-fails though the suite passed.

## Decision
Surgical, inline fix (no shared encoding helper — keeps this branch
independently mergeable alongside sibling sub-iterates a1-3 / a1-4 which fix
UTF-8 in other files):

- F24: add `encoding="utf-8"` to every config `read_text` in the four readers;
  widen the existing `except` tuples to include `UnicodeDecodeError` where the
  reader already swallows decode-class errors (defensive — a malformed file
  should fail-soft, not crash the hook).
- F25: add `encoding="utf-8", errors="replace"` to the runner `subprocess.run`.
  Do NOT change the no-shell contract (F0.5 runner runs with shell=False).
  `errors="replace"` keeps a genuinely malformed byte from re-introducing the
  crash while preserving valid UTF-8 glyphs.

## Alternatives considered
- **Shared `proc_text.py` helper (WP0):** rejected for THIS sub-iterate —
  would couple the branch to siblings and create a merge hot-file. The audit
  itself marks WP0 optional ("let each UTF-8 package add `encoding=` inline").
- **`errors="strict"` on the runner:** rejected — a single malformed byte in
  voluminous test output would re-crash F0.5; `replace` is the audit's
  prescribed fix.

## Test plan (TDD, written first)
`shared/tests/test_utf8_config_readers.py`:
- F24: each reader parses a CJK / Cyrillic config under a forced-cp1252
  default locale (monkeypatch `locale.getpreferredencoding`), with a guard
  asserting the fixture bytes genuinely raise under cp1252-strict (so the test
  is not vacuous).
- F25: `run_with_retries` + `verify_surface` over a fixture runner emitting
  `❯` + em-dash → no crash, correct `tests_run` parse, clean evidence log
  (no `�` replacement of the glyphs we want).

## Risk flags
`touches_io_boundary` (config JSON read + runner subprocess decode) → Code
Review Cascade + Confidence Calibration fire regardless of the small size.

## Affected Boundaries (ADR-024)
- **Producer:** `lib/config.py::write_config` (UTF-8, `ensure_ascii=False`) →
  **Consumer:** the four config readers. Round-trip probe: write a CJK/Cyrillic
  config, read it back through each consumer under cp1252.
- **Producer:** the project test runner (vitest/pytest, UTF-8 stdout) →
  **Consumer:** `surface_verification.run_with_retries` decode → evidence log.
  Round-trip probe: subprocess emits `❯`/em-dash bytes → decode → file.
