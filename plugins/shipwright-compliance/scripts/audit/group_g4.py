"""G4 - a commit that says it closes a triage card, while the card is still open.

REPORT ONLY: it never appends a status. Card ``trg-52196e41``: a PR body or
commit message names ``Closes trg-xxxxxxxx`` and nobody records the status
event, so the card stays on the board after its work shipped.

**Grammar (verb-adjacent, not line-anchored - measured on 1500 commits, only 6
matched a line-anchored form).** A token is, case-insensitive::

    (closes|fixes|resolves) [triage [card]] trg-<8 hex>
        [ (, | and) [and] trg-<8 hex> ]*

Not tokens: a partial close (``Fixes trg-X (first half)``; say ``Part of
trg-X``), ``Related:``, ``supersedes``, ``triage trg-X`` without a verb,
``fixed here, filed as trg-X``, ``deferred to triage trg-X``. A commit whose
subject starts with ``Revert "`` is ignored. Range: commits since the latest
release tag; with no tag the last :data:`FALLBACK_COMMITS` commits, and the
detail says so. One ``git log`` call.

A token is a finding when the card's resolved status is ``triage`` or
``snoozed``; ``dismissed`` / ``promoted`` are silent; an id missing from the
store is an ``info:`` evidence line, never a finding.

"Report only" means it never writes a status; a finding is a normal MEDIUM
``fail`` (operator decision 3.2), so it turns the audit verdict red and feeds the
compliance backlog card. Known misses (grammar is verb-adjacent on one line):
a hard-wrapped body, ``Closes `trg-X```, ``Closes: trg-X``, past tense
(``Closed``), negation ("no longer closes trg-X") still matches, and the
original commit of a later Revert stays in range.

**Known limit:** a status that exists only in the gitignored outbox
(``triage.outbox.jsonl``) is invisible to CI, so CI can report a card the
author's machine already closed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from scripts.audit import git_log_scan
from scripts.audit.audit_adapters import SOURCE_DETECTIVE_ONLY, Finding

CHECK_ID = "G4"
NAME = "Commit closes a triage card that has no status event"
FALLBACK_COMMITS = 500
OPEN_STATUSES = frozenset({"triage", "snoozed"})

_ID = r"trg-[0-9a-f]{8}(?![0-9a-z_])"  # no longer id: trg-<8 hex>x is not a card
# An id directly followed by "(first half", "(part 2", ... is a PARTIAL close:
# the card correctly stays open, so it is not a token (write "Part of trg-X").
_ID_FULL = rf"{_ID}(?![ \t]*(?:\([^)\n]*\b(?:half|part)\b|(?:first|second|1st|2nd)[ \t]+half))"
_TOKEN_RE = re.compile(
    rf"\b(?:closes|fixes|resolves)\b[ \t]+(?:triage[ \t]+(?:card[ \t]+)?)?"
    rf"{_ID_FULL}(?:[ \t]*(?:,|\band\b)[ \t]*(?:and[ \t]+)?{_ID_FULL})*",
    re.IGNORECASE,
)
_ID_RE = re.compile(_ID, re.IGNORECASE)


def closing_ids(message: str) -> list[str]:
    """Card ids a commit message closes, in order, lowercased, de-duplicated."""
    if message.lstrip().startswith('Revert "'):
        return []
    seen: dict[str, None] = {}
    for m in _TOKEN_RE.finditer(message):
        for cid in _ID_RE.findall(m.group(0)):
            seen.setdefault(cid.lower())
    return list(seen)


def parse_log(raw: str) -> list[tuple[str, str]]:
    """``(sha, message)`` pairs from ``--format=%H%x1f%B%x1e`` output."""
    out = []
    for rec in raw.split("\x1e"):
        sha, sep, body = rec.strip("\n").partition("\x1f")
        if sep and sha.strip():
            out.append((sha.strip(), body))
    return out


def evaluate(commits: list[tuple[str, str]], status_by_id: dict[str, str]):
    """``(findings, unknown)`` where each is a list of ``(sha, card_id[, status])``."""
    findings: list[tuple[str, str, str]] = []
    unknown: list[tuple[str, str]] = []
    for sha, message in commits:
        for cid in closing_ids(message):
            status = status_by_id.get(cid)
            if status is None:
                unknown.append((sha, cid))
            elif status in OPEN_STATUSES:
                findings.append((sha, cid, status))
    return findings, unknown


def _check(project_root: Path, config: dict[str, Any]) -> Finding:
    def finding(status: str, detail: str, evidence: list[str] | None = None) -> Finding:
        return Finding(
            group="G", check_id=CHECK_ID, name=NAME, severity="MEDIUM",
            source=SOURCE_DETECTIVE_ONLY, status=status, detail=detail,
            evidence=evidence or [],
        )

    if not git_log_scan.is_git_repo(project_root):
        return finding("skip", "not a git repository")
    from scripts.audit.triage_bundle import _triage_api  # noqa: PLC0415
    read_all_items = _triage_api()[3]
    if read_all_items is None:
        return finding("skip", "triage module unavailable")
    status_by_id = {
        it["id"]: it.get("status") for it in read_all_items(project_root)
        if isinstance(it.get("id"), str)
    }
    pattern = (config.get("b7_exclusions") or {}).get("last_release_tag_pattern", "v*")
    tag = git_log_scan.latest_release_tag(project_root, pattern)
    if tag is None:
        rev, scope = [f"-{FALLBACK_COMMITS}"], f"no release tag matching '{pattern}': last {FALLBACK_COMMITS} commits"
    else:
        rev, scope = [f"{tag}..HEAD"], f"since {tag}"
    try:
        raw = git_log_scan._run_git(
            project_root, ["log", "--format=%H%x1f%B%x1e", *rev], timeout=60)
    except Exception as exc:  # noqa: BLE001 - a git error is not a card finding
        return finding("skip", f"git log failed: {exc}", [str(exc)])
    commits = parse_log(raw)
    try:
        if git_log_scan._run_git(project_root, ["rev-parse", "--is-shallow-repository"]).strip() == "true":
            scope += ", SHALLOW clone: history truncated"
    except Exception:  # noqa: BLE001 - informational only
        pass
    findings, unknown = evaluate(commits, status_by_id)
    info = [f"info: {sha[:12]} names {cid}, which is not in the triage store" for sha, cid in unknown]
    if not findings:
        return finding("pass", f"{len(commits)} commit(s) {scope}; no closing token on an open card", info)
    evidence = [f"{sha[:12]} closes {cid}, still '{st}'" for sha, cid, st in findings] + info
    detail = (f"{len(findings)} closing token(s) on cards still open ({scope}); "
              "record the status with triage_cli dismiss/promote")
    return finding("fail", detail, evidence)


def run(project_root: Path, config: dict[str, Any] | None, _data: Any) -> list[Finding]:
    try:
        return [_check(project_root, config or {})]
    except Exception as exc:  # noqa: BLE001 - crash isolation: an internal error is not a card finding
        return [Finding(group="G", check_id=CHECK_ID, name=NAME, severity="MEDIUM",
                        source=SOURCE_DETECTIVE_ONLY, status="skip",
                        detail=f"check raised {type(exc).__name__}: {exc}")]
