"""Pin props_count for inline object types (sub-iterate F).

External review caught: `_count_props` only handled `interface FooProps {...}`
and destructured `({a, b}: ...)` correctly. Inline object types like
`function Foo(props: { title: string; body?: string })` collapsed to a
single comma-split chunk → 1 (or 0) instead of the actual count.

The original test_component_inventory.py asserted only that components were
*discovered*, not that props_count was correct for inline forms — so the
bug was silent.
"""

from __future__ import annotations

from pathlib import Path

from lib.component_inventory import build_component_inventory


def _make_tsx(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_inline_object_type_semicolon_delimited(tmp_path: Path) -> None:
    _make_tsx(
        tmp_path / "src" / "components" / "Card.tsx",
        "export default function Card(props: { title: string; body?: string }) "
        "{ return null; }\n",
    )
    inv = build_component_inventory(tmp_path)
    card = next(c for c in inv["components"] if c["name"] == "Card")
    assert card["props_count"] == 2


def test_inline_object_type_three_props(tmp_path: Path) -> None:
    _make_tsx(
        tmp_path / "src" / "components" / "Modal.tsx",
        "export const Modal = (p: { open: boolean; onClose: () => void; size?: 'sm' | 'lg' }) "
        "=> null;\n",
    )
    inv = build_component_inventory(tmp_path)
    modal = next(c for c in inv["components"] if c["name"] == "Modal")
    assert modal["props_count"] == 3


def test_destructured_props_still_works(tmp_path: Path) -> None:
    """Existing destructured-props path mustn't regress."""
    _make_tsx(
        tmp_path / "src" / "components" / "Header.tsx",
        "export function Header({ title, subtitle, onMenu }: { title: string; "
        "subtitle?: string; onMenu: () => void }) { return null; }\n",
    )
    inv = build_component_inventory(tmp_path)
    header = next(c for c in inv["components"] if c["name"] == "Header")
    # The inline-type matcher should win first (3 props from the type body).
    # The destructured-props path is the secondary fallback; either yields 3.
    assert header["props_count"] == 3


def test_interface_props_still_works(tmp_path: Path) -> None:
    """Existing interface-based path mustn't regress."""
    _make_tsx(
        tmp_path / "src" / "components" / "Form.tsx",
        "export interface FormProps {\n"
        "  email: string;\n"
        "  password: string;\n"
        "  remember?: boolean;\n"
        "  onSubmit: () => void;\n"
        "}\n"
        "export function Form(props: FormProps) { return null; }\n",
    )
    inv = build_component_inventory(tmp_path)
    form = next(c for c in inv["components"] if c["name"] == "Form")
    assert form["props_count"] == 4
