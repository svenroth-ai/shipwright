"""``lib.review_capture_redact``: mask what a provider's stderr can leak, keep it readable."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.review_capture_redact import redact, redact_unavailable_stderr  # noqa: E402
from lib.review_unavailable import artifact_paths  # noqa: E402

RUN = "iterate-2026-10-09-redact"


def _shaped(prefix: str, n: int = 24) -> str:
    """A throwaway value with a well-known key SHAPE, assembled at runtime (no literal for a secret scanner)."""
    return prefix + "x" * n


_OPENAI, _GITHUB, _GOOGLE = _shaped("s" + "k-"), _shaped("gh" + "p_"), _shaped("AI" + "za")


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize(("text", "gone"), [
    ("POST https://user:pw@gw.example.com/v1?x=1 failed", "gw.example.com"),
    ("Authorization: Bearer abcdefghijklmnop", "abcdefghijklmnop"),
    (f"rejected {_OPENAI}", _OPENAI),
    ("api_key: s3cr3t-value-here", "s3cr3t-value-here"),
    (f"token={_GITHUB}", _GITHUB),
    (f"key {_GOOGLE} was bad", _GOOGLE),
])
def test_secrets_and_urls_are_masked(text, gone):
    assert gone not in redact(text)


@pytest.mark.covers("FR-01.11")
def test_plain_error_text_is_left_alone():
    text = "httpx.ReadTimeout: timed out after 120s\n"
    assert redact(text) == text


@pytest.mark.covers("FR-01.11")
def test_only_an_adapter_backed_unavailable_row_is_touched(tmp_path):
    _, err_rel = artifact_paths(RUN, "external_code")
    err = tmp_path / err_rel
    err.parent.mkdir(parents=True)
    err.write_text("see https://x.example/y", encoding="utf-8")
    assert redact_unavailable_stderr(tmp_path, RUN, "external_code", "user-opt-out") == []
    assert redact_unavailable_stderr(tmp_path, RUN, "doubt", "unavailable") == []
    assert redact_unavailable_stderr(tmp_path, "../escape", "external_code", "unavailable") == []
    assert "x.example" in err.read_text(encoding="utf-8")
    assert redact_unavailable_stderr(tmp_path, RUN, "external_code", "unavailable") == [err_rel]
    assert redact_unavailable_stderr(tmp_path, RUN, "external_code", "unavailable") == []  # idempotent


@pytest.mark.covers("FR-01.11")
def test_a_utf16_capture_keeps_its_encoding(tmp_path):
    """PowerShell 5.1's `2>` writes UTF-16 with a BOM; the evidence reader decodes it, so must we."""
    _, err_rel = artifact_paths(RUN, "plan")
    err = tmp_path / err_rel
    err.parent.mkdir(parents=True)
    err.write_bytes("fail https://gw.example/v1".encode("utf-16"))
    assert redact_unavailable_stderr(tmp_path, RUN, "plan", "unavailable") == [err_rel]
    assert "gw.example" not in err.read_bytes().decode("utf-16")


@pytest.mark.covers("FR-01.11")
def test_an_undecodable_capture_is_masked_losslessly_and_a_query_token_goes_with_its_url(tmp_path):
    _, err_rel = artifact_paths(RUN, "external_code")
    err = tmp_path / err_rel
    err.parent.mkdir(parents=True)
    err.write_bytes(b"caf\xe9 failed https://gw.example/v1?token=abc123 ok")  # latin-1, not UTF-8
    assert redact_unavailable_stderr(tmp_path, RUN, "external_code", "unavailable") == [err_rel]
    out = err.read_bytes()
    assert b"abc123" not in out and b"gw.example" not in out and out.startswith(b"caf\xe9 failed")
    assert not list(err.parent.glob("*.tmp"))


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("text, gone", [
    ('{"api_key": "abcd1234"}', "abcd1234"),
    ("{'token': 'zz99qq'}", "zz99qq"),
    ('token="quoted99"', "quoted99"),
    ("x-api-key: hdr12345", "hdr12345"),
    ("Basic dXNlcjpwYXNzd29yZDEyMzQ=", "dXNlcjpw"),
    ("key github_pat_" + "A1b2C3d4E5f6G7h8I9j0K1", "A1b2C3"),
    ("id AKIA" + "ABCDEFGHIJKLMNOP", "ABCDEFGHIJKLMNOP"),
    ("x " + "-" * 5 + "BEGIN RSA PRIVATE" + " KEY" + "-" * 5, "BEGIN RSA"),
])
def test_more_secret_shapes_are_masked(text, gone):
    assert gone not in redact(text)


@pytest.mark.covers("FR-01.11")
def test_ordinary_prose_with_basic_survives():
    assert redact("Basic authentication failed") == "Basic authentication failed"


@pytest.mark.covers("FR-01.11")
def test_the_raw_envelope_is_masked_but_keeps_its_stamp(tmp_path):
    import json
    raw_rel, _ = artifact_paths(RUN, "external_code")
    raw = tmp_path / raw_rel
    raw.parent.mkdir(parents=True)
    stamp = {"run_id": RUN, "at": "2026-10-09T00:00:00+00:00"}
    raw.write_text(json.dumps({"error": "ConnectError https://gw.example/v1", "capture": stamp}), encoding="utf-8")
    assert redact_unavailable_stderr(tmp_path, RUN, "external_code", "unavailable") == [raw_rel]
    data = json.loads(raw.read_text(encoding="utf-8"))
    assert "gw.example" not in data["error"] and data["capture"] == stamp


@pytest.mark.covers("FR-01.11")
def test_a_whole_key_block_is_masked_body_included():
    d = "-" * 5
    block = f"{d}BEGIN RSA PRIVATE KEY{d}\nMIIEowIBAAKCAQEA1234\n{d}END RSA PRIVATE KEY{d}\nafter"
    out = redact("before\n" + block)
    assert "MIIEow" not in out and out.endswith("after") and out.startswith("before")
    assert "MIIEow" not in redact(f"{d}BEGIN PRIVATE KEY{d}\nMIIEowIBAAKCAQEA1234")  # truncated: no footer


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("text, gone", [
    ("Invalid API key: abc123def456", "abc123def456"),
    ("glm " + "0123456789abcdef0123456789abcdef" + ".Zk93LmQ2xP", "Zk93LmQ2xP"),
])
def test_human_readable_and_glm_shapes_are_masked(text, gone):
    assert gone not in redact(text)


@pytest.mark.covers("FR-01.11")
def test_a_utf16_raw_envelope_is_masked_too(tmp_path):
    raw_rel, _ = artifact_paths(RUN, "external_code")
    raw = tmp_path / raw_rel
    raw.parent.mkdir(parents=True)
    raw.write_bytes('{"error": "https://gw.example/v1"}'.encode("utf-16"))
    assert redact_unavailable_stderr(tmp_path, RUN, "external_code", "unavailable") == [raw_rel]
    assert b"gw.example" not in raw.read_bytes().replace(b"\x00", b"")
