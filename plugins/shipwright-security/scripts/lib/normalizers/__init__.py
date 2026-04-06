"""Normalizers for OSS security scanner output.

Each module exposes a normalize(raw_json) -> list[dict] function that
converts tool-specific JSON output into the normalized finding schema
defined in scanner_backend.py.
"""

from normalizers.semgrep import normalize as normalize_semgrep
from normalizers.trivy import normalize as normalize_trivy
from normalizers.gitleaks import normalize as normalize_gitleaks

__all__ = ["normalize_semgrep", "normalize_trivy", "normalize_gitleaks"]
