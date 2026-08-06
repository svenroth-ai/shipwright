"""AC10 — the operator-facing message: useful, bounded, and content-free.

Split from ``test_runconfig_corrupt_reader.py`` for the 300-LOC budget. These
assert the CONTRACT of what a person and a machine see when the run config
cannot be used; that suite asserts what the reader DECIDES.
"""
import json
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))  # for runconfig_corrupt_shapes

import orchestrator  # noqa: E402,F401 — installs the ``orchestrator`` shim namespace
from orchestrator_pkg import config_io  # noqa: E402
from orchestrator_pkg.config_io import RunConfigUnreadable  # noqa: E402
from orchestrator_pkg.constants import CONFIG_NAME  # noqa: E402
from runconfig_corrupt_shapes import CANARY_MARKER, write  # noqa: E402


def test_message_never_echoes_file_content(tmp_path):
    write(tmp_path, '{"marker": "%s", ' % CANARY_MARKER)
    with pytest.raises(RunConfigUnreadable) as excinfo:
        config_io.read_run_config(tmp_path)
    rendered = str(excinfo.value) + json.dumps(excinfo.value.payload())
    assert CANARY_MARKER not in rendered


@pytest.mark.parametrize("content", ["{oops", "null"])
def test_message_is_encodable_on_a_cp1252_console(tmp_path, content):
    """PRINTED text; on Windows that console is cp1252, so a stray em-dash
    would replace the diagnosis with a UnicodeEncodeError traceback."""
    write(tmp_path, content)
    with pytest.raises(RunConfigUnreadable) as excinfo:
        config_io.read_run_config(tmp_path)
    rendered = str(excinfo.value) + json.dumps(excinfo.value.payload())
    rendered.encode("cp1252")  # must not raise


def test_detail_is_bounded(tmp_path):
    write(tmp_path, "{oops")
    with pytest.raises(RunConfigUnreadable) as excinfo:
        config_io.read_run_config(tmp_path)
    assert len(excinfo.value.detail) <= config_io.MAX_DETAIL_CHARS


def test_initialises_its_base_and_keeps_the_cause(tmp_path):
    """A bare ``str(exc)`` must still be useful; the traceback must survive."""
    write(tmp_path, "{oops")
    with pytest.raises(RunConfigUnreadable) as excinfo:
        config_io.read_run_config(tmp_path)
    assert str(excinfo.value).strip(), "RuntimeError base was never initialised"
    assert CONFIG_NAME in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, json.JSONDecodeError)


def test_payload_survives_an_awkward_project_path(tmp_path):
    """Output must not be corruptible by the path. Backslashes (the real
    escaping hazard) are in every Windows path; ``"`` / ``|`` are illegal
    there and cannot be tested portably."""
    awkward = tmp_path / "it's a dir (x)"
    awkward.mkdir()
    write(awkward, "{oops")
    with pytest.raises(RunConfigUnreadable) as excinfo:
        config_io.read_run_config(awkward)
    # The round-trip is the assertion: a payload that cannot survive
    # dumps->loads is one a caller cannot parse.
    assert json.loads(json.dumps(excinfo.value.payload()))["reason"] == "config_unreadable"


