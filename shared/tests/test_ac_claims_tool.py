"""Q2 phase 1: the ``ac_claims.py`` tool builds the claims file from the AC record and prints where it landed."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from lib import ac_decision as ad
from lib import ac_record as ar
from shared.tests.ac_test_helpers import BASE_SPEC, cat_of, repo

_TOOL = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "ac_claims.py"
_RUN = "iterate-2026-11-07-q2-tool"
_ADD = {"kind": "add", "ac": "FR-01.03.AC06", "owner_fr": "FR-01.03", "new_text": "Given a draft, when saved twice, then both are kept"}


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_TOOL), *args], capture_output=True, text=True, check=False)


@pytest.mark.covers("FR-01.11/AC50")
def test_build_writes_the_file_and_reports_the_count(tmp_path):
    root = repo(tmp_path)
    ar.append_record(root, _RUN, ad.decide([_ADD], cat_of(BASE_SPEC)))
    done = _run("build", "--project-root", str(root), "--run-id", _RUN, "--base-ref", "HEAD")
    out = json.loads(done.stdout)
    assert done.returncode == 0 and out["claims"] == 1 and Path(out["path"]).is_file()


@pytest.mark.covers("FR-01.11/AC50")
def test_an_unusable_base_ref_is_a_skip_not_a_failure(tmp_path):
    root = repo(tmp_path)
    done = _run("build", "--project-root", str(root), "--run-id", _RUN, "--base-ref", "no-such-ref")
    assert done.returncode == 0 and json.loads(done.stdout)["status"] == "skipped"


@pytest.mark.covers("FR-01.11/AC50")
def test_an_unsafe_run_id_is_refused(tmp_path):
    root = repo(tmp_path)
    done = _run("build", "--project-root", str(root), "--run-id", "../x", "--base-ref", "HEAD")
    assert done.returncode == 2
