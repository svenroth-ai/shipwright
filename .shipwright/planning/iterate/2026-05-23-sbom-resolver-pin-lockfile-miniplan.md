# Mini-Plan: SBOM resolver — pin to per-manifest .venv METADATA

- **Run ID:** iterate-2026-05-23-sbom-resolver-pin-lockfile
- **Type:** bug (medium)
- **Spec:** `.shipwright/planning/iterate/2026-05-23-sbom-resolver-pin-lockfile.md`

## Root cause (confirmed empirically)

`plugins/shipwright-compliance/scripts/lib/data_collector.py:816-845`
calls `importlib.metadata.metadata(package_name)`. That delegates to the
**ambient** `sys.path` of the orchestrator's Python process — not the
`<manifest_dir>/.venv/` that holds the *correct* installed-package
metadata for the manifest being scanned.

Symptoms:
- (A) **Determinism break:** ambient `sys.path` varies across runs
  (which `.venv` the shell entered, recent `uv pip` activity, etc.),
  so consecutive renders disagree on license counts.
- (B) **Broken launch payload:** `cd plugins/<x> && uv sync` populates
  `plugins/<x>/.venv/Lib/site-packages/`. The next `update_compliance`
  runs from repo root with its *own* `sys.path` — never sees the plugin
  venv → package stays `"unknown"` → triage item never resolves.

## Approach

Pinpoint replacement, mirroring d325fd6 (deterministic render
timestamps): derive from authoritative input data (filesystem dist-info),
not ambient process state.

### Implementation steps (single source file)

**File: `plugins/shipwright-compliance/scripts/lib/data_collector.py`**

1. Replace `_detect_python_license(package_name) -> str` with
   `_detect_python_license(package_name, manifest_dir: Path) -> str`.
2. New body — pure filesystem lookup:
   - Compute `<manifest_dir>/.venv/Lib/site-packages/` and
     `<manifest_dir>/.venv/lib/python*/site-packages/` (POSIX glob).
   - For each candidate site-packages dir that exists:
     - Glob `<sp>/<normalized_name>-*.dist-info/METADATA` where
       `normalized_name = package_name.replace("-", "_")` (PEP 503).
     - First match wins (deterministic: glob results sorted).
     - Parse via `email.parser.HeaderParser` (RFC822 — same shape
       `importlib.metadata` parses internally; no PyPI dep).
     - License extraction order, matching the old semantics for
       value-equivalence on pre-existing fixtures:
       1. `License:` header (if non-empty, non-`UNKNOWN`)
       2. `License-Expression:` header (PEP 639)
       3. `Classifier: License :: ... :: <Name> License` (Trove)
     - One-line clamp (`.strip().splitlines()[0]`).
   - Return `"unknown"` when no match.
3. Update the single caller `_parse_pyproject_deps(pyproject_path)`:
   `_detect_python_license(name, manifest_dir=pyproject_path.parent)`.
4. Remove the `from importlib import metadata as _metadata` import path
   in the resolver. (The module elsewhere doesn't use it.)

### Test changes

**File: `plugins/shipwright-compliance/tests/test_data_collector.py`**

- Replace 2 deleted tests (`test_python_license_via_importlib_metadata`,
  `test_python_license_unknown_for_missing_package`) with a single
  signature-contract test in `TestSbomLockfileAndWorkspace`.
- Add `TestPythonLicenseFromVenvMetadata` (17 tests) covering: layout
  (Windows + POSIX), no-venv, no-dist-info, no-license, literal-UNKNOWN,
  License-vs-License-Expression precedence, License-Expression fallback,
  Trove-classifier fallback, multiline clamp, ignore-ambient-sys.path,
  cross-manifest isolation, determinism, PEP 503 normalization,
  integration with `collect_dependencies`, launch-payload outcome
  simulation, anti-regression probe (`importlib.metadata` calls
  detonated by monkeypatch).

**No changes needed in:**

- `_detect_npm_license` — already deterministic (lockfile-first; Phase 0f).
- `sbom_generator.py` — pure consumer of `DependencyInfo.license`.
- `emit_undeclared_triage` — keys off `license == "unknown"`; behavior
  unchanged when fix lands. All 13 existing `TestEmitUndeclaredTriage`
  tests pass on AC-8.

## Alternative considered (rejected)

**Alternative: pin to `uv.lock`.** Empirically verified `uv.lock` does
NOT carry a license field — only package name, version, source URL,
hash, dependency graph. Rejected.

**Alternative: keep `importlib.metadata` as fallback when no dist-info
in plugin venv.** Rejected — re-introduces the ambient-state bug;
fallback would silently fire whenever the operator runs the regen from
a Python interpreter that happens to have the package installed
globally, masking the "this plugin's deps aren't installed" signal that
the triage item is supposed to surface. The "unknown" fallback is the
correct deterministic behavior.

**Alternative: install dependencies on the fly.** Out of scope (security
+ blast radius). The triage item's launch payload IS the user-driven
install pathway.

## Files to change

- `plugins/shipwright-compliance/scripts/lib/data_collector.py` (modify,
  ~30 LOC: replace `_detect_python_license` body + signature + caller)
- `plugins/shipwright-compliance/tests/test_data_collector.py` (modify,
  ~250 LOC added — already authored in RED phase)

## Test strategy

- Full plugin suite (80 → 96 tests) green after fix.
- `TestPythonLicenseFromVenvMetadata` (17 tests) is the boundary-probe
  round-trip + drift-protection layer.
- F0.5 surface=cli runs the same suite.
- Existing `TestEmitUndeclaredTriage` proves the triage producer's
  behavior is unchanged (`unknown → triage → uv sync → resolved` flow
  works end-to-end).
