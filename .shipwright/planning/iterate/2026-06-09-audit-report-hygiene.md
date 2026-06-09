# Iterate Spec — audit-report hygiene (next producer in the ADR-089 leak class)

- **run_id:** `iterate-2026-06-09-audit-report-hygiene`
- **Intent:** change (framework infra) · **Complexity:** medium (producer output-path
  change + gitignore canon propagation to every adopted repo + `touches_io_boundary`
  JSON write).
- **Risk flags:** `touches_io_boundary` (JSON report write). → Boundary Probe + round-trip +
  Confidence Calibration.
- **Spec Impact:** NONE (framework producer behaviour; no product FR) → event `change_type=infra`.
- **Follow-up to:** `iterate-2026-06-09-idle-main-artifact-hygiene` (PR #173) — same
  producer-leak class, different producer (the compliance detective audit). Surfaced during
  the idle-main clean-state review.

## Problem

`plugins/shipwright-compliance/scripts/audit/audit_report.py::write` (driven by
`run_audit.py` / `/shipwright-compliance`, default `--format both`) writes two generated,
transient detective-audit artifacts:

- `shipwright_audit_report.json` — to the **repo ROOT** → leaks as `??` in every repo
  (framework + every adopted repo). Root-anchored, so the `.shipwright/`-scoped gitignore
  canon cannot cover it.
- `.shipwright/compliance/audit-report.md` — under the re-included `compliance/` home →
  tracked-eligible → leaks too.

Neither is in `audit_staleness.DOC_REGISTRY` (not a tracked-durable doc). Both regenerate
each audit run. The framework-local idle-main-artifact-hygiene iterate only gitignored the
root json **framework-locally** (PR #173 housekeeping); adopted repos still leak both.

## Decision (evidence-based, ADR-089 "transient ⇒ gitignored path")

- **`.md`:** stays at `.shipwright/compliance/audit-report.md` (many `group_*.py` reference
  that path) → just **re-exclude** it in the gitignore canon. Non-breaking (path unchanged;
  the file stays on disk for readers, now gitignored).
- **`.json`:** **relocate** root → `.shipwright/compliance/audit-report.json` (beside the
  `.md`) so the `.shipwright/`-scoped canon CAN re-exclude it → propagates to adopted repos.
  Safe: the canonical contract is **stdout** (`run_audit` prints the JSON payload; code
  comment: "stdout always carries the JSON payload so automated callers have a stable
  contract"). No machine-consumer reads the root FILE — only the writer, `run_audit`'s
  `written` dict (uses `relative_to`, auto-follows), `SKILL.md` (doc), and one test.
- **Canon:** re-exclude BOTH under `.shipwright/compliance/` in the template + framework
  managed block (congruent) → adopt + `gitignore_selfheal` carry it to adopted repos.
- **Cleanup:** drop the now-obsolete framework-local root `shipwright_audit_report.json`
  ignore line (added in PR #173 housekeeping); remove the stale root file from main post-merge.

## Acceptance criteria

- AC-1: `write` writes the json to `.shipwright/compliance/audit-report.json`; the root file
  is no longer produced. stdout JSON contract preserved.
- AC-2: canon re-excludes `audit-report.md` + `audit-report.json` under
  `.shipwright/compliance/` (template + framework, congruent) → propagates to adopted repos.
- AC-3: obsolete framework-local root ignore line removed.
- AC-4: empirical test — after a real `write(report, repo)` in a tmp git repo with the canon
  `.gitignore`, `git status --porcelain -uall` shows neither audit artifact; path/round-trip
  assertions; congruence intact.
- AC-5: docs — `SKILL.md`, guide, hooks-and-pipeline artifact-write matrix.

## Out of scope
- The `.md` consumer `group_*.py` paths (unchanged). No new audit-content behaviour.

## Confidence Calibration

- **Boundaries touched:** `audit_report.write` JSON output path; gitignore canon
  (template + framework managed block + congruence); `run_audit` `written` dict (uses
  `relative_to` → auto-follows) + stdout JSON contract (unchanged); SKILL.md + guide +
  hooks-and-pipeline doc references; `test_audit_report` path assertion.
- **Empirical probes run (real git repo, real `write()`, no mocks):**
  - `write()` in a tmp git repo with the canon `.gitignore` → `git status --porcelain -uall`
    shows NEITHER `audit-report.md` nor `audit-report.json` nor a root json. ✔ (Would FAIL
    pre-relocation: root json escapes the `.shipwright/`-scoped canon.)
  - Path round-trip: `write()` returns `paths["json"] == .shipwright/compliance/audit-report.json`,
    the file parses, and the ROOT file is NOT produced. ✔
  - Congruence: template ⇄ framework managed block still byte-congruent with both new
    re-excludes. ✔ · canon-path lint green · compliance plugin suite 654 green.
- **Test Completeness Ledger** (testable ⇒ tested; 0 testable-but-untested):

  | # | Behavior (AC) | Disposition | Evidence |
  |---|---|---|---|
  | 1 | json written to `.shipwright/compliance/audit-report.json` (AC-1) | tested | `test_write_creates_both_artifacts` |
  | 2 | root `shipwright_audit_report.json` no longer produced (AC-1) | tested | `test_write_creates_both_artifacts` (assert-not-exists) |
  | 3 | `--format` flags still respected (regression) | tested | `test_write_respects_format_flags` |
  | 4 | both artifacts gitignored under canon — git-status-clean, propagates (AC-2/AC-4) | tested | `test_audit_artifacts_gitignored_under_canon` (real git + `-uall`) |
  | 5 | template ⇄ framework congruent with the 2 re-excludes (AC-2/AC-3) | tested | `test_gitignore_template_congruent` |
  | 6 | stdout JSON payload unchanged (AC-1 contract) | tested | existing run_audit e2e CLI tests (`covered-by-existing-test`; stdout path untouched) |

  AC-3's removal of the now-dead framework-local root ignore line is dead-config cleanup,
  not a separate testable behavior — its net effect (no root json leak) is behavior #2/#4.
- **Confidence-pattern check:**
  - *Asymptote (depth):* relocation chosen over a root-pattern canon hack because the
    `.shipwright/`-scoped canon can only propagate ignores under `.shipwright/`; verified no
    machine-consumer reads the ROOT file (only stdout, the documented contract) before
    moving it — proven by grep of all consumers, not assumed.
  - *Coverage (breadth):* both artifacts (.md re-excluded in place + .json relocated); both
    canon files (congruent); all consumers (writer, run_audit comment, SKILL, guide,
    hooks-and-pipeline, test); regression (format flags, full compliance suite). The `.md`
    path is unchanged so `group_*.py` consumers are unaffected.
