"""Every `--output-schema` file the Codex review transport passes must give each
`const`/`enum` property an explicit `type`.

Found live (2026-10-02, codex-cli 0.159.2, gpt-6.1-sol): the OpenAI structured-output
endpoint rejects an untyped `{"const": ...}` / `{"enum": [...]}` with
`invalid_json_schema ... schema must have a 'type' key`, so the spec/doubt/plan_review
roles (and the new architecture_internal one) exited 1 on every launch while the offline
tests (which never reach the API) stayed green. The code schema's one untyped enum was
typed too for consistency; the live probe did not isolate it as a failure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.codex_review_roles import ROLE_SCHEMAS  # noqa: E402


def _untyped(node: object, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        if ("const" in node or "enum" in node) and "type" not in node:
            found.append(path or "<root>")
        for key, value in node.items():
            found += _untyped(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found += _untyped(value, f"{path}/{index}")
    return found


@pytest.mark.parametrize("role", sorted(ROLE_SCHEMAS))
def test_const_and_enum_properties_declare_a_type(role: str) -> None:
    schema = json.loads(ROLE_SCHEMAS[role].read_text(encoding="utf-8"))
    assert _untyped(schema) == [], f"{role}: untyped const/enum is rejected by the live API"
