#!/usr/bin/env python3
"""CLI wrapper around ``lib.ac_identity.mint`` — the AC-id minting tool E1
requires ("the id is assigned, not typed").

    uv run shared/scripts/tools/mint_ac_ids.py \\
        --spec-file .shipwright/planning/01-adopted/spec.md \\
        --registry-file shipwright_ac_registry.json \\
        --write

Default (no ``--write``) is a DRY RUN: prints what would be minted, changes
nothing on disk — the safe way to see the effect before committing to it.
``--write`` applies the mint to the spec file AND persists the updated
registry, so a later run on the same or a different spec file never reuses
a number this run assigned.

Not wired into anything yet (deliberately — P3.1's own scope, SPEC §5:
"S1 ... Keine Wirkung stromabwärts"). Later sub-iterates (P3.2+) are what
make the minted ids load-bearing.

**Concurrency (external code review, 2026-09-06, openai high).** Two
``--write`` invocations racing on the SAME registry file could both read the
same high-water mark and mint the same next AC id — exactly what the
registry exists to prevent. The whole read-mint-write sequence below runs
inside ``lib.file_lock.file_lock()``, keyed on a ``<registry-file>.lock``
sidecar, so a second concurrent invocation waits (or times out loudly) rather
than silently racing.

**Write ORDER (external code review, 2026-09-06 round 2, openai high).**
``--write`` persists the REGISTRY before the spec, not after. ``mint()``
already documents (and tests) that a registry sitting AHEAD of every marker
in the document is safe and self-healing — it is exactly the "interrupted
write" case, and the next mint simply leaves the gap unfilled, never reusing
it. The reverse order is not safe: if the process died after the spec write
but before the registry write, and the newly-marked criterion were then
hand-deleted before a successful retry, nothing would remember that number
was ever issued, and a later mint could reuse it. Registry-first means the
worst an interruption ever produces is a harmless gap, never a reuse.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import ac_identity  # noqa: E402
from atomic_write import durable_atomic_write  # noqa: E402
from file_lock import file_lock  # noqa: E402

#: How long ``--write`` waits for another concurrent invocation on the same
#: registry file before giving up loudly rather than racing it.
_LOCK_TIMEOUT_SECONDS = 30.0


def _load_registry(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: registry must be a JSON object, got {type(raw).__name__}")
    for fr_id, value in raw.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(
                f"{path}: registry[{fr_id!r}] must be a non-negative int, got "
                f"{value!r} ({type(value).__name__})"
            )
    return raw


def _mint_once(spec_path: Path, registry_path: Path, *, write: bool) -> dict:
    content = spec_path.read_text(encoding="utf-8")
    registry = _load_registry(registry_path)
    result = ac_identity.mint(content, registry)

    payload = {
        "spec_file": str(spec_path),
        "registry_file": str(registry_path),
        "assigned": [{"fr_id": fr_id, "ac_id": ac_id} for fr_id, ac_id in result.assigned],
        "written": False,
    }

    if write:
        # Registry BEFORE spec -- see module docstring "Write ORDER": a
        # registry ahead of the document is safe and self-healing, the
        # reverse is not.
        #
        # Written unconditionally (not just when it changed) so the file is
        # genuinely "created on first --write if absent" as documented above,
        # even for a spec with no criterion bullets at all (external code
        # review, 2026-09-06, GLM low #5).
        #
        # durable_atomic_write, not write_text (code review round 3): the
        # house pattern for a tracked artifact a crash mid-write must never
        # leave truncated -- a plain write_text interrupted partway through
        # would leave invalid JSON (registry) or a half-rewritten spec.md in
        # place, exactly what "registry BEFORE spec" above is trying to make
        # safe to interrupt.
        durable_atomic_write(
            registry_path,
            json.dumps(result.registry, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        if result.content != content:
            durable_atomic_write(spec_path, result.content)
        payload["written"] = True

    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--spec-file", required=True, help="The spec.md to mint AC ids into")
    parser.add_argument(
        "--registry-file", required=True,
        help="Tracked JSON: fr_id -> highest AC number ever minted for it "
             "(created on first --write if absent)",
    )
    parser.add_argument(
        "--write", action="store_true",
        help="Apply the mint: rewrite --spec-file in place and persist "
             "--registry-file. Without this flag nothing is written.",
    )
    args = parser.parse_args(argv)

    spec_path = Path(args.spec_file)
    registry_path = Path(args.registry_file)
    lock_path = Path(str(registry_path) + ".lock")

    with file_lock(lock_path, timeout_seconds=_LOCK_TIMEOUT_SECONDS):
        payload = _mint_once(spec_path, registry_path, write=args.write)

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
