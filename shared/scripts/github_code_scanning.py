"""Thin ``gh`` shell for the code-scanning alert surface — list and dismiss.

A sibling leaf of ``github_api`` rather than an addition to it, for a concrete
reason: ``github_api.py`` measures 321 LOC against a baselined ``current`` of
321, and the anti-ratchet rule blocks at ``measured > current``, so a single
added line is a hard pre-commit and CI failure. That module already solves this
the same way (it re-exports the ``security_findings`` downloaders with
``# noqa: F401 - impl split for anti-ratchet``).

Two things live here that ``github_api`` cannot express:

* **write.** ``_gh_api`` has no ``--method`` parameter and no way to pass one,
  by construction — it is a read-only client.
* **state.** ``_fetch_alert_list`` hardcodes ``?state=open``; convergence has to
  see dismissed alerts too, or it cannot tell "already accepted" from "never
  seen" and cannot restore visibility on expiry.

The module-wide ``github_api`` contract is preserved: a *failed* fetch returns
``None`` and a *successful empty* fetch returns ``[]``. Collapsing them would
let a network blip read as "every alert cleared" (ADR-052) — and here that would
additionally read as "converged", which is the one lie this tool must not tell.

**Repository identity is resolved locally and never inferred.**
``gh api repos/{owner}/{repo}/…`` substitutes those placeholders from the
*current working directory's* git remote, so a mutation addressed through
placeholders can target a different repository than the one whose register was
read. Every path here is built from an explicit, validated ``owner/repo``
literal that the caller resolved from the checked-out tree.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any

_TIMEOUT_SECONDS = 30

#: Alert states convergence needs. ``open`` to dismiss, ``dismissed`` to
#: recognise what is already accepted and what must be reopened on expiry.
STATES = ("open", "dismissed")

#: ``owner/repo`` shape, validated before interpolation into a REST path
#: (mirrors ``grade/gh_bridge``'s defence against a crafted remote). Bounded
#: character classes, no nested quantifiers — linear, ReDoS-safe.
_OWNER_REPO_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?"
    r"/[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?$"
)


class RepoIdentityError(ValueError):
    """The repository to act on could not be established — never guess one."""


def validate_owner_repo(owner_repo: Any) -> str:
    """Return ``owner_repo`` if it is a well-formed slug, else raise.

    Raising (not returning ``None``) is deliberate: every caller of this is
    about to address a mutation, and a soft failure there degrades into acting
    on whatever the working directory happens to point at.
    """
    if not isinstance(owner_repo, str) or not _OWNER_REPO_RE.match(owner_repo):
        raise RepoIdentityError(
            f"refusing to act on unresolvable repository identity {owner_repo!r} — "
            "resolve it from the checked-out tree's origin remote first"
        )
    return owner_repo


def _run(args: list[str]) -> tuple[int, str]:
    # encoding is explicit: `text=True` decodes with the LOCALE codec, which on
    # a Windows runner is cp1252 and dies on the first non-Latin-1 byte in an
    # alert body. That surfaced here as a failed fetch — fail-closed, correctly,
    # but permanently: the tool could never converge on Windows at all.
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS,
            encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return result.returncode, result.stdout or ""


def list_alerts(owner_repo: str, state: str) -> list[dict] | None:
    """Every alert in ``state``, following pagination; ``None`` on any failure.

    ``--paginate`` merges the pages into one JSON array (verified against this
    repo at ``per_page=10`` over 5 pages), so an incomplete listing surfaces as
    a failed fetch rather than as a short one. That matters more here than
    usual: a truncated listing reads as "nothing left to converge".
    """
    slug = validate_owner_repo(owner_repo)
    code, out = _run([
        "gh", "api",
        f"repos/{slug}/code-scanning/alerts?state={state}&per_page=100",
        "--paginate",
    ])
    if code != 0:
        return None
    try:
        data = json.loads(out or "null")
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def dismiss_alert(
    owner_repo: str, number: int, *, reason: str, comment: str
) -> tuple[bool, str]:
    """Dismiss one alert. Returns ``(ok, message)``.

    Never called except from a plan entry backed by a non-expired register
    entry — see ``alert_convergence.plan_convergence``.
    """
    slug = validate_owner_repo(owner_repo)
    code, out = _run([
        "gh", "api", "--method", "PATCH",
        f"repos/{slug}/code-scanning/alerts/{int(number)}",
        "-f", "state=dismissed",
        "-f", f"dismissed_reason={reason}",
        "-f", f"dismissed_comment={comment}",
    ])
    return code == 0, out.strip()


def reopen_alert(owner_repo: str, number: int) -> tuple[bool, str]:
    """Reopen one alert, restoring visibility.

    Only ever called for an alert carrying this tool's provenance marker; a
    human's dismissal is never reopened.
    """
    slug = validate_owner_repo(owner_repo)
    code, out = _run([
        "gh", "api", "--method", "PATCH",
        f"repos/{slug}/code-scanning/alerts/{int(number)}",
        "-f", "state=open",
    ])
    return code == 0, out.strip()
