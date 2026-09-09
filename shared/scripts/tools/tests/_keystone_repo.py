"""A real git repo with a real spec.md, shared by the P3.6 keystone tests.

Not a ``test_*`` module, so pytest does not collect it — the ``_backfill_support.py``
convention already in this directory.

**Real git, never a mock.** ``_keystone_ac_digest`` is the gate's only git-facing
half, and a wrong invocation there fails in the one direction the design forbids:
silently, as "no acceptance criterion changed". A mocked reader would test the
mock. Reused by ``test_keystone_ac_digest.py``, ``test_keystone_readers.py``,
``test_check_keystone_ac_gate.py`` and ``test_keystone_gate_infra.py`` so the four
cannot drift into asserting against different spec shapes.

The CLI harness at the bottom (:func:`bound_manifest`, :func:`run_gate`,
:func:`edit_ac01`) lives here for the same reason and not merely to save lines:
external code review (glm, low) found it copy-pasted verbatim into the second CLI
test module, which is precisely the drift this module's first paragraph says it
exists to prevent. Two copies of "the manifest the gate is graded against" can
diverge silently, and the module asserting the WEAKER shape would still be green.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

import check_keystone_ac_gate as gate  # noqa: E402
from verifiers import _keystone_ac_digest as kd  # noqa: E402

SPEC_REL = "docs/spec.md"
MANIFEST_RELPATH = kd.MANIFEST_RELPATH

#: FR-01.01 carries two minted criteria plus a trailing prose line (so a
#: prose-only edit can be shown to be inert); FR-01.02 carries one.
BASE_SPEC = """# Spec

## 2. Functional Requirements

### FR-01.01: Widgets

- [AC01] The widget must fizz.
- [AC02] The widget must buzz.

Some prose that is not a criterion at all.

### FR-01.02: Gadgets

- [AC03] The gadget must whirr.
"""


def git(*args: str, cwd: Path) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True, encoding="utf-8")
    return done.stdout.strip()


def manifest(spec_rel: str = SPEC_REL, ids=("FR-01.01", "FR-01.02")) -> dict:
    return {
        "requirements": {
            f"ns::{fr}": {"id": fr, "status": "active", "spec_path": spec_rel}
            for fr in ids
        },
    }


def make_repo(tmp_path: Path, *, spec: str = BASE_SPEC,
              manifest_obj: dict | None = None) -> Path:
    """A one-commit repo on ``main`` carrying ``spec`` and a v4-ish manifest."""
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / ".shipwright" / "compliance").mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=root)
    git("config", "user.email", "t@example.com", cwd=root)
    git("config", "user.name", "T", cwd=root)
    (root / SPEC_REL).write_text(spec, encoding="utf-8")
    write_manifest(root, manifest_obj if manifest_obj is not None else manifest())
    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", "base", cwd=root)
    return root


def write_manifest(root: Path, obj: dict) -> None:
    (root / MANIFEST_RELPATH).write_text(json.dumps(obj, indent=2), encoding="utf-8")


def commit_spec(root: Path, text: str, message: str = "head") -> str:
    (root / SPEC_REL).write_text(text, encoding="utf-8")
    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", message, cwd=root)
    return git("rev-parse", "HEAD", cwd=root)


def commit_all(root: Path, message: str) -> str:
    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", message, cwd=root)
    return git("rev-parse", "HEAD", cwd=root)


# --------------------------------------------------------------------------
# The CLI harness, shared by both check_keystone_ac_gate test modules
# --------------------------------------------------------------------------

def bound_manifest(*, bind_ac: bool = True, executed: str = "pass") -> dict:
    """The base/head manifest, with FR-01.01/AC01 bound to one unit test.

    ``bind_ac=False`` models the dodge: the ``@covers`` tag lost its ``/AC01``
    suffix, so the generator emits no ``acs`` entry for it at all.
    """
    node = {
        "id": "FR-01.01", "status": "active", "spec_path": SPEC_REL,
        "required_layers": ["unit"], "required_layers_source": "inferred_legacy",
        "acs": {},
    }
    if bind_ac:
        node["acs"] = {"AC01": {"tests": {"unit": [
            {"id": "tests/test_widget.py::test_fizz", "layer": "unit",
             "status": "enabled", "executed": executed},
        ]}}}
    return {
        "requirements": {
            "ns::FR-01.01": node,
            "ns::FR-01.02": {"id": "FR-01.02", "status": "active", "spec_path": SPEC_REL,
                             "required_layers": ["unit"],
                             "required_layers_source": "inferred_legacy", "acs": {}},
        },
    }


def run_gate(root: Path, head_sha: str, base_sha: str = "HEAD~1", capsys=None):
    """``(exit_code, payload)`` from an in-process ``main(argv)`` call."""
    resolved = git("rev-parse", base_sha, cwd=root) if base_sha else ""
    argv = ["--project-root", str(root), "--head-sha", head_sha]
    if resolved:
        argv += ["--base-sha", resolved]
    code = gate.main(argv)
    payload = json.loads(capsys.readouterr().out)
    return code, payload


def edit_ac01(root: Path, message: str = "edit AC01") -> str:
    """Commit a real one-criterion edit to FR-01.01/AC01."""
    return commit_spec(
        root, BASE_SPEC.replace("The widget must fizz.", "The widget must fizz TWICE."),
        message,
    )
