"""Scaffold the append-log ``merge=union`` ``.gitattributes`` into adopted repos.

The Shipwright churn machinery keeps concurrent appends to the tracked append-log
artifacts (``shipwright_events.jsonl``, ``.shipwright/triage.jsonl``) merge-clean
via a root ``.gitattributes`` declaring ``merge=union``. That protection lived
only in the monorepo; without it every adopted repo falls back to git's default
conflict behavior the moment two iterates append concurrently (WebUI proved it —
#96–#100 hand-resolved exactly these files). This scaffolder lands the same
driver at adopt time.

Unlike ``gitleaks_config_scaffolder`` (whole-file, **never-overwrite**), a target
repo frequently **already has** a hand-rolled ``.gitattributes`` (line-ending
rules, LFS, linguist overrides). So this scaffolder **merges** — it appends only
the missing union lines under a managed marker and preserves every existing user
entry bit-for-bit (idempotent: a second run is a no-op). The merge logic is the
single source in ``shared/scripts/lib/gitattributes_union.py``, loaded by
absolute file path to avoid the adopt-``lib`` / shared-``lib`` package-name
collision (same technique as ``gitleaks_config_scaffolder``).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TypedDict

# Layout (identical in dev repo and ~/.claude plugin cache):
#   <root>/plugins/shipwright-adopt/scripts/lib/<this-file>.py
#   <root>/shared/scripts/lib/gitattributes_union.py
# parents[0]=lib, [1]=scripts, [2]=shipwright-adopt, [3]=plugins, [4]=<root>.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_UNION_MODULE_FILE = _REPO_ROOT / "shared" / "scripts" / "lib" / "gitattributes_union.py"


def _load_union_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "_shipwright_adopt_gitattributes_union", _UNION_MODULE_FILE
    )
    if spec is None or spec.loader is None:
        raise FileNotFoundError(
            f"could not load gitattributes-union logic from {_UNION_MODULE_FILE}"
        )
    module = importlib.util.module_from_spec(spec)
    # Register before exec so the module's @dataclass can resolve its own
    # __module__ in sys.modules (PEP-563 string annotations look it up); a
    # file-path load otherwise leaves it unregistered → AttributeError.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_UNION = _load_union_module()
GITATTRIBUTES_PATH: str = _UNION.GITATTRIBUTES_PATH  # type: ignore[attr-defined]


class ScaffoldResult(TypedDict):
    wrote: bool
    path: str
    reason: str  # "scaffolded" | "merged" | "already_present"


def scaffold_gitattributes(project_root: Path) -> ScaffoldResult:
    """Merge the union fragment into ``project_root/.gitattributes``.

    Returns a structured result so the adopt handoff banner can render the
    "installed" / "merged into existing" / "already present" line without
    re-reading the filesystem.
    """
    target = project_root / GITATTRIBUTES_PATH
    existing = target.read_text(encoding="utf-8") if target.exists() else None

    merged, changed = _UNION.merge_into(existing)  # type: ignore[attr-defined]
    if not changed:
        return {"wrote": False, "path": str(target), "reason": "already_present"}

    target.parent.mkdir(parents=True, exist_ok=True)
    # newline="" — write the merged bytes verbatim (merge_into already chose the
    # right EOL style); no platform newline translation.
    with target.open("w", encoding="utf-8", newline="") as fh:
        fh.write(merged)

    return {
        "wrote": True,
        "path": str(target),
        "reason": "scaffolded" if existing is None else "merged",
    }
