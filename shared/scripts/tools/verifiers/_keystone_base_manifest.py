"""Read the traceability manifest AT THE BASE COMMIT — THE KEYSTONE GATE's other
trust boundary (P3.6, design §5.3).

Its own module because it shares nothing with per-AC digesting but the failure
philosophy: this reads a JSON artifact out of git, that reads criteria out of
markdown. What they DO share is :class:`ReadError`, which lives here because
this is the file whose whole subject is telling a real fault apart from an
honest absence.

**Why the base manifest is read at all.** Head-only binding resolution made
`deleting the ``/ACnn`` suffix from one ``@covers`` tag` convert a HARD block
into a silent exit 0 — the gate's central dodge, arriving through the binding
side instead of the marker side. A link count at base is a *structural* claim,
not an execution claim, and base is an ancestor of the default branch, so it
needs no regeneration to be trustworthy.
"""

from __future__ import annotations

import json
from pathlib import Path

from .git_blob_read import read_committed_text
from .git_helpers import _run_git

MANIFEST_RELPATH = ".shipwright/compliance/test-traceability.json"

__all__ = ["MANIFEST_RELPATH", "ReadError", "read_base_manifest", "require_manifest_shape"]


class ReadError(Exception):
    """A genuine infrastructure fault — the CLI maps this to exit 2, never to a
    green 'nothing changed'."""


def require_manifest_shape(manifest: dict, where: str) -> dict:
    """Fail closed on a manifest that is valid JSON but not a manifest.

    External code review (openai, medium). Every reader of a parsed manifest —
    ``_keystone_core._links_for``, ``_keystone_ac_digest._spec_paths``,
    ``_layer_coverage_core._active_nodes`` — spells the lookup
    ``(manifest.get("requirements") or {}).values()``. That idiom is safe for
    *missing* and *falsy*, and raises ``AttributeError`` for a truthy non-mapping:
    ``{"requirements": []}`` after a schema change, or a list-shaped export.
    Uncaught, that is a Python exit **1 with no JSON at all** — indistinguishable
    at the CI-log level from a real hard finding, so an author would go editing a
    spec that is fine (the same misroute the ``EmptyLinkWalk`` catch fixed).

    Validating ONCE at each read boundary, rather than defensively at each of the
    three call sites, is deliberate: a per-site guard would have to choose a
    fallback, and every available fallback ("treat as zero links") is the silent
    zero this whole module argues against.

    The key must also be PRESENT. A parsed object with no ``requirements`` at all
    is not an older manifest — the honestly-old case is the absent-file branch of
    :func:`read_base_manifest`, which returns ``{}`` with a warning under its own
    JSON key — it is a truncated or wrong file, and reading it as "no requirements
    exist" disarms ``binding_removed`` for every AC in the PR.

    **The walk goes THREE levels deep, not one** (Tier-3 PR review, blocking —
    the first version of this function stopped at the top level and the tests
    stopped with it). ``_links_for`` spells the same fragile idiom twice more:
    ``(node.get("acs") or {}).get(ac_id)`` and
    ``(ac_node.get("tests") or {}).values()``. So ``{"acs": []}`` or
    ``{"tests": []}`` reproduced the exact crash one and two levels down. A
    NON-MAPPING node or AC node is skipped rather than rejected, because every
    reader already guards those with ``isinstance(..., dict)`` — validating what
    the readers do not guard, and only that, is what keeps this from becoming a
    second, drifting copy of the manifest schema.
    """
    requirements = manifest.get("requirements")
    if not isinstance(requirements, dict):
        if requirements is None and "requirements" not in manifest:
            raise ReadError(
                f"{MANIFEST_RELPATH} {where} has no 'requirements' key -- it parses as JSON but "
                "is not a traceability manifest. Reading it as 'no requirements exist' would "
                "silently zero every base link count, so this is an infrastructure fault."
            )
        raise ReadError(
            f"{MANIFEST_RELPATH} {where} has a 'requirements' value of type "
            f"{type(requirements).__name__}, not an object."
        )
    for key, node in requirements.items():
        if not isinstance(node, dict):
            continue  # every reader skips a non-mapping node already
        acs = node.get("acs")
        if acs is not None and not isinstance(acs, dict):
            raise ReadError(
                f"{MANIFEST_RELPATH} {where}: requirements[{key!r}].acs is of type "
                f"{type(acs).__name__}, not an object."
            )
        for ac_id, ac_node in (acs or {}).items():
            if not isinstance(ac_node, dict):
                continue  # _links_for skips a non-mapping AC node already
            tests = ac_node.get("tests")
            if tests is not None and not isinstance(tests, dict):
                raise ReadError(
                    f"{MANIFEST_RELPATH} {where}: requirements[{key!r}].acs[{ac_id!r}].tests is "
                    f"of type {type(tests).__name__}, not an object."
                )
    return manifest


def read_base_manifest(project_root: Path, base_sha: str) -> tuple[dict, str]:
    """``(manifest, warning)`` — the committed manifest AT ``base_sha``.

    THREE-WAY and fail-closed. ``check_agent_doc_budget._base_text`` and
    ``anti_ratchet.measure_staged`` both default a failed base read to
    permissive/empty; doing that HERE would silently make ``base_links == 0`` for
    every AC on any read failure, which (a) disarms ``_keystone_core``'s
    ``binding_removed`` (the AC falls to ``unbound`` -> exit 0, reopening the
    delete-the-``/ACnn``-suffix dodge) and (b) collapses the caller's
    ``_spec_paths(head, base)`` union back to head-only. So:

    * the path is genuinely ABSENT at a VALID base commit -> ``({}, warning)``.
      The caller surfaces the warning under its own JSON key, so the (real, and
      exploitable-looking) degradation is LOGGED rather than silently inferred;
    * the blob EXISTS but is unreadable / unparseable / not an object ->
      ``ReadError``. A corrupt existing manifest is a genuine infra fault,
      categorically unlike an honestly-absent one;
    * git fails any other way -> ``ReadError``.

    The absent-vs-broken split is ``git_blob_read.read_committed_text``'s, not a
    local ``git show``: that module exists because ``git show <sha>:<path>``
    conflates the two outcomes into one non-zero exit, AND makes git stat
    ``<cwd>/<sha>:<path>``, which crosses Windows' 260-char ``MAX_PATH`` in this
    very repo — a gate built on it passes on a shallow checkout and fails on a
    deep one. Reading by blob OID carries no path in the argument at all.
    """
    if not base_sha:
        raise ReadError("no base commit was resolved")
    body, err = read_committed_text(project_root, base_sha, MANIFEST_RELPATH)
    if err:
        raise ReadError(err)
    if body is None:
        rc_commit, _, _ = _run_git(project_root, "rev-parse", "--verify", f"{base_sha}^{{commit}}")
        if rc_commit != 0:
            raise ReadError(f"base commit {base_sha!r} could not be resolved by git")
        return {}, (
            f"{MANIFEST_RELPATH} does not exist at base commit {base_sha[:12]} -- every AC reads "
            "as having zero links at base, so binding_removed cannot fire for this PR and the "
            "spec-path scan degrades to head-only. Expected only for a branch point predating the "
            "compliance manifest."
        )
    try:
        manifest = json.loads(body)
    except ValueError as exc:
        raise ReadError(f"{MANIFEST_RELPATH} at {base_sha[:12]} is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ReadError(f"{MANIFEST_RELPATH} at {base_sha[:12]} is not a JSON object")
    return require_manifest_shape(manifest, f"at {base_sha[:12]}"), ""
