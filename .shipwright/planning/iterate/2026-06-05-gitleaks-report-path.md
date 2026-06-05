# Iterate: gitleaks `--report-path -` never reaches stdout (secret scanner silently returns 0)

- **Run ID:** iterate-2026-06-05-gitleaks-report-path
- **Intent:** BUG
- **Complexity:** small + `touches_io_boundary` (subprocess → report-file → JSON parse → normalized findings)
- **Date:** 2026-06-05

## Symptom (as reported)

`plugins/shipwright-security/tests/test_oss_backend_smoke.py::test_gitleaks_detect_scans_committed_shipwright_dir`
uses a positive-control gate: if gitleaks does not find `src/main_key.pem`
it `pytest.skip()`s (carrying `# test-hygiene: allow-silent-skip`). It SKIPS
in **every** CI run (`Got paths: []`) while the Semgrep + Trivy smoke tests
pass — so gitleaks' real detection + node_modules-exclusion contract is
NEVER exercised in CI. Earlier investigation framed this as a
Windows-detects / Linux-finds-0 divergence and concluded it needed a Linux
repro.

## Root cause (PROVEN, platform-independent — no Linux repro needed)

`_run_gitleaks` invokes:

```
gitleaks detect --report-format json -s <target> --report-path - --config <toml>
```

and `_run_tool` parses the subprocess **stdout** as JSON.

gitleaks v8.21.2 does **not** treat `--report-path -` as stdout. In
`cmd/root.go::findingSummaryAndExit`:

```go
reportPath, _ := cmd.Flags().GetString("report-path")
...
if reportPath != "" {
    if err := report.Write(findings, cfg, ext, reportPath); err != nil { ... }
}
```

and `report/report.go::Write` does `os.Create(reportPath)` with **no**
`-`→stdout special-casing. So `--report-path -` makes gitleaks create a
literal file named `-` and write the JSON report there. gitleaks writes
**nothing** structured to stdout (its human summary goes to stderr). The
wrapper reads empty stdout → `_run_tool` returns `None` → `_run_gitleaks`
returns `[]` → 0 findings → positive-control miss → silent skip.

This happens on **every** platform. The "Windows detects / Linux finds 0"
framing was a measurement artifact: the manual reproduction command had no
`--report-path -`, so it surfaced gitleaks' own stderr summary ("1 finding")
— that is gitleaks *detecting*, not the wrapper returning a finding. CI is
Linux-only (ubuntu-latest), so "skips in every CI run" simply = the only
place the broken wrapper path runs.

### Physical evidence in this very repo

The session-start `git status` showed `?? -` — an untracked file literally
named `-` at the repo root. Its contents:

```json
[ { "Description": "Identified a Private Key...",
    "File": "key.pem", "Entropy": 4.635579,
    "Commit": "b16110731161ef4fab319a73fa37c3f354728044", ... } ]
```

i.e. gitleaks DID detect the synthetic fixture (1 private-key finding,
entropy 4.64 — matching the investigation), wrote it to a file named `-`,
and the wrapper never saw it. The populated `Commit` field confirms
git-history (`detect`) mode works for this fixture — so the fix makes the
smoke test pass on Linux too.

### Production impact

This is a real latent defect, not just a test artifact: the monorepo's own
`security.yml` runs `scan.py` → `OSSBackend` → `_run_gitleaks`, so the
gitleaks **secret-detection** leg of the production scan has been returning
0 findings for every scan, and littering a stray `-` file in the CWD each
run. Semgrep + Trivy were unaffected (they emit JSON to stdout natively).

## Why the bug survived

Every `_run_gitleaks` unit test mocks `subprocess.run` with
`stdout = json.dumps(fixture)` — encoding the *wrong* assumption that
gitleaks writes its JSON to stdout. The only real-binary test (the smoke
test) skipped via the positive-control gate, whose `allow-silent-skip`
rationale ("upstream rule churn / registry fetch failure") was copied from
the Semgrep gate. That rationale is FALSE for gitleaks: `useDefault=true`
uses the binary-embedded ruleset with **no network fetch**, so a gitleaks
miss is deterministic, not flaky churn.

## Fix

