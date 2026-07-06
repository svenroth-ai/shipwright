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

The owner-scoped predicate itself lives in the shared leaf module
``gh_action_tag_owner`` so the triage / Control-Grade artifact-ingest path
(``shared/scripts/security_findings.py``) applies the IDENTICAL accepted-risk
drop to the raw SARIF adopted repos upload — the plugin local scan was the only
place it fired before. The helpers below stay as thin wrappers over that module
so callers importing them are unaffected.

Accept register: docs/security-ci-setup.md (§ Accepted-risk rule tailoring).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

from normalizers.semgrep import normalize

# Shared leaf util (unique top-level name, never ``lib.*`` — ADR-045). Bootstrap
# ``shared/scripts`` onto sys.path the same way the plugin's tools reach shared.
_SHARED_SCRIPTS = Path(__file__).resolve().parents[2].parent.parent / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from gh_action_tag_owner import (  # noqa: E402
    accept_github_owned_action_tags,
    action_owner_from_file,
    is_github_owned_owner,
    is_mutable_action_tag_rule,
)

_EXCLUDE_RULES_ENV = "SHIPWRIGHT_SEMGREP_EXCLUDE_RULES"
# Registry rule IDs are dot-separated slugs (letters/digits/dot/underscore/
# hyphen). This allowlist rejects path separators, globs and whitespace so a
# CI-config value can never smuggle anything unexpected into the filter.
_RULE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_FORBIDDEN_RULE_IDS = frozenset({".", ".."})


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
    """Whether SHIPWRIGHT_SEMGREP_ACCEPT_GH_OWNED_ACTION_TAGS opts in. Default OFF.

    Thin wrapper over ``gh_action_tag_owner.accept_github_owned_action_tags``.
    """
    return accept_github_owned_action_tags()


def _is_github_owned_action_tag(finding: dict[str, Any]) -> bool:
    """True iff a mutable-action-tag finding points at a GitHub-owned action.

    Owner comes from the workflow file at the finding's line (see module
    docstring); an unresolvable owner returns False so the finding is KEPT.
    """
    if not is_mutable_action_tag_rule(finding.get("rule")):
        return False
    owner = _action_owner_from_file(
        finding.get("affected_file"), finding.get("affected_line")
    )
    return is_github_owned_owner(owner)


def _action_owner_from_file(path: Any, line: Any) -> str | None:
    """Owner of the ``uses:`` ref on ``line`` of workflow ``path`` — cwd-relative,
    because the local scan runs in the scan's own cwd. Thin wrapper over
    ``gh_action_tag_owner.action_owner_from_file``; None on any failure (KEEP)."""
    return action_owner_from_file(path, line)
