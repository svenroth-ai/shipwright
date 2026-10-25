"""Which build sections a build check judges: the gated split's own.

For a non-final split the build skill runs ``archive_split`` before its result is applied:
the split's ``sections`` move to ``split_<prefix>_sections`` (the key
``collect_all_build_sections`` reads) and ``sections`` becomes ``[]`` for the next split.
A check that reads only ``sections`` then judges nothing for the split it was asked about.

Mirrored by ``phase_validators_split.sections_for_split`` in the run plugin (pinned equal
by a test there). No imports, so either package can carry it without the other.
"""

from __future__ import annotations

from typing import Any, Optional


def archived_sections_key(split_id: str) -> str:
    """``split_<prefix>_sections``, the key ``archive_split`` files a split under."""
    return f"split_{split_id.split('-', 1)[0]}_sections"


def sections_for_split(build_config: Any, split_id: Optional[str]) -> list:
    """The sections of ``split_id``: the current list, unless the build config has moved on
    to another split (both known and different) — then that split's archived bucket, but
    only when ``archive_split`` recorded this exact name in ``completed_splits`` (a prefix
    can be shared or left over), else ``[]``. No split id: the current list, as before."""
    if not isinstance(build_config, dict):
        return []
    sections = build_config.get("sections")
    current = build_config.get("current_split") or ""
    if split_id and current and split_id != current:
        done = build_config.get("completed_splits")
        sections = (build_config.get(archived_sections_key(split_id))
                    if isinstance(done, list) and split_id in done else None)
    return sections if isinstance(sections, list) else []


def build_config_for_split(build_config: Any, split_id: Optional[str]) -> dict:
    """``build_config`` as the split ``split_id`` saw it: ``current_split`` is that split
    and ``sections`` its own. Unchanged when no split id is given or it is the current one;
    a non-object config reads as ``{}``."""
    if not isinstance(build_config, dict):
        return {}
    current = build_config.get("current_split") or ""
    if not (split_id and current and split_id != current):
        return build_config
    return {**build_config, "current_split": split_id,
            "sections": sections_for_split(build_config, split_id)}
