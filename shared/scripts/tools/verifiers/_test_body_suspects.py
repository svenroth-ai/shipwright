"""TEST-BODY SUSPECT detector — the third, lower-priority item P3.7's own
sub-iterate spec named and explicitly deferred (campaign
``req3-04c-ac-identity-wave2``; design:
``.shipwright/planning/iterate/2026-09-10-p3-7-feeder-checks.md``, "Deferred"
section), delivered here bundled with p3.8 (provenance: ``trg-d03a239d``,
filed at p3.8's own finalization after the original bundling-authorization
card id could not be found in the tracked triage store).

**ADVISORY, never a hard gate — by the same class-level rule P3.6's own
design doc names (§7) and P3.8's own sub-iterate spec restates verbatim:
"mechanics raise the flag, a human decides."** Unlike its P3.7 siblings
(``check_ac_coverage_ratchet.py``, ``check_orphan_ac_binding.py``), which are
HARD or ratcheted gates, nothing here may ever block a merge — see
``check_test_body_suspects.py``'s own module docstring for how that is
enforced at the CLI boundary (an unconditional ``exit 0``, not merely a
convention).

**The predicate.** An AC whose own criterion digest is UNCHANGED between base
and head (the same "no text edit happened" test ``_ac_binding_regression``
already computes), that has >=1 test bound to it at head, where that bound
test's own FUNCTION BODY digest changed between base and head. A test can be
edited for entirely legitimate reasons (a refactor, a better assertion
message, an unrelated fixture change) — this check cannot and does not judge
that; it only surfaces the co-occurrence for a human to look at, exactly the
same "signal, not verdict" spirit P3.6's ``binding_removed`` finding already
carries for a DIFFERENT case (the criterion's own text changing).

**Reuses, never reimplements** (the same brief P3.7(a)/(b) already followed):
``_ac_binding_regression.head_and_base_minted`` for the per-``(fr, ac)``
criterion digest at both commits (the exact "unchanged" test this check
needs), ``_keystone_links.links_for`` for the bound test ids, and
``_layer_coverage_ac.spec_text_at`` for the base/head file reads — the same
git-blob reader every sibling in this family already uses, so a test file
that is uncommitted, renamed, or otherwise not on disk in the exact worktree
shape is read identically to how the criterion text itself is read.

**What "the test body" means here.** The manifest's own link ``id`` (and
``path``, byte-identical to ``id`` — ``_keystone_links.links_for``'s own
callers already treat them as the one field) is a pytest node id:
``<file>::<name>`` for a module-level function, or
``<file>::<Class>::<name>`` for a method. This module locates that exact
``def``/``async def`` by walking the AST from the module body down through
any named ``ClassDef``s, and digests the verbatim source segment
(``ast.get_source_segment``) — not a normalized/AST-only comparison, so a
change that is byte-identical after, say, black-reformatting still reads as
unchanged (a real edit rarely round-trips to the same bytes, and staying
literal keeps this module a single, obvious hash rather than a second
opinion on what "the same code" means).

**Three ways a candidate is silently excluded, never misreported** — the
same discipline every sibling in this family already applies (state a
warning, never guess):

* the bound link's own ``id`` does not parse as ``<file ending .py>::<name...>``;
* the test file could not be read at one side, or is genuinely absent there
  (a file added/removed between base and head is not a body EDIT — it is a
  different, larger change this check does not speak to);
* the named function/method could not be located in the AST at one side (a
  rename, a move to a different file, or an unparseable file) — this check
  has no opinion on where the test WENT, only on what happens to a test that
  stayed in place under the same qualified name.

A display-id collision (``_layer_coverage_core.collision_display_ids``) is
excluded exactly like every sibling feeder check excludes it, for the
identical reason: ``links_for`` pools link counts across every active node
sharing a display id, so a "0 links at head" or a body-digest comparison
keyed on a pooled/ambiguous binding is not a real per-criterion answer.
"""

from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from ._ac_binding_regression import head_and_base_minted  # noqa: E402
from ._keystone_links import links_for  # noqa: E402
from ._layer_coverage_ac import spec_text_at  # noqa: E402
from ._layer_coverage_core import collision_display_ids  # noqa: E402


