"""Redact the stderr capture that backs an ``unavailable`` review row before it ships.

``unavailable`` on ``plan`` / ``external_code`` is backed by the adapter's captured
stdout and stderr (``lib.review_unavailable``). F6 stages the whole run dir, so a
``<stem>.stderr.txt`` is committed — and a provider's stderr can carry the gateway
or provider URL, a bearer token, or a key echoed in an error message. What the
claim needs is only that the file is non-empty and says something failed, so the
secrets are masked in place and the error text stays readable.

Scope: the stderr and the raw envelope of an ``unavailable`` row. Captures of a completed pass
are committed as written.

Best-effort pattern masking, not a guarantee: a secret of a shape none of these
patterns knows survives. ``redact_unavailable_stderr`` is called by
``record_review_pass.py record`` BEFORE an ``unavailable`` row is written.
"""

from __future__ import annotations

import codecs
import os
import re
from pathlib import Path

try:
    from .review_unavailable import ADAPTER_REVIEW_TYPES, UNAVAILABLE, artifact_paths
    from .review_record_schema import is_safe_run_id
except ImportError:  # loaded with lib/ itself on sys.path
    from review_unavailable import ADAPTER_REVIEW_TYPES, UNAVAILABLE, artifact_paths  # type: ignore[no-redef]
    from review_record_schema import is_safe_run_id  # type: ignore[no-redef]

__all__ = ["redact", "redact_unavailable_stderr"]

_MASK = "[REDACTED]"
#: ``(pattern, replacement)`` in application order; a URL goes first so its userinfo/query are gone with it.
_DASH = "-" * 5
_PATTERNS = (
    # a whole key block, body included (to its footer, or to the end of the text when truncated)
    (re.compile(_DASH + r"BEGIN [A-Z ]*PRIVATE" + r" KEY" + _DASH + r"[\s\S]*?(?:" + _DASH + r"END [A-Z ]*PRIVATE" + r" KEY" + _DASH + r"|\Z)"),
     _MASK),
    (re.compile(r"https?://[^\s\"'<>)\]]+", re.IGNORECASE), "[URL REDACTED]"),
    (re.compile(r"(?i)\b(bearer\s+[A-Za-z0-9._~+/=-]{8,}|basic\s+[A-Za-z0-9+/=]{16,})"), _MASK),
    (re.compile(r"(?i)\b((?:[a-z_-]*api[\s_-]*key|[a-z_-]*token|[a-z_-]*secret|password|authorization)[\"']?\s*[:=]\s*[\"']?)[^\s,;\"']+"),
     r"\1" + _MASK),
    (re.compile(r"(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|[0-9a-f]{32}\.[A-Za-z0-9]{8,})"),
     _MASK),
)


def redact(text: str) -> str:
    """``text`` with URLs, bearer tokens, ``key=value`` secrets and well-known key shapes masked."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _replace(path: Path, blob: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, path)  # all or nothing: a failure leaves the original, and the caller refuses the row


def redact_unavailable_stderr(project_root: Path | str, run_id: str, review_type: str,
                              reason_code: str | None) -> list[str]:
    """Mask the captures (stderr and raw envelope) of an adapter-backed ``unavailable`` row; the paths changed, else ``[]``.

    A symlink or a missing file is left alone (the evidence rule already refuses a symlink).
    """
    if reason_code != UNAVAILABLE or review_type not in ADAPTER_REVIEW_TYPES or not is_safe_run_id(run_id):
        return []
    changed: list[str] = []
    for rel in artifact_paths(run_id, review_type):  # the raw envelope and the stderr capture, masked alike
        path = Path(project_root) / rel
        if path.is_symlink() or not path.is_file():
            continue
        blob = path.read_bytes()
        codec = "utf-16" if blob[:2] in (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE) else "utf-8"  # PowerShell 5.1 `>`
        try:
            original = blob.decode(codec)
        except UnicodeDecodeError:
            codec, original = "latin-1", blob.decode("latin-1")  # lossless: every byte round-trips
        masked = redact(original)  # text-level on purpose: JSON structure, BOM and stamp stay as written
        if masked != original:
            _replace(path, masked.encode(codec))
            changed.append(rel)
    return changed
