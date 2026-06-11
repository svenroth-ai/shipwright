"""Portable, repo-relative ``spec_path`` helpers for campaign sub-iterates.

Campaign ``2026-06-07-tracked-campaign-status`` follow-up N1 (``trg-196f4aa6``).
The producers used to write a sub-iterate's ``spec_path`` as a machine-ABSOLUTE
campaign-dir path (``C:\\01_Development\\…``), useless on a fresh clone or a Linux
WebUI server. These pure helpers yield the repo-root-relative POSIX form
(``.shipwright/planning/iterate/campaigns/<slug>/sub-iterates/<id>-<slug>.md``),
identical on every machine/OS. Pulled into their own ≤300-LOC module so
``campaign_status.py`` (the projection) stays under its bloat ceiling and there
is no circular import with ``campaign_status_io`` (which imports from both).
"""

from __future__ import annotations

from pathlib import Path

#: The segment every campaign path is anchored on to drop the machine prefix.
_SHIPWRIGHT_ANCHOR = ".shipwright"


def relativize_spec_path(spec_path: str | None) -> str | None:
    """Return the **repo-root-relative POSIX** form of a ``spec_path``.

    A machine-absolute path (``C:\\…\\.shipwright\\…`` or ``/home/…/.shipwright/…``)
    is relativized by anchoring on the ``.shipwright`` segment; an already-relative
    path is returned forward-slash-normalised. ``None``/empty pass through
    unchanged. Idempotent: a value already in repo-relative form is returned
    byte-identical.
    """
    if not spec_path:
        return spec_path
    parts = str(spec_path).replace("\\", "/").split("/")
    if _SHIPWRIGHT_ANCHOR in parts:
        return "/".join(parts[parts.index(_SHIPWRIGHT_ANCHOR):])
    return "/".join(p for p in parts if p)


def campaign_spec_path(campaign_dir, sub_id: str, sub_slug: str) -> str:
    """Repo-root-relative POSIX ``spec_path`` for a campaign sub-iterate file.

    Anchored on ``.shipwright`` so it is identical on every machine/OS. When
    ``campaign_dir`` is not under ``.shipwright`` (a test fixture / unusual
    layout) it falls back to the campaign-dir-relative
    ``sub-iterates/<id>-<slug>.md``.
    """
    full = Path(campaign_dir) / "sub-iterates" / f"{sub_id}-{sub_slug}.md"
    parts = str(full).replace("\\", "/").split("/")
    if _SHIPWRIGHT_ANCHOR in parts:
        return "/".join(parts[parts.index(_SHIPWRIGHT_ANCHOR):])
    return f"sub-iterates/{sub_id}-{sub_slug}.md"
