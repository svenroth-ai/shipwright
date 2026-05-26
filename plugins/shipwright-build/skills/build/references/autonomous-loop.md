# Autonomous Section Loop

When invoked with `--autonomous` flag (or when `/shipwright-run` dispatches in `autonomy: autonomous` mode), build all pending sections sequentially without manual gates.

**Flag:** `/shipwright-build --autonomous` or `/shipwright-build --from 02 --autonomous`

**Pre-requisites:** `shipwright_build_config.json` must exist with at least one pending section.

## Loop Procedure

1. **Export env vars** before the loop:

```bash
export SHIPWRIGHT_ROOT_SESSION_ID="${SHIPWRIGHT_SESSION_ID}"
export SHIPWRIGHT_LOOP_ID=""  # set after init
```

2. **Initialize loop state:**

```bash
uv run "{shared_root}/scripts/lib/autonomous_loop.py" init \
  --state .shipwright/loop_state.json \
  --kind section \
  --units-from shipwright_build_config.json \
  --branch-strategy single-branch \
  --root-session-id "$SHIPWRIGHT_ROOT_SESSION_ID"
```

Parse stdout JSON: extract `loop_id`. Then: `export SHIPWRIGHT_LOOP_ID="{loop_id}"`.

3. **Loop (repeat until exit code 2):**

```
3a. Pick next unit:
    uv run ... next --state .shipwright/loop_state.json
    -> exit 2 = all done -> go to step 4
    -> Parse JSON: id, spec_path, attempt, loop_id

3b. Export unit env:
    export SHIPWRIGHT_LOOP_UNIT_ID="{id}"

3c. Spawn section-builder subagent:
    result = Task(subagent_type="section-builder", prompt=<brief with section_file, project_root, etc.>)

3d. Wait for terminal marker (max 30s):
    Wait until .shipwright/runs/{loop_id}/{id}/DONE exists

3e. Parse result JSON defensively:
    Try json.loads(result). If fail -> read .shipwright/runs/{loop_id}/{id}/result.json as fallback.

3f. Record result:
    uv run ... record --state .shipwright/loop_state.json --unit {id} --result '{json}'
    -> exit 3 = failure or contract violation -> go to step 4 (strict-stop)

3g. Continue loop (go to 3a)
```

4. **Finalize:**

```bash
uv run ... finalize --state .shipwright/loop_state.json
```

Print summary. If all complete: *"All sections complete. Run /shipwright-changelog to create PR."*
If any failed: print failure details and aggregated handoff path.

**When NOT using `--autonomous`:** skip this section entirely, proceed to Kern Step 12 (manual next-section prompt).
