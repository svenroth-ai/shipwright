# ADR-097: Bloat exception — `oss_backend.py` → 421-LOC and `test_oss_backend.py` → 655-LOC

<!-- Bloat-baseline exception granted for the gitleaks --report-path fix
     (iterate-2026-06-05-gitleaks-report-path). -->

- **Status:** accepted
- **Date:** 2026-06-05
- **Re-Review-Date:** 2026-09-05 _(3 months out — re-check whether
  `oss_backend.py` should be split into per-tool runner modules and
  whether `test_oss_backend.py` should split its exclusion-contract
  group into its own file.)_
- **Incident Reference:** iterate-2026-06-05-gitleaks-report-path
  (Run-ID), decision-drop `iterate-2026-06-05-gitleaks-report-path_001`,
  triage `trg-190ff3b9`. The limit was crossed when fixing the gitleaks
  `--report-path -` bug (the secret scanner was silently returning 0
  findings on every platform).

## Context

`oss_backend.py` (grandfathered 374 → 421, +47) is the OSS scanner
backend: it orchestrates Semgrep, Trivy and Gitleaks, normalizes their
output, owns the per-scanner exclusion contract, and runs each tool via
a shared `_run_tool`. The +47 is the bug fix itself: gitleaks
`--report-path -` writes a literal file named `-` (never stdout), so the
report is now written to a real `mkstemp` temp file and read back via a
new `_run_tool(report_path=...)` branch + a `_read_report_file` helper,
plus stderr surfacing on empty output. None of it is removable without
re-introducing the silent-0-findings defect.

`test_oss_backend.py` (grandfathered 543 → 655, +112) gained five tests
+ one helper that pin the fix and satisfy the Test Completeness Ledger
(testable ⇒ tested): findings-from-report-file (RED→GREEN regression),
report-path-is-not-`-`, temp-report cleanup, stderr-on-empty, and
malformed-report-json. Each row is cited in the iterate's
`test_completeness` ledger; removing any creates an untested-testable
gap that the F11 gate blocks.

## Ousterhout Argument

`oss_backend.py` is a deep module: the public interface is one method
(`OSSBackend.scan(target, scan_types) -> findings`) registered through
the backend registry, behind which sits substantial, cohesive behaviour
— three external-tool invocations, output normalization, the
gitignore-vs-plugin exclusion contract, temp config/report lifecycle,
and a forced-UTF-8 subprocess env. Splitting it into per-tool files
would expose shared internals (`_run_tool`, `_resolve_excludes`,
`_utf8_subprocess_env`, the exclusion constants) across module
boundaries that today are private to one backend — widening the
interface to shrink the line count, the opposite of a deep module. The
one-backend-per-file shape is the established plugin pattern
(`oss_backend.py`, `aikido_backend.py`, …).

## YAGNI Check

Walked each responsibility added by this change: report temp-file
write+read (needed today — it is the fix), `_read_report_file` (needed —
isolates the OSError-tolerant read), `report_path` param on `_run_tool`
(needed — gitleaks has no stdout-report mode), empty-payload stderr
surfacing (needed — removes the swallowed-failure blind spot that hid
this bug). No speculative scope was added. On the test side, every new
test pins a behaviour that exists today; none is "might need later".

## Chesterton-Fence Check

Git history of `oss_backend.py` shows the file deliberately keeps all
three runners + the exclusion contract together (Sub-Iterate H "per
scanner exclusion contract"); the fence (one cohesive backend module)
stands for a documented reason. Tearing it down (splitting) was not done
because the reason still holds and the bug fix does not change the
module's responsibilities — it corrects one runner's IO channel. The
test file's size fence is simply "one test module per backend"; the
re-review date schedules the split decision rather than forcing churn
inside a focused bug fix.

## Decision

Raise the baseline `current` for both files (state `grandfathered` →
`exception`, `adr` = `ADR-097`):

- `plugins/shipwright-security/scripts/lib/oss_backend.py`: 374 → 421
- `plugins/shipwright-security/tests/test_oss_backend.py`: 543 → 655

The exception is bounded by the Re-Review-Date; the preferred long-term
remediation is to split `oss_backend.py` into per-tool runner modules
and move the exclusion-contract tests into their own file.
