"""Unit tests for stack_detector.detect_stack."""

from pathlib import Path

from lib.stack_detector import detect_stack


def test_nextjs_supabase_ts(nextjs_repo: Path) -> None:
    sig = detect_stack(nextjs_repo)
    assert sig["primary_language"] == "typescript"
    assert sig["runtime"]["node"] == "22.x"
    assert "typescript" in sig["runtime"]
    assert "next" in sig["frontend"]
    assert "react" in sig["frontend"]
    assert "@supabase/supabase-js" in sig["database"]
    assert "has-package-json" in sig["signals"]
    assert "has-tsconfig-strict" in sig["signals"]


def test_python_fastapi(python_cli: Path) -> None:
    sig = detect_stack(python_cli)
    assert sig["primary_language"] == "python"
    assert "python" in sig["runtime"]
    assert "fastapi" in sig["backend"]
    # psycopg3 resolves to key "psycopg"
    assert any("psycopg" in k for k in sig["database"].keys())
    assert "has-pyproject-toml" in sig["signals"]


def test_missing_manifest(tmp_path: Path) -> None:
    sig = detect_stack(tmp_path)
    assert sig["primary_language"] == "unknown"
    assert sig["runtime"] == {}
    assert sig["frontend"] == {}


def test_excludes_filter_nested(nested_shipwright: Path) -> None:
    # With webui/ excluded, nested package.json shouldn't affect stack
    sig = detect_stack(nested_shipwright, excludes={"webui"})
    assert sig["primary_language"] == "javascript" or sig["primary_language"] == "typescript"
    # Root has next (via root package.json), which is fine
