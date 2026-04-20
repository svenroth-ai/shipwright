"""Unit tests for folder_introspector.introspect_folders."""

from pathlib import Path

from lib.folder_introspector import introspect_folders


def test_nextjs_layers(nextjs_repo: Path) -> None:
    result = introspect_folders(nextjs_repo)
    layer_names = {layer["name"] for layer in result["layers"]}
    assert "presentation" in layer_names
    # Check some paths under presentation
    presentation = next(l for l in result["layers"] if l["name"] == "presentation")
    assert any("app" in p for p in presentation["paths"])


def test_python_cli_layers(python_cli: Path) -> None:
    result = introspect_folders(python_cli)
    # No strongly-layered structure in the minimal fixture; may be empty.
    # Just assert the shape is correct.
    assert "layers" in result
    assert "loc_by_layer" in result


def test_empty_project(tmp_path: Path) -> None:
    result = introspect_folders(tmp_path)
    assert result["layers"] == []
    assert result["loc_by_layer"] == {}


def test_excludes_webui(nested_shipwright: Path) -> None:
    result = introspect_folders(nested_shipwright, excludes={"webui"})
    for layer in result["layers"]:
        for path in layer["paths"]:
            assert not path.startswith("webui")
