"""gh_bridge — the single hardened, injectable GitHub CLI seam.

Every network call the grader makes goes through a ``GhRunner`` (a callable
returning :class:`GhResult`). The default :func:`run_gh` is a **list-arg,
``shell=False``** ``gh`` invocation (untrusted repo — never string-concat, plan
§14 A). Tests inject a fake runner returning canned payloads, so the whole
network layer is exercised **hermetically** — no live GitHub, no token.

Failures are classified, not swallowed: a ``403``/rate-limit is distinct from an
auth failure is distinct from a missing ``gh`` binary, so the signal modules can
degrade **deterministically** to the next tier or ``n/a``.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

# github.com (or a GHE host containing "github") OWNER/REPO from any remote URL.
_REMOTE_RE = re.compile(
    r"(?:github[^/@:]*)(?:[:/])(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)
# GitHub owner/repo slugs are [A-Za-z0-9._-]; validate before either half is
# interpolated into a ``gh api`` REST path (defence-in-depth against a crafted
# remote injecting ``..``/odd path segments — gh only talks to GitHub, but keep
# the values well-formed).
_SLUG_RE = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class GhResult:
    """Outcome of a ``gh`` call, with a classified failure kind."""

    ok: bool
    stdout: str = ""
    returncode: int = 0
    #: "" | "not_found" | "timeout" | "rate_limited" | "auth" | "http_error" | "subprocess"
    error: str = ""


#: A ``gh`` runner: ``(args, *, timeout) -> GhResult``. Injected in tests.
GhRunner = Callable[..., GhResult]


def _classify(stderr: str) -> str:
    low = stderr.lower()
    if "rate limit" in low or "rate-limit" in low or "403" in low:
        return "rate_limited"
    if ("authentication" in low or "gh auth login" in low or "401" in low
            or "not logged" in low or "requires authentication" in low):
        return "auth"
    return "http_error"


def run_gh(args: list[str], *, timeout: int = 30, input_text: str | None = None) -> GhResult:
    """Run ``gh <args>`` read-only, list-arg. Never raises — returns a GhResult."""
    try:
        proc = subprocess.run(
            ["gh", *args], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, input=input_text, check=False,
        )
    except FileNotFoundError:
        return GhResult(ok=False, error="not_found")
    except subprocess.TimeoutExpired:
        return GhResult(ok=False, error="timeout")
    except (OSError, subprocess.SubprocessError):
        return GhResult(ok=False, error="subprocess")
    if proc.returncode != 0:
        return GhResult(
            ok=False, stdout=proc.stdout or "", returncode=proc.returncode,
            error=_classify(proc.stderr or ""))
    return GhResult(ok=True, stdout=proc.stdout or "", returncode=0)


def owner_repo_from_remote(url: str) -> tuple[str, str] | None:
    """Extract ``(owner, repo)`` from a GitHub remote URL, or ``None``."""
    if not url:
        return None
    match = _REMOTE_RE.search(url.strip())
    if not match:
        return None
    owner, repo = match.group("owner"), match.group("repo")
    if not _SLUG_RE.match(owner or "") or not _SLUG_RE.match(repo or ""):
        return None
    if owner in (".", "..") or repo in (".", ".."):
        return None
    return owner, repo


def default_branch(gh: GhRunner, owner: str, repo: str) -> str:
    """The repo's default branch name (``""`` when it can't be determined)."""
    _result, data = gh_json(gh, ["repo", "view", f"{owner}/{repo}", "--json",
                                 "defaultBranchRef"])
    ref = data.get("defaultBranchRef") if isinstance(data, dict) else None
    name = ref.get("name") if isinstance(ref, dict) else None
    return name if isinstance(name, str) else ""


def gh_json(gh: GhRunner, args: list[str], *, timeout: int = 30) -> tuple[GhResult, Any]:
    """Run ``gh`` and JSON-parse stdout. ``data`` is ``None`` on failure/non-JSON."""
    result = gh(args, timeout=timeout)
    if not result.ok:
        return result, None
    try:
        return result, json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return result, None
