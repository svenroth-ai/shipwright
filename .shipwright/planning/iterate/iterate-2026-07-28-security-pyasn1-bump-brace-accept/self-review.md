# Self-Review — iterate-2026-07-28-security-pyasn1-bump-brace-accept

Diff under review: `.trivyignore.yaml`, `shipwright_accepted_risks.yaml`,
`plugins/shipwright-plan/uv.lock`, `shared/tests/test_dependency_cve_floors.py` (new).

## 1. Does it do what was asked?

Yes, and the two findings are deliberately treated differently rather than
uniformly suppressed:

- **CVE-2026-59885 / CVE-2026-59886 (pyasn1 0.6.3)** — root-remediated by bumping
  to 0.6.4. `pyasn1-modules` requires `>=0.6.1,<0.7.0`, so the bump resolved
  cleanly: 3 lines changed, no collateral resolution churn.
- **CVE-2026-14257 (brace-expansion 2.1.2)** — accepted, because no fix path
  exists for this tree (see §7).

## 2. Leftover debug / dead code?

None. No prints, no commented-out code, no TODOs.

## 3. Do tests cover the change?

Yes, and the coverage is genuinely new rather than assumed:

- `test_dependency_cve_floors.py` (new) pins the pyasn1 floor. **Proven to go
  red**: run against the pre-bump lockfile (`git show HEAD:...`) it reports
  `0.6.3 → passes floor? False`. A guard that cannot fail is theatre; this one
  fails.
- `test_trivyignore_register.py` (existing) validates the new accept is scoped,
  time-bounded and justified — 4/4 green.
- `test_accepted_risks_register.py` + `accepted_risks_cli check` (existing)
  reconcile the two registers — "4 register entries, 4 suppressions, no drift".

## 4. Naming / conventions consistent?

Yes. The `.trivyignore.yaml` and `shipwright_accepted_risks.yaml` entries mirror
the shape, tone and field order of the existing OTel entries. The new test file
follows `test_trivyignore_register.py`'s pattern, including its
"a guard that never rejects is worthless" self-check.

## 5. Error handling / failure messages

The floor test fails with the offending version, the CVEs at stake, why the
floor exists, and the exact `uv lock --upgrade-package` command to fix it — so a
future failure is self-servicing rather than a puzzle.

## 6. Scope creep?

Checked deliberately; none of the three additions is discretionary:

- The `shipwright_accepted_risks.yaml` entry was **required** — the drift gate
  failed the build without it (`UNRECORDED trivy-ignore: CVE-2026-14257`). This
  was discovered by the test suite, not assumed.
- The floor test was **required** by the Test Completeness Ledger: the pyasn1
  behavior is testable, and "could-test-but-didn't" is not an available
  disposition.

One adjacent gap was found and deliberately NOT fixed here (filed instead, see
§7): `uv.lock` is absent from `TOUCHES_BUILD_FILE_PATTERNS`.

## 7. Affected Boundaries

| Boundary | Change | Risk |
|---|---|---|
| `.trivyignore.yaml` | Trivy `--ignorefile` input — suppresses a finding *before* `findings.json`, i.e. before the critical-gate | Scoped to one path + one CVE; time-bounded to 2027-01-28 |
| `shipwright_accepted_risks.yaml` | Governance register; expiry surfaces as "EXPIRED — re-review" on the dashboard | Same scope + expiry, kept in lockstep by the drift gate |
| `plugins/shipwright-plan/uv.lock` | Dependency resolution for the plan plugin | Single-package bump, patch-level, upstream constraint satisfied |

**Reachability finding backing the accept:** brace-expansion arrives solely via
`lighthouse -> minimatch -> brace-expansion` in the dev-only perf runner
(`node_modules/` is gitignored, package is `private`). It globs local paths while
driving Chrome against the project's own dev URL — no attacker-influenced brace
pattern reaches `expand()`. The only fix is 5.0.8; `minimatch 9.0.9` requires
`^2.0.2`, and the v2 line has **no backport** — 2.1.2 is its head, published
2026-07-08, fifteen days *before* the 5.0.8 fix (2026-07-23). The
`maintenance-v2` dist-tag means maintained, not patched; this was verified
against the installed source, which has no `maxLength` option.

**Deliberately deferred:** `uv.lock` is not in
`risk_detectors.TOUCHES_BUILD_FILE_PATTERNS` (a JS-only list: `package-lock.json`,
`yarn.lock`, `pnpm-lock.yaml`, …), so a Python lockfile change raises no
`touches_build` flag. That is a real detection gap, but fixing it would change
risk classification for every future iterate — out of scope for a security
remediation, and filed for its own iterate.

## Machine-readable checklist

```json
{
  "items": [
    {"name": "does-what-was-asked", "verdict": "pass",
     "note": "pyasn1 root-remediated to 0.6.4; brace-expansion accepted with scope + expiry"},
    {"name": "no-debug-or-dead-code", "verdict": "pass",
     "note": "no prints, commented-out code or TODOs in the diff"},
    {"name": "tests-cover-the-change", "verdict": "pass",
     "note": "new floor guard proven red on the pre-bump lockfile (0.6.3); register policy + drift gate green"},
    {"name": "naming-and-conventions", "verdict": "pass",
     "note": "entries mirror the existing OTel entries; test mirrors test_trivyignore_register.py"},
    {"name": "error-handling", "verdict": "pass",
     "note": "floor failure names the version, the CVEs, the rationale and the exact fix command"},
    {"name": "no-scope-creep", "verdict": "pass",
     "note": "governance entry forced by the drift gate; floor test forced by the ledger; uv.lock detection gap deferred, not fixed here"},
    {"name": "affected-boundaries", "verdict": "pass",
     "note": "three data/config boundaries, no code paths; suppression scoped to one CVE + one path, expires 2027-01-28"}
  ]
}
```
