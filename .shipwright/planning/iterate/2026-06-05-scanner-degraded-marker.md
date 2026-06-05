# Iterate: a fataled/truncated scanner leg degrades to a green result (no degraded marker)

- **Run ID:** iterate-2026-06-05-scanner-degraded-marker
- **Intent:** CHANGE (Spec Impact: MODIFY — the `scan()` contract gains a degraded-scan channel)
- **Complexity:** medium + `touches_io_boundary` (subprocess stdout/report-file → `json.loads` → findings; `findings.json` config emission read by the CI gate)
- **Date:** 2026-06-05
- **Follow-up from:** iterate-2026-06-05-gitleaks-report-path

## Symptom (as reported)

`iterate-2026-06-05-gitleaks-report-path` made `_run_tool` *log* stderr when an
`expect_nonzero` tool (gitleaks) yields an empty/unparseable report. But the
return contract was unchanged: `_run_tool` still returns `None`, and
`_run_gitleaks`/`_run_semgrep`/`_run_trivy` still map `None → []`. `[]` means
**"clean: 0 findings"** to every downstream consumer.

So a gitleaks **fatal** (exit 1: `dubious ownership` / corrupt repo / config
error) or a **truncated** report — and equally a semgrep/trivy **empty-stdout**
crash — degrades to a green secrets/SAST/SCA leg. This is the *same failure
class* as the `--report-path -` bug just fixed: a scanner that didn't actually
run is indistinguishable from one that ran and found nothing.

## Root cause

`_run_tool` collapses two distinct outcomes onto the same `None` sentinel:

1. **clean** — the tool ran and legitimately produced no findings
   (semgrep/trivy emit a non-empty JSON envelope `{"results":[]}`; gitleaks
   writes a non-empty `[]` to the report file). These parse fine and return
   `[]` *through the normal path* — they never reach a `None` branch.
2. **degraded** — the tool was in `capabilities` and was invoked, but produced
   no parseable output. EVERY `None`-returning branch of `_run_tool` is this
   case: unexpected non-zero exit, empty payload, timeout, `JSONDecodeError`,
   `FileNotFoundError`.

The `_run_*` wrappers then erase the distinction (`None → []`), and `scan()`
returns a findings list with no way to say "the secrets leg never ran".

## Fix (design: side-channel `scan_errors`, NOT a synthetic finding)

