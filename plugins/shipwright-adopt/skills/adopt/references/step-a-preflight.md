# Step A — Pre-flight (and Step A.0 — Bloat Baseline)

## Step A.0 — Bloat Baseline (must run first)

Before any other artifact write, generate the bloat allowlist so the
Stop-Gate hook (`bloat_gate_on_stop.py`) has something to compare
against on the first Stop event of the Adopt session. Without this
the gate falls back to "pass silently" (AC-7) and offers no protection
for the rest of Adopt's onboarding writes.

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/lib/baseline_generator.py" \
  --project-root <cwd>
```

Writes `<cwd>/shipwright_bloat_baseline.json` with all current
over-limit files as `state=grandfathered`. Idempotent — re-runs
overwrite atomically.

## Step A — Pre-flight

Run:

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/checks/setup_adopt.py" \
  --project-root <cwd> \
  [--exclude-path <p>]...
```

The script emits JSON with `ok`, `hard_stops`, `warnings`,
`nested_projects`, and `existing_artifacts`. If `ok=false`, **halt and
show the reason** — no further steps. If `nested_projects` is non-empty,
**ask the user** via `AskUserQuestion` for each one: include / exclude /
adopt separately. Default recommendation: `Exclude`.

If `existing_artifacts` is non-empty, **show the list** to the user and
**ask** via `AskUserQuestion`:

> "Found N existing artifacts that adopt would touch:
>   • CLAUDE.md
>   • .shipwright/agent_docs/decision_log.md (will be auto-merged with new ADRs)
>   • .shipwright/agent_docs/architecture.md (will be backed up + overwritten)
>   • ...
>
> Adopt automatically backs each one up to .shipwright/adopt/backups/
> before any write. Load-bearing CLAUDE.md (>1 KB) is preserved untouched
> and adopt's suggested content is written to .shipwright/adopt/CLAUDE.md.adopt-suggested.
> Continue?"

Default recommendation: `Continue` (preservation is on by default; the
user can review every change via the `.preserved` files afterward).
