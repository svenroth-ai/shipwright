# Section State Update (Step 10)

Detail for Kern Step 10. Marks the section complete in config with test results and review findings, records the event, then runs the canon-hybrid finalization (per section vs once per split-completion).

## Update Section State

```bash
uv run "{plugin_root}/scripts/tools/update_section_state.py" \
  --section "{section_name}" \
  --status "complete" \
  --commit "$(git rev-parse HEAD)" \
  --tests-passed {tests_passed} \
  --tests-total {tests_total} \
  --review-findings '{review_findings_json}' \
  --review-type "{review_type}"
```

Where:

- `{tests_passed}` / `{tests_total}` — from the last test run (Step 4)
- `{review_findings_json}` — JSON array of findings from code review (Step 6), e.g. `[{"finding": "Missing validation", "status": "fixed"}]`. Use `[]` if no findings.
- `{review_type}` — `"full-review"` if Step 6b (full code review) was triggered, `"self-review"` if only Step 6a (self-review checklist) was performed

## Record Event in Unified Event Log

> **CRITICAL:** Call `record_event.py` immediately after each section completes. Do NOT batch multiple sections in a loop with `--deduplicate-by-commit` using the same commit hash — dedup checks (section, commit) but batching with identical commits from a different context will collapse events. Each section has its own commit from Step 8.

```bash
uv run "{shared_root}/scripts/tools/record_event.py" \
  --project-root "$(pwd)" \
  --type work_completed --source build \
  --split "{current_split}" --section "{section_name}" \
  --commit "$(git rev-parse HEAD)" \
  --tests-passed {tests_passed} --tests-total {tests_total} \
  --review-type "{review_type}" \
  --review-findings {review_findings_count} --review-fixed {review_fixed_count} \
  --affected-frs "{comma_separated_FRs}" \
  --deduplicate-by-commit
```

Where `{comma_separated_FRs}` is the list of FRs from the section spec that this section implements (e.g. `"FR-01.01,FR-01.02"`). If the section spec does not reference specific FRs, use the split-level FR range. Omit `--review-findings` and `--review-fixed` if no review was performed (self-review with 0 findings).

**Dashboard update:**

```bash
uv run "{shared_root}/scripts/tools/update_build_dashboard.py" \
  --project-root "$(pwd)" --section "{section_name}" --step 10 --status complete --session-id "{SHIPWRIGHT_SESSION_ID}"
```

## Check Phase-Complete Trigger

```bash
uv run "{plugin_root}/../../plugins/shipwright-run/scripts/lib/orchestrator.py" \
  get-build-progress --project-root "$(pwd)"
```

> **Iterate 12.3 canon hybrid.** C1 (`record_event`), C2
> (`update_build_dashboard`) and C4 (`write_decision_log`) run **per
> section** (above); C3 (canon-marker session_handoff) + C5
> (`append_changelog_entry` one bullet per completed section) +
> `phase_history` append run **once per split completion**, below.
> Per-section C3/C5 would spam the handoff and create partial CHANGELOG
> entries mid-split. Both split-done branches share the same canon
> closure below.

## Split-Level Canon Finalization

If `split_done == true` (either final split or split-loop), run the
**split-level canon finalization** BEFORE the branch-specific work:

