"""Tiny schema-driven checker for ``shared/schemas/stack_profile.schema.json``.

Supports exactly the JSON-Schema constructs that file uses (``type``,
``properties``, ``required``, ``items``, ``additionalProperties`` as a
boolean, ``minimum``) plus annotation keywords. Any other keyword raises
``UnsupportedConstruct`` so the schema file and its enforcement cannot
silently diverge (a CI test also compares this checker with ``jsonschema``).

Stdlib-only. Imported by ``profile_resolver`` (never directly by loaders).
"""

from __future__ import annotations

ANNOTATIONS = frozenset(
    {"$schema", "$id", "$comment", "title", "description", "default", "examples"}
)
SUPPORTED = frozenset(
    {"type", "properties", "required", "items", "additionalProperties", "minimum"}
)
_TYPES = ("object", "array", "string", "integer", "number", "boolean", "null")


class UnsupportedConstruct(ValueError):
    """The schema file uses a keyword this checker does not implement."""


def assert_supported(schema: object, where: str = "#") -> None:
    """Raise ``UnsupportedConstruct`` for any keyword outside ``SUPPORTED``."""
    if not isinstance(schema, dict):
        raise UnsupportedConstruct(f"{where}: schema node must be an object")
    for key, value in schema.items():
        if key in ANNOTATIONS:
            continue
        if key not in SUPPORTED:
            raise UnsupportedConstruct(f"{where}: unsupported keyword {key!r}")
        if key == "properties":
            for prop, sub in value.items():
                assert_supported(sub, f"{where}/properties/{prop}")
        elif key == "items":
            assert_supported(value, f"{where}/items")
        elif key == "additionalProperties" and value is not True:
            # False would need the '_' comment exemption that jsonschema lacks.
            raise UnsupportedConstruct(f"{where}: additionalProperties must be true")
        elif key == "type":
            names = [value] if isinstance(value, str) else list(value)
            for t in names:
                if t not in _TYPES:
                    raise UnsupportedConstruct(f"{where}: unsupported type {t!r}")


def _type_ok(value: object, name: str) -> bool:
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    if name == "integer":
        if isinstance(value, float):
            return value.is_integer()  # Draft 2020-12: 1.0 is an integer
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, (int, float)) and not isinstance(value, bool)  # number


def _kind(value: object) -> str:
    for name in _TYPES:
        if _type_ok(value, name):
            return name
    return type(value).__name__


def check(data: object, schema: dict, where: str = "$") -> list[tuple[str, str]]:
    """Return ``[(code, message)]``; ``code`` is required|type|minimum."""
    problems: list[tuple[str, str]] = []
    wanted = schema.get("type")
    if wanted is not None:
        names = [wanted] if isinstance(wanted, str) else list(wanted)
        if not any(_type_ok(data, n) for n in names):
            problems.append(
                ("type", f"{where}: expected {' or '.join(names)}, got {_kind(data)}")
            )
            return problems
    if "minimum" in schema and isinstance(data, (int, float)) and not isinstance(data, bool):
        if data < schema["minimum"]:
            problems.append(("minimum", f"{where}: {data} is below {schema['minimum']}"))
    if isinstance(data, dict):
        for key in schema.get("required", []):
            if key not in data:
                problems.append(("required", f"{where}: missing required key {key!r}"))
        props = schema.get("properties", {})
        for key, sub in props.items():
            if key in data:
                problems.extend(check(data[key], sub, f"{where}.{key}"))
    if isinstance(data, list) and "items" in schema:
        for i, item in enumerate(data):
            problems.extend(check(item, schema["items"], f"{where}[{i}]"))
    return problems
