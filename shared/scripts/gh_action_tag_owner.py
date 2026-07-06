#!/usr/bin/env python3
"""Owner-scoped predicate for ``github-actions-mutable-action-tag`` findings.

Lifted out of ``plugins/shipwright-security/scripts/lib/semgrep_tailoring.py`` so
BOTH the plugin's CI self-scan tailoring AND the shared triage / Control-Grade
artifact-ingest path (``security_findings._findings_from_sarif``) can apply the
SAME accepted-risk drop: the declined-SHA-pin posture (framework decision
2026-06-30) formally accepts mutable tags on GitHub-owned actions
(``actions/*``, ``github/*``). UNPINNED THIRD-PARTY actions stay flagged — that
is the supply-chain guard the rule exists for.

Both channels are opt-in via ``SHIPWRIGHT_SEMGREP_ACCEPT_GH_OWNED_ACTION_TAGS``
and default OFF, so nothing is dropped unless a repo opts in.

Leaf module: stdlib-only, so it imports cleanly from ``shared/scripts/`` (a
sibling top-level import) and from the plugin (via the ``shared/scripts``
sys.path bootstrap, by this UNIQUE top-level name — never ``lib.*``, to avoid the
ADR-045 ``lib`` sys.modules collision in cross-plugin pytest).

Owner is read from the workflow FILE at the finding's line, NOT from the
scanner's matched snippet: semgrep redacts the snippet to "requires login" when
run unauthenticated (as CI does), and a SARIF ``region.snippet`` is redacted the
same way. When the owner can't be determined — file unreadable, line out of
range, no ``uses:`` value, or (at the ingest path) no ``workflow_base`` to
resolve the repo-relative path against — the caller KEEPS the finding: fail
toward the signal, never silently over-suppress.

Accept register: docs/security-ci-setup.md (§ Accepted-risk rule tailoring).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

ACCEPT_GH_ACTION_TAGS_ENV = "SHIPWRIGHT_SEMGREP_ACCEPT_GH_OWNED_ACTION_TAGS"
# Registry rule ids are dot-separated and doubled (…mutable-action-tag.
# github-actions-mutable-action-tag); a suffix match is stable across the
# check_id (plugin normalizer) and the SARIF ruleId (ingest path).
MUTABLE_TAG_RULE_SUFFIX = "github-actions-mutable-action-tag"
GITHUB_OWNED_ACTION_OWNERS = frozenset({"actions", "github"})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_USES_RE = re.compile(r"\buses\s*:\s*['\"]?\s*([A-Za-z0-9._@/-]+)")


def accept_github_owned_action_tags(environ: Any = None) -> bool:
    """Whether the opt-in env var enables the GH-owned drop. Default OFF."""
    env = os.environ if environ is None else environ
    return env.get(ACCEPT_GH_ACTION_TAGS_ENV, "").strip().lower() in _TRUE_VALUES


def is_mutable_action_tag_rule(rule_id: Any) -> bool:
    """True iff ``rule_id`` is the mutable-action-tag rule (suffix match)."""
    return str(rule_id or "").endswith(MUTABLE_TAG_RULE_SUFFIX)


def is_github_owned_owner(owner: Any) -> bool:
    """True iff ``owner`` is a GitHub-owned action namespace (actions/github)."""
    return owner in GITHUB_OWNED_ACTION_OWNERS


def action_owner_from_file(
    path: Any, line: Any, base_dir: Any = None
) -> str | None:
    """Owner segment (before the first ``/``) of the ``uses:`` ref on ``line``
    of workflow ``path``. ``None`` on any read/parse failure (fail-safe KEEP).

    ``base_dir`` resolves a repo-relative ``path`` at the triage/grade ingest
    path (the workflow files live in the checked-out repo, not the downloaded
    SARIF artifact). Under a ``base_dir`` the ingest contract is enforced: a
    ``path`` that is absolute or escapes the base with ``..`` is rejected
    (returns ``None`` → KEEP), so a crafted SARIF ``uri`` can't resolve outside
    the repo and over-suppress a finding via an unrelated workflow line. Left
    ``None``, ``path`` is opened as-is — the plugin's local-scan path runs in the
    same cwd as the scan and passes its own (possibly absolute) affected-file.
    """
    if not path or not isinstance(line, int) or line < 1:
        return None
    if base_dir is not None:
        if os.path.isabs(path) or ".." in Path(str(path)).parts:
            return None
        target = Path(base_dir) / path
    else:
        target = Path(path)
    try:
        rows = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if line > len(rows):
        return None
    match = _USES_RE.search(rows[line - 1])
    if not match:
        return None
    return match.group(1).split("@", 1)[0].split("/", 1)[0] or None


def is_github_owned_action_tag(
    rule_id: Any, path: Any, line: Any, base_dir: Any = None
) -> bool:
    """True iff a finding is a mutable-action-tag pointing at a GitHub-owned
    action. An unresolvable owner returns ``False`` so the finding is KEPT."""
    if not is_mutable_action_tag_rule(rule_id):
        return False
    return is_github_owned_owner(action_owner_from_file(path, line, base_dir))