def _parse_test_id(test_id: str) -> tuple[str, list[str]] | None:
    """``(file_path, [qualname parts])``, or ``None`` when ``test_id`` is not
    a recognizable ``<file ending .py>::<name>[::<name> ...]`` pytest node id."""
    parts = test_id.split("::")
    if len(parts) < 2:
        return None
    file_path = parts[0]
    qualname = parts[1:]
    if not file_path.endswith(".py") or not all(qualname):
        return None
    return file_path, qualname


def _function_source(text: str, qualname: list[str]) -> str | None:
    """The verbatim source of the ``def``/``async def`` at ``qualname`` (a
    dotted path of ``ClassDef``/``FunctionDef`` names, module body down) — or
    ``None`` when the file does not parse, or nothing at that path is a
    function/method."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None

    def _walk(nodes: list[ast.stmt], remaining: list[str]) -> str | None:
        name = remaining[0]
        for node in nodes:
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != name:
                continue
            if len(remaining) == 1:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return ast.get_source_segment(text, node)
                return None  # the last qualname segment named a class, not a test function
            if isinstance(node, ast.ClassDef):
                found = _walk(node.body, remaining[1:])
                if found is not None:
                    return found
            # else: a FunctionDef with more qualname left over -- nested defs
            # are not a pytest collection shape this module needs to resolve.
        return None

    return _walk(tree.body, qualname)


def _digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def test_body_suspects(
    project_root: Path, base_sha: str, head_sha: str, head_manifest: dict, base_manifest: dict,
) -> tuple[list[dict[str, str]], list[str]]:
    """``(suspects, warnings)``. Each suspect is
    ``{"fr_id": ..., "ac_id": ..., "test_id": ...}`` — never deduplicated
    across multiple bound tests for the same AC, since each is its own
    independent "look at this" pointer for a human.

    Reuses ``head_and_base_minted`` for the base/head criterion digests (may
    raise :class:`verifiers._ac_binding_regression.ReadError` exactly as that
    function's own docstring specifies — propagated, not swallowed, so the
    CLI layer's own "advisory, never fails" guarantee is enforced in ONE
    place, not silently duplicated here).
    """
    head_minted, base_minted, warnings = head_and_base_minted(
        project_root, base_sha, head_sha, head_manifest, base_manifest,
    )
    collisions = collision_display_ids(head_manifest) | collision_display_ids(base_manifest)
    suspects: list[dict[str, str]] = []
    file_text_cache: dict[tuple[str, str], str | None] = {}

    def _read(path: str, sha: str) -> str | None:
        key = (path, sha)
        if key not in file_text_cache:
            file_text_cache[key] = spec_text_at(project_root, sha, path)
        return file_text_cache[key]

    for key, head_digest in sorted(head_minted.items()):
        if base_minted.get(key) != head_digest:
            continue  # AC criterion added or its text changed -- not this check's territory
        fr_id, ac_id = key
        if fr_id in collisions:
            continue
        for link in links_for(head_manifest, fr_id, ac_id):
            test_id = str(link.get("id") or link.get("path") or "")
            parsed = _parse_test_id(test_id)
            if parsed is None:
                warnings.append(
                    f"{fr_id}/{ac_id}: bound test id {test_id!r} is not a recognizable "
                    "<file>::<name> pytest node id -- skipped.",
                )
                continue
            file_path, qualname = parsed
            head_text = _read(file_path, head_sha)
            base_text = _read(file_path, base_sha)
            if head_text is None or base_text is None:
                side = "head" if head_text is None else "base"
                warnings.append(
                    f"{fr_id}/{ac_id}: {test_id} -- could not read {file_path!r} at the "
                    f"{side} commit; skipped.",
                )
                continue
            if head_text == "" or base_text == "":
                continue  # the file is genuinely absent at one side -- not a body EDIT
            head_src = _function_source(head_text, qualname)
            base_src = _function_source(base_text, qualname)
            if head_src is None or base_src is None:
                continue  # not found at one side (renamed/moved) -- nothing to compare
            if _digest(head_src) != _digest(base_src):
                suspects.append({"fr_id": fr_id, "ac_id": ac_id, "test_id": test_id})

    return suspects, warnings


__all__ = ["test_body_suspects"]
