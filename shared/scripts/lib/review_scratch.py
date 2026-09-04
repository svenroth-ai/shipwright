"""Private, run-scoped scratch files for the code-review pipeline's
bash-to-python handoff (a diff file, a units-list JSON, …).

Exists to close a Windows-only bug: a bare `/tmp/<name>` path resolves to two
different physical files under Git-Bash (MSYS mounts `/tmp` onto `%TEMP%`)
and native Python (a leading `/` resolves against the current drive's root,
e.g. `C:\\tmp\\<name>`) — see iterate-2026-09-03-review-scratch-path.
`resolve()` is a pure function of `(run_id, name)`: both the bash write site
and the python read site call it independently and land on the identical
path, so nothing is passed *between* them and nothing to reinterpret.

Reuses the private-root hardening `host_resource_lease.py` already applies
to `%LOCALAPPDATA%\\Shipwright` / `$XDG_RUNTIME_DIR/shipwright` / the sticky
POSIX shared temp root, rather than trusting a plain `tempfile.gettempdir()`
+ `os.makedirs` (world-readable on a shared host, spoofable via a pre-created
symlink) for files that can carry a source diff.

Cleanup is explicit only — every call site invokes `cleanup()` once it is
done with its run. Leftover files in this private, ACL-hardened root are a
non-problem, not a garbage-collection target.

Stdlib-only (no `uv run --project` needed by the CLI).
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from scripts.lib._host_resource_locking import (
    HostLeaseError, _reject_linked_components, _safe_dir, _safe_file, _safe_runtime_root,
)
from scripts.lib.host_resource_lease import _private_shipwright_base

ReviewScratchError = HostLeaseError

_NAMESPACE = "review-scratch-v1"
_COMPONENT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")
_RESERVED = {".", ".."}
_WIN_RESERVED_RE = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\.[^.]*)?$")


def _validate_component(value: str, *, label: str) -> str:
    """Validate, then canonicalize to lowercase: two run_ids/names differing
    only by case must resolve to the SAME path everywhere, not silently
    collide only on a case-insensitive filesystem (Windows/macOS)."""
    lowered = value.lower()
    if (lowered in _RESERVED or not _COMPONENT_RE.fullmatch(lowered)
            or _WIN_RESERVED_RE.fullmatch(lowered)):
        raise ReviewScratchError(f"unsafe review-scratch {label}: {value!r}")
    return lowered


def _namespace_root() -> tuple[Path, Path, bool]:
    base, anchor, allow_sticky_shared = _private_shipwright_base()
    return base / _NAMESPACE, anchor, allow_sticky_shared


def _run_root(run_id: str) -> Path:
    run_id = _validate_component(run_id, label="run_id")
    namespace, anchor, allow_sticky_shared = _namespace_root()
    _safe_runtime_root(anchor, allow_sticky_shared=allow_sticky_shared)
    _safe_dir(namespace, trusted_parent=anchor)
    run_root = namespace / run_id
    _safe_dir(run_root, trusted_parent=anchor)
    return run_root


def resolve(run_id: str, name: str) -> Path:
    """Return the absolute scratch path for `name` under this `run_id`,
    creating its parent directory if needed. Deterministic — safe to call
    independently from both the bash write site and the python read site."""
    name = _validate_component(name, label="name")
    run_root = _run_root(run_id)
    target = run_root / name
    _safe_file(target, allow_missing=True)
    return target


def cleanup(run_id: str) -> None:
    """Remove this run's entire scratch subdirectory. A no-op if it does not
    exist. Only ever targets the caller's own `run_id`. Threat model: the
    private, ACL-hardened root defends against another OS user planting a
    reparse point here — not against a same-user race between the checks
    below and `rmtree` (out of scope: nothing untrusted runs as this user
    inside the window)."""
    run_id = _validate_component(run_id, label="run_id")
    namespace, anchor, allow_sticky_shared = _namespace_root()
    run_root = namespace / run_id
    # lexists, not exists/is_symlink: a Windows directory JUNCTION is a
    # reparse point but not a symlink (is_symlink() misses it), and exists()
    # follows reparse points so a DANGLING one reads as absent either way —
    # lexists never follows the final component, whatever its reparse tag.
    if not os.path.lexists(run_root):
        return
    _safe_runtime_root(anchor, allow_sticky_shared=allow_sticky_shared)
    if run_root.is_symlink() or namespace not in run_root.parents:
        raise ReviewScratchError(f"refusing to remove unsafe review-scratch path: {run_root}")
    # The actual junction/reparse-point guard — is_symlink() above only
    # catches IO_REPARSE_TAG_SYMLINK, never IO_REPARSE_TAG_MOUNT_POINT
    # (directory junctions); this checks FILE_ATTRIBUTE_REPARSE_POINT,
    # which is set for either tag.
    _reject_linked_components(run_root)
    shutil.rmtree(run_root)
