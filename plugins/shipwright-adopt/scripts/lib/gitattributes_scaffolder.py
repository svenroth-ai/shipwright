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

from pathlib import Path
from typing import TypedDict

try:  # tool context: lib/ is on sys.path (setup_adopt/_load_lib)
    from shared_loader import load_shared_module
except ImportError:  # test / package context: scripts/ on sys.path, lib is a package
    from lib.shared_loader import load_shared_module

# gitattributes_union's @dataclass resolves its own __module__ during exec, which
# needs the module registered in sys.modules first; load_shared_module registers
# before exec (and cleans up on failure) so this resolves — see shared_loader.
_UNION = load_shared_module(
    "scripts/lib/gitattributes_union.py", "_shipwright_adopt_gitattributes_union"
)
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
