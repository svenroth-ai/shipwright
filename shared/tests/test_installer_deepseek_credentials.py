"""Installer labels for the current external-review credentials. @FR-01.03"""

from pathlib import Path


VERIFY_SH = Path(__file__).resolve().parents[2] / "scripts" / "verify-setup.sh"


def test_verify_setup_does_not_report_historical_gemini_keys_as_active_review():
    src = VERIFY_SH.read_text(encoding="utf-8")
    assert "env_has GEMINI_API_KEY" not in src
    assert "env_has GOOGLE_API_KEY" not in src
    assert "external review via Gemini" not in src
