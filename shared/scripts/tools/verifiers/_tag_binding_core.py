"""Pure verdict of the test-tag gate: which added or changed tests name no requirement.

Input is two REGENERATED traceability manifests (base = the merge-base, head = the
commit under test; ``_layer_coverage_regen``), the paths the diff touched, a reader for a
file at either side, the run's per-test exemptions and the FRs the run says it affects.
Nothing here touches git or the filesystem, so every rule is testable on dicts.

Ratchet semantics: a test that was untagged at base and is untouched at head is not this
gate's business. A finding is one of:

* ``untagged-added``     an untagged test id that did not exist at base and is not a move
                         (same normalised body as a base test that vanished in the diff);
* ``tag-removed``        a test tagged at base and untagged at head;
* ``untagged-modified``  a legacy untagged test whose normalised body changed;
* ``invalid-tag``        a malformed tag that is new at head;
* ``unresolved-tag``     a tag that resolves to no live FR, even through the fold-map;
* ``ambiguous-name``     an added/edited test whose name now occurs twice in one file while
                         a same-named sibling is untagged or the siblings carry different
                         tags: the manifest's ``<file>::<name>`` identity cannot tell them
                         apart, so a tag on one would silently cover the other (siblings that
                         all carry the SAME tags only WARN - the shared id is then honest);
* ``bad-exemption``      an exemption that is per-diff, or whose code does not fit.

Not findings: a legacy untagged test in a changed file that the identity layer cannot
locate at EITHER side (a shape it does not parse) is treated as untouched; an untagged id
whose file the diff did not touch (newly collected after a config widening) WARNs.

``touched`` is every test the diff added or edited (moves excluded) — the denominator of
the exemption share F12 and the PR body print.

Exemptions are per test (``scope = <file>::<name>``, kind ``test_exemption``):
``fixture-or-helper`` holds only for a function pytest would not collect;
``mechanical-refactor`` only for an existing test whose body differs from base by renamed
identifiers alone. A ``tag-removed``, ``invalid-tag`` or ``unresolved-tag`` finding is
never exemptable. A tag at head pointing at an FR outside the run's expected set WARNs;
with no expected set at all (no ``work_completed`` event for the run) that check WARNs that
it did not run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from ._tag_binding_identity import body_digests, mechanically_renamed, sibling_tag_sets, would_collect

__all__ = ["TagVerdict", "evaluate", "manifest_tagged_ids"]

#: ``(path, side) -> text``; ``""`` = absent at that side, ``None`` = unreadable.
Reader = Callable[[str, str], "str | None"]
#: One ``<file>::<test>``: no glob in the path; the name may hold brackets (a parametrised
#: title), only a bare wildcard is refused. Backslashes are normalised before the match.
_SCOPE_RE = re.compile(r"^[^*?\[\]:]+::(?![*?]+$).+$")
_TEST_DIRS = frozenset({"tests", "test", "__tests__", "e2e", "integration-tests"})
_EXEMPTABLE = frozenset({"untagged-added", "untagged-modified"})


@dataclass
class TagVerdict:
    findings: list[tuple[str, str, str]] = field(default_factory=list)  # (kind, test, why)
    warnings: list[str] = field(default_factory=list)
    exempted: list[tuple[str, str]] = field(default_factory=list)       # (test, code)
    tagged_new: list[str] = field(default_factory=list)
    moved: list[tuple[str, str]] = field(default_factory=list)          # (base id, head id)
    touched: set[str] = field(default_factory=set)                       # added or edited


def _is_test_id(test_id: str) -> bool:
    """Real test roots only: no ``fixtures`` tree, no production ``test_*.py`` module."""
    parts = test_id.split("::", 1)[0].replace("\\", "/").split("/")
    if "fixtures" in parts:
        return False
    if ("scripts" in parts or "verifiers" in parts) and not _TEST_DIRS & set(parts):
        return False
    return True


def _links(manifest: dict):
    for key, node in (manifest.get("requirements") or {}).items():
        if not isinstance(node, dict):
            continue
        groups = list((node.get("tests") or {}).values())
        for ac_node in (node.get("acs") or {}).values():
            if isinstance(ac_node, dict):
                groups += list((ac_node.get("tests") or {}).values())
        for links in groups:
            for link in links or []:
                if isinstance(link, dict):
                    yield str(key).split("::")[-1], str(link.get("id") or link.get("path") or "")


def manifest_tagged_ids(manifest: dict) -> set[str]:
    ids = {test for _fr, test in _links(manifest)}
    ids |= {str(o.get("test", "")) for o in manifest.get("orphans") or [] if isinstance(o, dict)}
    ids |= {str(i.get("test", "")) for i in manifest.get("invalid_tags") or [] if isinstance(i, dict)}
    return {i for i in ids if i}


def _split(test_id: str) -> tuple[str, str]:
    path, _, name = test_id.partition("::")
    return path, name


def _digests(read: Reader, test_id: str, side: str):
    path, name = _split(test_id)
    text = read(path, side)
    if text is None:
        return None
    return body_digests(text, path, name) if text else ()


def _exemption_findings(test_id: str, code: str, read: Reader, base_ids: set[str]) -> str | None:
    """``None`` when the exemption holds for ``test_id``, else why not."""
    path, name = _split(test_id)
    if code == "fixture-or-helper":
        text = read(path, "head")
        if text is None or would_collect(text, path, name):
            return "fixture-or-helper refused: the function is collected as a test"
        return None
    if code == "mechanical-refactor":
        if test_id not in base_ids:
            return "mechanical-refactor refused: the test did not exist at base"
        base, head = read(path, "base"), read(path, "head")
        if not base or not head or not mechanically_renamed(base, head, path, name):
            return "mechanical-refactor refused: the body changed beyond a consistent identifier rename"
        return None
    return f"exemption code {code!r} does not apply to a test"


def _claim_origin(vanished: dict[str, list[str]], digests, name: str) -> str | None:
    """Consume the vanished base test this one moved from, preferring one of the same name;
    a second copy of the same body finds nothing left and reads as an added test."""
    for digest in digests:
        pool = vanished.get(digest) or []
        if pool:
            pick = next((o for o in pool if _split(o)[1] == name), pool[0])
            pool.remove(pick)
            return pick
    return None


def _flag(
    base: dict, head: dict, changed: set[str], read: Reader, v: TagVerdict,
) -> None:
    base_untagged = {t for t in base.get("untagged_tests") or [] if _is_test_id(t)}
    head_untagged = {t for t in head.get("untagged_tests") or [] if _is_test_id(t)}
    base_tagged = manifest_tagged_ids(base)
    vanished: dict[str, list[str]] = {}  # digest -> base ids that disappeared; each matches ONE move
    for old in sorted(base_untagged - head_untagged):
        if _split(old)[0] in changed:
            for digest in _digests(read, old, "base") or ():
                vanished.setdefault(digest, []).append(old)
    names = {_split(o)[1] for pool in vanished.values() for o in pool}
    # Same-name candidates claim their origin first, so a copy cannot steal the original's move.
    for test in sorted(head_untagged - base_untagged, key=lambda t: (_split(t)[1] not in names, t)):
        if test in base_tagged:
            v.findings.append(("tag-removed", test, "was tagged at base, untagged at head"))
            continue
        if _split(test)[0] not in changed:
            v.warnings.append(f"{test}: newly collected legacy test (its file is not in this diff; "
                              "a widened test root or exclude_dirs) - tag it when it is next edited")
            continue
        digests = _digests(read, test, "head")
        if digests is None:
            v.findings.append(("untagged-added", test, "cannot read the file at head"))
            continue
        origin = _claim_origin(vanished, digests, _split(test)[1])
        if origin:
            v.moved.append((origin, test))
            continue
        v.findings.append(("untagged-added", test, "added without a requirement tag"))
    for test in sorted(head_untagged & base_untagged):
        if _split(test)[0] not in changed:
            continue
        before, after = _digests(read, test, "base"), _digests(read, test, "head")
        if before is None or after is None:
            v.findings.append(("untagged-modified", test, "cannot read the file to compare bodies"))
        elif not before and not after:
            continue  # a shape the identity layer cannot locate at either side: untouched
        elif not before or not after:
            v.findings.append(("untagged-modified", test, "located at only one side, still no requirement tag"))
        elif before != after:
            v.findings.append(("untagged-modified", test, "body changed, still no requirement tag"))


def _flag_tags(base: dict, head: dict, v: TagVerdict) -> None:
    base_invalid = {(i.get("test"), i.get("raw")) for i in base.get("invalid_tags") or [] if isinstance(i, dict)}
    for item in head.get("invalid_tags") or []:
        if not isinstance(item, dict) or not _is_test_id(str(item.get("test") or "")):
            continue  # a fixture repo's deliberately malformed tag is not this project's test
        if (item.get("test"), item.get("raw")) not in base_invalid:
            v.findings.append(("invalid-tag", str(item.get("test") or "<unbound>"),
                               f"malformed tag {item.get('raw')!r} ({item.get('reason', '')})"))
    base_orphans = {(o.get("test"), o.get("tagged_fr")) for o in base.get("orphans") or [] if isinstance(o, dict)}
    for item in head.get("orphans") or []:
        if not isinstance(item, dict) or not _is_test_id(str(item.get("test") or "")):
            continue
        if (item.get("test"), item.get("tagged_fr")) not in base_orphans:
            v.findings.append(("unresolved-tag", str(item.get("test")),
                               f"tag {item.get('tagged_fr')} resolves to no live FR, even through the fold-map ({item.get('reason', '')})"))


def evaluate(
    base: dict, head: dict, changed: set[str], read: Reader,
    exemptions: list[dict], expected_frs: set[str] | None,
) -> TagVerdict:
    v = TagVerdict()
    _flag(base, head, changed, read, v)
    _flag_tags(base, head, v)
    base_ids = {t for t in base.get("untagged_tests") or []} | manifest_tagged_ids(base)
    _touch(base_ids, head, changed, read, v)
    by_scope: dict[str, str] = {}
    for item in exemptions:
        if item.get("kind") != "test_exemption":
            continue
        scope = str(item.get("scope", "")).replace("\\", "/")
        if not _SCOPE_RE.match(scope):
            v.findings.append(("bad-exemption", scope, "per-diff or blanket exemption refused: scope must name one <file>::<test>"))
            continue
        by_scope[scope] = str(item.get("reason_code", ""))
    kept: list[tuple[str, str, str]] = []
    for kind, test, why in v.findings:
        code = by_scope.pop(test, None) if kind in _EXEMPTABLE else None
        if code is None:
            kept.append((kind, test, why))
            continue
        refusal = _exemption_findings(test, code, read, base_ids)
        if refusal:
            kept.append(("bad-exemption", test, refusal))
        else:
            v.exempted.append((test, code))
    v.findings = kept
    v.warnings += [f"exemption for {s} matches no flagged test (unused)" for s in sorted(by_scope)]
    _expected_tags(base, base_ids, head, expected_frs, v)
    return v


def _touch(base_ids: set[str], head: dict, changed: set[str], read: Reader, v: TagVerdict) -> None:
    """Fill ``v.touched`` and flag a name the diff made ambiguous inside one file."""
    head_ids = set(head.get("untagged_tests") or []) | manifest_tagged_ids(head)
    moved_to = {new for _old, new in v.moved}
    for test in sorted(t for t in head_ids if _is_test_id(t) and _split(t)[0] in changed):
        after = _digests(read, test, "head") or ()
        before = (_digests(read, test, "base") or ()) if test in base_ids else ()
        if test in moved_to or (test in base_ids and before == after):
            continue
        v.touched.add(test)
        if len(after) > 1 and len(after) > len(before):
            _ambiguous(test, len(after), read, v)


def _ambiguous(test: str, count: int, read: Reader, v: TagVerdict) -> None:
    path, name = _split(test)
    text = read(path, "head")
    tags = sibling_tag_sets(text, path, name) if text else None
    if tags and all(tags) and len(set(tags)) == 1:
        v.warnings.append(f"{test}: {count} tests in one file share this name and carry the same tags, "
                          "so the shared id is honest - still, rename them apart")
        return
    v.findings.append(("ambiguous-name", test, f"{count} tests in one file share this name and one is "
                       "untagged or they carry different tags, so one tag would cover all - rename them apart"))


def _expected_tags(base: dict, base_ids: set[str], head: dict, expected: set[str] | None, v: TagVerdict) -> None:
    """Every (FR, test) binding new at head; one outside the expected FRs WARNs."""
    before = set(_links(base))
    new_links = sorted({(fr, t) for fr, t in _links(head) if (fr, t) not in before and _is_test_id(t)})
    v.tagged_new = sorted({t for fr, t in new_links if t not in base_ids})
    if expected is None:
        v.warnings.append("no work_completed Spec-Impact FRs found; out-of-scope tag check not run")
        return
    if not expected:
        return
    for fr, test in new_links:
        if fr not in expected:
            v.warnings.append(f"{test} is tagged {fr}, outside this run's Spec-Impact FRs {sorted(expected)}")