```bash
# Set SHIPWRIGHT_RUN_ID for this split's build run if not already set.
# (The orchestrator propagates it when a full pipeline is driving; set
# it manually for standalone /shipwright-build invocations.)
: "${SHIPWRIGHT_RUN_ID:=build-$(date +%Y%m%d-%H%M%S)-{current_split}}"
export SHIPWRIGHT_RUN_ID

# C3 — Canon-marked session handoff (one per split completion).
uv run "{shared_root}/scripts/tools/generate_session_handoff.py" \
  --project-root "$(pwd)" --canon-marker --phase build \
  --reason "build phase complete: {current_split}, {N} sections"

# C5 — Append one CHANGELOG [Unreleased] bullet per completed section
# of the split. The helper dedupes per category, so re-running is safe.
# Category is derived from the conventional commit type of each section
# commit (feat -> Added, refactor -> Changed, fix -> Fixed). In practice,
# iterate the build_config.sections[] with status=complete and match
# the commit message prefix.
for section in {completed_sections_of_current_split}; do
  # Derive category + entry from each section's commit and name.
  commit_type=$(git show --format=%s "{section_commit}" | awk -F: '{print $1}' | awk -F'(' '{print $1}')
  case "$commit_type" in
    feat) category=Added ;;
    fix) category=Fixed ;;
    refactor) category=Changed ;;
    *) category=Added ;;
  esac
  uv run "{shared_root}/scripts/tools/append_changelog_entry.py" \
    --project-root "$(pwd)" \
    --category "$category" \
    --entry "Build: {current_split}/{section_name} complete ({tests_passed}/{tests_total} tests)"
done

# phase_history — audit trail with per-section sub-entries.
# Serialize completed sections from build_config as a JSON array.
sections_json=$(jq -c '{split: .current_split, sections: [.sections[] | select(.status == "complete") | {id: .name, status: .status, commit: .commit, tests_passed: .tests_passed, tests_total: .tests_total}]}' shipwright_build_config.json)
uv run "{shared_root}/scripts/tools/append_phase_history.py" \
  --project-root "$(pwd)" --phase build --run-id "$SHIPWRIGHT_RUN_ID" \
  --entry-json "$sections_json"
```

## Branch-Specific Work

### If split_done == true AND all_done == true (final split complete)

1. **Persist dev_url** — detect dev server port and write to build config for downstream phases:
   - Read `CLAUDE.md` for `PORT=` references
   - Read `package.json` scripts for `--port` flags
   - If found: add `"dev_url": "http://localhost:{port}"` to `shipwright_build_config.json`
2. Mark build phase complete (triggers compliance update automatically).
   `_validate_build()` now runs the modular build_checks verifier:
   per-section C1/C4 iteration, phase-level C2/C3/C5, phase_history,
   `check_build_test_files_exist` (B3) + `check_commit_sha_in_git` (B6)
   preventive checks. Missing artifacts or test-file drift blocks
   this call via ask-level issues.

```bash
uv run "{plugin_root}/../../plugins/shipwright-run/scripts/lib/orchestrator.py" \
  update-step --project-root "$(pwd)" --step build --status complete
```

3. Push feature branch to remote:

```bash
git push -u origin "$(git branch --show-current)"
```

4. Update delivery dashboard with pipeline status:

```bash
uv run "{shared_root}/scripts/tools/update_build_dashboard.py" \
  --project-root "$(pwd)" --phase build --session-id "{SHIPWRIGHT_SESSION_ID}"
```

### If split_done == true AND all_done == false (more splits remain)

1. **Archive completed split** (moves sections to `split_NN_sections`, updates `current_split`):

```bash
uv run "{shared_root}/scripts/tools/archive_split.py" \
  --project-root "$(pwd)" --next-split "{next_split_name}"
```

2. Push feature branch to remote:

```bash
git push -u origin "$(git branch --show-current)"
```

3. Print: "Split {current_split} complete. Archived to split_{prefix}_sections. Continuing to plan + build for next split. Test/changelog/deploy run once after all splits."
4. Update delivery dashboard:

```bash
uv run "{shared_root}/scripts/tools/update_build_dashboard.py" \
  --project-root "$(pwd)" --section "{section_name}" --status complete --session-id "{SHIPWRIGHT_SESSION_ID}"
```

5. **Mark build phase complete** for this split (pipeline continues to test -> changelog -> deploy, then orchestrator loops back to plan for next split):

```bash
uv run "{plugin_root}/../../plugins/shipwright-run/scripts/lib/orchestrator.py" \
  update-step --project-root "$(pwd)" --step build --status complete
```
