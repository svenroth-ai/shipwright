"""Unit tests for feature_inferrer.infer_features_ast."""

from pathlib import Path

from lib.feature_inferrer import infer_features_ast
from lib.stack_detector import detect_stack


def test_nextjs_app_router(nextjs_repo: Path) -> None:
    stack = detect_stack(nextjs_repo)
    features = infer_features_ast(nextjs_repo, stack)
    routes = {f["route"] for f in features}
    assert "/" in routes
    assert "/dashboard" in routes
    # (auth) is a route group, should not appear in route path
    assert "/login" in routes  # from src/app/(auth)/login/page.tsx
    # FR-IDs assigned sequentially
    fr_ids = [f["fr_id"] for f in features]
    assert all(fid.startswith("FR-01.") for fid in fr_ids)


def test_python_fastapi(python_cli: Path) -> None:
    stack = detect_stack(python_cli)
    features = infer_features_ast(python_cli, stack)
    routes = {f["route"] for f in features}
    assert "/health" in routes
    assert "/users" in routes


def test_empty_project(tmp_path: Path) -> None:
    stack = detect_stack(tmp_path)
    features = infer_features_ast(tmp_path, stack)
    assert features == []
