"""A bundled node profile copied verbatim into a project is a CUSTOM profile (campaign S5 hand-off from S2).

Bundled node profiles declare ``testing.unit`` / ``testing.e2e`` without a ``command``; once copied they get
no bundled-only defaults (D9), so ``/shipwright-test`` exits 3, and the message must name the key the
USER has to add for that very layer (not always ``testing.unit``). Tagged to FR-01.06.
"""

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib import test_runner  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.06")

_BUNDLED = Path(__file__).resolve().parents[3] / "shared" / "profiles" / "vite-hono.json"


def _copy_verbatim(root: Path) -> None:
    dest = root / ".shipwright" / "profiles"
    dest.mkdir(parents=True)
    shutil.copy2(_BUNDLED, dest / "vite-hono.json")


@pytest.mark.parametrize("layer,key", [("unit", "testing.unit.command"), ("e2e", "testing.e2e.command")])
def test_copied_bundled_profile_names_the_real_key_per_layer(tmp_path, monkeypatch, capsys, layer, key):
    declared = json.loads(_BUNDLED.read_text(encoding="utf-8"))["testing"]
    assert layer in declared and not (isinstance(declared[layer], dict) and declared[layer].get("command"))
    _copy_verbatim(tmp_path)
    ran = []
    monkeypatch.setattr(test_runner, "run_tests", lambda cmd, cwd=None: ran.append(cmd) or {"success": True})
    monkeypatch.setattr(sys, "argv", ["test_runner.py", "--cwd", str(tmp_path), "--profile", "vite-hono",
                                      "--layer", layer])
    assert test_runner.main() == 3
    out = json.loads(capsys.readouterr().out)
    assert ran == [] and f"defines no {layer} command" in out["error"] and f"`{key}`" in out["error"]


def test_hint_maps_pgtap_to_its_db_tests_key(tmp_path):
    root = tmp_path
    (root / ".shipwright" / "profiles").mkdir(parents=True)
    (root / ".shipwright" / "profiles" / "my-stack.json").write_text(
        json.dumps({"name": "my-stack", "testing": {"db_tests": {"dir": "db"}}}), encoding="utf-8")
    with pytest.raises(ValueError, match=r"`testing\.db_tests\.command`"):
        test_runner.get_test_command("my-stack", "pgtap", cwd=str(root))
