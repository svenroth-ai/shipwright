# Sub-Iterate B8 — shared/contracts/* + adopt-bridge + test-boundary refactor

> Part of campaign `2026-05-25-bloat-cleanup-B-shipwright`. Read
> `.shipwright/planning/iterate/campaigns/2026-05-25-bloat-cleanup-B-shipwright/campaign.md`
> for the campaign-level intent and dependency topology.

        ## Context

        Two existing callsites currently reach across plugin
        boundaries through subprocess + ancestor-path-walk:

        1. `plugins/shipwright-adopt/scripts/lib/compliance_bridge.py`
           — spawns the compliance plugin via subprocess and walks
           parent directories to find it.
        2. `plugins/shipwright-test/scripts/tools/boundary_coverage_report.py`
           — uses a `_ITERATE_LIB` path constant computed by walking
           ancestors to import the iterate library.

        Both patterns are fragile (path layout coupling) and slow
        (subprocess spawn). This sub-iterate introduces stable
        contracts in `shared/contracts/` that both callsites import
        directly.

        ## Scope

        1. Create `shared/contracts/compliance.py` with the public
           surface compliance currently exposes (top of the surface:
           `collect_all`, `CollectorResult`, `CollectorConfig`, etc.).
        2. Create `shared/contracts/iterate.py` with the public
           surface iterate exposes that other plugins consume (top of
           the surface: `is_io_boundary_change`, `iterate_state`,
           `boundary_coverage`).
        3. Update `compliance_bridge.py` to import from
           `shared.contracts.compliance` directly.
        4. Update `boundary_coverage_report.py` to import from
           `shared.contracts.iterate` directly.
        5. Add an integration test that exercises both consumer paths
           against the contracts (real import, real call).

        ## Acceptance Criteria

        - [ ] `shared/contracts/compliance.py` <= 300 LOC; public
          surface unchanged from what compliance currently exposes.
        - [ ] `shared/contracts/iterate.py` <= 300 LOC; public
          surface unchanged from what iterate currently exposes.
        - [ ] `compliance_bridge.py` no longer spawns a subprocess
          and no longer walks ancestor directories.
        - [ ] `boundary_coverage_report.py` no longer uses
          `_ITERATE_LIB` path-ref; imports directly from
          `shared.contracts.iterate`.
        - [ ] `plugins/shipwright-adopt/tests/` green.
        - [ ] `plugins/shipwright-test/tests/` green.
        - [ ] `plugins/shipwright-compliance/tests/` green.
        - [ ] New integration test
          `integration-tests/test_shared_contracts_consumers.py`
          drives both consumer paths against the contracts end-to-end.

        > **Baseline:** This sub-iterate does NOT remove an entry from
        > the baseline (no file is over the limit to begin with). It
        > also MUST NOT add new oversize entries — every new file
        > stays <= 300 LOC.

        ## Empirical-Verification Mandate (user-set, no exceptions)

F0.5 surface verification MUST be empirical, not spec-only. This
iterate is classified medium+ and the user has explicitly
mandated rigorous empirical checks before merge. Concretely:

1. **Author AND run** the surface runner. `tests_run > 0` is
   required by `surface_verification.py` — a `--grep` mismatch
   returning exit 0 counts as failure.
2. **Round-trip probes** for every Affected Boundary the split
   touches (e.g. SKILL.md producer/consumer of section headings
   between Kern and references, Python public-API import surface,
   baseline.json producer/consumer between pre-commit hook and
   Stop-gate).
3. **Parity probe** (B1 only — see runner overrides) — invoke the
   affected `/shipwright-<X>` skill against a known fixture flow
   and compare behaviour pre/post-split. Any drift -> ROLLBACK.
4. **No `surface=none`** unless there is no startable surface AND
   a one-line justification is filed in the iterate ADR. The
   autonomous loop will reject `surface=none` without it.

Spec-only authorship counts as no test and fails F0.5.

        ## CI Gate (campaign-level — orchestrator enforces)

After the PR opens, the orchestrator polls `gh pr checks <number>`
until ALL of the following are green:

1. Pre-commit hook (local, fires at commit time)
2. CI bloat-check workflow (`anti-ratchet` check on the PR)
3. Plugin / shared test suites that the iterate touched
4. Constitution-gate (Phase-Quality Stop hook output captured in CI)

Only after all four are green does the orchestrator invoke
`gh pr merge --squash --delete-branch`. If any check is red, the
orchestrator pings the runner to remediate and re-push BEFORE
proceeding.

        ## Runner Overrides (campaign-specific)

These override the sub-iterate-runner contract
(`plugins/shipwright-iterate/agents/sub-iterate-runner.md`) for
this campaign:

1. **DO push to origin and open a PR.** The campaign auto-merge
   policy requires per-sub-iterate PRs that the orchestrator
   polls + merges via `gh pr merge --squash --delete-branch`. The
   runner SHALL execute `git push -u origin {branch_name}` and
   `gh pr create --base {base_branch} --head {branch_name}` as
   the final step before writing `result.json`.
2. **Result-JSON MUST contain `pr_url` + `pr_number`** so the
   orchestrator can drive the merge gate.
3. **DO NOT amend prior commits.** Each sub-iterate produces one
   or more conventional commits on its own branch.
4. **Branch base:** `{base_branch}` (supplied by the
   orchestrator; first unit in the stack uses `origin/main`).
5. **Baseline update is part of the same atomic commit as the
   split** — see CLEANUP-INVARIANT above.


        ## Implementation Notes

        - The contracts are PUBLIC — once committed they are part of
          the cross-plugin API. Add type hints and docstrings.
        - Re-exports from `shared/contracts/__init__.py` make
          downstream imports nicer (`from shared.contracts import
          compliance`). Add an `__init__.py` if missing.
        - Keep the contract files small and surface-only. Logic
          stays in the source plugins; contracts are typed
          re-export facades.

        ## Stacking Base

        Base branch for this sub-iterate: `B1.plan`'s post-merge `main`.
