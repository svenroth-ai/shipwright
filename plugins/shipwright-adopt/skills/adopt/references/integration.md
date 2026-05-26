# Integration

- **Phase-Quality audit**: Adopt registers as phase `adopt` in
  `shared/scripts/lib/phase_quality.py` (`PLUGIN_TO_PHASE`, `C4_PHASES`,
  `_WORKFLOW_PHASE_DISPATCH`). `shared/scripts/tools/verifiers/adopt_compliance.py`
  runs A1–A8 canon checks on every Stop hook.
- **Cross-plugin docs**: `plugins/shipwright-project/skills/project/SKILL.md`
  Step A.1 points users to /shipwright-adopt when code already exists.
- **Marketplace**: this plugin is registered in `scripts/update-marketplace.sh`
  so it lands in `~/.claude/plugins/cache/shipwright/` after sync.
