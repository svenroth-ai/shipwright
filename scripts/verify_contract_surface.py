#!/usr/bin/env python3
"""Drive BOTH cross-repo contract producers end-to-end and check what they emit.

The unit gates pin the shape a producer *would* emit. This drives the actual command
line a consumer runs — ``grade.py --format json`` and ``analyze_codebase.py`` — against a
real repository, parses the bytes that come out, and checks them against the contract
fixture published for the version they claim.

That difference matters: everything upstream of ``json.dumps`` could be correct while a
wrapper, a custom encoder, or a changed CLI flag silently altered what actually reaches
the Command Center. This is the only check that reads the real output of the real command.

    uv run scripts/verify_contract_surface.py

Exit 0 = both artifacts conform. Non-zero = the surface a consumer fetches has drifted
from the contract this repo publishes.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_GRADE = _ROOT / "plugins" / "shipwright-grade"
_ADOPT = _ROOT / "plugins" / "shipwright-adopt"


def _force_utf8_stdio() -> None:
    """Emit UTF-8 regardless of the console code page.

    This script prints arrows; on a Windows cp1252 console a bare ``print`` of those
    raises UnicodeEncodeError and the whole gate dies for a cosmetic reason. Same guard
    grade.py carries.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - defensive
                pass


def _load(name: str):
    """Load a shared contract module by path (never via sys.path — ADR-045)."""
    spec = importlib.util.spec_from_file_location(
        name, _ROOT / "shared" / "scripts" / "lib" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CE = _load("contract_skeleton")


def _fixture(plugin: Path, stem: str, version: str) -> dict:
    path = plugin / "tests" / "contracts" / f"{stem}-{version}.json"
    if not path.is_file():
        raise SystemExit(
            f"FAIL: {stem} claims schema_version {version}, but {path.name} does not "
            "exist. A version the consumer cannot look up is not a contract."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _prune_opaque(skeleton, opaque: tuple[str, ...], prefix: str = ""):
    """Blank the subtrees the contract declares OPAQUE, exactly as the pin does.

    ``stack.frontend`` is ``{"react": …}`` here and ``{"vue": …}`` in the next repo — the
    keys ARE the finding, so the contract pins them by kind and requires the consumer to
    iterate them. Comparing their interiors would be comparing content, not contract.
    """
    if isinstance(skeleton, dict):
        out = {}
        for key, sub in skeleton.items():
            path = f"{prefix}.{key}" if prefix else key
            out[key] = ("<opaque:object>" if isinstance(sub, dict) else "<opaque>") \
                if path in opaque else _prune_opaque(sub, opaque, path)
        return out
    if isinstance(skeleton, list):
        return [_prune_opaque(item, opaque, f"{prefix}[]") for item in skeleton]
    return skeleton


def _conforms(artifact: str, pinned: dict, payload: dict) -> list[str]:
    """Every path the artifact emits must be pinned, with a type the pin allows.

    Subset, not equality: one repository need not exercise every arm of the contract (it
    may score every dimension, so ``score`` shows up as ``number`` where the pin allows
    ``number|null``, and with the network off it emits an empty ``network_enrichments``).
    """
    opaque = tuple(pinned.get("opaque", ()))
    pin = CE.flatten(pinned["contract"]["skeleton"])
    actual = CE.flatten(_prune_opaque(CE.skeleton_of(payload), opaque))
    problems: list[str] = []
    for path, token in sorted(actual.items()):
        if token == "array<unpinned>":  # An empty array is a valid instance of a pinned one.
            if not any(key.startswith(f"{path}[]") for key in pin):
                problems.append(f"{artifact}: emits array {path!r}, which is not pinned")
            continue
        if path not in pin:
            problems.append(f"{artifact}: emits {path!r}, which the contract does not pin")
        elif not set(token.split("|")) <= set(pin[path].split("|")):
            problems.append(
                f"{artifact}: {path} is {token!r}, contract allows {pin[path]!r}")
    return problems


def check_grade() -> list[str]:
    """`grade.py --format json` — the payload the WebUI's Grade screen renders."""
    # Through `uv run --directory`, not the ambient interpreter: grade.py resolves its
    # own plugin env (defusedxml, for the hardened JUnit parser). Running it with the
    # root venv's python is not the command a user runs, and it dies on the import.
    done = subprocess.run(
        ["uv", "run", "--directory", str(_GRADE), "scripts/tools/grade.py",
         str(_ROOT), "--format", "json"],
        capture_output=True, text=True, check=False, timeout=900,
    )
    if done.returncode != 0:
        return [f"grade.py --format json exited {done.returncode}: {done.stderr[-500:]}"]
    payload = json.loads(done.stdout)
    version = payload.get("schema_version")
    if not version:
        return ["grade.py --format json emits no schema_version — the consumer cannot "
                "tell a shape it understands from one it does not"]
    print(f"  grade.py --format json      → schema_version {version}, "
          f"{len(payload['dimensions'])} dimensions")
    return _conforms("grade", _fixture(_GRADE, "grade-report", version), payload)


def check_adopt() -> list[str]:
    """`analyze_codebase.py` — the snapshot the WebUI's Adopt screen reads."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "snapshot.json"
        done = subprocess.run(
            [sys.executable, str(_ADOPT / "scripts" / "tools" / "analyze_codebase.py"),
             "--project-root", str(_ROOT), "--output", str(out),
             "--exclude-path", ".worktrees"],
            capture_output=True, text=True, check=False, timeout=600,
        )
        if done.returncode != 0:
            return [f"analyze_codebase.py exited {done.returncode}: {done.stderr[-500:]}"]
        if not out.is_file():
            return ["analyze_codebase.py wrote no snapshot.json"]
        payload = json.loads(out.read_text(encoding="utf-8"))
    version = payload.get("schema_version")
    if not version:
        return ["snapshot.json carries no schema_version"]
    print(f"  analyze_codebase.py         → schema_version {version}, "
          f"stack={payload['stack'].get('primary_language')!r}")
    return _conforms("adopt", _fixture(_ADOPT, "adopt-snapshot", version), payload)


def main() -> int:
    _force_utf8_stdio()
    print("Driving both cross-repo contract producers end-to-end:")
    problems = check_grade() + check_adopt()
    if problems:
        print("\nFAIL — the surface a consumer fetches has drifted from the contract:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nPASS — both artifacts conform to the contract they publish. (2 surfaces)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
