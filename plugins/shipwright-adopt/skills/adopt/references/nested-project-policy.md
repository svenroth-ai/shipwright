# Nested-Project Policy

Adopt detects sub-directories that look like independent projects and
asks the user how to handle them. The canonical case in this monorepo
is `webui/` — an embedded Shipwright sub-project with its own
`shipwright_run_config.json`, its own `CLAUDE.md`, its own
`.shipwright/agent_docs/`, and its own pipeline state.

## Detection markers

A directory is flagged as a nested project if it has **any** of:

- A `.git/` directory (git submodule or separate clone)
- A `shipwright_run_config.json` (separate Shipwright pipeline state)
- Both `CLAUDE.md` and `.shipwright/agent_docs/` (has own Shipwright artifacts)
- A `package.json` AND one of the above (workspace inside a larger
  project)

Directories on the global ignore list (`node_modules`, `dist`,
`.venv`, etc.) are never flagged.

## User prompt

For each detected nested project, Adopt asks:

```
Found nested project: <path>
  Markers: <list>
  Status: <reason>

Options:
  • Exclude (recommended — adopt as separate project later)
  • Include (merge the sub-project's state into parent — NOT RECOMMENDED)
  • Adopt separately (exit now, re-run /shipwright-adopt from within <path>)
```

**Default recommendation: Exclude.** Merging sub-project state would
mix pipelines and typically produces undefined behavior.

## Effect of Exclude

When a nested project is excluded:

1. All Layer-1 detectors receive the exclude path and skip matching
   content underneath it.
2. The crawler (`route_crawler.py`) starts from the parent's dev-server
   only — sub-project routes are not discoverable unless the parent
   includes them.
3. `shipwright_run_config.json.adoption.nested_excluded` records the
   excluded paths for future audit.
4. The sub-project's existing `shipwright_*_config.json` files are
   **not modified** — they remain intact for the sub-project's own
   `/shipwright-iterate` sessions.

## Effect of Include (not recommended)

Adopt **still respects the sub-project's own Shipwright artifacts** —
it does not overwrite `webui/shipwright_run_config.json` or similar.
What it does:

- The stack detector merges manifests from the nested dir into the
  parent signature (possibly polluting profile match).
- The folder introspector counts the nested LOC in parent layers.
- The crawler attempts to cover both apps (may confuse).

This mode exists for monorepos where the "nested" marker was a
false-positive. Use with caution.

## Effect of Adopt separately

The skill exits immediately with a recommendation to `cd <path> &&
/shipwright-adopt`. No artifacts are written to the parent.
