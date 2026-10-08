"""Loads the shared diff-size review threshold into this plugin lib.

The rule (``> 100`` added+removed lines against the merge-base, with the
finalization records left out) is defined once, in
``shared/scripts/lib/review_diff_threshold.py``. A plain ``from lib import ...``
would collide here: this plugin has its own ``scripts/lib`` and Python caches
whichever ``lib`` package loads first (ADR-044). So the file is loaded by path
under a private module name. The module is registered in ``sys.modules``
BEFORE it is executed (ADR-045), which keeps a re-entrant import from loading
a second copy.

There is no local fallback copy, on purpose. A fallback is how one definition
becomes two. A missing shared tree raises ``ImportError`` and names the file.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODULE_NAME = "_shipwright_shared_review_diff_threshold"
_REL = Path("shared") / "scripts" / "lib" / "review_diff_threshold.py"


def _locate() -> Path:
    """Walk up to the first ancestor that holds ``shared/`` (works in the monorepo and
    in the plugin cache). Same idiom as ``campaign_progress._find_shared_scripts``."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / _REL
        if candidate.is_file():
            return candidate
    raise ImportError(f"cannot find {_REL.as_posix()} above {here.parent}")


def _load():
    cached = sys.modules.get(_MODULE_NAME)
    if cached is not None:
        return cached
    path = _locate()
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(_MODULE_NAME, None)
        raise
    return module


_shared = _load()

SHARED_SOURCE: Path = Path(_shared.__file__)
PLAN_REVIEW_DIFF_LOC_THRESHOLD: int = _shared.PLAN_REVIEW_DIFF_LOC_THRESHOLD
exceeds_diff_threshold = _shared.exceeds_diff_threshold
is_counted_path = _shared.is_counted_path
