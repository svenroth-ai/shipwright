"""`_gh` decodes `gh`'s bytes as UTF-8, never with the locale codec.

@FR-01.17

On Windows `text=True` decodes with cp1252, so a check named with an em-dash was
compared against a garbled copy of itself and reported twice: once as
"runs but gates nothing" and once as "configured but never reported".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _required_checks_fakes import load_producer  # noqa: E402

crc = load_producer()

NAME = "Tests \u2014 unit"


class _BytesProc:
    def __init__(self, stdout: bytes, stderr: bytes = b"", returncode: int = 0) -> None:
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def _router(kwargs_seen: list[dict]):
    payload = json.dumps(
        [{"type": "required_status_checks",
          "parameters": {"required_status_checks": [{"context": NAME}]}}],
        ensure_ascii=False,
    ).encode("utf-8")

    def _run(argv, **kwargs):
        kwargs_seen.append(kwargs)
        if argv[-1].endswith("/protection"):
            return _BytesProc(b"", b"gh: Not Found (HTTP 404)", 1)
        return _BytesProc(payload)

    return _run


@pytest.mark.covers("FR-01.17")
def test_gh_asks_for_bytes_not_locale_text(monkeypatch) -> None:
    seen: list[dict] = []
    monkeypatch.setattr(crc.subprocess, "run", _router(seen))
    crc.fetch_configured_contexts("o/r", "main")
    assert seen and all(not k.get("text") and "encoding" not in k for k in seen)


@pytest.mark.covers("FR-01.17")
def test_em_dash_check_name_survives_and_is_not_flagged(monkeypatch) -> None:
    monkeypatch.setattr(crc.subprocess, "run", _router([]))
    configured = crc.fetch_configured_contexts("o/r", "main")
    assert configured == [NAME]
    result = crc.compare_required_checks([NAME], configured)
    assert result["in_sync"] and not result["unenforced"] and not result["phantom"]


@pytest.mark.covers("FR-01.17")
def test_garbled_copy_would_be_flagged_twice_but_decoded_name_at_most_once(monkeypatch) -> None:
    """A genuinely missing em-dash check shows up in ONE list, not both."""
    monkeypatch.setattr(crc.subprocess, "run", _router([]))
    configured = crc.fetch_configured_contexts("o/r", "main")
    result = crc.compare_required_checks([NAME, "lint"], configured)
    flagged = result["unenforced"] + result["phantom"]
    assert flagged.count(NAME) == 0 and flagged == ["lint"]
    result = crc.compare_required_checks(["lint"], configured)
    assert (result["unenforced"] + result["phantom"]).count(NAME) == 1


@pytest.mark.covers("FR-01.17")
def test_stderr_is_decoded_too(monkeypatch) -> None:
    def _run(argv, **kwargs):
        return _BytesProc(b"", "gh: bad \u2014 thing (HTTP 403)".encode("utf-8"), 1)

    monkeypatch.setattr(crc.subprocess, "run", _run)
    try:
        crc._gh(["api", "x"])
    except crc.GhError as exc:
        assert "\u2014" in str(exc) and exc.status == 403
    else:
        raise AssertionError("expected GhError")
