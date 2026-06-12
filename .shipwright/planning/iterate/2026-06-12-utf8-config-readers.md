# Iterate ADR — iterate-2026-06-12-utf8-config-readers

**Campaign:** 2026-06-10-audit-1-auto · **Sub-iterate:** a1-5 · **WP8 (F24+F25)**
**Complexity:** small · **Risk flags:** `touches_io_boundary`

## Decision
Surgical, inline UTF-8 fix for the WP8 config/runner readers (no shared
helper — keeps this branch independently mergeable beside siblings a1-3/a1-4):

- **F24** — added explicit `encoding="utf-8-sig"` to the four config readers
  (`artifact_sync.detect_drift`, `suggest_iterate.main`,
  `classify_complexity.detect_cross_split`, `classify_intent._find_affected_frs`)
  and widened their `except` tuples with `UnicodeDecodeError` where the reader
  already swallows decode-class errors. `utf-8-sig` (vs plain `utf-8`) also
  tolerates a UTF-8 BOM from a hand-edited (Notepad) config — an edge the
  external plan review surfaced. `lib/config.py` was already UTF-8-correct;
  pinned with a regression test.
- **F25** — added `encoding="utf-8", errors="replace"` to the F0.5 runner
  subprocess in `surface_verification.run_with_retries`. No change to the
  no-shell contract.

## External-Plan-Review-Findings (OpenRouter: openai + gemini)

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| OAI-1 | med | `lib/config.py` scope ambiguity | accepted-and-fixed — confirmed already UTF-8-correct; added regression-guard test pinning it |
| OAI-2 | med | widening `except` may silently swallow corruption | rejected-with-reason — only widened in readers that ALREADY fail-soft (advisory hooks); hard-failing readers (`artifact_sync`, `read_config`) keep their strict contract |
| OAI-3 | med | UTF-8 BOM still breaks `json.loads(read_text("utf-8"))` | accepted-and-fixed — switched the four readers to `utf-8-sig`; added 2 BOM tolerance tests |
| OAI-4 | low | locale monkeypatch may be vacuous on Linux CI | accepted-and-fixed — see code-review CR-2 (added a platform-independent `Path.read_text` strict-encoding guard) |
| OAI-5/6 | med | `errors="replace"` can mask corruption near parse tokens | accepted-and-fixed — added a malformed-byte (0x9D) to the runner fixture; assert tests_run still parses + only the bad byte → U+FFFD |
| OAI-7 | med | evidence-log WRITE path must also be UTF-8 | accepted-verified — `verify_surface` already `write_text(..., encoding="utf-8")`; test asserts clean round-trip |
| OAI-8 | low | stderr decode path | accepted-verified — `capture_output=True` applies the same `encoding/errors` to stderr; fixture emits `❯` on stderr too |
| GEM-1 | high | Popen vs run API mismatch | rejected-with-reason — `run_with_retries` uses `subprocess.run` (verified); the high severity rested on a false `Popen` premise |
| GEM-2/3 | med | locale-mock / stderr | duplicates OAI-4/OAI-8 (same dispositions) |

## External-Code-Review-Findings (OpenRouter: openai + gemini)

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| CR-1 | med | `lib/config.py` scope | accepted-and-fixed — same as OAI-1; documented in-scope-and-already-compliant |
| CR-2 | med | locale-monkeypatch regression detection not robust | accepted-and-fixed — added `test_readers_pass_explicit_encoding_to_read_text` patching `Path.read_text` to RAISE without an explicit `encoding=`, exercising every reader (platform-independent) |
| CR (gemini) | — | response truncated / non-substantive | n/a |

Overall external verdict: ship-with-fixes → all medium findings addressed.

## Self-Review (7-item, ADR-029)
1. **Spec Compliance** — PASS. All three ACs met: CJK-FR config parses under
   forced cp1252; runner emitting `❯`/em-dash parses tests_run + clean log;
   full F0 green (see F0 below).
2. **Error Handling** — PASS. Readers fail-soft only where already advisory;
   strict readers keep their JSONDecodeError contract; runner `errors="replace"`
   never crashes on malformed bytes.
3. **Security Basics** — PASS. No new inputs/trust boundaries; `shell=False`
   preserved; `errors="replace"` noted in ADR for log-observability.
4. **Test Quality** — PASS. 10 tests; non-vacuous cp1252-crash guard +
   positive-behavior asserts + platform-independent strict-encoding guard +
   BOM + malformed-byte cases.
5. **Performance Basics** — PASS. No new I/O or loops; one-kwarg changes.
6. **Naming & Structure** — PASS. Inline edits with WP8-anchored comments; no
   new abstractions (deliberate, per merge-isolation).
7. **Affected Boundaries (ADR-024)** — PASS. Producer (`lib/config.write_config`
   UTF-8) ↔ consumers (4 readers) round-trip probed; producer (test runner
   UTF-8 stdout) ↔ consumer (`run_with_retries` decode → evidence log) round
   -trip probed. See Confidence Calibration.

## Confidence Calibration (ADR-029, touches_io_boundary)
**Probes run (REAL):**
- PROBE1 (BOM): UTF-8-BOM config → `json.loads(read_text("utf-8"))` RAISES
  `JSONDecodeError`; `utf-8-sig` PARSES. **Bug found → fixed (utf-8-sig) →
  re-probed via 2 BOM tests (pass).**
- PROBE2 (config round-trip): `write_config` CJK+Cyrillic+em-dash →
  read back through all 4 consumers + `read_config` under forced cp1252 →
  byte-exact. **No findings.**
- PROBE3 (runner decode): authoritative `_RUNNER_SCRIPT` (❯ + em-dash + CJK +
  raw 0x9D byte, on stdout AND stderr) → `run_with_retries` → exit 0,
  tests_run=5, valid glyphs survive, 0x9D → single U+FFFD, no crash. **No
  findings.** (Two earlier exit-1 readings were bash-heredoc escaping
  artifacts in the probe harness, not code defects — confirmed by running the
  exact test-module constant directly.)

**Asymptote:** each boundary has ≥2 consecutive clean probes (BOM fixed then
clean; config clean×1 + clean round-trip; runner clean via authoritative
fixture + suite). Asymptote reached.

**Edge cases not probed (acceptable):**
- Non-UTF-8 *legacy* config encodings (e.g. Shift-JIS): out of scope — the
  canonical writer only ever emits UTF-8; a foreign encoding is a malformed
  config handled by fail-soft / strict contracts.
- Runner output on a true non-UTF-8 locale child that mis-encodes its OWN
  source: a child-process bug, not a decode-path bug (the decode handles
  whatever bytes arrive).
