# Mini-Plan: triage-producers-2

- **Run ID:** iterate-2026-05-14-triage-producers-2

## Approach

Each new producer is a thin caller of
`shared/scripts/triage.append_triage_item_idempotent`. The function is
imported lazily inside a small `_emit_*` helper at the bottom of each
target module, mirroring the iterate-1a `_emit_tier1_fails_to_triage`
pattern. Lazy imports protect against environments where
`shared/scripts/` isn't on `sys.path` (e.g. an isolated subprocess).

All emissions are best-effort: any exception is caught + logged to
stderr + swallowed, never blocking the caller's primary exit semantics.
This mirrors the iterate-1a producer's contract.

## Files to change

### Source

1. `plugins/shipwright-security/scripts/tools/generate_security_report.py`
   — add `_emit_findings_to_triage(project_root, findings)` helper +
   one call from `main()` after consolidation, before report rendering.
   ~80 LOC added.
2. `plugins/shipwright-test/scripts/lib/performance_check.py` — add
   `_emit_failures_to_triage(project_root, results, gate, dev_url,
   success)` helper + one call from `main()` after `evaluate_gate`,
   before exit. ~80 LOC added.
3. `shared/scripts/surface_verification.py` — add
   `_emit_failure_to_triage(project_root, run_id, surface, condition,
   detail, evidence_path)` helper + three call-sites in `main()`
   keyed on `exit_code` returned by `verify_surface()`. ~70 LOC added.
4. `shared/scripts/hooks/check_drift.py` — add
   `_emit_drift_to_triage(project_root, timestamp_drifted,
   content_findings)` helper + one call from `main()` after warnings
   list is built. ~60 LOC added.
5. `shared/scripts/artifact_sync.py` — add `_emit_drift_to_triage(...)`
   helper + one call from `detect_drift()` when `drift_detected=True`.
   ~40 LOC added.
6. `shared/scripts/triage.py` — extend `KNOWN_SOURCES` tuple to add
   `"f0.5"` and `"drift"`. Source field is free-form so this is
   informational, but it documents the new producers for the next
   reader. ~2 LOC change.

### Tests

7. `shared/tests/test_security_triage_emit.py` — new (~90 LOC)
8. `shared/tests/test_performance_triage_emit.py` — new (~100 LOC)
9. `shared/tests/test_f0_5_triage_emit.py` — new (~100 LOC)
10. `shared/tests/test_drift_triage_emit.py` — new, covers both
    drift sites in one file (~110 LOC)

Pattern (from `test_phase_quality_triage_emit.py`):

```python
import importlib.util
from pathlib import Path
import sys

def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

def test_emits_one_item_per_finding(tmp_path):
    triage_root = Path(__file__).resolve().parents[1] / "scripts"
    sys.path.insert(0, str(triage_root))
    from triage import read_all_items
    sec = _load_module("gsr", <path to generate_security_report.py>)
    sec._emit_findings_to_triage(tmp_path, [<synthetic finding>])
    items = read_all_items(tmp_path)
    assert len(items) == 1
    assert items[0]["source"] == "security"
    # ... etc
```

### Docs

11. `docs/triage-inbox.md` — extend Producers table + add
    "Deferred producers" subsection. ~25 LOC added.
12. `docs/hooks-and-pipeline.md` — append the new producer sites to
    the artifact-write matrix. ~5 LOC added.

## Test strategy

- **Unit / boundary tests** (the 4 new files) — each driving the
  producer with synthetic findings against a tmp_path triage store,
  asserting on shape + dedup + idempotency.
- **Drift-protection tests** — the existing
  `shared/tests/test_triage_storage.py` covers the JSONL round-trip;
  new producer tests reuse the same `read_all_items` assertion
  shape so a triage schema change breaks both. No new drift test
  needed.
- **Concurrency** — `append_triage_item_idempotent` already has the
  lock + dedup-scan-under-lock test
  (`test_idempotent_concurrency_under_lock`) from iterate-1a. Not
  re-tested at the producer layer.
- **F0** — `uv run pytest shared/tests/ -v` from the monorepo root,
  expecting all green plus 4 new tests.
- **F0.5** — surface=`cli`, runner explicitly listed in the spec's
  Verification section. Each test file is non-empty by construction
  (>= 3 test_ functions per file), so `tests_run == 0` is structurally
  impossible.

## Alternative approaches considered

- **Centralized triage-emit helper** (one `_emit_to_triage` in
  `shared/scripts/triage.py`, called by every producer): rejected
  because each producer's `severity → kind` mapping and dedup-key
  shape differ. Centralization would force a flag-laden API that's
  harder to read than five small adapters.
- **Hook-level emit** (emit from the Stop hook, not from inside the
  producer module): rejected because the security report is invoked
  by `/shipwright-security`'s own flow (not the iterate Stop chain),
  and the perf gate runs in `/shipwright-test`. Emitting from inside
  each producer keeps the flow local and observable in unit tests.
- **Source-string normalization** (e.g. snake_case `f0_5` instead of
  `"f0.5"`): rejected — the handoff explicitly locks `"f0.5"` and
  `KNOWN_SOURCES` is informational. The `.` is fine on the wire.

## Risk + mitigation

- **Risk:** producer raises during emit and breaks the caller.
  **Mitigation:** every emit-helper wraps the loop in try/except,
  best-effort. Tests assert that a producer-side stub raising
  `ValueError` does NOT propagate.
- **Risk:** dedup-key collision across producers (two producers both
  emit the same dedup_key on the same commit). **Mitigation:**
  dedup-key always prefixes the producer source identifier
  (`f"{tool}:..."`, `f"perf:..."`, `f"f0.5:..."`, `f"drift:..."`), so
  collisions are structurally impossible.
- **Risk:** the test seam imports the producer module by file path
  and pulls heavy dependencies (e.g. `subprocess`, `urllib`,
  `playwright`). **Mitigation:** the new emit helpers are
  side-effect-free at import time; the heavy code paths run only
  inside `main()` which the tests don't invoke. Confirmed by
  inspection of each target module.
