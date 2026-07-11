"""Tests for adopt brief-intake (K2d): a brief pre-fills the Step-C
product-description confirmation and REMOVES that question; profile + scope
stay scan-gated; no brief -> Step C runs exactly as today (AC3).

Exercises the ADR-045-safe reuse of the shared ``brief_intake`` helper
(``adopt_brief_intake`` loads it via ``spec_from_file_location``, never a
namespace-polluting ``from lib import brief_intake``).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

# adopt conftest.py already puts the plugin's `scripts/` on sys.path.
import lib.adopt_brief_intake as abi  # noqa: E402
from lib.adopt_brief_intake import adopt_intake  # noqa: E402

_SENTINEL = "_shipwright_adopt_brief_intake"

SCRIPT = str(
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "lib"
    / "adopt_brief_intake.py"
)

FULL_BRIEF = {
    "description": "A booking tool for my yoga studio",
    "users": "public",
    "persistence": "yes",
    "run_location": "web",
}

CODED_ONLY_BRIEF = {
    "users": "team",
    "persistence": "no",
    "run_location": "local",
}


# --- Full brief: product description pre-filled, question removed -------------

def test_full_brief_prefills_product_description():
    result = adopt_intake(FULL_BRIEF)
    assert result["has_brief"] is True
    assert result["product_description"] == "A booking tool for my yoga studio"
    assert result["brief_prefilled"] == ["product_description"]


def test_full_brief_keeps_profile_and_scope_scan_gated():
    """Detection over questions: profile + scope come from the code scan, never
    the brief — even a fully-populated brief does not pre-answer them."""
    result = adopt_intake(FULL_BRIEF)
    assert result["scan_gated"] == ["profile", "scope"]
    assert "profile" not in result["brief_prefilled"]
    assert "scope" not in result["brief_prefilled"]


def test_full_brief_asks_fewer_questions_than_no_brief():
    """The core AC1/AC2 claim: a brief with a description removes exactly the
    product-description prompt (fewer questions), nothing more."""
    with_brief = adopt_intake(FULL_BRIEF)
    without = adopt_intake(None)
    assert without["brief_prefilled"] == []
    assert with_brief["brief_prefilled"] == ["product_description"]
    # Same scan-gated set either way — a brief only ever subtracts.
    assert with_brief["scan_gated"] == without["scan_gated"]


# --- Partial brief: coded answers but no description -------------------------

def test_coded_only_brief_prefills_nothing():
    """A brief that carries only coded answers (no free-text description) cannot
    pre-fill the product description — that Step-C prompt still fires."""
    result = adopt_intake(CODED_ONLY_BRIEF)
    assert result["has_brief"] is True
    assert result["product_description"] is None
    assert result["brief_prefilled"] == []
    assert result["scan_gated"] == ["profile", "scope"]


def test_blank_description_is_not_prefilled():
    result = adopt_intake({"description": "   "})
    assert result["product_description"] is None
    assert result["brief_prefilled"] == []


# --- No brief: Step C unchanged (AC3) ----------------------------------------

def test_no_brief_leaves_step_c_unchanged():
    result = adopt_intake(None)
    assert result["has_brief"] is False
    assert result["product_description"] is None
    assert result["brief_prefilled"] == []
    assert result["scan_gated"] == ["profile", "scope"]


def test_missing_brief_file_degrades_to_no_brief(tmp_path):
    """An explicit but absent brief file degrades to the no-brief path (adopt
    re-asks as today) rather than half-reading a bogus description (AC3)."""
    missing = tmp_path / "wizard-brief.json"  # never created
    result = adopt_intake("@" + str(missing))
    assert result["has_brief"] is False
    assert result["brief_prefilled"] == []


# --- Brief arrival shapes: inline payload + file path ------------------------

def test_inline_json_payload_prefills_description():
    payload = json.dumps(FULL_BRIEF)
    result = adopt_intake(payload)
    assert result["has_brief"] is True
    assert result["brief_prefilled"] == ["product_description"]


def test_brief_file_path_is_read(tmp_path):
    brief_file = tmp_path / "wizard-brief.json"
    brief_file.write_text(json.dumps(FULL_BRIEF), encoding="utf-8")
    result = adopt_intake(str(brief_file))
    assert result["has_brief"] is True
    assert result["product_description"] == "A booking tool for my yoga studio"


# --- Malformed / non-dict input degrades safely (never crashes) --------------

def test_malformed_inline_json_does_not_crash():
    """A malformed inline JSON payload falls back to free text (the brief_intake
    contract) rather than raising — adopt still gets a usable, safe result."""
    result = adopt_intake('{"description": not-valid-json')
    assert result["has_brief"] is True
    assert result["scan_gated"] == ["profile", "scope"]
    # Falls back to treating the raw payload as a free-text description.
    assert isinstance(result["product_description"], str)


def test_non_dict_json_file_prefills_nothing(tmp_path):
    """A brief FILE whose JSON is a list/scalar (not an object) degrades to
    'brief present but nothing to pre-fill' — never a mis-prefilled or crashed
    result, so profile + scope stay scan-gated."""
    brief_file = tmp_path / "wizard-brief.json"
    brief_file.write_text("[1, 2, 3]", encoding="utf-8")
    result = adopt_intake(str(brief_file))
    assert result["product_description"] is None
    assert result["brief_prefilled"] == []
    assert result["scan_gated"] == ["profile", "scope"]


# --- CLI (subprocess — the SKILL invocation path) ----------------------------

def test_cli_emits_adopt_intake_json():
    proc = subprocess.run(
        [sys.executable, SCRIPT, "--brief", json.dumps(FULL_BRIEF)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["has_brief"] is True
    assert out["brief_prefilled"] == ["product_description"]
    assert out["scan_gated"] == ["profile", "scope"]


def test_cli_no_brief_is_legacy():
    proc = subprocess.run(
        [sys.executable, SCRIPT],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["has_brief"] is False
    assert out["brief_prefilled"] == []


# --- main() in-process (subprocess coverage does not count toward diff-cover) -

def test_main_with_brief_prints_json(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["adopt_brief_intake.py", "--brief", json.dumps(FULL_BRIEF)])
    rc = abi.main()
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["has_brief"] is True
    assert out["brief_prefilled"] == ["product_description"]
    assert out["scan_gated"] == ["profile", "scope"]


def test_main_no_brief_prints_legacy(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["adopt_brief_intake.py"])
    rc = abi.main()
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["has_brief"] is False
    assert out["brief_prefilled"] == []


# --- Loader: fail-closed + poison-free cache (ADR-045 reuse hardening) --------

def test_loader_raises_when_spec_is_none(monkeypatch):
    """A None spec (file gone / unreadable) fails closed with ImportError and
    never registers a broken sentinel."""
    monkeypatch.setattr(abi.importlib.util, "spec_from_file_location", lambda *a, **k: None)
    sys.modules.pop(_SENTINEL, None)
    with pytest.raises(ImportError):
        abi._load_brief_intake()
    assert _SENTINEL not in sys.modules
    # Restore a clean state for later tests.
    monkeypatch.undo()
    sys.modules.pop(_SENTINEL, None)


def test_failed_exec_leaves_no_poisoned_sentinel(monkeypatch):
    """If exec_module raises, the half-initialised module must NOT stay cached
    under the sentinel — otherwise the memoization would return the broken
    module on every later call instead of re-raising."""
    sys.modules.pop(_SENTINEL, None)

    class _BoomLoader:
        def create_module(self, spec):
            return None

        def exec_module(self, module):
            raise RuntimeError("boom during exec")

    boom_spec = importlib.util.spec_from_loader(_SENTINEL, loader=_BoomLoader())
    monkeypatch.setattr(
        abi.importlib.util, "spec_from_file_location", lambda *a, **k: boom_spec
    )

    with pytest.raises(RuntimeError):
        abi._load_brief_intake()
    assert _SENTINEL not in sys.modules, "cache was poisoned with a broken module"

    # After restoring the real loader, a fresh load succeeds and the second
    # call returns the memoized module (early-return path).
    monkeypatch.undo()
    sys.modules.pop(_SENTINEL, None)
    mod = abi._load_brief_intake()
    assert hasattr(mod, "intake")
    assert abi._load_brief_intake() is mod
