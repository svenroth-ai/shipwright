"""Per-requirement acceptance-criteria digests, read straight out of git.

Why this exists (iterate-2026-07-27-name-the-blocker): the cross-layer gate
resolved behaviour change from the FR **table row** — title and required_layers.
`shared/fr-authoring.md` §3 makes FOLDING the common case, though: when a change
completes, fixes or extends an existing capability you append an acceptance
criterion to the requirement rather than mint a row. Such a change leaves the row
byte-identical, so it always landed in "no FR-row-level behaviour change was
determinable". The gate was blind to precisely the authoring pattern the
framework recommends.

**No manifest change.** The traceability manifest is a frozen contract
(``additionalProperties: false`` at root and requirement level; the committed
artifact is churn-allowlisted), and it deliberately carries no AC prose. It does
not need to: every requirement node already carries ``spec_path``, and the base
commit is already resolved for the regeneration, so the criteria can be read from
git directly. Nothing about the artifact or its schema moves.

Two rules the parser follows, both narrower than "diff the section":

* **A criterion includes its continuation lines.** This repo's own `(E)` bullets
  wrap, and the guarantee often lives on the second line.
* **Only criteria count.** Prose around them is excluded, because in a
  post-rollout repo a resolved change is a HARD gate and a typo fix must not
  demand executed-passing tests. Criteria text is whitespace-normalised, so
  re-wrapping a paragraph is not a change either.
"""

from __future__ import annotations

import hashlib
import re

from .git_helpers import _run_git

#: A requirement's own section in a spec: ``### FR-XX.YY — Title``. The anchor and
#: the id form are the ones both generators emit and the manifest schema pins.
_FR_SECTION_RE = re.compile(r"^###\s+(?P<fr>FR-\d{2}\.\d{2})\b", re.MULTILINE)

#: A criterion bullet: ``-``/``*``/``+`` or ``1.``, incl. the ``- [ ]`` checkbox
#: form used by the worked example in ``shared/fr-authoring.md`` §3.
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?P<text>.*\S)\s*$")


def _criteria(body: str) -> list[str]:
    """The section's criteria, each whitespace-normalised and including any
    continuation lines that belong to it."""
    out: list[str] = []
    current: list[str] | None = None
    for line in body.splitlines():
        bullet = _BULLET_RE.match(line)
        if bullet:
            if current is not None:
                out.append(" ".join(current))
            current = [bullet.group("text")]
            continue
        if current is None:
            continue
        if not line.strip() or not line[:1].isspace():
            # A blank line, or a line starting in column 0, ends the criterion.
            out.append(" ".join(current))
            current = None
            continue
        current.append(line.strip())
    if current is not None:
        out.append(" ".join(current))
    return [" ".join(c.split()) for c in out]


def _criteria_region(text: str) -> str:
    """The ``## Acceptance Criteria`` section, or the whole document.

    Bullets elsewhere are not criteria — a requirement discussed under some other
    top-level section, with a list of implementation notes, must not read as a
    criteria change, because post-rollout that is a HARD gate demanding
    executed-passing tests (external code review).

    The fallback is deliberate and is the safe direction: a spec that names its
    criteria some other way is scanned whole rather than yielding nothing. Going
    SILENT is the one outcome worse than over-firing.
    """
    heading = re.search(r"^##\s+Acceptance Criteria\s*$", text or "", re.MULTILINE)
    if not heading:
        return text or ""
    rest = text[heading.end():]
    following = re.search(r"^##(?!#)", rest, re.MULTILINE)
    return rest[:following.start()] if following else rest


def criteria_digests(text: str) -> dict[str, str]:
    """FR id → digest of that requirement's acceptance criteria."""
    region = _criteria_region(text)
    matches = list(_FR_SECTION_RE.finditer(region))
    digests: dict[str, str] = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(region)
        joined = "\n".join(_criteria(region[match.end():end]))
        digests[match.group("fr")] = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return digests


def spec_text_at(project_root, sha: str, path: str) -> str | None:
    """The file's content at ``sha``; ``""`` when absent there; ``None`` when it
    could not be read.

    The three-way answer is the point. Collapsing "cannot read history" into
    ``""`` would make a broken repository look like a spec with no criteria, and
    the gate would then conclude that nothing changed — a false green in exactly
    the situation where it should fail closed.
    """
    if not sha or not path:
        return None
    # Does the blob exist at that commit? A missing path is a real answer (a new
    # spec file); a git failure on a path that IS there is an infrastructure gap.
    rc, _, _ = _run_git(project_root, "cat-file", "-e", f"{sha}:{path}")
    if rc != 0:
        rc_commit, _, _ = _run_git(project_root, "rev-parse", "--verify", f"{sha}^{{commit}}")
        return "" if rc_commit == 0 else None
    rc, out, _ = _run_git(project_root, "show", f"{sha}:{path}")
    return out if rc == 0 else None


def _spec_paths(*manifests: dict) -> list[str]:
    """Every ``spec_path`` named by either manifest — the union, so a spec that
    was renamed or added between base and head is still compared."""
    paths: set[str] = set()
    for manifest in manifests:
        for node in (manifest.get("requirements") or {}).values():
            if isinstance(node, dict) and node.get("spec_path"):
                paths.add(str(node["spec_path"]))
    return sorted(paths)


def changed_criteria_ids(
    project_root, base_sha: str, head_sha: str, base: dict, head: dict,
) -> tuple[set[str], str]:
    """``(fr_ids_whose_criteria_changed, error)``.

    ``error`` is a non-empty reason when a spec could not be read at one side;
    the caller renders that as an infrastructure failure (blocking at medium+)
    rather than as "nothing changed".
    """
    changed: set[str] = set()
    for path in _spec_paths(base, head):
        base_text = spec_text_at(project_root, base_sha, path)
        head_text = spec_text_at(project_root, head_sha, path)
        if base_text is None or head_text is None:
            side = "base" if base_text is None else "head"
            return set(), f"could not read {path} at {side} commit"
        base_digests = criteria_digests(base_text)
        head_digests = criteria_digests(head_text)
        for fr in set(base_digests) | set(head_digests):
            if base_digests.get(fr) != head_digests.get(fr):
                changed.add(fr)
    return changed, ""


__all__ = ["criteria_digests", "spec_text_at", "changed_criteria_ids"]
