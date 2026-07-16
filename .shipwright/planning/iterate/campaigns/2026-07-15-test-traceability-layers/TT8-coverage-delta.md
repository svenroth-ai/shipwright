# TT8 — monorepo traceability retrofit: coverage delta (durable record)

> Campaign `2026-07-15-test-traceability-layers`, sub-iterate TT8 (dogfood). Durable, tracked
> coverage-delta record. Two scopes below: the **written/manifest-tracked** scope and the
> **complete repo-wide inventory** (TT8's design mandate per the `test_links` collector
> docstring: "the COMPLETE repo-wide inventory + backfill of scattered/non-conventional test
> dirs is the shared engine's job (adopt TT7 / retrofit TT8), not a compliance regen").

## Provenance (reproducible)

- Engine: `backfill_test_links/1.0.0` · collector: `test_links/1.0.0`
- Written-scope command (applied): `uv run shared/scripts/tools/backfill_test_links.py
  --project-root .` (default roots → `integration-tests/`; split-convention flag **OFF**)
- Complete-inventory command (dry-run): `... --test-root integration-tests --test-root
  plugins --test-root shared --dry-run`
- Manifest regen: `uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py
  --project-root . --phase iterate`
- Manifest `source_commit`: `a85c22cdbad650ffcea85cf455b01e95d16474fd` (branch base) · scan
  date 2026-07-16

## Split-convention decision

`--repo-follows-split-convention` left **OFF**: the monorepo's real tests use behavior-named
`test_*.py`, not the `NN-` split prefix (the only `NN-` file is a fixture). Dry-run with the
flag ON produced identical results (inert here) → OFF is correct (advisory).

## Scope A — written + manifest-tracked (`integration-tests/`)

The compliance `test_links` collector's `generate_file` scans only conventional root-level
dirs (`tests, test, __tests__, e2e, integration-tests, src, app, packages`). On this monorepo
only `integration-tests/` matches (29 files, 162 test functions). TT8 writes the
high-confidence tags **here**, where the regenerated manifest reflects them.

| Bucket (written scope) | Count |
|---|---|
| Tests scanned (`integration-tests/`) | 162 |
| **Confidently mapped — `@FR` tags written** | **3** |
| Low-confidence proposals (not written) | 10 |
| Confirmed / possible orphans | 0 / 0 |
| Unmapped | 149 |

The 3 written tags are `integration-tests/test_events_log_parity.py::test_parity_*` →
**FR-01.11** (`/shipwright-iterate`), `unique_commit` signal, integration layer. Manifest
enumerates **158 untagged + 3 tagged = 161** tests (the collector's per-test count; the
engine's 162 is a 1-test def-vs-node heuristic delta). Coverage renders `MISSING` because
execution evidence was `not_run` this regen (R1: `ok` needs enabled + executed=pass) —
advisory, since FR-01.11 is `defaulted_legacy`/`inferred_legacy`.

## Scope B — complete repo-wide inventory (all non-fixture test roots)

A full-corpus dry-run over `integration-tests/ + plugins/ + shared/` (**test fixtures
excluded** — see below):

| Bucket (complete inventory, fixtures excluded) | Count |
|---|---|
| Tests scanned (full corpus, incl. fixtures) | 7419 |
| High-confidence `@FR` candidates (plugins/*/tests + shared/tests) | 187 |
| Low-confidence proposals | 24 |
| **Confirmed / possible orphans (real)** | **0 / 0** |
| Unmapped | 7137 |
| Repo-wide pre-existing skips | 50 |

The 187 high-confidence candidates map via `unique_commit` (78× FR-01.14, 61× FR-01.11, 28×
FR-01.06, 13× FR-01.13, 7× FR-01.09; areas: 108× `shared/tests`, 33× `plugins/shipwright-iterate`,
33× `plugins/shipwright-test`, 13× `plugins/shipwright-adopt`). **They are NOT written in
TT8** because the collector's manifest scope excludes `plugins/*/tests` — tags there would be
dropped on the next `generate_file` regen, creating an incoherent tags-in-files /
absent-in-manifest state. They are inventoried as triage (`trg-01bb6cae`) instead.

**FOLLOW-ON (concrete, not vague):** extend the `test_links` collector's test-root scope (or
add a per-repo test-root config) so `plugins/*/tests` + `shared/tests` are manifest-scanned.
That framework iterate makes the 187 candidates manifest-meaningful; only then should they be
auto-written. Until then, writing them would be write-then-drop.

### Fixture false-positives (excluded — important)

The full scan sweeps in the campaign's own golden test fixtures
(`plugins/shipwright-compliance/tests/fixtures/traceability/`,
`shared/scripts/tools/tests/fixtures/backfill/`) — intentional mini-repos with **synthetic**
FRs (FR-03.xx / FR-05.xx) the TT1–TT7 tests assert against. These produced **14 spurious
"orphans" + 52 spurious "unmapped"** that are NOT real rot. All fixture hits are excluded from
the tables above. The engine does **not** write tags into fixture data files (verified —
byte-stable). **The real monorepo has ZERO orphans.**

## Coverage delta (headline)

- **Written & manifest-tracked:** 3 confident tags (integration-tests).
- **Complete inventory:** 187 high-confidence candidates + 24 proposals confidently or
  plausibly mappable; 7137 unmapped residue; **0 real orphans**; 50 pre-existing skips.
- Confident-mappable across the corpus ≈ 211 / ~7351 non-fixture tests (~2.9%). Low by design:
  the monorepo tracks 15 framework-internal FRs, so most unit tests legitimately map to none;
  the backfill is deterministic-first / high-confidence-only (never fabricates coverage).

## Gate behaviour (advisory-for-legacy — verified)

- **D-orphan:** PASS — "no test is tagged with a removed/absent FR" (real orphans = 0; the 3
  written tags point at a live FR).
- **D-layer:** PASS (LOW) — "no explicit FR is missing a required layer; 15 advisory gap(s)
  (0 ambiguous fan-out — deferred to TT5; rest pre-rollout legacy)". Provenance-driven
  advisory (NOT a blanket `--advisory` flag): all 15 monorepo FRs are legacy-provenance, so
  none hit the post-rollout hard gate. No false hard-block.
- **D1/D3/D4:** pre-existing detective findings on `shipwright_events.jsonl` (untouched here) —
  unrelated to the test-tag layer; grade held at A/94.7.

## Triage filed (rolled up — mirrors TT7, no card-flood)

- `trg-01bb6cae` — 187 high-confidence plugin/shared candidates (await collector-scope extension).
- `trg-f92f5f32` — 7137 unmapped (full corpus, review candidates, never accusations).
- `trg-a57392a2` — 24 low-confidence proposals to review.
- `trg-e32343ab` — 50 pre-existing skips (repo-wide inventory, one summary card).

## Follow-on (from external plan/code review)

- **Collector-scope extension** (above) — makes plugin-test tags manifest-meaningful; the
  gate to auto-writing the 187 candidates.
- **"Drive residue to zero"** (Gemini M#2) — a future explicit "no product FR" disposition
  (e.g. an `@FR-framework` / directory-exclusion convention) so framework-internal tests are
  permanently classified rather than re-flagged as residue each run. Out of TT8 scope (a new
  tag vocabulary is a design decision, not a retrofit).
