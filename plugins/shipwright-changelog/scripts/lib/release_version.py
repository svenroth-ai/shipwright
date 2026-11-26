"""The release version at the boundary (operator decision Q8, finding D16).

An operator may type a version (Step 3). The tag is ``v{version}``, so ``v1.2.0`` used to become ``vv1.2.0``. Here a
leading ``v`` is cut off and anything that is not a SemVer number (``MAJOR.MINOR.PATCH`` with an optional pre-release
part, no leading zeros) is refused with a clear error; nothing is guessed. Build metadata (``+...``) stays refused, as the
CLI refused it before. ``not_above`` says whether a version is not higher than the last tag, in SemVer precedence; a last
tag that is no SemVer number cannot be compared and returns ``None`` (the caller reports that, it never guesses an order);
a tag's build metadata is ignored for the order, as SemVer says. Digits are ASCII only (``re.ASCII``).
"""

from __future__ import annotations

import re

_NUM = r"(?:0|[1-9]\d*)"
_PRE_ID = r"(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
SEMVER = re.compile(rf"({_NUM})\.({_NUM})\.({_NUM})(?:-({_PRE_ID}(?:\.{_PRE_ID})*))?", re.ASCII)
_BUILD = re.compile(r"\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*\Z", re.ASCII)  # only ever stripped from a TAG, never accepted as input


def normalize(text: str) -> str:
    """``text`` without one leading ``v``; ``ValueError`` (with the reason) when the rest is not a SemVer number."""
    bare = text.strip()
    bare = bare[1:] if bare.startswith("v") else bare
    if not SEMVER.fullmatch(bare):
        raise ValueError(f"{text!r} is not a SemVer version (MAJOR.MINOR.PATCH, optional -prerelease, no leading zeros)")
    return bare


def _key(version: str) -> tuple:
    found = SEMVER.fullmatch(version)
    if found is None:
        raise ValueError(version)
    core = tuple(int(found.group(n)) for n in (1, 2, 3))
    pre = found.group(4)
    if pre is None:  # a release ranks above every pre-release of the same core
        return core, (1,)
    ids = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split("."))  # numeric ids rank below alphanumeric
    return core, (0, ids)


def not_above(version: str, last_tag: str | None) -> bool | None:
    """True when ``version`` is not higher than ``last_tag``; False when it is (or there is no tag); None when either is
    no SemVer number and cannot be compared (a library caller passing ``v1.3.0`` still gets an answer, never a raise)."""
    if not last_tag:
        return False
    try:
        last = normalize(_BUILD.sub("", last_tag.strip()))
        current = normalize(version)
    except ValueError:
        return None
    return _key(current) <= _key(last)
