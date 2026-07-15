# finalize_bundle — collapse the F1/F3/F4/F5c/F5b LLM round-trips

The finalize phase runs a handful of sub-second tools one at a time. The
wall-clock cost is the **LLM turn-taking** (think → build a command → read output
→ next), not the scripts. `finalize_bundle.py` lets you author all the
finalization content **once** into a JSON payload and invoke the five tools in
**one** turn.

It is a **pure orchestrator**: it writes no artifact itself. Every file is
produced by the same unchanged tool as before (F1 `artifact_sync`, F3
`write_decision_drop`, F4 `write_changelog_drop`, F5c `append_iterate_entry`,
F5b `finalize_iterate`). The bundle only changes how many LLM turns invoke them.

## When to use it

Use it for the normal finalization of a run once F0/F0.5 have passed and you have
done the **manual** steps that stay outside the bundle:

- **F5** — write `shipwright_test_results.json` (incl. the ledger) **BEFORE** the
  bundle, because F5b's compliance regen reads it.
- **F2** (architecture.md bullet) / **F3a** (conventions.md `## Learnings`) — the
  conditional agent-doc bullets; if F2 flags an impact, put the matching value in
  `decision.architecture_impact` in the payload.
- **F6** — the atomic commit + explicit per-path `git add` stays a manual step
  AFTER the bundle.

If you prefer, you can still run the five tools individually per F1/F3/F4/F5c/F5b
— the bundle is an optimization, not a new requirement.

## Two-step workflow (required)

The payload is passed by **file**, never inline, so a large multi-field JSON is
robust against shell quoting:

1. **Write** the payload to a file (e.g. `.shipwright/runs/<run_id>/finalize_payload.json`).
2. **Run** the bundle:

```bash
uv run "{shared_root}/scripts/tools/finalize_bundle.py" \
  --payload-file "{payload_file}" --project-root "{project_root}"
```

`--project-root` is the ONLY source of the project root (the payload carries
none — no precedence ambiguity). It is the iterate **worktree** root.

## Payload schema (strict — unknown top-level keys are rejected)

```json
{
  "run_id": "iterate-YYYY-MM-DD-slug",
  "artifact_sync": { "ref": "HEAD~1..HEAD", "skip": false },
  "decision": {
    "section": "Iterate — <type>: <desc>",
    "title": "…", "context": "…", "decision": "…", "consequences": "…",
    "rationale": "…", "rejected": "…",
    "architecture_impact": "component|data-flow|convention|none",
    "spec_ref": ".shipwright/planning/adr/<NNN>-<slug>.md"
  },
  "changelog": [ { "category": "Added|Changed|Deprecated|Removed|Fixed|Security",
                   "bullet": "… (no leading '- ')" } ],
  "iterate_entry": { "type": "…", "complexity": "…", "branch": "…",
                     "spec": "…", "tests_passed": true, "adr": "<run_id>" },
  "finalize": { "reason": "iterate: <desc>", "event_extras": { … } }
}
```

- **`run_id`** — required, non-empty.
- **`artifact_sync`** — optional. F1 **ALWAYS runs** (default ref `HEAD~1..HEAD`);
  the only bypass is an explicit `"skip": true`, which **bypasses the drift
  gate** — use it only when there is no prior commit to diff against.
- **`decision`** — required. `section/title/context/decision/consequences` are
  required; `rationale/rejected/architecture_impact/spec_ref` are optional and
  omitted from the F3 argv when absent. Field-length budgets (≤500 chars) are
  enforced by the tool itself.
- **`changelog`** — required, non-empty list; one `write_changelog_drop` call per
  bullet.
- **`iterate_entry`** — required object, passed verbatim as F5c `--entry-json`
  (the tool adds `run_id`/`date`).
- **`finalize.event_extras`** — required object, passed verbatim as F5b
  `--event-extras-json`. The **ADR-059 FR-gate still applies**: behavior-affecting
  changes (`spec_impact` add/modify/remove) must be FR-linked (`affected_frs`/
  `new_frs`); behavior-preserving (`spec_impact: none`) uses the No-FR branch
  (`change_type` ∈ docs/tooling/compliance/infra + `none_reason`). Do NOT put
  secrets in `event_extras` — it is forwarded as a child-process argv.

## Order, abort semantics & retry

Dependency order: **F1 → F3 → F4(×N) → F5c → F5b**. F1 first so drift aborts
BEFORE any write; F5b last (it reads the test-results for compliance regen +
records the `work_completed` event).

- **Drift (F1):** detected from the `artifact_sync` stdout `drift_detected` field
  (not the raw exit code). On drift the bundle STOPs with `failed_step: "F1"` —
  update the affected specs, then re-run.
- **Any step fails:** the bundle STOPs, emits exactly ONE JSON document with
  `success: false` + `failed_step: "<F>"` + the tool's captured stderr, and exits
  1. **Fix the cause and re-run the WHOLE bundle** — all five tools are
  idempotent per `run_id` (the two drop-writers dedup on identical
  `(run_id, content)`; F5c / F5b are idempotent by design), so a re-run never
  duplicates an artifact.

**Retry caveats (idempotency is content-keyed, not run-keyed).** The
drop-writers dedup only when the payload content is UNCHANGED across the retry.
If a retry ALSO edits the `decision` or a `changelog` bullet, the superseded
first-run drop is **not** removed — both survive and aggregate as separate
entries at release. So on a retry, change ONLY the section that failed (usually
`finalize.event_extras`), not the ADR / changelog text. Two more inherited
finalize_iterate/append_iterate_entry behaviours: (a) once a `work_completed`
event exists for the `run_id`, a retry does **not** overwrite it — a corrected
`event_extras` classification is NOT re-applied (patch/delete the event manually
if you must change it after it recorded); (b) the F5c iterate-entry is idempotent
by file-identity (one file per `run_id`), not by bytes — a retry rewrites it with
a fresh `date`, which is expected and unchecked downstream.

**F5 precondition (not enforced).** The bundle does NOT verify that F5
(`shipwright_test_results.json`) was written first — do it before the bundle so
F5b's compliance regen reads it. finalize_iterate treats compliance regen as
best-effort (it re-runs at F11 / on Stop), so a skipped regen does not fail the
bundle; its status is surfaced under `steps.F5b.finalize_steps` (the
`finalize_steps.compliance` entry reads `skipped`) so it is visible rather than
buried.
- **Exit codes:** `0` every step ok · `1` a step aborted · `2` the payload could
  not be read / parsed / validated (no subprocess ran).

## Result shape

```json
{
  "success": true, "run_id": "…", "failed_step": null,
  "steps": {
    "F1":  { "status": "ok|drift|failed|skipped", "returncode": 0, "stdout": "…", "stderr": "…" },
    "F3":  { "status": "ok|failed", "returncode": 0, "stdout": "…", "stderr": "…" },
    "F4":  { "status": "ok|failed", "drops": [ { "category": "…", "bullet": "…", "status": "ok" } ] },
    "F5c": { "status": "ok|failed", "…": "…" },
    "F5b": { "status": "ok|failed", "…": "…" }
  }
}
```

After a successful bundle, proceed to **F6** (stage the artifacts with the
explicit per-path `git add` list — see [F6](F6.md) — and commit).
