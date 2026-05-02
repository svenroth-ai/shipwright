# Mini-Plan: compliance-group-a5

- **Run ID:** iterate-20260501-compliance-group-a5
- **Iterate spec:** `.shipwright/planning/iterate/2026-05-01-compliance-group-a5.md`

## Approach

Author a self-contained `group_a5.py` module that consumes the
convention-lock constants via `audit_adapters.load_shared_lib(
"security_workflow")`. Each sub-check (A5.1–A5.7) is a function returning
`(status, detail, evidence)`. Top-level `run()` wraps every sub-check in
try/except and emits a single `fail` Finding per crashed check, mirroring
Group A's crash-isolation contract.

YAML parsing uses PyYAML directly (stdlib-level — already a compliance-
plugin dep). The dormant-trigger contract is enforced by line-walk
(checking commented-out `pull_request:` / `schedule:` keys), because
PyYAML drops comments. The `permissions:`, gate-step-id, SARIF category,
and fork-PR guard are inspected via parsed structure.

## Files to change

| File | Action | Purpose |
| --- | --- | --- |
| `plugins/shipwright-compliance/scripts/audit/group_a5.py` | NEW | A5 sub-checks + run() |
| `plugins/shipwright-compliance/scripts/audit/_registry.py` | EDIT | register `group_a5.run` on letter "A" after `group_a.run` |
| `plugins/shipwright-compliance/scripts/audit/audit_detector.py` | EDIT | add `a5_*` override keys to `_DEFAULT_CONFIG` |
| `plugins/shipwright-compliance/skills/compliance/SKILL.md` | EDIT | add A5 to the group bullet, drop "follow-up: Group A5" paragraph |
| `plugins/shipwright-compliance/tests/test_audit_group_a5.py` | NEW | TDD tests for every AC |

## Test strategy

- **Hermetic fixtures.** Every test builds a synthetic
  `.github/workflows/security.yml` under `tmp_path`. No network, no
  reads outside the tmp dir. Mirrors the existing
  `test_audit_groups_a_d.py` pattern.
- **Coverage** — at minimum one happy-path test per AC plus one
  negative test that proves the failure surfaces (HIGH/MEDIUM/LOW
  severity assertion + `detail` substring assertion):
  - A5.1: skip when file absent
  - A5.2: fail when YAML is malformed
  - A5.3: fail when `security-events: write` missing; pass when extra
    optional permissions present
  - A5.4: fail when no step carries the gate id; pass when present
    in any job's steps
  - A5.5: fail when SARIF category mismatched / upload step absent
  - A5.6: pass when triggers commented; fail when active `pull_request:`
    is present; fail when `workflow_dispatch:` missing
  - A5.7: fail when no fork-guard `if:` on the upload step
  - A5.8: every Finding has `source=detective-only` and `group="A"`
  - A5.9: crash inside one sub-check produces a fail Finding without
    suppressing the others (use a monkeypatched `_check_a5_*` that
    raises)
- **End-to-end** — extend the existing
  `test_registry_wires_a_and_d_via_run_all` test (or add a peer test) to
  assert that `register_all()` registers an A5-aware Group A entry.
  The simplest contract: A5 findings merge into letter "A" via a single
  registry entry that calls both `group_a.run` and `group_a5.run`.
- **Real-template happy path.** One test feeds the actual
  `shared/templates/github-actions/security.yml.template` (read from the
  monorepo) into A5 and asserts every sub-check passes. Pins the
  template ↔ A5 contract in lockstep with the existing
  `test_security_workflow_convention.py` drift test.

## Smoke run plan

After tests are green and finalize commits, run
`/shipwright-compliance` against three target projects:

1. **shipwright monorepo** — has its own
   `.github/workflows/security.yml`. A5 should surface the
   missing-`id` drift on the Critical-Findings step (line 140) as
   `A5.4 fail`. Other A5 sub-checks should pass (permissions,
   SARIF category, dormant triggers, fork guard).
2. **shipwright-webui (adopted)** — security.yml scaffolded by
   `/shipwright-adopt`. All A5 sub-checks should pass (the template
   was authored in lockstep with the convention-lock).
3. **aiportal** — no `.github/workflows/`. A5.1 should `skip` cleanly,
   A5.2..A5.7 should not run (skip-on-precondition).

If any smoke result diverges from the expected outcomes, document the
divergence in the iterate spec's `Open follow-ups` section and decide
whether it's real drift (track as a follow-up iterate) or an A5 bug
(fix in this iterate before commit).

## Risk assessment

- **No risk flags triggered.** Pure detective check, no production
  surface, no DB / auth / migrations / shared-infra changes.
- **Reviewer focus areas** (for full code review + external review):
  - YAML parsing edge cases — empty `permissions:`, missing `jobs:`,
    `steps:` not a list. Group A's pattern of "yield nothing rather
    than crashing" applies; crash isolation in `run()` is the safety
    net.
  - Dormant-trigger detection — PyYAML drops comments, so we cannot
    distinguish "commented-out `pull_request:`" from "absent
    `pull_request:`" through the parsed structure alone. The line-walk
    in `test_security_workflow_convention.TestDormantTriggers` is the
    canonical pattern; reuse it.
  - Convention-lock consumption — never re-declare gate id /
    permissions / SARIF category as literals in `group_a5.py`. Always
    pull from the loaded shared module so future template changes
    propagate without touching the audit code.
