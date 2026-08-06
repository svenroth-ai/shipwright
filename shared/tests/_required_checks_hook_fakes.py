"""Shared loader + runner fake for the required-checks hook's two test modules.

Not a test module (the leading underscore keeps pytest from collecting it). Same
split rationale as `_required_checks_fakes.py` beside it, and as
`test_verify_local.py` / `test_verify_local_ci_drift.py`: one subject, two
concerns, both under the 300-line budget.

- ``test_check_required_checks_hook.py`` — the fail-soft contract, the
  invocation shape, the F7 scope guard, and ``main()``.
- ``test_check_required_checks_hook_throttle.py`` — how often it is allowed to
  reach the network at all.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / "shared" / "scripts" / "hooks" / "check_required_checks_hook.py"
PRODUCER = REPO_ROOT / "shared" / "scripts" / "tools" / "check_required_checks.py"
ITERATE_HOOKS = REPO_ROOT / "plugins" / "shipwright-iterate" / "hooks" / "hooks.json"


def load_hook():
    """Load by path, registering before exec (ADR-045).

    Never via `sys.path` for `lib`: the hook lives beside `shared/scripts/lib`, and
    binding that name for the test interpreter is the collision that reads green
    locally and red in CI. Its own directory IS added, because the hook imports its
    sibling `required_checks_state` by name — a uniquely-named module, the same
    shape `run_if_cache_ready.py` uses for `cache_repair_lock`. Running as a script
    puts that directory on the path automatically; `spec_from_file_location` does
    not, so the test harness supplies it.
    """
    hooks_dir = str(HOOK.parent)
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    spec = importlib.util.spec_from_file_location("_required_checks_hook_probe", HOOK)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_required_checks_hook_probe"] = module  # BEFORE exec — ADR-045
    spec.loader.exec_module(module)
    return module


def completed(code: int) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=b"", stderr=b"")


class Recorder:
    """A stand-in for `subprocess.run` that records the call and returns `result`."""

    def __init__(self, result=None, raises: BaseException | None = None) -> None:
        self.result = result if result is not None else completed(0)
        self.raises = raises
        self.calls: list[dict] = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": argv, **kwargs})
        if self.raises is not None:
            raise self.raises
        return self.result


def make_project(root: Path) -> Path:
    """A minimally Shipwright-managed tree.

    `shipwright_run_config.json` is what makes it one — for the canonical
    predicate AND for the degraded fallback. The `.shipwright/` directory is
    incidental (the throttle stamp lands there); it is deliberately NOT what
    qualifies the tree, which `test_a_bare_shipwright_directory_is_not_a_shipwright_project`
    pins from the other side.
    """
    (root / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8"
    )
    (root / ".shipwright").mkdir(exist_ok=True)
    return root
