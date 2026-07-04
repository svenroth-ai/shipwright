"""security_signal — Security dimension from GitHub code-scanning SARIF (dim 5).

Network-only enrichment (behind :class:`NetworkPolicy`). Fetches the latest
code-scanning analysis SARIF for the target and parses it with the shared,
**suppression-aware** ``security_findings._findings_from_sarif`` (dismissed /
``# nosemgrep`` results are dropped), then reuses ``ci_security``'s severity
summary + the *never-a-false-CRITICAL* grade guard — so the cold-repo Security
score is computed exactly like the dashboard's.

Honest degradation (never a false clean): local-only / no code-scanning / 403 /
auth-fail → ``n/a``; and a **malformed** SARIF payload is ``n/a`` too, never
silently read as "0 findings → clean" (the invalid-SARIF negative-fixture AC).
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from gh_bridge import GhRunner, default_branch, gh_json
from network_policy import NetworkPolicy
from reuse_bridge import load_findings_from_sarif, load_security_grade


@dataclass(frozen=True)
class SecuritySignal:
    measurable: bool
    open_high_critical: int | None
    detail: str
    source: str


def _na(detail: str) -> SecuritySignal:
    return SecuritySignal(measurable=False, open_high_critical=None,
                          detail=detail, source="")


def _latest_analysis_id(gh: GhRunner, owner: str, repo: str) -> tuple[int | None, str]:
    """Newest **default-branch** code-scanning analysis id + a degrade note.

    Filtering by the default branch (not the absolute newest analysis, which
    could be a transient PR/feature-branch scan) grades the security posture of
    the code that actually ships.
    """
    path = f"/repos/{owner}/{repo}/code-scanning/analyses?per_page=1"
    branch = default_branch(gh, owner, repo)
    if branch:
        # URL-encode the branch (a name may contain #/?/&/space) so it can't
        # break or inject into the query string; keep '/' for path-style branch
        # names like feature/x (external review GPT #6 / Gemini).
        path += f"&ref=refs/heads/{quote(branch, safe='/')}"
    result, data = gh_json(gh, ["api", path])
    if not result.ok:
        if result.error in ("rate_limited", "http_error"):
            return None, "code-scanning unavailable (disabled / 403 / rate-limited)"
        if result.error == "auth":
            return None, "code-scanning unavailable (authentication required)"
        return None, "code-scanning unavailable"
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return None, "no code-scanning analyses found"
    analysis_id = data[0].get("id")
    if not isinstance(analysis_id, int):
        return None, "no code-scanning analyses found"
    return analysis_id, ""


def _fetch_sarif(gh: GhRunner, owner: str, repo: str, analysis_id: int) -> str | None:
    path = f"/repos/{owner}/{repo}/code-scanning/analyses/{analysis_id}"
    result = gh(["api", path, "-H", "Accept: application/sarif+json"], timeout=60)
    return result.stdout if result.ok else None


def compute_security_signal(
    policy: NetworkPolicy,
    gh: GhRunner,
    *,
    findings_from_sarif: Callable[[Path], list | None] | None = None,
    security_grade: tuple[Callable, Callable] | None = None,
) -> SecuritySignal:
    """Open high/critical from code-scanning SARIF, or a graceful ``n/a``."""
    if not policy.enabled:
        return _na("no code-scanning ingested (local-only)")

    owner, repo = policy.owner, policy.repo
    assert owner and repo  # policy.enabled implies a resolved owner/repo
    analysis_id, note = _latest_analysis_id(gh, owner, repo)
    if analysis_id is None:
        return _na(note)

    sarif_text = _fetch_sarif(gh, owner, repo, analysis_id)
    if not sarif_text:
        return _na("code-scanning SARIF could not be downloaded")

    # SARIF is a JSON format, so json.loads is the correct parser and is XXE-safe
    # by construction (JSON has no DTDs/entities) — the spec's "defusedxml for
    # SARIF" wording is about XML and applies to the JUnit path only. Validate
    # BEFORE handing off: a malformed payload must be n/a, never read as a clean
    # empty scan (the invalid-SARIF negative fixture).
    try:
        doc = json.loads(sarif_text)
    except (json.JSONDecodeError, ValueError):
        return _na("invalid SARIF payload")
    # ``runs`` must be a genuine array — ``{"runs": null}`` / ``{"runs": "x"}``
    # would otherwise slip past to ``_findings_from_sarif`` and read as a clean
    # 0-finding scan (false CLEAN on a malformed payload).
    if not isinstance(doc, dict) or not isinstance(doc.get("runs"), list):
        return _na("invalid SARIF payload")

    findings_from_sarif = findings_from_sarif or load_findings_from_sarif()
    summarize, grade = security_grade or load_security_grade()
    with tempfile.TemporaryDirectory(prefix="grade-sarif-") as td:
        (Path(td) / "analysis.sarif").write_text(sarif_text, encoding="utf-8")
        findings = findings_from_sarif(Path(td))
    if findings is None:
        return _na("invalid SARIF payload")

    summary = summarize(findings, None, scan_date="", source="github-code-scanning")
    measurable, open_hc = grade(summary)
    if not measurable or open_hc is None:
        return _na("code-scanning summary not trustworthy")

    policy.record(f"code-scanning SARIF ({owner}/{repo})")
    detail = f"{open_hc} open high/critical (code-scanning)"
    return SecuritySignal(measurable=True, open_high_critical=open_hc,
                          detail=detail, source="github-code-scanning")