1. **Production (`oss_backend.py`):** write the gitleaks report to a real
   temp file and read it back. Add an optional `report_path` parameter to
   `_run_tool` (semgrep/trivy keep stdout parsing; gitleaks reads the file).
   Keep `detect` (git-history) mode — root cause is the report path, not the
   scan mode. Clean up both temp files. Surface stderr when an
   `expect_nonzero` tool yields no parseable output (removes the
   swallowed-failure blind spot).
2. **Unit tests:** fix the tests that mock JSON on stdout to simulate the
   *real* gitleaks contract (write JSON to the `--report-path` file, empty
   stdout). Add regression sentinels: findings come from the report file
   (not stdout); the report-path is a real file, never `-`; the report temp
   file is cleaned up.
3. **Smoke test (ADR-044):** drop the gitleaks `allow-silent-skip` marker;
   convert the positive-control gate to the canonical CI-gated pattern
   (`if is_ci(): pytest.fail(diagnostic)`), with an actionable diagnostic
   (gitleaks version + fixture git log). The Semgrep gate keeps its skip —
   its network-registry rationale is genuinely valid.
4. **Docs:** update SKILL.md + references/oss-scanners.md to show the fixed
   invocation (report file, not `--report-path -`).

## Affected Boundaries

- subprocess invocation (gitleaks CLI) → on-disk JSON report file → UTF-8
  read → `json.loads` → `normalize_gitleaks` → normalized finding schema.
- The `--report-path` CLI contract with gitleaks (file path, not stdout).

## Confidence Calibration

- **Boundaries touched:** gitleaks subprocess → temp report file (mkstemp) →
  UTF-8 file read → `json.loads` → `normalize_gitleaks`. The `--report-path`
  argument contract.
- **Empirical probes run:**
  - Read gitleaks v8.21.2 source (`cmd/root.go`, `report/report.go`):
    confirmed `--report-path -` → `os.Create("-")`, no stdout path. (PROOF)
  - Inspected the stray `./-` file: valid gitleaks JSON, private-key
    finding, populated `Commit` field → detect-mode detection works. (PROOF)
  - Baseline `test_oss_backend.py`: 50 passed before changes.
  - Failing-test-first: new report-file test is RED on current code, GREEN
    after fix (recorded below).
- **Test Completeness Ledger:** see table below.
- **Confidence-pattern check:** asymptote — root cause is read directly from
  upstream source + a physical artifact, not inferred ("are you confident?"
  replaced by reading the bytes). Coverage — the report-file contract, the
  no-`-` sentinel, cleanup, the full-scan path, and the real-binary smoke
  gate are each pinned by a test.

### Test Completeness Ledger

| Behavior (introduced/changed) | Disposition | Evidence |
|---|---|---|
| `_run_gitleaks` returns findings from the report **file** (not stdout) | `tested` | `TestRunGitleaks::test_reads_findings_from_report_file_not_stdout` (RED→GREEN) |
| `--report-path` value is a real temp file, never `-` | `tested` | `TestRunGitleaks::test_report_path_is_real_file_not_dash` |
| both gitleaks temp files (config + report) are cleaned up | `tested` | `test_gitleaks_cleans_up_temp_config` + `TestRunGitleaks::test_cleans_up_temp_report_file` |
| full `OSSBackend.scan` combines gitleaks (report-file) + semgrep + trivy | `tested` | `test_full_scan_combines_all_tools` (updated to real contract) |
| `_run_tool` surfaces stderr when an expect_nonzero tool yields no output | `tested` | `TestRunGitleaks::test_surfaces_stderr_on_empty_report` |
| gitleaks still runs in `detect` (history) mode | `tested` | `test_gitleaks_stays_in_detect_mode` |
| timeout / missing-binary still degrade to `[]` | `tested` | `test_returns_empty_on_timeout`, `test_returns_empty_on_missing_binary` |
| smoke positive-control fails (not skips) in CI on a real gitleaks miss | `tested` | `test_gitleaks_detect_scans_committed_shipwright_dir` (CI-gated fail) + static probe `scan_for_silent_skip_without_ci_guard` |
| real gitleaks binary detection on Linux CI | `untestable` (`requires-external-nondeterministic-service`) — verified by the iterate's own PR CI run, not unit-mockable | smoke test executes in the gating CI job; PR CI is the live Linux probe |

0 testable-but-untested behaviors.
