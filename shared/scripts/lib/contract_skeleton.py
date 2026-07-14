"""contract_skeleton — the shape half of the cross-repo output-contract engine.

Backs the contract gates for the two artifacts an **external consumer** — the Command
Center WebUI — renders field-for-field: ``shipwright-grade``'s ``ReportModel`` (via
``grade.py --format json``) and ``shipwright-adopt``'s ``.shipwright/adopt/snapshot.json``.
The contract itself is stated in each plugin's SKILL.md ("Cross-repo contract"); the
immutable git baseline that makes the gate a *mechanism* lives in ``contract_baseline``.

**The skeleton is the JSON wire shape**, not Python annotations: int/float collapse to
one ``number`` and tuples become arrays, so rewriting ``Optional[float]`` as
``float | None`` cannot fire a false "retype".

**Nullability is part of the shape, not a sidecar.** A container that becomes nullable is
BREAKING — the consumer indexes into it — but it adds no field, so a naive field-graph
diff would call it "no change" and let the version stand. So every container carries an
explicit kind leaf (``object`` / ``object|null`` / ``array``), and gaining a null arm
therefore reads as a **retype ⇒ major**. Getting this wrong is a *silent* break: the
payload still parses, and the consumer still crashes.

**Known limit:** a value-domain break can have an identical field graph (a 4th ``status``
value). ``performed >= required`` — never equality — keeps a deliberate major bump
available for that class; pin closed vocabularies separately where they are enumerable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# Weakest to strongest; a bump "performs" everything at or below its rank.
_BUMP_RANK = {"none": 0, "minor": 1, "major": 2}

# Reserved key carrying a container's kind. Payload keys never collide with it: it is
# injected by _merge, never read from a producer.
KIND = "__kind__"


class ContractViolation(AssertionError):
    """A cross-repo output contract broke (or its version was not bumped)."""


@dataclass(frozen=True)
class ContractDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    retyped: list[str] = field(default_factory=list)

    @property
    def is_breaking(self) -> bool:
        """Removed or retyped ⇒ the consumer's existing field access breaks."""
        return bool(self.removed or self.retyped)


def skeleton_of(payload: Any) -> Any:
    """Recursive type-skeleton of ``payload`` as it lands on the wire.

    Round-trips through ``json`` first, so the subject is exactly what the consumer
    receives and a non-JSON type fails here rather than entering the pin silently.
    """
    return _skeleton(json.loads(json.dumps(payload)))


def _skeleton(value: Any) -> Any:
    if value is None:
        return "null"
    if isinstance(value, bool):  # BEFORE int — bool subclasses int in Python.
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        element: Any = None
        for item in value:
            shape = _skeleton(item)
            element = shape if element is None else _merge(element, shape)
        return [] if element is None else [element]
    if isinstance(value, dict):
        return {key: _skeleton(value[key]) for key in sorted(value)}
    raise ContractViolation(f"not JSON-serializable: {type(value).__name__}")


def _kind(shape: Any) -> str:
    if isinstance(shape, dict):
        return str(shape.get(KIND, "object"))
    return "array" if isinstance(shape, list) else str(shape)


def _merge(left: Any, right: Any) -> Any:
    """Union two skeletons — how a list of mixed samples becomes one element type."""
    if left == right:
        return left
    if isinstance(left, dict) and isinstance(right, dict):
        return {
            key: (_merge(left[key], right[key]) if key in left and key in right
                  else left.get(key, right.get(key)))
            for key in sorted({*left, *right})
        }
    if isinstance(left, list) and isinstance(right, list):
        if not left or not right:
            return right or left
        return [_merge(left[0], right[0])]
    # An OPTIONAL OBJECT keeps its shape and records the null arm on itself. Collapsing
    # it to "null|object" would erase the pin on everything inside — the nested drift the
    # gate exists to catch — while dropping the null arm entirely would hide a BREAKING
    # change (the consumer indexes into what it was promised is always there).
    for token, other in ((left, right), (right, left)):
        if token == "null" and isinstance(other, dict):
            return {**other, KIND: "object|null"}
    # Everything else — scalars, and any structural mismatch (incl. a nullable ARRAY) —
    # degrades to a union of kinds. That is a leaf, so a list that gains a null arm reads
    # as removed-array-leaves + added-scalar ⇒ breaking. Fails safe.
    parts: set[str] = set()
    for shape in (left, right):
        parts.update(_kind(shape).split("|"))
    return "|".join(sorted(parts, key=lambda part: (part == "null", part)))


def flatten(skeleton: Any) -> dict[str, str]:
    """Skeleton → ``{dotted.path: type-token}``; arrays are marked ``[]``.

    Every CONTAINER gets a leaf of its own (``object`` / ``object|null`` / ``array``), not
    just the scalars inside it — that is what makes "this object became nullable" a
    retype rather than an invisible non-change.
    """
    out: dict[str, str] = {}
    _flatten(skeleton, "", out)
    return out


