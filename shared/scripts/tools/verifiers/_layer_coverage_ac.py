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

The actual per-FR criteria extraction — anchor matching, checkbox/assertion-
marker stripping, placeholder rejection, continuation lines, whitespace
normalisation — is ``lib.fr_criteria`` (campaign REQ3.04 sub-iterate R0):
this module used to walk it alone, and two OTHER readers (``spec_parser``'s S5,
Group I's I6) each walked their own narrower version. All three now delegate to
the one parser; the section-scoping below (``## Acceptance Criteria`` only, or
the whole document as a fail-safe) stays here because it is specific to this
gate's git-diffing use, not a property of "what is a criterion".
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib import fr_criteria  # noqa: E402

from .git_helpers import _run_git  # noqa: E402


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
    """FR id → digest of that requirement's acceptance criteria.

    ``strict=False``: this gate's own ``test_prose_outside_a_criterion_is_not_a_criterion_change``
    requires a note between the heading and its bullets not to hide them — the
    same documented exception ``group_i_criteria.has_criteria`` makes, tracked
    together in ``lib.fr_criteria``'s module docstring. S5's fallback
    (``leading_criteria``) does not extend that tolerance.
    """
    region = _criteria_region(text)
    digests: dict[str, str] = {}
    for fr_id, block in fr_criteria.iter_anchored_blocks(region):
        joined = "\n".join(fr_criteria.block_criteria(block, strict=False))
        digests[fr_id] = hashlib.sha256(joined.encode("utf-8")).hexdigest()
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
