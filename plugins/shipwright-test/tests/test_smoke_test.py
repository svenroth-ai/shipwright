"""Tests for shared smoke_test module."""

from smoke_test import run_smoke_test


def test_smoke_test_unreachable():
    """Test against unreachable URL — should fail gracefully."""
    result = run_smoke_test("http://localhost:19999", timeout=2)
    assert result["success"] is False
    assert result["error"] is not None
    assert result["url"] == "http://localhost:19999"


def test_smoke_test_invalid_url():
    """Invalid URL — should fail gracefully."""
    result = run_smoke_test("not-a-url", timeout=2)
    assert result["success"] is False
    assert result["error"] is not None


def test_smoke_test_result_structure():
    """Verify result has all expected fields."""
    result = run_smoke_test("http://localhost:19999", timeout=1)
    assert "success" in result
    assert "url" in result
    assert "status_code" in result
    assert "response_time_ms" in result
    assert "health_check" in result
    assert "error" in result
