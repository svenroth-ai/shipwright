"""Concealed executables (``SURFACE_CONCEALED_EXECUTABLE``).

A file with a documentation/config extension whose bytes start like a program
(PE, ELF, Mach-O, a shebang) or an archive is hiding what it is from any
extension-based review. Only the first bytes are read, so the check is cheap to
run over every file in the tree.

Part of the advisory ``skill_surface_scan`` package; see its docstring for the
attribution note (categories inspired by NVIDIA SkillSpector, Apache-2.0; rules
re-implemented, no code or text copied).
"""

from __future__ import annotations

from pathlib import Path

DOC_SUFFIXES = {
    ".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".csv", ".toml", ".ini", ".cfg",
}

# (prefix bytes, label)
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"MZ", "a Windows executable (PE)"),
    (b"\x7fELF", "a Linux executable (ELF)"),
    (b"\xca\xfe\xba\xbe", "a Mach-O / Java class binary"),
    (b"\xcf\xfa\xed\xfe", "a Mach-O executable"),
    (b"\xce\xfa\xed\xfe", "a Mach-O executable"),
    (b"PK\x03\x04", "a zip archive"),
    (b"\x1f\x8b", "a gzip archive"),
    (b"#!", "a script (shebang)"),
)
_HEAD_BYTES = 64


def scan_concealed(path: Path, suffix: str, emit) -> None:
    """Emit when a documentation-extension file starts like an executable or archive."""
    if suffix not in DOC_SUFFIXES:
        return
    try:
        with path.open("rb") as handle:
            head = handle.read(_HEAD_BYTES)
    except OSError:
        return
    for prefix, label in _MAGIC:
        # "MZ" opens ordinary prose too (initials, names); a real PE header has NULs.
        if head.startswith(prefix) and (prefix != b"MZ" or b"\x00" in head):
            emit(
                "medium",
                "SURFACE_CONCEALED_EXECUTABLE",
                f"'{path.name}' has a documentation extension ({suffix}) but its content is "
                f"{label}. Extension-based review would not notice it.",
                None,
                "Rename it to its real type or remove it; documentation files must be text.",
            )
            return
