"""fetch — the NETWORK half of the empirical suite (record / --refresh only).

Fetch a real OSS repo **at a pinned commit SHA** into a throwaway directory, so a
projection can be recorded once and replayed offline forever after. Reuses the
grader's own hardening: :func:`clone.normalize_url` (scheme allowlist),
:mod:`git_exec` (list-arg, ``shell=False``, non-interactive), and the post-checkout
size cap.

Two fetch strategies (a launch-gating suite must be robust to host quirks):

1. **Shallow SHA fetch** — ``git fetch --depth 1 origin <sha>`` (GitHub enables
   ``allowAnySHA1InWant`` for reachable commits). Smallest transfer.
2. **Treeless-clone fallback** — ``git clone --filter=blob:none`` + ``checkout
   <sha>`` when a host rejects the shallow SHA fetch (orphaned commit, network
   boundary). Fetches history but defers blobs; still bounded by the size cap.

A failure names the repo + SHA + remediation rather than a bare non-zero exit.
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from clone import CLONE_TIMEOUT_SECONDS, MAX_CLONE_BYTES, _dir_size_over, normalize_url
from gh_bridge import GhResult, GhRunner, run_gh
from git_exec import run_git
from replay import is_pinned_sha
from resolve_target import ResolvedTarget, TargetError, resolve_target

# Disable the ``ext`` + ``file`` transports for every fetch/clone (a hostile
# remote must not be able to run a command or read local files). Global ``-c``
# flags precede the subcommand — run_git's own hardening ``-c`` flags lead, and
# these ride in front of the subcommand in ``args``.
_TRANSPORT_GUARD = [
    "-c", "protocol.ext.allow=never",
    "-c", "protocol.file.allow=never",
]

# The projector grades from git HISTORY (``collect_events`` caps at 500 commits),
# so a ``--depth 1`` fetch would starve requirement/change traceability to a
# single event and mis-grade every real repo. Fetch the newest N commits ending
# at the pinned SHA — matching ``repo_context.Caps.max_commits`` — so the cold
# grade equals what a full local clone would produce.
_HISTORY_DEPTH = 500


class FetchError(TargetError):
    """A pinned SHA could not be fetched — names the repo, SHA and remedy."""


def _fetch_shallow_sha(
    url: str, sha: str, dest: Path, *, timeout: int, depth: int = _HISTORY_DEPTH,
) -> bool:
    """Strategy 1: ``git init`` + depth-N fetch of the exact SHA. True on success."""
    dest.mkdir(parents=True, exist_ok=True)
    if run_git(["init", "-q"], dest, timeout=timeout)[0] != 0:
        return False
    if run_git(["remote", "add", "origin", url], dest, timeout=timeout)[0] != 0:
        return False
    rc, _ = run_git(
        [*_TRANSPORT_GUARD, "fetch", "--depth", str(depth), "--no-tags", "origin", sha],
        dest, timeout=timeout)
    if rc != 0:
        return False
    rc, _ = run_git(["checkout", "-q", "--detach", "FETCH_HEAD"], dest, timeout=timeout)
    return rc == 0


def _clone_treeless(url: str, sha: str, dest: Path, *, timeout: int) -> bool:
    """Strategy 2 (fallback): treeless clone, then checkout the SHA. True on success."""
    rc, _ = run_git(
        [*_TRANSPORT_GUARD, "clone", "--filter=blob:none", "--no-checkout",
         "--no-tags", "--", url, str(dest)],
        dest.parent, timeout=timeout)
    if rc != 0 or not (dest / ".git").exists():
        return False
    rc, _ = run_git(["checkout", "-q", "--detach", sha], dest, timeout=timeout)
    return rc == 0


@contextmanager
def open_target_at_sha(
    url: str, sha: str, *, timeout: int = CLONE_TIMEOUT_SECONDS,
    max_bytes: int = MAX_CLONE_BYTES,
) -> Iterator[ResolvedTarget]:
    """Yield a :class:`ResolvedTarget` for ``url`` checked out at ``sha``.

    The checkout lives in a ``TemporaryDirectory`` purged on exit (even on error).
    Raises :class:`FetchError` for a bad SHA, an unfetchable commit, or a checkout
    that exceeds the size cap.
    """
    normalized = normalize_url(url)  # scheme allowlist (raises TargetError)
    if not is_pinned_sha(sha):
        raise FetchError(f"{url}: pinned_sha must be a 40-hex commit SHA (got {sha!r})")

    with tempfile.TemporaryDirectory(prefix="shipwright-grade-empirical-") as tmp:
        dest = Path(tmp) / "repo"
        ok = _fetch_shallow_sha(normalized, sha, dest, timeout=timeout)
        if not ok:
            shutil.rmtree(dest, ignore_errors=True)
            ok = _clone_treeless(normalized, sha, dest, timeout=timeout)
        if not ok:
            raise FetchError(
                f"could not fetch {url} @ {sha}: the commit must be reachable and "
                f"public. Verify the pinned_sha still exists (both a shallow SHA "
                f"fetch and a treeless clone failed).")
        if _dir_size_over(dest, max_bytes):
            raise FetchError(
                f"{url} @ {sha}: checkout exceeds the {max_bytes // 1_000_000} MB "
                f"size cap (huge repo — record it in the CI launch-gate job only)")
        yield resolve_target(str(dest))


class RecordingGh:
    """A ``gh`` runner that wraps a base runner and keeps a **redacted** audit log.

    The log records only *which* calls were made and their outcome — never the raw
    response body (URLs/headers/payloads are a data-exposure surface and pure diff
    churn). The projected signal itself is already captured in ``grade_inputs``;
    this is the "which gh calls happened, did they succeed" audit trail (§7).
    """

    def __init__(self, base: GhRunner = run_gh) -> None:
        self._base = base
        self.log: list[dict] = []

    def __call__(self, args, *, timeout: int = 30, input_text: str | None = None) -> GhResult:
        result = self._base(args, timeout=timeout, input_text=input_text)
        self.log.append({
            "args": list(args),
            "ok": result.ok,
            "error": result.error,
            "returncode": result.returncode,
            "stdout_len": len(result.stdout or ""),
        })
        return result


def preflight_network() -> list[str]:
    """Return a list of human-readable blockers for ``--refresh`` (empty = ready).

    Checks the two binaries + gh auth up front so a refresh fails with an
    actionable message instead of a confusing mid-run error.
    """
    problems: list[str] = []
    if shutil.which("git") is None:
        problems.append("git not found on PATH — install git to record fixtures")
    if shutil.which("gh") is None:
        problems.append("gh (GitHub CLI) not found — install it to enrich CI/security tiers")
        return problems
    status = run_gh(["auth", "status"])
    if not status.ok:
        problems.append(
            "gh is not authenticated — run `gh auth login` (network tiers need a token)")
    return problems
