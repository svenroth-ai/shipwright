"""Serialize one target invocation into a golden-file cell.

Split out of ``_collect_realm`` so each module stays inside the 300-line gate;
this half answers "what does a cell look like", the other half answers "how do
I reach the callable".

The cell records MORE than a value. If the baseline held only normalized value
payloads, campaign step S2 could change a target's return type, its laziness,
its ordering, or its exception behaviour and the matrix would still pass --
which would make this harness worse than useless, because it would certify a
change it cannot see.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

MAX_TEXT = 400  # cap file-text payloads so the golden file stays reviewable


def _spec_files(root: Path) -> list[Path]:
    """Every spec.md the materialized fixture actually contains."""
    planning = root / ".shipwright" / "planning"
    if not planning.is_dir():
        return []
    return sorted(p for p in planning.rglob("spec.md") if p.is_file())


def _posixify(value):
    """Canonicalize OS path separators inside an already-normalized value.

    Applied ONLY to targets flagged ``platform_sep`` in the registry --
    currently just ``setup-design-session.find_specs``, which returns
    ``str(relative_path)`` and therefore emits a backslash-separated
    string on Windows
    and ``01-auth/spec.md`` on Linux.

    That output is genuinely platform-dependent, so no serialization can be both
    faithful and identical across platforms. Baking the Windows form into the
    baseline would make the harness red on ubuntu CI from day one -- and the
    natural remedy (regenerate) is precisely the habit this corpus is designed
    to prevent. So the matrix carries the stable posix form and the
    platform-dependence itself is pinned in a dedicated explicit test.
    Narrowly scoped so a real backslash in spec CONTENT (e.g. an escaped
    pipe) is never rewritten.
    """
    if isinstance(value, str):
        return value.replace("\\", "/")
    if isinstance(value, list):
        return [_posixify(v) for v in value]
    if isinstance(value, dict):
        return {k: _posixify(v) for k, v in value.items()}
    return value

def _norm(value, root: Path):
    """Normalize a value for JSON, preserving type identity and order."""
    if isinstance(value, Path):
        try:
            return "<root>/" + value.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return "<abs>/" + value.as_posix().rsplit("/", 2)[-1]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _norm(getattr(value, f.name), root)
                for f in dataclasses.fields(value)}
    if isinstance(value, (list, tuple)):
        return [_norm(v, root) for v in value]
    if isinstance(value, (set, frozenset)):
        # sorted ONLY because a set has no order to preserve; the type is
        # recorded separately so this is not laundering an ordered result.
        return sorted(_norm(v, root) for v in value)
    if isinstance(value, dict):
        return {str(k): _norm(v, root) for k, v in value.items()}
    if isinstance(value, str):
        s = value.replace(str(root).replace("\\", "/"), "<root>")
        s = s.replace(str(root), "<root>")
        return s if len(s) <= MAX_TEXT else s[:MAX_TEXT] + f"...<+{len(s)-MAX_TEXT}>"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return f"<unserializable {type(value).__name__}>"

# pathlib instantiates a platform-specific CONCRETE subclass, so
# ``type(p).__name__`` is "WindowsPath" on Windows and "PosixPath" on Linux.
# Recording that verbatim freezes the generating machine's OS into the baseline
# and reddens CI on the other platform. The behaviour being frozen is "returns
# Path objects"; which concrete subclass is an artifact of where the tests ran,
# exactly like the path separator.
_PLATFORM_TYPE_ALIASES = {"WindowsPath": "Path", "PosixPath": "Path"}

# Reading a DIRECTORY as if it were a file raises a different OSError subclass
# per platform: PermissionError on Windows, IsADirectoryError on Linux. The
# portable behaviour -- and the one the corpus is freezing -- is "this target
# lets the error escape rather than swallowing it". Recording the concrete
# subclass would freeze the generating machine's OS, exactly like the path
# separator and the pathlib subclass name did.
#
# The narrow alias is deliberate: a blanket "any OSError -> OSError" would also
# flatten NotADirectoryError, which IS portable and which the planning-file
# fixture relies on to split the targets. The concrete per-platform subclass is
# pinned separately in test_requirements_corpus_registry.py.
_DIR_READ_ALIAS = "OSError:not-a-readable-file"
_PLATFORM_EXCEPTION_ALIASES = {
    "PermissionError": _DIR_READ_ALIAS,
    "IsADirectoryError": _DIR_READ_ALIAS,
}


def neutral_exception_name(exc: BaseException) -> str:
    raw = type(exc).__name__
    return _PLATFORM_EXCEPTION_ALIASES.get(raw, raw)


def _neutral_type_name(obj) -> str:
    raw = type(obj).__name__
    return _PLATFORM_TYPE_ALIASES.get(raw, raw)


def _type_of(value) -> str:
    if isinstance(value, list) and value:
        return f"list[{_neutral_type_name(value[0])}]"
    return _neutral_type_name(value)

def _record(call, root: Path, target: dict | None = None) -> dict:
    """Invoke *call* and record outcome kind, type, laziness, value.

    The exception MESSAGE is deliberately not recorded -- only its type. OS
    error strings embed the temp path and are locale-dependent (a German
    Windows box and an English CI runner disagree word-for-word), so pinning
    them would buy fragility rather than coverage. Which exception type escapes
    is the behaviour that matters.
    """
    try:
        result = call()
    except Exception as exc:  # noqa: BLE001 -- the exception IS the behaviour
        return {"outcome": "raised", "exception": neutral_exception_name(exc)}
    lazy = hasattr(result, "__next__") and hasattr(result, "__iter__")
    declared = _type_of(result)
    if lazy:
        try:
            result = list(result)
        except Exception as exc:  # noqa: BLE001
            return {"outcome": "raised", "lazy": True,
                    "exception": neutral_exception_name(exc)}
    cell = {
        "outcome": "returned",
        "type": "generator" if lazy else declared,
        "value": _norm(result, root),
    }
    if lazy:
        cell["consumed_type"] = _type_of(result)
    if target and target.get("platform_sep"):
        cell["value"] = _posixify(cell["value"])
        cell["platform_sep_normalized"] = True
    return cell
