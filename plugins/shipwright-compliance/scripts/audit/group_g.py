"""Group G — Agent-docs freshness vs. git activity (plan v7 Step 8).

Two detective-only checks that scan commits since the latest release tag:

- **G2** — Conventional-commit scope match. Each commit subject is parsed
  for a conventional-commit ``type(scope):`` prefix; the scope must
  resolve to either:
    1. an entry in ``audit_config.json.g2_alias_map`` (canonical scope or
       alias), OR
    2. a known split name in ``shipwright_project_config.json.splits[]``,
       OR
    3. a member of ``g2_stoplist`` (explicitly opted out — usually generic
       cross-cutting scopes like ``deps``, ``ci``, ``docs``).
  Anything else is flagged so the operator either adds the scope to the
  alias map or renames the commit to use a known scope. Commits with no
  conventional prefix at all are silently ignored — G2 only audits what
  the convention promises to deliver.

- **G3** — ADR-ID references in commit bodies must exist in
  ``.shipwright/agent_docs/decision_log.md``. Detects the case where a
  commit body says "supersedes ADR-042" but ADR-042 was never recorded
  (typo, copy-paste error, or the ADR was rolled back without updating
  references). Subject lines are intentionally NOT scanned for ADR
  references — the Shipwright convention puts ``Run-ID:`` and ADR refs
  in the multi-line body, never in the conventional-commit subject.

Both checks reuse :mod:`git_log_scan` for git plumbing (subprocess + git
CLI; no GitPython dependency), and skip cleanly when the project is not
a git repo or has no release tag yet.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.audit.audit_adapters import (
    SOURCE_DETECTIVE_ONLY,
    Finding,
    load_shared_lib,
)
from scripts.audit import git_log_scan


adr_headers = load_shared_lib("adr_headers")


# ---------------------------------------------------------------------------
# Suggested-iterate hint
# ---------------------------------------------------------------------------

def _suggest(check_id: str, label: str) -> str:
    return (
        f"/shipwright-iterate --type change "
        f"\"reconcile {check_id} ({label}) "
        f"— see .shipwright/compliance/audit-report.md\""
    )


# ---------------------------------------------------------------------------
# Conventional-commit subject parser
# ---------------------------------------------------------------------------

# ``type(scope): description`` or ``type(scope)!: description``. Bare
# ``type: description`` (no scope) yields scope=None and is ignored —
# G2 only audits commits that DO declare a scope. Type is case-insensitive
# so ``Feat(auth): ...`` and ``FIX(auth): ...`` are treated the same as
# ``feat(auth): ...`` (real-world repos vary on type casing).
_CC_SUBJECT_RE = re.compile(
    r"^(?P<type>[A-Za-z]+)\((?P<scope>[^)]+)\)!?:\s",
)


@dataclass(frozen=True)
class _CommitSubject:
    sha: str
    full_subject: str
    scope: str | None  # None when no parens block present


def _git_commit_subjects(repo: Path, shas: list[str]) -> list[_CommitSubject]:
    """Return ``(sha, subject, scope)`` for each commit in ``shas``.

    A single ``git log -s --pretty=format:%H|%s <shas>`` would be cheaper,
    but git rejects an unbounded number of positional revs. We batch via
    ``git show -s`` per commit; the call is cheap and isolates parse
    failures to a single commit.
    """
    out: list[_CommitSubject] = []
    for sha in shas:
        try:
            result = subprocess.run(
                ["git", "-C", str(repo), "show", "-s",
                 "--pretty=format:%s", sha],
                capture_output=True, text=True, timeout=10,
                encoding="utf-8", errors="replace", check=False,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode != 0:
            continue
        subject = (result.stdout or "").splitlines()[0:1]
        subject_line = subject[0] if subject else ""
        m = _CC_SUBJECT_RE.match(subject_line)
        scope = m.group("scope").strip() if m else None
        out.append(_CommitSubject(sha=sha, full_subject=subject_line,
                                  scope=scope))
    return out


def _git_commit_bodies(repo: Path, shas: list[str]) -> dict[str, str]:
    """Return ``{sha: body}`` excluding the subject line.

    Empty body → ``""`` value, key still present (so callers can see we
    looked). Failures drop the SHA from the result.
    """
    out: dict[str, str] = {}
    for sha in shas:
        try:
            result = subprocess.run(
                ["git", "-C", str(repo), "show", "-s",
                 "--pretty=format:%b", sha],
                capture_output=True, text=True, timeout=10,
                encoding="utf-8", errors="replace", check=False,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode != 0:
            continue
        out[sha] = result.stdout or ""
    return out


def _project_split_names(project_root: Path) -> set[str]:
    """Return the set of split names from ``shipwright_project_config.json``."""
    cfg_path = project_root / "shipwright_project_config.json"
    if not cfg_path.exists():
        return set()
    try:
        import json
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    splits = data.get("splits", []) if isinstance(data, dict) else []
    if not isinstance(splits, list):
        return set()
    out: set[str] = set()
    for entry in splits:
        if isinstance(entry, dict):
            name = entry.get("name")
            if isinstance(name, str) and name:
                out.add(name)
    return out


def _alias_lookup(g2_alias_map: dict[str, Any]) -> set[str]:
    """Flatten the alias map into a lookup set (canonical + variants).

    ``{"auth": ["auth", "authn"]}`` → ``{"auth", "authn"}``.
    """
    out: set[str] = set()
    for canonical, variants in g2_alias_map.items():
        if isinstance(canonical, str):
            out.add(canonical)
        if isinstance(variants, list):
            for v in variants:
                if isinstance(v, str):
                    out.add(v)
    return out


# ---------------------------------------------------------------------------
# G2 — Conventional-commit scope match
# ---------------------------------------------------------------------------


def _check_g2(
    project_root: Path,
    config: dict[str, Any],
) -> tuple[str, str, list[str]]:
    if not git_log_scan.is_git_repo(project_root):
        return "skip", "not a git repository", []

    pattern = (config.get("b7_exclusions") or {}).get(
        "last_release_tag_pattern", "v*",
    )
    tag = git_log_scan.latest_release_tag(project_root, pattern)
    if tag is None:
        return "skip", f"no release tag matching '{pattern}'", []

    commits = git_log_scan.commits_since_tag(project_root, tag)
    if isinstance(commits, git_log_scan.ScanError):
        return "fail", f"git log failed: {commits.detail}", [commits.detail]
    if not commits:
        return "pass", f"no commits since {tag}", []

    stoplist = {s for s in (config.get("g2_stoplist") or [])
                if isinstance(s, str)}
    aliases = _alias_lookup(config.get("g2_alias_map") or {})
    splits = _project_split_names(project_root)
    known = stoplist | aliases | splits

    subjects = _git_commit_subjects(project_root, commits)
    unmatched: list[tuple[str, str, str]] = []  # (sha, scope, subject)
    examined = 0
    for cs in subjects:
        if cs.scope is None:
            # No conventional-commit subject prefix — G2 doesn't audit
            # those (that's a separate convention, possibly governed by
            # commitlint hooks).
            continue
        examined += 1
        if cs.scope in known:
            continue
        unmatched.append((cs.sha, cs.scope, cs.full_subject))

    if examined == 0:
        return "skip", (
            f"no conventional-commit subjects in {len(commits)} commit(s) "
            f"since {tag}"
        ), []
    if not unmatched:
        return "pass", (
            f"every conventional scope in {examined} commit(s) "
            f"resolves against alias-map / split / stoplist"
        ), []

    detail = "; ".join(
        f"{sha[:8]} scope={scope!r}" for sha, scope, _ in unmatched[:5]
    )
    if len(unmatched) > 5:
        detail += f"; (+{len(unmatched) - 5} more)"
    evidence = [
        f"{sha[:12]} scope={scope!r} subject={subject!r}"
        for sha, scope, subject in unmatched
    ]
    return "fail", detail, evidence


# ---------------------------------------------------------------------------
# G3 — ADR-ID references in commit bodies
# ---------------------------------------------------------------------------


# Match any ADR-N reference regardless of zero-padding length so a
# commit body that writes ``ADR-7`` is still compared against the
# decision_log (which may declare it as ``ADR-007``). Format-mismatch
# IS the dangling-ref signal callers want G3 to surface.
_ADR_REF_RE = re.compile(r"\bADR-\d+\b")


def _read_decision_log_ids(project_root: Path) -> set[str]:
    """Return the set of ADR ids declared in decision_log.md.

    Looks for the standard agent_docs location; returns an empty set when
    the file is absent (the caller will skip G3 in that case).
    """
    candidate = project_root / ".shipwright" / "agent_docs" / "decision_log.md"
    if not candidate.exists():
        return set()
    try:
        content = candidate.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set()
    headers = adr_headers.parse_adr_headers(content)
    return {h.id for h in headers}


def _check_g3(
    project_root: Path,
    config: dict[str, Any],
) -> tuple[str, str, list[str]]:
    if not git_log_scan.is_git_repo(project_root):
        return "skip", "not a git repository", []

    declared = _read_decision_log_ids(project_root)
    if not declared:
        return "skip", (
            "no .shipwright/agent_docs/decision_log.md "
            "(or no parseable ADR headers)"
        ), []

    pattern = (config.get("b7_exclusions") or {}).get(
        "last_release_tag_pattern", "v*",
    )
    tag = git_log_scan.latest_release_tag(project_root, pattern)
    if tag is None:
        return "skip", f"no release tag matching '{pattern}'", []

    commits = git_log_scan.commits_since_tag(project_root, tag)
    if isinstance(commits, git_log_scan.ScanError):
        return "fail", f"git log failed: {commits.detail}", [commits.detail]
    if not commits:
        return "pass", f"no commits since {tag}", []

    bodies = _git_commit_bodies(project_root, commits)
    dangling: list[tuple[str, str]] = []  # (sha, adr_ref)
    examined = 0
    for sha, body in bodies.items():
        refs = _ADR_REF_RE.findall(body)
        for ref in refs:
            examined += 1
            if ref not in declared:
                dangling.append((sha, ref))

    if examined == 0:
        return "skip", (
            f"no ADR-N refs in {len(commits)} commit body/bodies since {tag}"
        ), []
    if not dangling:
        return "pass", (
            f"every ADR ref in {examined} body-mention(s) is declared"
        ), []

    detail = "; ".join(f"{sha[:8]} → {ref}" for sha, ref in dangling[:5])
    if len(dangling) > 5:
        detail += f"; (+{len(dangling) - 5} more)"
    evidence = [f"{sha[:12]} references {ref}" for sha, ref in dangling]
    return "fail", detail, evidence


# ---------------------------------------------------------------------------
# Top-level run()
# ---------------------------------------------------------------------------


_NAME_BY_CHECK = {
    "G2": "Conventional-commit scope matches alias-map / split / stoplist",
    "G3": "Commit-body ADR refs exist in decision_log.md",
}

_SEVERITY_BY_CHECK = {"G2": "MEDIUM", "G3": "MEDIUM"}


def run(
    project_root: Path,
    config: dict[str, Any] | None,
    _data: Any,
) -> list[Finding]:
    """Run G2 + G3 and return Findings (G-ordered: G2 G3)."""
    cfg = config or {}
    runners: list[tuple[str, Any]] = [
        ("G2", lambda: _check_g2(project_root, cfg)),
        ("G3", lambda: _check_g3(project_root, cfg)),
    ]

    out: list[Finding] = []
    for check_id, fn in runners:
        try:
            status, detail, evidence = fn()
        except Exception as exc:  # noqa: BLE001 — crash isolation
            out.append(Finding(
                group="G", check_id=check_id, name=_NAME_BY_CHECK[check_id],
                severity=_SEVERITY_BY_CHECK[check_id],
                source=SOURCE_DETECTIVE_ONLY, status="fail",
                detail=f"check raised {type(exc).__name__}: {exc}",
            ))
            continue
        out.append(Finding(
            group="G", check_id=check_id, name=_NAME_BY_CHECK[check_id],
            severity=_SEVERITY_BY_CHECK[check_id],
            source=SOURCE_DETECTIVE_ONLY,
            status=status, detail=detail,
            evidence=list(evidence),
            suggested_iterate_cmd=(
                _suggest(check_id, _NAME_BY_CHECK[check_id])
                if status == "fail" else None
            ),
        ))
    return out
