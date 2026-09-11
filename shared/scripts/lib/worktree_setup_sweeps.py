"""Canon self-heal + outbox sweep run right after a fresh worktree is created
(steps 4.6/4.7/5 of ``setup_iterate_worktree.setup()`` — AFTER step 4.5's
``lib.layer_promotion_sweep``, deliberately: that sweep needs ``HEAD`` to
still equal the worktree's freshly-fetched base, before either self-heal or
the outbox sweep can add a commit of their own).

Split out of that orchestrator purely to keep it under the file-size
guideline — no behavior change versus the pre-split code, same call order,
same reported warnings shape.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.gitattributes_selfheal import self_heal_gitattributes  # noqa: E402
from lib.gitignore_selfheal import self_heal_gitignore  # noqa: E402
from lib.sweep_outbox import sweep_outbox_to_branch, sweep_warnings  # noqa: E402


def run_canon_and_outbox_sweeps(
    main_root: Path,
    worktree_path: Path,
    default_branch: str,
    *,
    note: Callable[[str], None],
) -> list[str]:
    """Self-heal the canon ``.gitattributes``/``.gitignore`` scaffolds into the
    worktree, then sweep the gitignored main-tree triage outbox into this
    worktree's tracked log + commit. Ordered deliberately: gitattributes
    before gitignore (D3 outbox-ignore block), both before the outbox sweep —
    either self-heal leaving the index dirty would false-skip the sweep's own
    staged-changes guard.

    ``note`` is the caller's own stderr printer, kept as a callback so this
    module carries no opinion about the ``setup_iterate_worktree:`` prefix.
    Returns the operator-facing warning strings (already passed to ``note``
    for the ones that need it), for the caller to fold into its own payload.
    """
    warnings: list[str] = []

    ga = self_heal_gitattributes(worktree_path)
    gi = self_heal_gitignore(worktree_path)
    for label, heal in (("gitattributes", ga), ("gitignore", gi)):
        if heal.status == "error":
            note(f"{label} self-heal {heal.reason}")
        if heal.status != "no_change":
            warnings.append(
                f"{label} self-heal {heal.status}" + (f": {heal.reason}" if heal.reason else "")
            )

    sweep = sweep_outbox_to_branch(main_root, worktree_path, default_branch=default_branch)
    for note_text in sweep_warnings(sweep):
        note(note_text)
        warnings.append(note_text)

    return warnings


__all__ = ["run_canon_and_outbox_sweeps"]
