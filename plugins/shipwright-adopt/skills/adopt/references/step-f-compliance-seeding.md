# Step F — Compliance Seeding

Run:

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/tools/seed_adopt_compliance.py" \
  --project-root <cwd>
```

Calls `update_compliance.py` for each retroactive phase (`project`,
`plan`, `build`, `test`). Falls back to direct-lib imports if the script
cannot be located. Populates `.shipwright/compliance/sbom.md`,
`.shipwright/compliance/change-history.md`, `.shipwright/compliance/traceability-matrix.md`,
`.shipwright/compliance/test-evidence.md`, `.shipwright/compliance/dashboard.md`.
