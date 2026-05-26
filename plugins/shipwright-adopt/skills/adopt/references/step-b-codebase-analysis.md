# Step B — Codebase Analysis (Layer 1)

Run:

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/tools/analyze_codebase.py" \
  --project-root <cwd> \
  [--exclude-path <p>]... \
  [--profile-hint <name>] \
  --output <cwd>/.shipwright/adopt/snapshot.json
```

This writes the structured snapshot with stack, profile-match,
conventions, CI, test frameworks, folder layers, features (AST), git
summary, nested projects. Pure read-only.

See [codebase-analysis.md](codebase-analysis.md) for detector
heuristics and edge cases.
