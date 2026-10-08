"""F11 gate: the F5c entry's per-exemption record is well-formed.

Every gate that accepts an exemption records it one item at a time under the
entry's ``exemptions`` key (``lib.exemption_record``). This check re-validates
that block at F11, so a hand-edited or stale entry cannot carry a count that
disagrees with its items, a free-text reason, or a scope that escapes the
project. An entry with no ``exemptions`` key is legacy / exemption-free and
SKIPs: absence is a legal answer here, an unreadable answer is not.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.exemption_record import entry_exemptions_error, entry_summary_line  # noqa: E402
from lib.iterate_entry import find_entry_by_run_id  # noqa: E402

from .common import CheckResult, Severity  # noqa: E402

CHECK_NAME = "exemption record well-formed"


def check_exemption_record(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    entry = find_entry_by_run_id(Path(project_root), run_id)
    if not entry or "exemptions" not in entry:
        return CheckResult(
            CHECK_NAME, True, f"skipped (no exemptions recorded for {run_id})",
            severity=Severity.SKIPPED.value,
        )
    err = entry_exemptions_error(entry)
    if err:
        return CheckResult(
            CHECK_NAME, False,
            f"{run_id}: the F5c entry's {err} - fix the `exemptions` block via "
            "append_iterate_entry.py (references/F5c.md)",
        )
    return CheckResult(CHECK_NAME, True, f"{run_id}: exemptions {entry_summary_line(entry)}")
