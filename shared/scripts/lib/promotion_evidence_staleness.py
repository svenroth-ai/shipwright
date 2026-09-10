"""The per-FR staleness guard anchor-based promotion needs (P3.4c): promoting
at a verified anchor ``A`` while the tree is at ``HEAD`` asserts "these tests
ran green" from a run at ``A``. Between ``A`` and ``HEAD`` a bound test can
have been deleted, renamed, weakened, or moved to another requirement —
promotion is one-way into hard enforcement, so a stale assertion here is
exactly the defect class the mechanism's own review rounds exist to catch.

**The guard, and it is deterministic — no judgement, no LLM, one git call
per run, not per FR.** :func:`changed_paths_between` runs exactly once for
the whole run (``promote_required_layers.py`` calls it once, reuses the
result for every requirement); :func:`evidence_stale_since_anchor` is then a
pure set-intersection per requirement against that one result — never a
second git invocation per FR (the same "never a sweep, but never a per-FR
git call either" shape ``diff_risk_recheck`` and this module's sibling
``ci_execution_evidence.py`` already both follow for their own single-query
designs).

**Never a bare ``set(values)`` guess at what changed.** ``--no-renames`` is
deliberate, not incidental: rename detection can collapse a moved-and-
modified test file into a single rename entry that omits the OLD path from
``--name-only`` output entirely — and the old path is exactly the bound
path this guard is checking for (a test moved to another requirement, one of
the three invalidating cases the spec names by example, is a rename by
git's own heuristic). ``--no-renames`` reports it as a plain delete-of-old +
add-of-new instead, so the old bound path always appears as "changed" — the
same fail-safe direction (widen what counts as invalidating, never narrow
it) every other guard in this mechanism already takes.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

#: The named ``reason_code`` this guard reports — closed-vocabulary style,
#: matching the sibling constants in ``lib.layer_promotion``.
REASON_EVIDENCE_STALE_SINCE_ANCHOR = "evidence_stale_since_anchor"

_GIT_TIMEOUT_SECONDS = 15

#: Same shape as `ci_provenance._COMMIT_RE` (external code review, low):
#: both commits reach `git diff ... f"{anchor}..{head}"` with no injection
#: guard otherwise. Today's only caller passes `resolve_head_sha`'s or
#: `ci_verified_anchor`'s own validated output, so this is not exploitable
#: now -- validated anyway, matching the sibling predicate's convention.
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")


def bound_test_files(node: dict) -> set[str] | None:
    """The file path (everything before ``::``) of every test link bound to
    this requirement node, across every layer — read from the ANCHOR
    commit's own manifest node (the caller passes that, never HEAD's), since
    that is what the anchor's CI run actually exercised.

    ``None`` — never a silently-incomplete set — when ``tests`` itself, any
    layer's link list, or any individual link, is not the shape this
    function knows how to read (``tests`` not a dict; a layer's value not a
    list; a link not a dict; a ``path``/``id`` that is missing or not a
    string). "Widen what counts as invalidating, never narrow it" (module
    docstring) applies to SHAPE, not only to content: a link this function
    cannot place is a link whose file this run genuinely does not know, and
    treating that as "contributes nothing" would silently narrow the
    invalidating set exactly the wrong way for a mechanism whose own stated
    stakes are "promotion is one-way into hard enforcement." The caller
    (:func:`evidence_stale_since_anchor`) treats ``None`` as unconditionally
    stale.

    ``tests`` reaching here unvalidated is the normal case, not a defect to
    guard against defensively (code-reviewer, medium): unlike an execution
    EVIDENCE node (which ``ci_execution_evidence._execution_shape_error``
    validates), a committed MANIFEST node's ``tests`` block is excluded from
    ``compare_traceability_manifest._structural_view`` entirely
    (``_REQUIREMENT_EXECUTION_KEYS``), so nothing upstream of this function
    ever shape-checks it — a malformed committed manifest reaches here
    exactly as often as a well-formed one."""
    tests = node.get("tests") or {}
    if not isinstance(tests, dict):
        return None
    files: set[str] = set()
    for links in tests.values():
        if not isinstance(links, list):
            return None
        for link in links:
            if not isinstance(link, dict):
                return None
            path = link.get("path") or link.get("id")
            if not (isinstance(path, str) and path):
                return None
            files.add(path.split("::", 1)[0])
    return files


def changed_paths_between(
    anchor_commit: str, head_commit: str, *, project_root: Path | str,
) -> set[str] | None:
    """``git diff --name-only --no-renames <anchor_commit>..<head_commit>``,
    as a set of repo-relative paths. ``None`` on any git failure — a caller
    must fail closed (treat every FR as potentially stale, never proceed as
    though nothing changed)."""
    for label, sha in (("anchor_commit", anchor_commit), ("head_commit", head_commit)):
        if not (isinstance(sha, str) and _COMMIT_RE.fullmatch(sha.lower())):
            print(f"changed_paths_between: {label} {sha!r} is not a 40 char hex SHA", file=sys.stderr)
            return None
    try:
        result = subprocess.run(  # nosec B603,B607 - fixed argv, shell=False
            [
                "git", "-C", str(project_root), "diff", "--name-only", "--no-renames",
                f"{anchor_commit}..{head_commit}",
            ],
            capture_output=True, text=True, timeout=_GIT_TIMEOUT_SECONDS,
            encoding="utf-8", errors="replace", check=False, shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def dirty_or_untracked_paths(*, project_root: Path | str) -> set[str] | None:
    """Every repo-relative path with content differing from committed
    ``HEAD`` right now — staged, unstaged, or untracked — via ``git status
    --porcelain``. ``None`` on any git failure, matching
    :func:`changed_paths_between`'s own fail-closed contract.

    Exists because this tool is never invoked from CI (Tier-3 PR review,
    blocking) — a human-operated CLI, so an uncommitted/untracked edit to a
    bound test file is invisible to :func:`changed_paths_between`'s
    commit-only diff, and the promotion this guard protects writes a
    durable ledger entry CI later trusts without re-checking evidence. The
    caller unions this into the committed diff before
    :func:`evidence_stale_since_anchor` — widen, never narrow, reusing that
    function's own logic rather than a parallel check."""
    try:
        result = subprocess.run(  # nosec B603,B607 - fixed argv, shell=False
            [
                "git", "-C", str(project_root), "status", "--porcelain=v1",
                "--no-renames", "--untracked-files=all",
            ],
            capture_output=True, text=True, timeout=_GIT_TIMEOUT_SECONDS,
            encoding="utf-8", errors="replace", check=False, shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    paths: set[str] = set()
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if path.startswith('"') and path.endswith('"') and len(path) >= 2:
            path = path[1:-1]
        if path:
            paths.add(path)
    return paths


def _looks_like_test_path(path: str) -> bool:
    """Whether ``path`` is shaped like a Python test file by this repo's own
    convention (``tests/`` directories collected by pytest; ``test_*.py``/
    ``*_test.py`` basenames) — used ONLY to widen the staleness guard's
    invalidating set to paths no manifest yet claims are bound to anything
    (see :func:`evidence_stale_since_anchor`'s ``unaccounted`` handling),
    never to decide what IS bound (that stays the manifest's job alone)."""
    normalized = path.replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1]
    if not basename.endswith(".py"):
        return False
    return (
        basename.startswith("test_") or basename.endswith("_test.py")
        or "/tests/" in f"/{normalized}"
    )


