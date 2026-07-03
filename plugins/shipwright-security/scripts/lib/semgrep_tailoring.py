#!/usr/bin/env python3
"""Accepted-risk Semgrep rule tailoring for the CI self-scan.

Suppresses Semgrep rule classes a repo has formally accepted, WITHOUT weakening
the scan for anyone else. Both channels are opt-in via environment variables and
default OFF, so ``normalize_tailored`` is a pure passthrough of the normalizer
unless a repo opts in. This lives at the producer (mirroring the CodeQL
query-filters and the SARIF-suppression parser) so accepted noise never reaches
findings.json — instead of being dismissed in Triage every week.

Two channels:
  SHIPWRIGHT_SEMGREP_EXCLUDE_RULES
      Comma-separated exact ``check_id``s to drop wholesale. For by-design rules
      with no per-match nuance (e.g. dependabot-missing-cooldown on a dormant
      dependabot config).
  SHIPWRIGHT_SEMGREP_ACCEPT_GH_OWNED_ACTION_TAGS
      Owner-scoped drop of github-actions-mutable-action-tag findings that point
      at a GitHub-owned action (actions/*, github/*) — the declined-SHA-pin
      posture (2026-06-30). UNPINNED THIRD-PARTY actions stay flagged: that is
      the supply-chain guard the rule exists for.

Owner is read from the workflow FILE at the finding's line, NOT from semgrep's
``extra.lines``: semgrep redacts the matched snippet to "requires login" when
run unauthenticated (which is how CI runs it), so the matched line is not a
reliable owner source. When the owner can't be determined (file unreadable,
line out of range, no ``uses:`` value) the finding is KEPT — fail toward the
signal, never silently over-suppress.

Accept register: docs/security-ci-setup.md (§ Accepted-risk rule tailoring).
"""

from __future__ import annotations

import os
import re
from typing import Any

from normalizers.semgrep import normalize

_EXCLUDE_RULES_ENV = "SHIPWRIGHT_SEMGREP_EXCLUDE_RULES"
_ACCEPT_GH_ACTION_TAGS_ENV = "SHIPWRIGHT_SEMGREP_ACCEPT_GH_OWNED_ACTION_TAGS"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
# Registry rule IDs are dot-separated slugs (letters/digits/dot/underscore/
# hyphen). This allowlist rejects path separators, globs and whitespace so a
# CI-config value can never smuggle anything unexpected into the filter.
_RULE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_FORBIDDEN_RULE_IDS = frozenset({".", ".."})

_MUTABLE_TAG_RULE_SUFFIX = "github-actions-mutable-action-tag"
_GITHUB_OWNED_ACTION_OWNERS = frozenset({"actions", "github"})
_USES_RE = re.compile(r"\buses\s*:\s*['\"]?\s*([A-Za-z0-9._@/-]+)")


def normalize_tailored(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """``normalize`` with accepted-risk suppression driven by env vars.

    Both channels default OFF, so with no env set this returns exactly what
    ``normalize`` returns. This is the entry point the OSS backend uses, so the
    CI self-scan honors the repo's accept register; direct callers of
    ``normalize`` are unaffected.
    """
    findings = normalize(raw)

    exclude_ids = _resolve_exclude_rule_ids()
    if exclude_ids:
        findings = [f for f in findings if f.get("rule") not in exclude_ids]

    if _accept_github_owned_action_tags():
        findings = [f for f in findings if not _is_github_owned_action_tag(f)]

    # Renumber so ids stay contiguous after any drops.
    for i, finding in enumerate(findings):
        finding["id"] = f"semgrep-{i + 1:04d}"
    return findings


def _resolve_exclude_rule_ids() -> frozenset[str]:
    """Exact ``check_id``s to drop, from SHIPWRIGHT_SEMGREP_EXCLUDE_RULES.

    Comma-separated; unset/empty -> ``frozenset()`` (nothing dropped). Invalid
    ids (path separators, globs, ``.``/``..``) are skipped, not passed through.
    """
    raw = os.environ.get(_EXCLUDE_RULES_ENV, "")
    if not raw.strip():
        return frozenset()
    out: set[str] = set()
    for candidate in raw.split(","):
        rule_id = candidate.strip()
        if (
            rule_id
            and rule_id not in _FORBIDDEN_RULE_IDS
            and _RULE_ID_RE.match(rule_id)
        ):
            out.add(rule_id)
    return frozenset(out)


def _accept_github_owned_action_tags() -> bool:
    """Whether SHIPWRIGHT_SEMGREP_ACCEPT_GH_OWNED_ACTION_TAGS opts in. Default OFF."""
    return os.environ.get(_ACCEPT_GH_ACTION_TAGS_ENV, "").strip().lower() in _TRUE_VALUES


def _is_github_owned_action_tag(finding: dict[str, Any]) -> bool:
    """True iff a mutable-action-tag finding points at a GitHub-owned action.

    Owner comes from the workflow file at the finding's line (see module
    docstring); an unresolvable owner returns False so the finding is KEPT.
    """
    if not str(finding.get("rule", "")).endswith(_MUTABLE_TAG_RULE_SUFFIX):
        return False
    owner = _action_owner_from_file(
        finding.get("affected_file"), finding.get("affected_line")
    )
    return owner in _GITHUB_OWNED_ACTION_OWNERS


def _action_owner_from_file(path: Any, line: Any) -> str | None:
    """Owner segment (before the first ``/``) of the ``uses:`` ref on ``line``
    of workflow ``path``. None on any read/parse failure (fail-safe KEEP).

    ``path`` is semgrep's cwd-relative path; this runs in the same process (and
    cwd) as the scan, so a plain ``open`` resolves it.
    """
    if not path or not isinstance(line, int) or line < 1:
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            rows = handle.readlines()
    except OSError:
        return None
    if line > len(rows):
        return None
    match = _USES_RE.search(rows[line - 1])
    if not match:
        return None
    return match.group(1).split("@", 1)[0].split("/", 1)[0] or None
