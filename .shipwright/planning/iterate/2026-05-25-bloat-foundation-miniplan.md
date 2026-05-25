# Mini-Plan: bloat-foundation

- **Run ID:** iterate-2026-05-25-bloat-foundation
- **Spec:** `.shipwright/planning/iterate/2026-05-25-bloat-foundation.md`

## Files (new vs modified)

### NEW

| Path | Purpose | Budget |
|---|---|---|
| `shared/scripts/lib/bloat_baseline.py` | Single producer for the entry schema **and** the classification logic. Exports `scan(project_root)`, `load(project_root)` (returns `BaselineDoc \| None`; logs to stderr + returns `None` on malformed file — fail-open), `classify_md(path)` (returns `"runtime-prompt" \| "doc" \| None`), `limit_for(path)`, `should_skip(path)`, `normalize_path(p)`, `MARKER_TTL_SECONDS`. `check_file_size.py::_md_classification` and `_limit_for` are **thin delegating wrappers** preserving the existing internal call sites; the implementation lives in the shared lib (resolves OpenAI MED #2 — single source of truth, no drift). | ≤200 LOC |
| `shared/scripts/hooks/bloat_gate_on_stop.py` | Stop-event blocking hook. Aggregates session markers under TTL, compares against baseline, emits `decision=block` with Iron-Law-style reason for `anti-ratchet` or new-`crossing` paths. | ≤200 LOC |
| `plugins/shipwright-adopt/scripts/lib/baseline_generator.py` | Adopt-onboarding wrapper around `bloat_baseline.scan` — writes the baseline file **before** hooks.json install. ≤100 LOC. | ≤100 LOC |
| `shared/tests/test_bloat_baseline.py` | Unit tests for the helper library — classification, limits, scan, load, JSON round-trip. | ≤300 LOC |
| `shared/tests/test_bloat_gate_on_stop.py` | Stop-Gate tests: block/pass matrix (anti-ratchet, crossing-new, crossing-grandfathered, no-baseline, TTL filter, malformed marker, multi-session aggregation). | ≤300 LOC |
| `shared/tests/test_hook_registry_bloat.py` | Meta-test: every `plugins/*/hooks/hooks.json` carries the PostToolUse + Stop entries. Reverse direction of AC-12. | ≤120 LOC |
| `plugins/shipwright-adopt/tests/test_baseline_generator.py` | Sequence test — baseline written before hooks installer (mocks the installer). | ≤120 LOC |

### MODIFIED

| Path | Change | Δ |
|---|---|---|
| `shared/scripts/hooks/check_file_size.py` | Add `_md_classification`, `_limit_for`, marker writer (`_write_marker`); replace pauschal markdown-skip with classification-aware skip. Keep PostToolUse advisory exit-0 contract. | +~120 LOC |
| `shared/tests/test_hooks.py::TestCheckFileSize` | Add tests for runtime-prompt classification, 400 vs 300 limits, marker writer (atomic + correct payload), `was_in_allowlist` flag, env-var fallback to `unknown`. | +~80 LOC |
| `plugins/shipwright-adopt/skills/adopt/SKILL.md` | Insert one step "Baseline generieren" before the existing hooks-install step in the infrastructure section. ≤10 LOC delta. | ≤+10 LOC |
| `plugins/shipwright-{adopt,build,changelog,compliance,deploy,design,iterate,plan,preview,project,run,security,test}/hooks/hooks.json` (12 files; `shipwright-build` already has PostToolUse) | Add PostToolUse `check_file_size.py` entry (idempotent — `shipwright-build` already has it; the rest get it new) and Stop-event `bloat_gate_on_stop.py` entry. | +6-10 LOC each |
| `docs/hooks-and-pipeline.md` | Reflect new Stop hook + extended PostToolUse hook in the hooks registry (CLAUDE.md rule). | ≤+30 LOC |

## Work breakdown (TDD ordering)

1. **`bloat_baseline.py` helper + its tests.** Foundation that
   Stop-Gate, Adopt, and `check_file_size.py` all depend on. RED
   first: classification + limit table + JSON load/scan unit tests.
2. **`check_file_size.py` extension + tests.** RED: extend
   `TestCheckFileSize` with runtime-prompt and marker-writer cases.
   Then GREEN: import helpers from `bloat_baseline`, write marker
   atomically.
3. **`bloat_gate_on_stop.py` + tests.** RED: every Stop block/pass
   case in the AC list. GREEN: implement reader + decision logic +
   Iron-Law reason body.
4. **`baseline_generator.py` + tests.** RED: order-of-operations
   test (baseline written before installer). GREEN: wrap
   `bloat_baseline.scan` + atomic write.
5. **Hooks.json registry update + meta-test.** RED: meta-test
   asserts both hooks present in every plugin. GREEN: edit each
   `hooks.json`.
6. **Adopt SKILL.md minimal addition** + `docs/hooks-and-pipeline.md`
   update (per CLAUDE.md rule when hooks change).
7. **F0 full test suite** + F0.5 surface verification with the
   pytest runner from the iterate spec.

## Test strategy

- **Producer→file→consumer round-trip** for both boundaries
  (marker file, baseline file). Required by `touches_io_boundary`.
  Distinct test for each boundary: marker produced by
  `_write_marker` → re-read by Stop-Gate's loader → asserts the
  expected `decision` (block/pass); baseline produced by
  `bloat_baseline.scan` + `_atomic_write_baseline` → re-read by
  the gate → asserts membership-by-normalized-path.
- **Schema-contract test** (OpenAI MED #9): generate a baseline
  with `scan()` against a fixture tree, hand the file directly to
  the Stop-Gate, assert decision matches. Catches any future
  schema drift between producer and consumer.
- **Drift protection meta-test** for the per-plugin hooks.json
  registry — full hook-object validation (event name, matcher,
  command shape, referenced script existence), not just JSON
  presence (OpenAI MED #10).
- **Stale-violation re-measurement test** (Gemini HIGH #2):
  marker says `crossing` for path X; before Stop event the file
  is shrunk to under-limit; assert Stop-Gate skips the entry and
  does not block.
- **Session-scoping test** (Gemini HIGH #3 / OpenAI HIGH #1):
  two distinct `bloat_pending.<sid>.json` files exist; with
  `SHIPWRIGHT_SESSION_ID=A`, only A's marker is consulted; B's
  anti-ratchet entry does not block.
- **`unknown` collision test** (OpenAI MED #5): two writes with
  no env-var, both end up in `bloat_pending.unknown.json` —
  asserts last-write-wins, documents the degraded mode.
- **Malformed baseline / marker fail-open test** (Gemini HIGH #4):
  truncated JSON in either file → gate exits 0, writes a stderr
  diagnostic.
- **Boundary probe coverage** of all 8 categories from
  `references/boundary-probes.md` — relevant ones get tests, N/A
  ones get a one-line justification in Self-Review.
- **Existing hook tests** stay green; only additive changes to
  `test_hooks.py::TestCheckFileSize`.

## Risk flags

- `touches_shared_infra` — `shared/scripts/hooks/`,
  `shared/scripts/lib/`, every `plugins/*/hooks/hooks.json`. →
  Full review + full test suite mandatory.
- `touches_io_boundary` — two producer/consumer pairs. → Boundary
  Probe sub-step in Build, mandatory round-trip test.

## Alternative considered

**Centralized hook registration via shared hooks.json** —
mentioned in the campaign as "Alternative (sauberer, falls Plugin-
System es zulässt)". Rejected for this iterate because Claude
Code's plugin model requires hooks under each plugin's own
`hooks/hooks.json` (every existing shared-script hook is
registered N times — once per plugin — for exactly this reason;
the per-plugin re-registration is the canonical pattern). Adopting
the centralized variant would require a Claude-Code plugin
contract change outside Shipwright's control.
