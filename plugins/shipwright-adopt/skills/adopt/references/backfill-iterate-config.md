# Backfilling `shipwright_iterate_config.json` on already-adopted projects

Projects adopted before 2026-05-05 ship without
`shipwright_iterate_config.json`. To backfill:

```bash
uv run python -c "
from pathlib import Path
import sys
sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
from lib.config_writer import write_iterate_config
write_iterate_config(Path('.'))
"
```

This writes the config with the documented defaults
(`external_review.feedback_iterations: 1`,
`external_code_review.enabled: true`). Both fields are operator opt-out
knobs — flip after the file exists, no re-adopt needed. The framework
ignores the file's absence (defaults stay in effect), so this is purely
about giving the operator a flat surface to edit.
