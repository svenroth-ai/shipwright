"""Regression coverage for CRLF-preserving provenance stamping."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools import compliance_provenance as provenance  # noqa: E402


def test_stamp_preserves_the_matched_crlf_terminator():
    payload = {
        "evidence.md": b"# Evidence\r\nSource-State: run=example\r\nbody\r\n",
    }
    stamped, moved = provenance.stamp_fixed_point(payload, "a" * 40, None)

    assert moved == ["evidence.md"]
    assert stamped["evidence.md"].splitlines(keepends=True)[1].endswith(b"\r\n")
    assert all(line.endswith(b"\r\n") for line in stamped["evidence.md"].splitlines(keepends=True))
