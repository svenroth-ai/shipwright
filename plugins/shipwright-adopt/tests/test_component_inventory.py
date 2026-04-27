"""Verify component_inventory scans React component trees (Tier 5).

Adopt currently produces no visual frontend documentation at all. This
helper enumerates components under conventional locations
(src/components/**, src/ui/**, src/app/**) so the generated
.shipwright/agent_docs/guideline.md can list them with prop and usage counts.
"""

from __future__ import annotations

from pathlib import Path

from lib.component_inventory import build_component_inventory


def _make_tsx(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_inventory_picks_up_components_in_src_components(tmp_path: Path) -> None:
    _make_tsx(
        tmp_path / "src" / "components" / "Button.tsx",
        "export interface ButtonProps { label: string; onClick: () => void }\n"
        "export function Button({ label, onClick }: ButtonProps) { return null; }\n",
    )
    _make_tsx(
        tmp_path / "src" / "components" / "Card.tsx",
        "export default function Card(props: { title: string; body?: string }) { return null; }\n",
    )
    inv = build_component_inventory(tmp_path)
    names = {c["name"] for c in inv["components"]}
    assert "Button" in names
    assert "Card" in names
    assert inv["total"] == 2


def test_inventory_picks_up_components_in_src_ui(tmp_path: Path) -> None:
    _make_tsx(
        tmp_path / "src" / "ui" / "Modal.tsx",
        "export const Modal = (props: { open: boolean }) => null;\n",
    )
    inv = build_component_inventory(tmp_path)
    assert any(c["name"] == "Modal" for c in inv["components"])


def test_inventory_counts_props_from_interface(tmp_path: Path) -> None:
    _make_tsx(
        tmp_path / "src" / "components" / "Form.tsx",
        "export interface FormProps {\n"
        "  email: string;\n"
        "  password: string;\n"
        "  onSubmit: () => void;\n"
        "}\n"
        "export function Form(props: FormProps) { return null; }\n",
    )
    inv = build_component_inventory(tmp_path)
    form = next(c for c in inv["components"] if c["name"] == "Form")
    assert form["props_count"] == 3


def test_inventory_counts_usage_via_grep(tmp_path: Path) -> None:
    """A component used in 3 places elsewhere in the tree shows usage_count >= 3."""
    _make_tsx(
        tmp_path / "src" / "components" / "Avatar.tsx",
        "export const Avatar = () => null;\n",
    )
    _make_tsx(
        tmp_path / "src" / "pages" / "profile.tsx",
        "import { Avatar } from '../components/Avatar';\nfunction P() { return <Avatar/>; }\n",
    )
    _make_tsx(
        tmp_path / "src" / "pages" / "settings.tsx",
        "import { Avatar } from '../components/Avatar';\nfunction S() { return <><Avatar/><Avatar/></>; }\n",
    )
    inv = build_component_inventory(tmp_path)
    avatar = next(c for c in inv["components"] if c["name"] == "Avatar")
    # >= 3 references (1 import + 3 usages, or similar — we count refs)
    assert avatar["usage_count"] >= 3


def test_inventory_skips_node_modules_and_build_dirs(tmp_path: Path) -> None:
    _make_tsx(
        tmp_path / "node_modules" / "lib" / "Foo.tsx",
        "export function Foo() { return null; }\n",
    )
    _make_tsx(
        tmp_path / "dist" / "Bar.tsx",
        "export function Bar() { return null; }\n",
    )
    _make_tsx(
        tmp_path / "src" / "components" / "Real.tsx",
        "export function Real() { return null; }\n",
    )
    inv = build_component_inventory(tmp_path)
    names = {c["name"] for c in inv["components"]}
    assert "Real" in names
    assert "Foo" not in names
    assert "Bar" not in names


def test_inventory_handles_no_frontend_gracefully(tmp_path: Path) -> None:
    inv = build_component_inventory(tmp_path)
    assert inv["total"] == 0
    assert inv["components"] == []


def test_inventory_handles_multi_service_pivot(tmp_path: Path) -> None:
    """Multi-service repos: the components live under client/src/, not src/.
    The walker should accept an explicit `frontend_root` to scan instead."""
    _make_tsx(
        tmp_path / "client" / "src" / "components" / "Header.tsx",
        "export const Header = () => null;\n",
    )
    inv = build_component_inventory(tmp_path / "client")
    names = {c["name"] for c in inv["components"]}
    assert "Header" in names
