"""Test roots declared by a stack profile, and the "no test folder" diagnostics (GitHub #972).

A stack profile may carry ``traceability.test_roots`` (the same vocabulary as the key of the same
name in ``shipwright_compliance_config.json``: folders or fixed-depth globs relative to the project
root). ``_test_links_io._resolve_test_roots`` asks this module only when the compliance config sets
no ``test_roots`` of its own. Entries returned here go through the SAME expansion loop as the config
entries, so ``**``, absolute paths, ``..`` and symlink escapes are dropped identically.

Which profile: the ``profile`` named in ``shipwright_run_config.json``, looked up in the project's
``.shipwright/profiles`` and the bundled profiles ONLY. The user-level directory is deliberately not
consulted: a manifest must come out the same locally, in CI and in the F11 gate's throwaway archives,
and only tracked files plus code reach all three.

Import notes (ADR-045): ``profile_consumer`` lives in ``shared/scripts`` and is imported ONCE, here at
module level, because the gate's ``_load_collector`` clears ``scripts.*`` from ``sys.modules`` right
after importing the collector -- a call-time import would run after that cleanup. ``shared/scripts``
is appended only when absent and removed only when THIS module added it (other callers keep theirs).
Nothing here raises: a profile problem degrades to "no profile roots" plus one stderr line per root.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[5] / "shared" / "scripts"
_ADDED = str(_SHARED_SCRIPTS) not in sys.path
if _ADDED:
    sys.path.append(str(_SHARED_SCRIPTS))
try:
    import profile_consumer as _pc
except ImportError:  # shared/ not reachable (a moved file): degrade to "no profile roots"
    _pc = None
finally:
    if _ADDED:
        try:
            sys.path.remove(str(_SHARED_SCRIPTS))
        except ValueError:
            pass

# Roots already warned about (one line per kind per project root per process). The F11 gate resolves
# roots on throwaway archives and passes warn=False -- its own failure text carries the diagnosis.
_WARNED_NO_ROOTS: set[str] = set()


def _once(kind: str, root: Path, message: str) -> None:
    key = f"{kind}::{Path(root).resolve()}" if kind else str(Path(root).resolve())
    if key in _WARNED_NO_ROOTS:
        return
    _WARNED_NO_ROOTS.add(key)
    sys.stderr.write(message)


def profile_test_roots(project_root: Path, *, warn: bool = True) -> tuple[str, list[str]]:
    """``(profile_name, entries)`` -- ``("", [])`` when no profile declares usable test roots."""
    if _pc is None:
        return "", []
    root = Path(project_root)
    name = ""
    try:
        name = _pc.config_profile(root) or ""
        if not name or name in _pc.SENTINELS:
            return "", []
        res = _pc.pr.resolve_profile(
            name, root,
            search_dirs=[d for d in _pc.pr.search_dirs(root) if d[0] != "user"],
        )
    except (ValueError, OSError) as exc:
        if warn:
            kind = getattr(exc, "kind", "")
            why = (
                f"stack profile {name!r} was not found in .shipwright/profiles or the bundled profiles "
                "(user-level profiles are not consulted for test roots)"
                if kind == "not_found" else
                f"the stack profile {name!r} could not be read ({type(exc).__name__}); fix that profile file"
                if name else
                f"shipwright_run_config.json could not be read ({type(exc).__name__}), so its `profile` is unknown"
            )
            _once("profile", root, f"[test_links] {root.resolve()}: {why}; using the default test folders. "
                  "To pick folders yourself set traceability.test_roots in shipwright_compliance_config.json.\n")
        return "", []
    block = res.data.get("traceability") if isinstance(res.data, dict) else None
    entries = block.get("test_roots") if isinstance(block, dict) else None
    if not isinstance(entries, list):
        return name, []
    return name, [e for e in entries if isinstance(e, str)]


def warn_profile_roots_unresolved(project_root: Path, profile_name: str) -> None:
    """The profile declared test folders and none of them exists: say so (a typo guard), then the
    caller falls back to the default folders."""
    _once("profile", project_root,
          f"[test_links] {Path(project_root).resolve()}: stack profile {profile_name!r} declares "
          "traceability.test_roots but none of those folders exists here; using the default test folders. "
          "Set traceability.test_roots in shipwright_compliance_config.json to your own folders.\n")


def warn_no_roots(project_root: Path, configured, default_dirs: tuple[str, ...]) -> None:
    """One stderr line when NO test folder resolved (see ``configured_test_roots``)."""
    key = str(Path(project_root).resolve())
    if f"profile::{key}" in _WARNED_NO_ROOTS:
        return  # the profile diagnostic already explained this root: one line, not two
    if configured == []:
        why = "traceability.test_roots is an empty list, which turns test scanning off"
    elif isinstance(configured, list):
        why = "traceability.test_roots matched no directory"
    else:
        why = "none of the default folders (" + ", ".join(default_dirs) + ") exists at the top level"
    _once("", project_root,
          f"[test_links] no test folder resolved for {key}: {why}, so no test file will be scanned "
          "and every requirement reads as untested. Set traceability.test_roots in "
          "shipwright_compliance_config.json to the folders that hold your tests "
          '(e.g. ["server/tests", "client/src", "client/e2e"]).\n')
