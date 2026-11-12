"""`--project-root` is accepted before AND after the subcommand (trg-87cd62db).

The WebUI passes it before the verb; operators type it after. A subparser
default would overwrite the value given before the verb, so the subparser copy
uses `default=argparse.SUPPRESS`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from triage import append_triage_item  # noqa: E402

TRIAGE_CLI = _SHARED_SCRIPTS / "tools" / "triage_cli.py"

pytestmark = pytest.mark.covers("FR-01.14/AC01")



def _list(args: list[str], cwd: Path) -> dict:
    res = subprocess.run([sys.executable, str(TRIAGE_CLI), *args],
                         capture_output=True, text=True, check=False, cwd=cwd)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _store(root: Path, title: str) -> str:
    return append_triage_item(root, source="t", severity="low", kind="bug",
                              title=title, detail="d")


def test_before_and_after_read_the_same_store(tmp_path: Path) -> None:
    store, elsewhere = tmp_path / "store", tmp_path / "elsewhere"
    elsewhere.mkdir()
    item_id = _store(store, "in the store")
    before = _list(["--project-root", str(store), "list", "--json"], elsewhere)
    after = _list(["list", "--json", "--project-root", str(store)], elsewhere)
    assert [i["id"] for i in before["open"]] == [item_id]
    assert before["open"] == after["open"]


def test_both_given_the_one_after_the_verb_wins(tmp_path: Path) -> None:
    first, second, elsewhere = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    elsewhere.mkdir()
    _store(first, "a")
    second_id = _store(second, "b")
    out = _list(["--project-root", str(first), "list", "--json",
                 "--project-root", str(second)], elsewhere)
    assert [i["id"] for i in out["open"]] == [second_id]


def test_neither_given_defaults_to_cwd(tmp_path: Path) -> None:
    item_id = _store(tmp_path, "cwd")
    out = _list(["list", "--json"], tmp_path)
    assert [i["id"] for i in out["open"]] == [item_id]
