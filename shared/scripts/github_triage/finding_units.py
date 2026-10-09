"""One triage card per critical/high security finding (rule + file).

The per-repo ``gh-security:{owner}/{repo}`` roll-up shares ONE dedup key across
every finding, so a single closed item hid all later ones. These cards carry a
key of their own - ``gh-security:{owner}/{repo}:{rule}:{path}`` - so a finding
is raised, closed when it disappears, and raised again if it returns, without
touching its neighbours. Lower severities stay in the roll-up: only what drives
the compliance grade (high/critical) deserves a card each.

Keys carry the feed (``cs`` code scanning / ``art`` artifact):
``gh-security:{owner}/{repo}:{cs|art}:{rule}:{path}``. Pure functions, no I/O,
except ``kept_card_keys`` / ``import_cards``. Scanner-supplied strings (rule id, file path) are
attacker-influenced in a hostile repo, so they are reduced to a safe character
set and capped; no finding description ever reaches a card.
"""

from __future__ import annotations

import re
import sys

from triage import AUTO_RESOLVABLE_STATUSES, read_all_items

from .severity import (
    artifact_extract_severity,
    cs_extract_severity,
    kind_for,
    max_severity,
    security_url,
    triage_severity,
)

PREFIX = "gh-security:"
CARD_SEVERITIES = ("critical", "high")

_UNSAFE = re.compile(r"[^A-Za-z0-9._/@:+-]")
_RUNNER_ROOT = re.compile(r"^/home/runner/work/[^/]+/[^/]+/")
_TOOL_PREFIX = re.compile(r"^(?:semgrep|trivy|gitleaks|codeql)/")
_MAX_PART = 120


def _clean(value, limit: int = _MAX_PART) -> str:
    return _UNSAFE.sub("_", str(value or "").strip())[:limit] or "unknown"


def _rule(rule) -> str:
    return _clean(_TOOL_PREFIX.sub("", str(rule or "").strip()))


def _path(path) -> str:
    text = _RUNNER_ROOT.sub("", str(path or "").replace("\\", "/").strip())
    return _clean(text.lstrip("/"))


def finding_key(owner_repo: str, rule, path, source: str = "cs") -> str:
    """``source`` is ``cs`` (code scanning) or ``art`` (artifact): the two feeds
    name the same finding differently, so each owns its own cards."""
    return f"{PREFIX}{owner_repo}:{source}:{_rule(rule)}:{_path(path)}"


def kept_card_keys(project_root, owner_repo: str | None, source: str) -> set[str]:
    """Keys of the OPEN (or parked) ``source`` cards - what a run on the OTHER feed must not close.

    When code scanning is briefly unreachable the artifact feed answers instead;
    its cards cannot vouch for code-scanning findings, so those stay untouched.
    """
    if owner_repo is None:
        return set()
    head = f"{PREFIX}{owner_repo}:{source}:"
    return {
        key for item in read_all_items(project_root)
        if item.get("status") in AUTO_RESOLVABLE_STATUSES
        and (key := item.get("dedupKey") or "").startswith(head)
    }


def _from_code_scanning(alerts) -> list[tuple]:
    out = []
    for alert in alerts or []:
        loc = (alert.get("most_recent_instance") or {}).get("location") or {}
        out.append((
            (alert.get("rule") or {}).get("id"), loc.get("path"),
            triage_severity(cs_extract_severity(alert)),
        ))
    return out


def _from_artifact(findings) -> list[tuple]:
    return [
        (f.get("rule") or f.get("cve_id"),
         f.get("affected_file") or f.get("affected_package"),
         triage_severity(artifact_extract_severity(f)))
        for f in findings or []
    ]


def card_units(
    *, owner_repo: str | None, code_scanning=None, artifact_findings=None,
    run_url: str | None = None,
) -> list[dict]:
    """Cards for the critical/high findings of ONE source (never both)."""
    if owner_repo is None:
        return []
    source = "cs" if code_scanning is not None else "art"
    rows = (
        _from_code_scanning(code_scanning) if source == "cs"
        else _from_artifact(artifact_findings)
    )
    groups: dict[str, dict] = {}
    for rule, path, severity in rows:
        # No rule AND no file (SARIF fallback shape) would collapse every finding
        # into one card - exactly the shared-key flaw the cards exist to remove.
        if severity not in CARD_SEVERITIES or not (rule or path):
            continue
        key = finding_key(owner_repo, rule, path, source)
        group = groups.setdefault(
            key, {"rule": _rule(rule), "path": _path(path), "sev": [], "n": 0})
        group["sev"].append(severity)
        group["n"] += 1
    url = run_url or security_url(owner_repo)
    units = []
    for key, g in groups.items():
        severity = max_severity(g["sev"])
        times = f" (x{g['n']})" if g["n"] > 1 else ""
        units.append({
            "severity": severity,
            "kind": kind_for(severity),
            "title": f"Security {severity}: {g['rule']} in {g['path']}{times}"[:160],
            "detail": (f"Repo {owner_repo} | {g['rule']} | {g['path']} | "
                       f"{g['n']} instance(s) | see {url}")[:1024],
            "dedup_key": key,
            "launch_payload": (
                "/shipwright-security\n\n"
                f"Context: an open {severity} security finding ({g['rule']}) in "
                f"{g['path']} of {owner_repo}.\nLive state: {url}\n"
                f"Source: triage item {key}"
            ),
        })
    return units


def import_cards(
    project_root, owner_repo: str | None, append, by_source: dict, *,
    code_scanning=None, artifact_findings=None, run_url: str | None = None,
) -> tuple[int, set[str]]:
    """Append the cards of ONE feed; return (new count, keys that must not be closed).

    Fail-soft: a malformed alert must never abort the import that carries the
    roll-up and the resolve pass. On the artifact feed the live code-scanning
    cards are returned as keys to keep (see ``kept_card_keys``).
    """
    try:
        keep = (kept_card_keys(project_root, owner_repo, "cs")
                if code_scanning is None else set())
        # Art cards only fill a gap: while live cs cards exist the same findings
        # are already on the board, and a brief code-scanning blip must not
        # raise a second copy of each.
        units = [] if keep else card_units(
            owner_repo=owner_repo, code_scanning=code_scanning,
            artifact_findings=artifact_findings, run_url=run_url)
        emitted = sum(1 for unit in units if append(unit))
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[github-triage] cards failed: {type(exc).__name__}: {exc}\n")
        # A failed card pass must never close anything: keep every live card.
        try:
            return 0, kept_card_keys(project_root, owner_repo, "cs") | kept_card_keys(
                project_root, owner_repo, "art")
        except Exception:  # noqa: BLE001
            return 0, set()
    by_source["gh-security:cards"] = by_source.get("gh-security:cards", 0) + emitted
    return emitted, keep
