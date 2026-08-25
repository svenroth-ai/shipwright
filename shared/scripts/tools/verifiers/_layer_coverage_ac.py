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


#: Any heading level names the section — `/shipwright-adopt` emits ``##
#: Acceptance Criteria`` (top-level); `/shipwright-project`'s own template
#: (``spec-generation.md:305``, both the abstract template and its worked
#: example) nests it one level deeper, ``### Acceptance Criteria``, under
#: ``## 2. Functional Requirements``. A level-2-only regex never matched
#: the real, shipped shape a project-generated spec.md uses, so THIS reader
#: fell back to whole-document scanning on every one of them — not a rare
#: exception but the normal path (Stage-3 doubt review, medium, 2026-08-25).
_AC_HEADING_RE = re.compile(r"^(#{1,6})\s+Acceptance Criteria\s*$", re.MULTILINE)


def _criteria_region(text: str) -> str:
    """The ``Acceptance Criteria`` section (any heading level), or the
    whole document.

    Bullets elsewhere are not criteria — a requirement discussed under some other
    top-level section, with a list of implementation notes, must not read as a
    criteria change, because post-rollout that is a HARD gate demanding
    executed-passing tests (external code review).

    The fallback is deliberate and is the safe direction: a spec that names its
    criteria some other way is scanned whole rather than yielding nothing. Going
    SILENT is the one outcome worse than over-firing. That fallback is meant to
    be a genuine LAST resort, though — not the path every real ``/shipwright-
    project`` spec takes because the heading match was too narrow; the region
    terminates at the next heading of the SAME OR HIGHER rank — required to be
    followed by whitespace, matching the SPIRIT of
    ``fr_criteria._ANY_HEADING``'s own rule (a bare ``#`` with no trailing
    space — a fenced code comment, a shell shebang — must never masquerade as
    a terminator). Not byte-identical to it, though: this ``\\s`` runs against
    raw multi-line text (so it can match a newline, terminating on a
    hash-only line at column 0 — a shape no real producer or this repo's own
    catalog emits, verified directly), where ``_ANY_HEADING`` requires
    ``\\s+`` against an already newline-stripped line (Stage-3 doubt review,
    medium, 2026-08-25; wording corrected 2026-08-25 — the two were not
    actually byte-identical as first claimed).

    A per-FR subheading shape — ``### FR-04.01`` / ``#### Acceptance
    Criteria`` / bullets, REPEATED per FR (the exact shape
    ``group_i_criteria``'s own
    ``test_deeper_subheading_stays_inside_the_block`` pins as supported) —
    makes ``_AC_HEADING_RE.search`` first-match the DEEPEST FR's own
    "Acceptance Criteria" subheading, then same-rank termination fires on the
    very next FR heading: the "found" region collapses to one FR's bullets
    with no anchor line inside it at all, and ``criteria_digests`` returns
    ``{}`` for the WHOLE document — silencing this HARD gate, worse than the
    old level-2-only regex's honest whole-document fallback (Stage-3 doubt
    review, high, 2026-08-25). Guarded against by comparing the region's own
    anchor set to the whole document's: a "found" region must never see
    STRICTLY FEWER FR ids than scanning the whole document would.
    """
    heading = _AC_HEADING_RE.search(text or "")
    if not heading:
        return text or ""
    level = len(heading.group(1))
    rest = text[heading.end():]
    following = re.search(rf"^#{{1,{level}}}(?!#)\s", rest, re.MULTILINE)
    region = rest[:following.start()] if following else rest

    # `region` is always a literal slice of `text`, so any anchor line found
    # scanning it is also found scanning the whole document — region_ids is
    # therefore ALWAYS a subset of whole_ids; a real mismatch can only mean
    # the region lost anchors the whole document has (never gained any).
    region_ids = {fr_id for fr_id, _ in fr_criteria.iter_anchored_blocks(region)}
    whole_ids = {fr_id for fr_id, _ in fr_criteria.iter_anchored_blocks(text or "")}
    if region_ids != whole_ids:
        return text or ""
    return region


def criteria_digests(text: str) -> dict[str, str]:
    """FR id → digest of that requirement's acceptance criteria.

    ``strict=False``: this gate's own ``test_prose_outside_a_criterion_is_not_a_criterion_change``
    requires a note between the heading and its bullets not to hide them — the
    same documented exception ``group_i_criteria.has_criteria`` makes, tracked
    together in ``lib.fr_criteria``'s module docstring. S5's fallback
    (``leading_criteria``) does not extend that tolerance.

    POOLS every block anchored to the same id (external code review, medium,
    2026-08-25) — the same rule ``fr_criteria.criteria_for`` already applies.
    ``iter_anchored_blocks``'s anchor surface (any heading level, plus the
    bold form, plus a looser id shape) makes a doubly-anchored id materially
    more likely than the old, narrower ``_FR_SECTION_RE`` did; a last-write-wins
    assignment let a criteria-bearing block be silently overwritten by a LATER,
    empty one for the same id, collapsing the digest to the empty-criteria
    value and making this HARD gate see "no change" when there was one.
    """
    region = _criteria_region(text)
    texts_by_id: dict[str, list[str]] = {}
    for fr_id, block in fr_criteria.iter_anchored_blocks(region):
        # Per-block, THEN pool the resulting texts (matches criteria_for's own
        # pattern) — never concatenate raw lines across a block boundary,
        # which could misread block B's leading indented line as a
        # continuation of block A's last, still-open bullet.
        texts_by_id.setdefault(fr_id, []).extend(
            fr_criteria.block_criteria(block, strict=False),
        )
    digests: dict[str, str] = {}
    for fr_id, texts in texts_by_id.items():
        joined = "\n".join(texts)
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
