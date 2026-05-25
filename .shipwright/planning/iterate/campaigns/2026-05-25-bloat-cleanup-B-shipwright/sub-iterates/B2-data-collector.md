# Sub-Iterate B2 — Split data_collector.py (1559 LOC)

> Part of campaign `2026-05-25-bloat-cleanup-B-shipwright`. Read
> `.shipwright/planning/iterate/campaigns/2026-05-25-bloat-cleanup-B-shipwright/campaign.md`
> for the campaign-level intent and dependency topology.

            ## Context

            `plugins/shipwright-compliance/scripts/lib/data_collector.py` is `1559` LOC — well above the
            300-LOC source budget. The file mixes multiple concerns
            that can be cleanly separated (see split layout below).

            ## Scope

            Split `plugins/shipwright-compliance/scripts/lib/data_collector.py` into the layout below, preserving
            the public import surface so existing callers don't
            break.

            ```
            plugins/shipwright-compliance/scripts/lib/data_collector.py  (DELETE or shim <= 50 LOC)
plugins/shipwright-compliance/scripts/lib/collectors/
    __init__.py            # re-exports collect_all + public types
    _common.py             # shared helpers (paths, json io)
    rtm.py                 # RTM collector
    test_evidence.py       # test evidence collector
    change_history.py      # change history collector
    sbom.py                # SBOM collector
    dashboard.py           # dashboard collector

            ```

            ## Acceptance Criteria

            - [ ] Each new module is <= 300 LOC.
            - [ ] `plugins/shipwright-compliance/scripts/lib/data_collector.py` is either:
              - (a) reduced to a thin re-export shim <= 50 LOC, OR
              - (b) deleted and replaced by a package directory whose
                `__init__.py` re-exports the public surface.
            - [ ] `shipwright_bloat_baseline.json` entry for
              `plugins/shipwright-compliance/scripts/lib/data_collector.py` is REMOVED in the same commit.
            - [ ] All existing callers of the public API work
              unchanged — verified by running the relevant test suite
              and at least one integration probe.
            - [ ] `collectors/__init__.py` exports `collect_all` with
  an unchanged signature.
- [ ] `/shipwright-compliance` integration probe
  regenerates the RTM + dashboard MDs byte-identically
  (or with explicitly-documented intentional differences).
- [ ] `plugins/shipwright-compliance/tests/test_data_collector.py`
  is updated to import from the new layout (test file
  path may stay; if the test file would still be > 300 LOC
  after the split, the iterate is allowed to refactor it
  into `tests/test_collectors/`).

            ## CLEANUP-INVARIANT (inherited from campaign — do NOT skip)

The same commit that splits the target file MUST update
`shipwright_bloat_baseline.json` per one of these rules:

- **(a) Path still exists post-split, now <= limit** (e.g. Kern
  SKILL.md is a thin shell pointing at `references/F*.md`) ->
  **REMOVE** the entry from `entries`.
- **(b) Path is deleted by the split** (replaced by a package
  directory whose `__init__.py` re-exports the public surface) ->
  **REMOVE** the entry from `entries`.
- **(c) Path still exists AND is still > limit** -> **FAIL** the
  iterate. Do NOT merge. Refactor further until (a) or (b) applies.

For every NEW submodule produced by this split:

- `.py` / `.ts` / `.tsx` source <= **300 LOC**.
- `references/*.md` runtime prompts loaded by a SKILL.md
  <= **400 LOC**.
- If a new file would exceed its limit at commit time -> split it
  further BEFORE committing. **Never add a fresh grandfathered
  entry to the baseline.**

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

            - Identify cohesive sub-surfaces in the original file
              (read it fully first). Group related functions into
              the same submodule.
            - Use `from .submodule import public_name` re-exports in
              `__init__.py` to preserve the import surface.
            - If the file already has `if __name__ == "__main__":` /
              CLI entry, keep it functional after the split.
            - Type hints + docstrings travel with the function they
              describe.

            ## Stacking Base

            Base branch for this sub-iterate: `B8`'s post-merge `main` (stacked).
