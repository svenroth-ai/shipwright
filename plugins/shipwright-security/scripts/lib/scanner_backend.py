#!/usr/bin/env python3
"""Scanner backend abstraction for shipwright-security.

Defines the ScannerBackend ABC, a backend registry, and the normalized
finding schema.  Every scanner implementation (Aikido, OSS, ...) must
subclass ScannerBackend and register itself via @register_backend.

The rest of the pipeline (classify -> remediate -> report -> compliance)
operates exclusively on normalized findings returned by scan().
"""

from __future__ import annotations

import os
import shutil
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths – reuse shared env loader
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parent.parent
SHARED_ROOT = PLUGIN_ROOT.parent.parent / "shared"

sys.path.insert(0, str(SHARED_ROOT / "scripts" / "lib"))
from env import load_shipwright_env  # noqa: E402

# ---------------------------------------------------------------------------
# Normalized finding schema (type hint / documentation only)
# ---------------------------------------------------------------------------

# Each backend must return a list[dict] where every dict has at least:
#
#   id               : str           – unique finding ID
#   severity         : str           – critical | high | medium | low | info
#   severity_score   : float         – 0-10
#   type             : str           – sast | sca | secret_detection | iac
#   rule             : str           – rule ID or CVE
#   cve_id           : str | None    – CVE identifier (SCA)
#   affected_package : str | None    – package name (SCA)
#   affected_file    : str | None    – file path
#   affected_line    : int | None    – line number
#   description      : str           – human-readable description
#   remediation_hint : str | None    – suggested fix
#   cwe_classes      : list[str]     – CWE identifiers
#   source           : str           – "aikido" | "semgrep" | "trivy" | "gitleaks"
#   _remediation_class : str         – set by classify_finding()

REQUIRED_FINDING_KEYS = {
    "id", "severity", "type", "rule", "source",
}


# ---------------------------------------------------------------------------
# Re-export classify_finding (backend-agnostic)
# ---------------------------------------------------------------------------

# Import from aikido_client to avoid duplication.  The function itself does
# not depend on Aikido – it only looks at severity and type fields.
try:
    from aikido_client import classify_finding  # noqa: F401
except ImportError:
    # Fallback: inline copy for when aikido_client is not on sys.path
    AUTO_FIXABLE_TYPES = {"dependency", "sca"}
    AGENT_FIXABLE_TYPES = {"sast", "secret_detection"}

    def classify_finding(finding: dict[str, Any]) -> str:  # type: ignore[misc]
        severity = finding.get("severity", "").lower()
        finding_type = finding.get("type", "").lower()
        if severity in ("low", "info", "informational"):
            return "informational"
        if finding_type in AUTO_FIXABLE_TYPES:
            return "auto-fixable"
        if finding_type in AGENT_FIXABLE_TYPES:
            return "agent-fixable"
        return "needs-review"


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

class ScannerBackend(ABC):
    """Base class for all scanner backends."""

    name: str                   # e.g. "aikido", "oss"
    capabilities: set[str]      # e.g. {"sast", "sca", "secrets"}
    requires_cloud: bool

    # Optional degraded-scan channel. A backend MAY (re)populate this in
    # ``scan()`` with one record per degraded leg — a scanner that was invoked
    # but produced no parseable output (fatal / timeout / truncated report) —
    # shaped ``{"scanner": str, "reason": str, "detail": str}``. It is the
    # control-plane counterpart to the data-plane findings list: a degraded
    # leg must NOT read as a clean "0 findings" scan. Consumers read it via
    # ``getattr(backend, "scan_errors", [])`` so backends that never set it
    # (and test mocks) default to "no degradation". Annotation only — no
    # mutable class default.
    scan_errors: list[dict[str, Any]]

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if this backend's prerequisites are met."""

    @abstractmethod
    def scan(self, target: str, scan_types: list[str] | None = None) -> list[dict[str, Any]]:
        """Run scan and return a list of normalized findings."""

    @abstractmethod
    def get_setup_instructions(self) -> str:
        """Return human-readable setup instructions for this backend."""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

BACKEND_REGISTRY: dict[str, type[ScannerBackend]] = {}


def register_backend(cls: type[ScannerBackend]) -> type[ScannerBackend]:
    """Class decorator – registers a ScannerBackend subclass."""
    BACKEND_REGISTRY[cls.name] = cls
    return cls


# ---------------------------------------------------------------------------
# Backend resolution
# ---------------------------------------------------------------------------

def get_backend(name: str | None = None) -> ScannerBackend:
    """Return an instantiated backend.

    Resolution order:
    1. Explicit *name* argument
    2. SHIPWRIGHT_SCANNER_BACKEND env var
    3. Auto-detect: Aikido credentials → Aikido; semgrep on PATH → OSS
    """
    load_shipwright_env()

    if name is None:
        name = os.environ.get("SHIPWRIGHT_SCANNER_BACKEND", "").lower() or None

    if name and name in BACKEND_REGISTRY:
        backend = BACKEND_REGISTRY[name]()
        if backend.is_configured():
            return backend
        raise RuntimeError(
            f"Backend '{name}' selected but not configured.\n"
            f"{backend.get_setup_instructions()}"
        )

    # Auto-detect
    for candidate_name in ("aikido", "oss"):
        cls = BACKEND_REGISTRY.get(candidate_name)
        if cls is None:
            continue
        candidate = cls()
        if candidate.is_configured():
            return candidate

    # Nothing found – build a helpful error message
    instructions = []
    for cls in BACKEND_REGISTRY.values():
        instructions.append(f"--- {cls.name} ---\n{cls().get_setup_instructions()}")
    raise RuntimeError(
        "No security scanner backend is configured.\n\n"
        + "\n\n".join(instructions)
    )


def check_security_available() -> bool:
    """Return True if any backend is configured.  Used by the orchestrator."""
    load_shipwright_env()

    if os.environ.get("SHIPWRIGHT_SCANNER_BACKEND"):
        return True
    if os.environ.get("AIKIDO_CLIENT_ID"):
        return True
    return any(shutil.which(t) for t in ("semgrep", "trivy", "gitleaks"))