A degraded-scan signal is a **control-plane** concern ("did the tool run?"),
categorically different from a **data-plane** finding ("what did the tool
find?"). Injecting a synthetic `severity: critical` "finding" would auto-fail
the gate, but it pollutes `by_severity` counts, the SARIF → GitHub
code-scanning feed, redaction, and the SBOM/compliance consumers — exactly the
surfaces a future reader would have to special-case. So the marker rides a
dedicated channel and `.findings[]` stays pure.

1. **`oss_backend.py` — record the marker at the source.**
   `_run_tool(..., errors=None)` appends one record
   `{"scanner", "reason", "detail"}` to the `errors` accumulator at *each*
   `None`-return site. `reason` is a closed vocabulary:
   `nonzero_exit | empty_output | timeout | invalid_json | missing_binary`.
   `_run_semgrep/_run_trivy/_run_gitleaks(target, errors=None)` thread it.
   `OSSBackend.scan()` resets `self.scan_errors = []` and passes it down. The
   findings return is UNCHANGED (`None → []`), so the existing degraded tests
   (`test_returns_empty_on_timeout`, `test_surfaces_stderr_on_empty_report`,
   `test_returns_empty_on_invalid_report_json`,
   `test_returns_empty_on_missing_binary`) — which pin the `[]` *findings*
   contract — stay green.

2. **`scanner_backend.py` — document the channel on the ABC.** Add the
   `scan_errors: list[dict[str, Any]]` annotation + docstring. Consumers read it
   via `getattr(backend, "scan_errors", [])` so the Aikido backend and test
   mocks default to "no degradation" with no code change.

3. **`scan.py` — threshold layer flags degraded.** `build_config` gains
   `scan_errors` → writes top-level `"degraded": bool` + `"scan_errors": [...]`
   into `findings.json`. `main()` reads `getattr(backend, "scan_errors", [])`
   (and round-trips it on the `--input-from-cache` path), threads it into
   `build_config` + the structured output, and returns **exit 2** (scan error)
   when degraded — checked before the `--fail-on` threshold so a degraded scan
   never reports as a clean exit 0.

4. **`run_scan_and_report.py` — report layer flags degraded.** Reads
   `scan_errors`, embeds `degraded`/`scan_errors` in the JSON sidecar, prepends
   a `⚠️ Degraded scan` banner to the Markdown, surfaces it in the summary, and
   returns **exit 1** when degraded.

5. **`generate_security_report.py` — honest CI PR comment.** Loads `degraded`
   from the input JSON and renders a degraded banner so the combined report
   can't say "✅ No security findings" while `findings.json` says degraded.

6. **`.github/workflows/security.yml` — close the green gate (fail-closed).**
   The critical-gate jq step reads `findings.json`; add a `.degraded == true`
   check that `exit 1`s. This is the change that makes the fix *real* — the
   scan step is `continue-on-error: true`, so scan.py's exit code is ignored in
   CI; the jq gate is the enforcement. (Adopted repos are unaffected: their
   `security.yml.template` runs the native scanner binaries directly — not
   `scan.py` — and already fails closed on missing/invalid SARIF.)

## Affected Boundaries

- subprocess (semgrep/trivy stdout · gitleaks report file) → `json.loads` →
  normalized findings **+** the new `scan_errors` accumulator.
- `scan()` ⇄ consumers: the `backend.scan_errors` instance attribute (read via
  `getattr` default `[]`).
- `findings.json` config: new top-level `degraded` (bool) + `scan_errors`
  (list) — produced by `scan.py`, consumed by the `security.yml` jq gate and
  round-tripped by `--input-from-cache`.

## Confidence Calibration

- **Boundaries touched:** subprocess→json.loads→findings; the `scan_errors`
  side channel; the `findings.json` `degraded`/`scan_errors` producer/consumer
  pair (scan.py ↔ security.yml jq gate ↔ cache round-trip).
- **Empirical probes run:**
  - Baseline: full security suite **114 → 142** on the touched files, **348
    passed / 3 smoke-skipped** whole-plugin; **141** integration tests pass
    (incl. `test_ci_self_gating`). ruff@0.15.15 clean. `check_ci_gate_coverage`
    OK (my gate edit did not loosen check (c)).
  - Failing-test-first: every new test class (source channel, scan.py exit,
    report banner, gate) was RED before the matching impl and GREEN after
    (recorded per-step in the build).
  - Round-trip probe (executed): `build_config(scan_errors=…)` → `json.dumps`
    → file → re-read → gate decision. **`degraded`-with-0-findings BLOCKS;
    `clean`-with-0-findings PASSES** — the exact clean-vs-degraded ambiguity
    this iterate removes. (`jq` is absent locally; the gate's jq *syntax* is
    pinned by `test_gate_exits_on_degraded`, its *content decision* by the
    Python round-trip.)
  - Cache round-trip: `--input-from-cache` on a degraded `findings.json` keeps
    `degraded` + re-emits markers + exit 2 (`test_cache_roundtrips_degraded`).
- **Test Completeness Ledger:** see table below.
- **Confidence-pattern check:** asymptote — every `None`-return branch of
  `_run_tool` is enumerated and each is pinned to a `reason` code by a test (no
  "are you confident" hand-wave). Coverage — source channel, ABC default,
  config producer, exit codes, cache round-trip, report banner, and the jq gate
  string are each pinned.

### Test Completeness Ledger

| Behavior (introduced/changed) | Disposition | Evidence |
|---|---|---|
| `_run_tool` records `nonzero_exit` on unexpected non-zero exit | `tested` | `TestScanErrors::test_records_nonzero_exit` |
| `_run_tool` records `empty_output` on empty payload (gitleaks fatal / semgrep+trivy empty stdout) | `tested` | `test_records_empty_output_gitleaks`, `test_records_empty_output_semgrep` |
| `_run_tool` records `timeout` / `invalid_json` / `missing_binary` | `tested` | `test_records_timeout`, `test_records_invalid_json`, `test_records_missing_binary` |
| degraded leg leaves the *findings* return as `[]` (no pollution) | `tested` | existing `test_returns_empty_on_*` stay green (re-run) |
| `OSSBackend.scan` exposes `scan_errors`; empty on a clean scan | `tested` | `test_scan_errors_empty_on_clean`, `test_scan_errors_populated_on_degraded_leg` |
| `scan()` resets `scan_errors` between calls (no leak across runs) | `tested` | `test_scan_errors_reset_between_calls` |
| `build_config` emits `degraded` + `scan_errors` | `tested` | `TestBuildConfigDegraded::*` |
| `scan.py` returns exit 2 when degraded (before `--fail-on`) | `tested` | `test_degraded_returns_2`, `test_clean_still_returns_0` |
| `degraded`/`scan_errors` round-trip through `--input-from-cache` | `tested` | `test_cache_roundtrips_degraded` |
| `run_scan_and_report` embeds degraded + exits 1 | `tested` | `test_run_scan_report_degraded_banner_and_exit` |
| `generate_security_report` renders a degraded banner | `tested` | `test_report_degraded_banner` |
| `security.yml` jq gate fails closed on `.degraded == true` | `tested` | `test_security_yml_gate_has_degraded_guard` (static workflow assertion) |
| real-binary degraded path on Linux CI | `untestable` (`requires-external-nondeterministic-service`) | exercised by this PR's CI run, not unit-mockable |

0 testable-but-untested behaviors.
