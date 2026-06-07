# Iterate: SBOM — distinguish "not installed" from "no declared license"

- **Run ID:** `iterate-2026-06-07-sbom-not-installed-vs-undeclared`
- **Intent:** CHANGE · **Complexity:** medium
- **Risk flags:** `touches_io_boundary` (writes `.shipwright/triage.jsonl`; reads
  dist-info METADATA / package-lock.json; writes `.shipwright/compliance/sbom.md`)
- **Spec impact:** MODIFY (SBOM triage producer + SBOM doc semantics; supersedes
  the ADR-056 "no-venv → undeclared → triage" model for the not-installed case)

## Problem

The SBOM license resolver (`detect_python_license` / `detect_npm_license`)
returns `"unknown"` in **two conflated** cases:

1. **Fall 1 — not installed:** no `.venv` dist-info / no lockfile+node_modules
   entry. We never actually looked at the package. This is a property of the
   *local scan environment*, not the repo.
2. **Fall 2 — no declared license:** the package *is* resolvable (dist-info
   present / in lockfile) but ships **no** license metadata.

`collect_undeclared_by_workspace` flags **both** as triage findings, so every
worktree/CI run without a synced venv emits recurring "undeclared license"
noise for well-known permissive packages (pytest, pyyaml, requests, …). This
is the user-reported "4 new SBOM entries" churn. It also makes the committed
`sbom.md` claim "unknown license" for packages it simply didn't scan.

## Goal (user intent)

The SBOM must answer the reader's question — **"is my repo license-sound?"** —
not "what did the scanner do". Surface genuine concerns; stay silent about
scan artifacts.

- **Not installed (Fall 1):** invisible. No triage item. No scary "unknown" in
  the doc. Listed in the inventory with a neutral `—`.
- **No declared license (Fall 2):** the reader **must** know → one clear,
  ecosystem-consolidated triage item + a "Dependencies Without a Declared
  License" doc section.

The fix is in the **producer** (plugin-side) so it works in **every** repo
that uses Shipwright — it keys off the resolution *mechanism* (dist-info
present?), not a hardcoded package list (a static known-license map was
rejected: it can't generalize to an adopted repo's own package set).

## Acceptance Criteria

- [ ] **AC-1** `detect_python_license` returns `NOT_INSTALLED` when no matching
      dist-info exists (no `.venv` or no dir); returns `UNKNOWN_LICENSE` only
      when dist-info **is** present but METADATA declares no license.
- [ ] **AC-2** `detect_npm_license` returns `NOT_INSTALLED` when the package is
      neither in the lockfile nor in `node_modules`; returns `UNKNOWN_LICENSE`
      when it is present (lockfile entry / installed package.json) but no
      license is declared.
- [ ] **AC-3** `collect_undeclared_by_workspace` includes **only** Fall-2
      packages (`license == UNKNOWN_LICENSE`); `NOT_INSTALLED` never produces a
      triage group → `emit_undeclared_triage` appends 0 for a not-installed
      workspace.
- [ ] **AC-4** Genuine Fall-2 packages still trigger the existing per-workspace
      / ecosystem-cluster triage logic unchanged.
- [ ] **AC-5 (doc)** `not-installed` deps render as `—` in the inventory and are
      excluded from `Unique licenses`, the license pie, and any concern count.
- [ ] **AC-6 (doc)** Fall-2 deps appear under `## Dependencies Without a
      Declared License` ("installed but ship no license metadata — verify
      before distribution"). The old "## Unknown Licenses → install &
      regenerate" section is removed.
- [ ] **AC-7 (doc verdict)** License Compliance shows a clear verdict:
      `✅ No license concerns` when no copyleft and no Fall-2 among resolved
      deps; lists concerns otherwise; says "No dependency licenses were
      resolved in this scan." when nothing was resolved (honest, not a false
      all-clear).
- [ ] **AC-8** No scan-coverage / "run uv sync" summary line anywhere.
- [ ] **AC-9** Repo's own 4 open SBOM triage items auto-dismiss on regen
      (their keys leave `current_keys`), leaving 0 open SBOM items.

## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| resolver `license` value (adds `not-installed`) | collector + SBOM doc | in-proc |
| `collect_undeclared_by_workspace` (fewer groups) | `emit_undeclared_triage` | in-proc |
| `emit_undeclared_triage` → `.shipwright/triage.jsonl` | WebUI + audit_detector | jsonl |
| `generate()` → `.shipwright/compliance/sbom.md` | humans / auditors | markdown |

Dedup-key shapes (`sbom:undeclared:` / `sbom:undeclared-cluster:`) are
**unchanged** — no consumer-contract migration.

## Test-Update-Klausel note

This iterate reverses the documented ADR-056 behavior "no-venv → undeclared →
triage" for the not-installed case. Existing tests that seeded *not-installed*
state to simulate "undeclared" are re-pointed to seed genuine Fall-2 state
(installed-but-no-license); `test_python_no_venv_still_emits` is replaced by a
test asserting the new silence. Module docstrings + ADR-056 reference updated
in the same diff (F3 decision drop records the reversal).

## Confidence Calibration
- **Boundaries touched:** triage.jsonl producer; sbom.md doc; in-proc resolver
  contract (python + npm).
- **Empirical probes run:**
  1. Regenerated `.shipwright/compliance/sbom.md` against the real worktree →
     diff confirmed: `Unique licenses 3 (…, unknown)` → `2 (Apache-2.0, MIT)`;
     pie `"unknown":3` slice removed; 3 not-installed runtime deps
     (google-genai 1.0.0, openai 1.0.0, requests 2.31.0) `unknown` → `-`;
     "## Unknown Licenses / install & regenerate" section removed; verdict
     "No license concerns: all resolved dependencies are permissively licensed."
  2. Resolver probes against real on-disk dist-info / lockfiles:
     no-venv/no-distinfo → `not-installed`; distinfo-present-no-license → `unknown`;
     no-lockfile+no-node_modules → `not-installed`; lockfile-present-no-license →
     `unknown` (test_sbom_not_installed.py, 16 tests).
  3. Artifact is ASCII-only (cp1252-default tooling); no `✅`/`—` leak.
- **Test Completeness Ledger:** AC-1 → TestPythonResolverDistinction (4);
  AC-2 → TestNpmResolverDistinction (4); AC-3 → TestCollectorSilence (3) +
  test_python_not_installed_is_silent; AC-4 → existing TestEmitUndeclaredTriage*
  re-seeded to Fall 2 (all green); AC-5/6/7/8 → TestDocSemantics (5) +
  test_not_installed_deps_are_silent_in_doc + test_no_copyleft. AC-9
  (repo's 4 items auto-dismiss) → covered by existing auto-resolve tests; fires
  on next compliance regen (not-installed leaves `current_keys`). No
  testable-but-untested behavior.
- **Confidence-pattern check:** depth = sentinel returned in BOTH not-installed
  paths per ecosystem (py: no-venv + no-distinfo; npm: no-lockfile +
  no-node_modules); breadth = resolver + collector silence + doc rendering +
  verdict (3 states) + idempotent auto-dismiss. Full compliance suite 636 pass,
  integration 141 pass, ruff clean.
