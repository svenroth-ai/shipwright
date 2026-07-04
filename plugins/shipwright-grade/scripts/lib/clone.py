"""clone — hardened, shallow, throwaway clone of an untrusted remote (G4).

URL clone-and-grade (plan §14 C) is the lead-magnet path: point the grader at a
GitHub URL and get a report. Cloning an *untrusted* remote is the real attack
surface, so every clone is:

- **scheme-allowlisted** (:func:`normalize_url`) — only ``https://``, an ``ssh://``
  / ``git@host:owner/repo`` SCP remote, or a ``owner/repo`` GitHub shorthand;
  ``http://`` / ``git://`` / ``file://`` / ``ext::…`` / anything else is rejected;
- **list-argument** (``shell=False`` via :mod:`git_exec`) with a ``--`` sentinel, so
  a hostile URL can never be parsed as a flag or injected into a shell;
- **shallow + single-branch + no-tags + no-submodule-recursion**, with the ``ext``
  and ``file`` git transports disabled — so a malicious ``.gitmodules`` or an
  ``ext::`` remote cannot execute a command or read local files;
- **time-capped** (the clone timeout bounds a slow remote) and **size-capped**
  (:func:`_dir_size_over` rejects an oversize checkout *after* clone).

**Residual, accepted for v1 (plan §6 defers sandboxed execution):** the size cap is
enforced *post*-checkout, so a crafted tree-bomb (few-byte pack, enormous working
tree) can materialise large on-disk data *during* checkout before the cap measures
it; the clone **timeout is the only active bound during checkout**. ``--depth 1
--single-branch`` limits it to one commit's tree. This is a bounded disk-DoS on the
standalone CLI, not code execution or data exfiltration. The caller
(:func:`resolve_target.open_target`) always clones into a
``tempfile.TemporaryDirectory`` that is purged on exit — even on a crash.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from git_exec import run_git
from resolve_target import _SHORTHAND_RE, TargetError  # shared owner/repo pattern

# Time + size caps (plan §6/§14 C). Deterministic bounds, not ad-hoc sampling.
# The clone timeout is the network-fetch cap (distinct from the grader's own
# ~60s traversal budget); shallow + single-branch keeps a normal repo well under
# it, and it also bounds how much a hostile remote can stream before the
# post-clone byte cap trips. Kept at the budget's order of magnitude.
CLONE_TIMEOUT_SECONDS = 60
MAX_CLONE_BYTES = 500_000_000  # 500 MB checkout ceiling (shallow keeps .git small)

# Scheme allowlist. https:// and an ssh/git@ SCP remote are accepted verbatim; a
# bare ``owner/repo`` (``_SHORTHAND_RE``, shared from resolve_target) is expanded
# to a GitHub HTTPS URL. Everything else is rejected. The host MUST start with an
# alphanumeric — a leading '-' would let a host like ``-oProxyCommand=…`` be parsed
# as an ssh option (CVE-2017-1000117 class), so we reject it at the allowlist
# rather than relying on the installed git's own hostname guard.
_HTTPS_RE = re.compile(r"^https://[A-Za-z0-9][\w.-]*(?::\d+)?/[^\s]+$", re.IGNORECASE)
_SCP_RE = re.compile(r"^(?:ssh://)?git@[A-Za-z0-9][\w.-]*[:/][^\s]+$", re.IGNORECASE)


def normalize_url(raw: str) -> str:
    """Validate + normalise a remote target to an allowlisted clone URL.

    Raises :class:`TargetError` for any scheme/shape outside the allowlist.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise TargetError("empty target")
    raw = raw.strip()
    if _HTTPS_RE.match(raw) or _SCP_RE.match(raw):
        return raw
    if _SHORTHAND_RE.match(raw) and ".." not in raw:
        return f"https://github.com/{raw}"
    raise TargetError(
        "unsupported target URL — allowed: https://…, git@host:owner/repo, "
        f"or owner/repo shorthand (got: {raw!r})"
    )


def _dir_size_over(path: Path, cap: int) -> bool:
    """True as soon as the cumulative file size under ``path`` exceeds ``cap``."""
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for name in filenames:
            try:
                total += (Path(dirpath) / name).stat().st_size
            except OSError:
                continue
            if total > cap:
                return True
    return False


def _run_clone(
    url: str, dest: Path, *, timeout: int = CLONE_TIMEOUT_SECONDS,
    allow_local: bool = False,
) -> None:
    """Shallow, hardened ``git clone`` of ``url`` into ``dest``.

    ``allow_local`` (tests only) relaxes the ``file``-transport block so a clone
    from a local bare repo can be exercised offline; production always leaves it
    ``False`` (the ``file`` + ``ext`` transports stay disabled).
    """
    file_policy = "always" if allow_local else "never"
    # The ``-c`` transport flags MUST precede the ``clone`` subcommand (global
    # config), so they lead the arg list; run_git prepends only its own hardening.
    args = [
        "-c", "protocol.ext.allow=never",
        "-c", f"protocol.file.allow={file_policy}",
        "clone", "--depth", "1", "--no-tags", "--single-branch",
        "--no-recurse-submodules", "--", url, str(dest),
    ]
    rc, _out = run_git(args, cwd=dest.parent, timeout=timeout)
    if rc != 0 or not (dest / ".git").exists():
        raise TargetError(
            f"clone failed (unreachable, private, or invalid remote): {url}")


def clone_repo(
    raw: str, dest: Path, *, timeout: int = CLONE_TIMEOUT_SECONDS,
    max_bytes: int = MAX_CLONE_BYTES, allow_local: bool = False,
) -> Path:
    """Validate ``raw``, shallow-clone it into ``dest``, enforce the size cap.

    Returns ``dest`` on success; raises :class:`TargetError` on a rejected URL, a
    clone failure, or a checkout that exceeds ``max_bytes``. ``dest`` must not yet
    exist (git creates it); the caller owns the throwaway parent directory.
    """
    url = normalize_url(raw)
    _run_clone(url, dest, timeout=timeout, allow_local=allow_local)
    if _dir_size_over(dest, max_bytes):
        raise TargetError(
            f"clone exceeds the {max_bytes // 1_000_000} MB size cap: {url}")
    return dest