def _flatten(skeleton: Any, prefix: str, out: dict[str, str]) -> None:
    if isinstance(skeleton, dict):
        if prefix:  # The root object is the payload itself — nothing to pin about it.
            out[prefix] = _kind(skeleton)
        for key, sub in skeleton.items():
            if key == KIND:
                continue
            _flatten(sub, f"{prefix}.{key}" if prefix else key, out)
    elif isinstance(skeleton, list):
        if skeleton:
            if prefix:
                out[prefix] = "array"
            _flatten(skeleton[0], f"{prefix}[]", out)
        else:
            # An empty array pins nothing about its elements. Callers assert these are
            # absent, so a weak pin cannot pass for a strong one.
            out[prefix] = "array<unpinned>"
    else:
        out[prefix] = str(skeleton)


def empty_array_paths(skeleton: Any) -> list[str]:
    """Paths whose element type went unobserved — i.e. the pin is weak there."""
    return sorted(p for p, t in flatten(skeleton).items() if t == "array<unpinned>")


def null_only_paths(skeleton: Any) -> list[str]:
    """Paths only ever observed as ``null`` — the pin says nothing about their real shape.

    The null twin of :func:`empty_array_paths`. A leaf pinned as bare ``"null"`` means no
    sample exercised it, so the published contract tells the consumer "this is always
    null" when in production it is an object. Callers assert these are absent (or
    allowlist them explicitly) rather than shipping a weak pin as a strong one.
    """
    return sorted(p for p, t in flatten(skeleton).items() if t == "null")


def diff_skeletons(base: Any, live: Any) -> ContractDiff:
    """Classify base → live. A rename reads as a removal plus an addition."""
    base_leaves, live_leaves = flatten(base), flatten(live)
    return ContractDiff(
        added=sorted(set(live_leaves) - set(base_leaves)),
        removed=sorted(set(base_leaves) - set(live_leaves)),
        retyped=sorted(path for path in set(base_leaves) & set(live_leaves)
                       if base_leaves[path] != live_leaves[path]),
    )


def required_bump(diff: ContractDiff) -> str:
    """The bump this diff obliges: breaking ⇒ major, additive ⇒ minor, else none."""
    if diff.is_breaking:
        return "major"
    return "minor" if diff.added else "none"


def parse_version(version: str) -> tuple[int, int]:
    parts = str(version).split(".")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise ContractViolation(f"schema_version {version!r} is not major.minor")
    return int(parts[0]), int(parts[1])


def bump_performed(base: str, live: str) -> str:
    """What the version actually did — numeric, not lexical (as strings "1.10" <
    "1.2", which would read a legitimate tenth minor release as a regression)."""
    base_pair, live_pair = parse_version(base), parse_version(live)
    if live_pair < base_pair:
        raise ContractViolation(
            f"schema_version regressed: {base} → {live}. A published contract version "
            "is never withdrawn; move forward instead.")
    if live_pair[0] > base_pair[0]:
        return "major"
    return "minor" if live_pair[1] > base_pair[1] else "none"


def require_bump(
    base_skeleton: Any, live_skeleton: Any, base_version: str, live_version: str,
    *, consumer: str, artifact: str = "This payload",
) -> ContractDiff:
    """The gate. Raise unless the version performed the bump the diff obliges."""
    diff = diff_skeletons(base_skeleton, live_skeleton)
    needed = required_bump(diff)
    performed = bump_performed(base_version, live_version)
    if _BUMP_RANK[performed] >= _BUMP_RANK[needed]:
        return diff
    raise ContractViolation(_message(
        diff, needed, performed, base_version, live_version, consumer, artifact))


def _message(
    diff: ContractDiff, needed: str, performed: str, base_version: str,
    live_version: str, consumer: str, artifact: str,
) -> str:
    lines = [
        "",
        f"{artifact} CHANGED SHAPE — and this is a CROSS-REPO CONTRACT.",
        f"{consumer} renders it field-for-field. A change here that ships without a",
        "matching change there does NOT fail loudly — it renders a half-empty card, or",
        "a plausible-but-wrong one.", "",
    ]
    for label, paths in (("removed", diff.removed), ("retyped", diff.retyped),
                         ("added", diff.added)):
        lines += [f"    {label:>8}:  {path}" for path in paths]
    lines += [
        "",
        "  That is {}.".format("BREAKING for the consumer" if diff.is_breaking
                               else "additive — the consumer ignores what it can't see"),
        f"  Required bump: {needed}.  Performed: {performed} "
        f"({base_version} → {live_version}).",
        "",
        f"  1. Bump schema_version by at least a {needed} advance over {base_version}.",
        "  2. Add a NEW versioned contract fixture — do NOT edit the published one. It is",
        "     frozen against origin/main; that is what makes this a gate, not a reminder.",
    ]
    if diff.is_breaking:
        lines.append(
            f"  3. Open the matching PR in {consumer}: an unrecognised MAJOR makes it\n"
            "     refuse to render rather than lie about the user's repo.")
    return "\n".join(lines)
