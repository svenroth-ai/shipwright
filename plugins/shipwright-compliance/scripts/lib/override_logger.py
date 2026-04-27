"""Log compliance overrides when user says "Continue anyway".

Writes to {project_root}/.shipwright/agent_docs/compliance_overrides.log.
The compliance plugin reads this file during report generation
to document which enforcement checks were overridden.

Format:
    [ISO-Timestamp] OVERRIDE hook=<name> reason="<user reason>" details={...}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def log_override(
    project_root: str | Path,
    hook_name: str,
    reason: str,
    details: dict[str, Any] | None = None,
) -> Path:
    """Append an override entry to compliance_overrides.log.

    Args:
        project_root: Target project root directory.
        hook_name: Name of the hook that was overridden.
        reason: User-provided reason or "User confirmed continue".
        details: Structured details from the hook's block output.

    Returns:
        Path to the log file.
    """
    log_dir = Path(project_root) / ".shipwright" / "agent_docs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "compliance_overrides.log"

    timestamp = datetime.now(timezone.utc).isoformat()
    details_json = json.dumps(details or {}, ensure_ascii=False)
    entry = f'[{timestamp}] OVERRIDE hook={hook_name} reason="{reason}" details={details_json}\n'

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)

    return log_path


def read_overrides(project_root: str | Path) -> list[str]:
    """Read all override log entries.

    Returns list of raw log lines. Empty list if no overrides logged.
    """
    log_path = Path(project_root) / ".shipwright" / "agent_docs" / "compliance_overrides.log"
    if not log_path.exists():
        return []
    return log_path.read_text(encoding="utf-8").strip().splitlines()
