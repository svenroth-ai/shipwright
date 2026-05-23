# Iterate Spec: SBOM resolver — pin to per-manifest .venv METADATA

- **Run ID:** iterate-2026-05-23-sbom-resolver-pin-lockfile
- **Type:** bug
- **Complexity:** medium
- **Status:** draft

## Goal

Replace the SBOM Python-license resolver's ambient-`sys.path` probe
(`importlib.metadata.metadata`) with a deterministic read of
`<manifest_dir>/.venv/.../site-packages/<pkg>-*.dist-info/METADATA`,
mirroring the d325fd6 deterministic-render-timestamps precedent. Fixes
both (A) non-deterministic license counts across consecutive renders
and (B) broken `cd plugins/<x> && uv sync && update_compliance` launch
payload (uv sync populates the plugin's `.venv/` but the resolver looked
elsewhere).

## Acceptance Criteria

- [ ] **AC-1 (root cause).** `_detect_python_license` no longer calls
      `importlib.metadata.metadata` and no longer depends on `sys.path`.
      Pre-existing call to `from importlib import metadata` is removed
      from the license-resolution path (a follow-up consumer may keep
      it for unrelated purposes; that's out-of-scope here).
- [ ] **AC-2 (per-manifest resolution).** Given a fixture pyproject at
      `<root>/plugins/<x>/pyproject.toml` with declared dep `pkg-foo`
      and a synthetic METADATA at
      `<root>/plugins/<x>/.venv/Lib/site-packages/pkg_foo-1.0.0.dist-info/METADATA`
      containing `License: Apache-2.0`, the resolver returns
      `"Apache-2.0"`. Same fixture without the dist-info returns
      `"unknown"`.
- [ ] **AC-3 (determinism).** Two consecutive `collect_dependencies`
      invocations against the same fixture tree produce byte-identical
      `DependencyInfo` lists (license fields included). No reliance on
      process-Python interpreter state between calls.
- [ ] **AC-4 (cross-manifest isolation).** Plugin A's `.venv` declaring
      `pkg-x@1.0.0` License: MIT and Plugin B's `.venv` declaring
      `pkg-x@2.0.0` License: Apache-2.0 are resolved independently per
      manifest; the SBOM does NOT cross-pollinate licenses.
- [ ] **AC-5 (cross-platform site-packages layout).** Resolver finds
      dist-info under both `<venv>/Lib/site-packages/` (Windows) and
      `<venv>/lib/python*/site-packages/` (POSIX). Tested with both
      glob shapes against synthetic fixtures (no actual interpreter
      version dependency in CI).
- [ ] **AC-6 (METADATA parser handles edge cases).** Parser extracts
      `License:` first, then `License-Expression:`, then falls back to
      `Classifier: License :: OSI Approved :: <Name> License` (matching
      the existing `_detect_python_license` semantics so the migration
      is value-equivalent for pre-existing test fixtures). Returns
      `"unknown"` when none present or value is literal `UNKNOWN`.
- [ ] **AC-7 (launch payload truth).** With the fixture from AC-2,
      simulating the operator workflow (`uv sync` → `.venv/` populated
      with dist-info METADATA → regenerate SBOM) flips the license from
      `"unknown"` to the declared value. Demonstrates the launch payload
      now resolves the triage item.
- [ ] **AC-8 (regression — Triage auto-resolve).** `emit_undeclared_triage`
      still emits when license=`"unknown"` and auto-dismisses when it
      flips to a real value. All 13 existing
      `TestEmitUndeclaredTriage` tests pass unchanged.

## Spec Impact

- **Classification:** none
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** Bug fix — restores intended behavior of the
  SBOM license resolver (deterministic license resolution from
  per-manifest authoritative metadata). ADR-056 already documented the
  SBOM triage producer contract; the resolver's promise to "read PKG-INFO
  from installed site-packages" was implicit in `_detect_python_license`
  comments. This iterate makes the implementation match the contract,
  no FR table change. BUG iterates are NOT gated by the F11 spec-impact
  verifier.

## Out of Scope

- Reading `uv.lock` directly: `uv.lock` does NOT carry license fields
  (verified empirically on `plugins/shipwright-plan/uv.lock`). The
  authoritative source for license info is the dist-info METADATA
  installed under each `.venv`.
- Auto-installing dependencies when `.venv` is missing. The launch
  payload remains the operator's escape hatch — this iterate only
  guarantees the resolver *uses* the right dist-info AFTER `uv sync`,
  not that it installs anything itself.
- npm-side resolver: `_detect_npm_license` already reads from
  `package-lock.json` deterministically (Phase 0f). Out of scope.
- Cross-platform interpreter version probing: tests use synthetic
  fixtures with hard-coded paths (`Lib/site-packages/` and
  `lib/python3.11/site-packages/`); production code globs.

## Design Notes

n/a — no UI surface.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `uv sync` / `pip install` (external) → `<manifest_dir>/.venv/.../site-packages/<pkg>-*.dist-info/METADATA` | `data_collector._detect_python_license` (this iterate) | RFC822-style key-value (PEP 621 METADATA) |

The METADATA file is a producer/consumer boundary between the Python
packaging toolchain and the SBOM resolver. The current implementation
hid this boundary behind `importlib.metadata` (which delegates the
producer side to `sys.path`-resolution). After this iterate the
boundary is explicit: a specific file on disk parsed by our code.

## Confidence Calibration

- **Boundaries touched:** dist-info METADATA file at
  `<manifest_dir>/.venv/{Lib,lib/python*}/site-packages/<pkg>-*.dist-info/METADATA`
  (producer: `uv sync` / `pip install`; consumer: this resolver).

- **Empirical probes run:**
  - Round-trip (producer→file→consumer): synthetic dist-info + real
    `collect_dependencies` invocation → license string flows through.
    `test_collect_dependencies_uses_per_manifest_resolver`,
    `test_launch_payload_outcome_simulation`. PASSED.
  - Cross-platform layout: Windows `Lib/site-packages/` + POSIX
    `lib/python*/site-packages/`. Both fixture shapes resolve.
    `test_reads_license_from_windows_layout`,
    `test_reads_license_from_posix_layout`. PASSED.
  - PEP 503 normalization: dotted name (`ruamel.yaml`), case
    (`Foo-Bar`), underscore (`google_genai`).
    `test_pep503_normalization_dotted_name`,
    `test_pep503_normalization_case_insensitive`,
    `test_pep503_name_normalization`. PASSED.
  - Multiple stale dist-info: two `pkg-1.0.0.dist-info` +
    `pkg-2.0.0.dist-info` side-by-side resolve deterministically to
    the higher version. `test_multiple_distinfo_picks_deterministically`.
    PASSED.
  - utf-8 encoding: METADATA with Ö/ö in Author field doesn't crash.
    `test_utf8_encoding_for_metadata`. PASSED.
  - Multiple `Classifier:` headers: license classifier is not the
    first one. `test_multiple_classifiers_finds_license_classifier`
    (uses `get_all`, not `get`). PASSED.
  - Filesystem-error resilience: `PermissionError` on METADATA read
    → return `"unknown"`, no crash. `test_filesystem_error_returns_unknown`.
    PASSED.
  - Cross-manifest isolation: plugin A and plugin B same package,
    different licenses → resolved independently.
    `test_cross_manifest_isolation`. PASSED.
  - Determinism contract: two consecutive calls byte-identical.
    `test_resolver_deterministic_across_runs`. PASSED.
  - Anti-regression: `importlib.metadata.metadata` is detonated by
    monkeypatch; resolver still works (proof it's pure filesystem).
    `test_no_importlib_metadata_call_in_resolver_path`. PASSED.
  - Ambient-sys.path immunity: process Python has `pytest` installed,
    but resolver returns `"unknown"` for `pytest` against an empty
    manifest `.venv`. `test_resolver_ignores_ambient_sys_path`. PASSED.

- **Edge cases NOT probed + why acceptable:**
  - `.egg-info/PKG-INFO` (legacy editable installs). uv produces
    PEP 660 dist-info exclusively; egg-info is out of scope. Documented
    in iterate ADR as known limitation.
  - Operator-input categories (POSIX `export`, inline `# comment`,
    quoted `#`) — METADATA is machine-written by `uv sync`, never
    human-edited. The 8-probe checklist's operator categories don't
    apply (justification per `references/boundary-probes.md`).
  - Truly-malicious METADATA contents (gigabyte file, billion-line
    classifier list). The producer is `uv sync` against PyPI — same
    trust boundary as `pip install`. Out of scope for this iterate.
  - Symbolic-link `.venv` → other location. `Path.is_dir()` follows
    symlinks; tested implicitly by all the layout tests. Not isolated
    further.

- **Confidence-pattern check:** the external LLM review surfaced 7
  HIGH/medium findings that I had NOT individually probed before review
  (PEP 503 dotted-name, multiple dist-info, utf-8, Classifier get_all,
  filesystem errors, sorted glob, multiple python-X.Y dirs). Per the
  asymptote heuristic, the "are you confident?" attestation was
  uncorrelated with bug presence. **One additional probe per the
  rule:** I re-checked the implementation against the iterate-2026-05-22
  precedent (deterministic-render-timestamps) for shape parity — the
  pattern is identical (derive output from a stable input artifact,
  not ambient process state). No new finding. Stopping rule met.

## Verification (medium+)

- **Surface:** `cli`
- **Runner command:** `cd plugins/shipwright-compliance && uv run --color=no pytest tests/test_data_collector.py tests/test_sbom_generator.py -v`
- **Evidence path:** `.shipwright/runs/iterate-2026-05-23-sbom-resolver-pin-lockfile/f05.log`
- **Justification (only if surface=none):** n/a
