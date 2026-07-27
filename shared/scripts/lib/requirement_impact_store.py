"""Where a requirement-impact declaration lives, and how it is read back.

Split from :mod:`lib.requirement_impact` so the rule stays filesystem-free (and
both stay inside the 300-line limit). The rule answers *is this declaration
valid*; this module answers *where does it go and what is on disk*.

**One file per declaration, not one shared append-log.** The first design used a
single tracked ``requirement-impact.jsonl``; external review attacked that choice
from four directions at once — concurrent append tearing when design and build
write together, an undefined merge-conflict policy for a new tracked append-log,
corruption that hides rather than names itself, and a scope identity
(``round-1``) that recurs across runs so a stale row could satisfy a later run's
completion gate.

A file per declaration answers all four structurally rather than with machinery:

* distinct filenames cannot interleave and cannot conflict, so this artifact
  needs no ``merge=union`` entry and no churn-resolver participation;
* identity lives in the filename, so one declaration per ``(run_id, phase,
  scope)`` is a filesystem property and a stale round from an earlier run can
  never satisfy this run's gate;
* a damaged file is isolated and *nameable* instead of poisoning a shared log.

Mirrors the established ``.shipwright/agent_docs/iterates/<run_id>.json`` shape.

Origin: trg-e9e5188e (FR-01.04, FR-01.05).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from lib.requirement_impact import PLANNING_ROOT

#: Where declarations live, under the canonical planning home — which the
#: gitignore re-include block already tracks, so this needs no gitignore change.
DECLARATION_DIRNAME = f"{PLANNING_ROOT}/requirement-impact"

#: Filename component separator. Two underscores because a run_id and a scope
#: may each contain single ones.
_FIELD_SEP = "__"

#: Characters allowed in a filename component; everything else collapses to "-".
_UNSAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

#: Git writes these when a merge could not be resolved. A declaration file
#: carrying one is damaged, and saying so beats reporting "missing". Anchored to
#: line starts: an unanchored scan would condemn a valid record whose 280-char
#: reason happens to contain "=======".
_CONFLICT_MARKER_RE = re.compile(r"^(<{7}|={7}|>{7})(\s|$)", re.MULTILINE)


def declaration_dir(project_root) -> Path:
    """The declaration directory for ``project_root``. Does NOT create it."""
    return Path(project_root) / DECLARATION_DIRNAME


def _safe_component(value) -> str:
    """Collapse anything path-unsafe so a scope can never escape the directory."""
    cleaned = _UNSAFE_FILENAME_RE.sub("-", str(value or "").strip())
    cleaned = cleaned.replace("..", "-").strip("-.")
    return cleaned or "unnamed"


def declaration_filename(run_id, phase, scope) -> str:
    """The ``(run_id, phase, scope)`` identity, as one path-safe filename.

    Identity in the filename is what makes a stale declaration harmless: a
    ``round-1`` recorded by an earlier run lands in a different file, so it can
    never satisfy this run's completion gate. It also makes "one declaration per
    unit" a filesystem property rather than a rule somebody has to enforce.

    A short digest of the RAW tuple is appended because sanitization is lossy —
    ``round/1`` and ``round-1`` both collapse to ``round-1``, and a run_id
    containing ``__`` can straddle the field separator. Without the digest those
    distinct identities would silently overwrite one another, which is precisely
    the "a duplicate is a detectable overwrite" property this design claims.
    """
    # NUL-joined: it cannot occur inside any of the three components, so
    # no two distinct identities can serialize to the same digest input.
    raw = chr(0).join(str(part) for part in (run_id, phase, scope))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    stem = _FIELD_SEP.join(_safe_component(part) for part in (run_id, phase, scope))
    return f"{stem}{_FIELD_SEP}{digest}.json"


def read_declarations(directory) -> tuple[list[dict], list[dict]]:
    """Return ``(records, problems)`` for every declaration in ``directory``.

    Damage is **named, never skipped**: a file that will not parse, or that still
    carries merge-conflict markers, becomes a ``{"path", "error"}`` problem.
    Silently dropping it would make a corrupt declaration look identical to an
    absent one, so a completion gate would report "you never declared this" when
    the truth is "your record is damaged" — two different remedies.

    A missing directory is not damage; it yields two empty lists.
    """
    records: list[dict] = []
    problems: list[dict] = []
    root = Path(directory)
    if not root.is_dir():
        return records, problems

    for path in sorted(root.glob("*.json")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # UnicodeDecodeError is a ValueError, not an OSError: a declaration
            # re-saved as UTF-16 (Notepad / PowerShell 5.1 redirection) used to
            # escape as a traceback whose exit code is the SAME as "this rule was
            # violated". Damage must be named, including this kind.
            problems.append({"path": str(path), "error": f"unreadable: {exc}"})
            continue
        if _CONFLICT_MARKER_RE.search(text):
            problems.append({
                "path": str(path),
                "error": "unresolved merge conflict markers — repair this file",
            })
            continue
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            problems.append({"path": str(path), "error": f"invalid JSON: {exc}"})
            continue
        if not isinstance(data, dict):
            problems.append({"path": str(path), "error": "not a JSON object"})
            continue
        records.append(data)
    return records, problems


def find_declaration(directory, *, run_id, phase, scope) -> tuple[dict | None, list[dict]]:
    """Return ``(declaration | None, problems)`` for one exact identity.

    Matches on the recorded fields rather than the filename so a hand-written
    record still resolves; the filename remains the collision-avoidance
    mechanism, not the lookup key.

    **Problems are returned, not swallowed.** An earlier version discarded them,
    which reproduced in the only production consumer exactly the failure this
    module's storage design exists to prevent: a corrupt declaration became
    indistinguishable from an absent one, so a gate would report "you never
    declared this" when the truth is "your record is damaged" — two different
    remedies. Callers must surface a non-empty ``problems`` rather than treating
    the ``None`` as a clean miss.
    """
    records, problems = read_declarations(directory)
    for record in records:
        if (record.get("run_id") == run_id
                and record.get("phase") == phase
                and record.get("scope") == scope):
            return record, problems
    return None, problems