def evidence_stale_since_anchor(
    node_at_anchor: dict, ci_node_at_anchor: dict, node_at_head: dict,
    spec_paths: set[str], changed: set[str],
) -> bool:
    """Whether anything that could invalidate ``node_at_anchor``'s evidence
    changed between the anchor and HEAD — the requirement's own bound test
    files (as the ANCHOR's manifest AND its CI evidence both record them),
    its BINDING itself (which files are bound at all), or its spec.md. Per
    FR, not per run: two requirements sharing a spec.md can independently
    promote or skip depending on which one's OWN bound tests moved.

    ``ci_node_at_anchor`` matters independently of ``node_at_anchor``
    (code-reviewer, high): the anchor's COMMITTED manifest node is not
    proof of what the anchor's CI run actually confirmed — ``tests`` is one
    of ``compare_traceability_manifest._REQUIREMENT_EXECUTION_KEYS``,
    excluded from ``structural_diff`` entirely, so
    ``resolve_execution_evidence``'s content-binding check does not vouch
    for the committed manifest's ``tests`` block matching the CI artifact's.
    A test retagged onto this FR between the committed anchor manifest and
    the anchor's actual CI run is structurally invisible and would be
    missing from ``bound_test_files(node_at_anchor)`` alone — silently
    narrowing the invalidating set to exclude a file the anchor's evidence
    genuinely covers. The caller passes the SAME node already used to build
    ``eval_node["tests"]`` for the promotion decision itself (the CI
    evidence artifact's own per-FR entry), so "what the anchor's evidence
    says ran" and "what this guard checks for changes" are provably the
    same source.

    ``node_at_head`` matters independently of the git diff (external plan
    review, glm/medium + openai/high, both independently): the traceability
    MANIFEST is itself a committed, drifting artifact, and a requirement's
    binding can change — a test newly bound to this FR, or unbound from it —
    without the bound file's own bytes ever changing and therefore without
    either file appearing in ``changed`` at all. Comparing only file CONTENT
    changes (the ``changed`` diff) against the anchor's OWN bound set misses
    exactly that: the anchor's CI run verified a *different set of tests*
    than the one HEAD's manifest now asserts is bound to this FR, and
    promoting would assert "these tests ran green" for a binding the anchor
    never actually covered. Any difference between the anchor's and HEAD's
    bound-file sets is therefore unconditionally invalidating, independent
    of the ``changed`` diff.

    ``spec_paths`` is a SET, not a single path (external code review,
    openai/high, on this function's PRIOR round): the anchor's own
    ``spec_path`` and the CURRENT (HEAD) node's ``spec_path`` are both
    invalidating — an FR that moved to a DIFFERENT spec.md between the
    anchor and HEAD must not promote using the anchor's evidence and then
    write into the new file, which the anchor run never covered at all.
    Checking only the anchor's path missed exactly that case; the caller
    passes both (usually identical, so usually a no-op union).

    Unconditionally stale — never merely "nothing matched" — when
    :func:`bound_test_files` returns ``None`` for ANY of the three nodes (an
    unparseable/malformed test link at the anchor's manifest, the anchor's
    CI evidence, or HEAD): the set of files this run needs to compare
    against is itself unknown, and "widen, never narrow" means treating
    that unknown as invalidating rather than as an empty, harmless set.

    **Direct-file staleness only** (external plan review, openai/medium): this
    guard proves the requirement's bound test FILES are byte-identical and
    binding-identical between the anchor and HEAD — it does not, and cannot
    cheaply, prove the tests still behave identically (a shared fixture,
    `conftest.py`, or test-runner config changing underneath an untouched
    bound file is out of scope, by design, per the iterate spec's own stated
    guarantee).

    **Obligation for future evidence inputs** (external architecture review,
    glm/low): any new evidence input added to ``resolve_execution_evidence``
    (beyond ``tests``/``coverage`` bound files and ``spec_path``) must be
    added to this function's invalidating set, or an anchored promotion will
    silently reuse stale evidence for FRs bound to that new input.

    ``node_at_anchor["id"]`` must equal ``node_at_head["id"]`` (Stage-3 doubt
    review, high, defense-in-depth half): both nodes are looked up by the
    same NAMESPACED manifest key, but nothing upstream of this function
    checks that the key still names the same display FR at both commits — a
    corrupted or hand-edited manifest reusing a key across two different
    FRs would otherwise let one FR's identity borrow another's anchor
    evidence undetected.

    **Files the manifest does not yet know are bound are unconditionally
    invalidating too** (Stage-3 doubt review, high, the substantive half):
    every check above compares sets the manifest (at the anchor, or via the
    anchor's own CI evidence) ALREADY claims are bound — none of them can
    ever catch a file that became newly relevant to this FR's binding
    without any manifest ever recording it, which is exactly the "drifted,
    unregenerated HEAD manifest" state this whole mechanism exists to
    operate in. A test file added or edited between the anchor and HEAD that
    is not a member of the anchor's own bound set is therefore ALSO
    invalidating, regardless of whether any manifest names it — conservative
    by construction (widen, never narrow): this can refuse a promotion that
    was genuinely fine (an unrelated FR's new test), but never the reverse.
    Detected via :func:`_looks_like_test_path` (this repo's own pytest
    collection convention — ``tests/`` directories, ``test_*.py``/``*_test.py``
    basenames), not manifest membership, since a newly-bound file is by
    definition absent from every manifest-derived set this function has.
    This is necessarily a run-wide signal, not a per-FR one (no cheap way to
    attribute an as-yet-unbound file to one specific FR without a second git
    call or content inspection per FR, which this guard's own module
    docstring rules out) — every FR sharing this run sees the same
    "unaccounted test-shaped change" fact.
    """
    if node_at_anchor.get("id") != node_at_head.get("id"):
        return True
    bound_anchor_manifest = bound_test_files(node_at_anchor)
    bound_anchor_ci = bound_test_files(ci_node_at_anchor)
    bound_head = bound_test_files(node_at_head)
    if bound_anchor_manifest is None or bound_anchor_ci is None or bound_head is None:
        return True
    bound_anchor = bound_anchor_manifest | bound_anchor_ci
    if bound_anchor != bound_head:
        return True
    unaccounted_test_changes = {
        p for p in changed if _looks_like_test_path(p) and p not in bound_anchor
    }
    if unaccounted_test_changes:
        return True
    invalidating = bound_anchor | {p for p in spec_paths if p}
    return bool(invalidating & changed)


__all__ = [
    "REASON_EVIDENCE_STALE_SINCE_ANCHOR",
    "bound_test_files",
    "changed_paths_between",
    "dirty_or_untracked_paths",
    "evidence_stale_since_anchor",
]

# `_looks_like_test_path` is intentionally NOT exported -- it exists only to
# widen `evidence_stale_since_anchor`'s own invalidating set and is not a
# general-purpose "is this a test file" classifier for other callers.
