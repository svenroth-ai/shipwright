"""One plain WARN line when too many event drop files are still open.

The fold (``tools/fold_events.py``) runs on its own only at a release, so a repo
that does not release for a while keeps accumulating files in
``shipwright_events.d/``. This is the detection half: it counts them and says so.

It is advisory. It returns text (or ``None``) and never raises, so a caller can
print it without any chance of changing an exit code. The legacy layout has no
drop folder and stays silent.
"""

from __future__ import annotations

from pathlib import Path

from .events_layout import events_layout
from .events_log import DROPS_DIR

# About where a directory listing of the folder starts to feel slow; the number the
# architecture review of the automatic fold named.
OPEN_FILES_WARN_THRESHOLD = 150


def count_open_drop_files(project_root: Path | str) -> int:
    """Number of ``*.jsonl`` drop files directly inside ``shipwright_events.d/``."""
    folder = Path(project_root) / DROPS_DIR
    try:
        if folder.is_symlink() or not folder.is_dir():
            return 0
        return sum(1 for p in folder.iterdir()
                   if p.suffix == ".jsonl" and not p.name.startswith(".") and p.is_file())
    except OSError:
        return 0


def open_files_warning(project_root: Path | str, threshold: int = OPEN_FILES_WARN_THRESHOLD) -> str | None:
    """The warning line, or ``None`` (legacy layout, below threshold, or unreadable)."""
    try:
        if events_layout(project_root) != "drops":
            return None
        count = count_open_drop_files(project_root)
    except Exception:  # noqa: BLE001 -- advisory: a failed look must never break the caller
        return None
    if count < threshold:
        return None
    fold = Path(__file__).resolve().parents[1] / "tools" / "fold_events.py"  # where it really is, also in a consumer project
    return (f"WARN: {count} event files are open in {DROPS_DIR}/. The next release folds the old "
            f"ones (files under 14 days old stay open); an operator, on main and never inside an iterate, can fold now: uv run \"{fold}\" fold --project-root \"{Path(project_root).resolve()}\"")
