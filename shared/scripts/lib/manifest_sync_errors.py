"""``ManifestSyncError`` — the shared exception type for
``manifest_sync_core`` and ``manifest_sync_marketplace``. Its own leaf
module so the two can import it without an inter-module cycle (the
ADR-248 pattern: extract the shared symbol out, don't have either import
the other)."""

from __future__ import annotations

__all__ = ["ManifestSyncError"]


class ManifestSyncError(RuntimeError):
    """A named, fail-closed failure. ``status`` is one of the closed
    vocabulary documented in ``manifest-sync.md``'s status table — never a
    bare unclassified message."""

    def __init__(self, status: str, detail: str, *, path: str | None = None) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.path = path
