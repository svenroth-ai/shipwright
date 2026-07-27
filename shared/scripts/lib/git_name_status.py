"""Pure parser for ``git diff --name-status -z`` output.

Split from :mod:`lib.requirement_impact_git` so that module stays inside the
300-line limit and so this — the part with all the index arithmetic — can be
tested without spawning git.

NUL-delimited and unquoted on every platform, which is why the ``-z`` form is
used: paths containing spaces, quotes or non-ASCII survive intact.

Origin: trg-e9e5188e (FR-01.05).
"""

from __future__ import annotations

from lib.requirement_impact import to_repo_relative_posix


class NameStatusError(ValueError):
    """The stream was malformed. Raised rather than returning a short result.

    A truncated diff that reads as a *short clean diff* is the worst possible
    answer: it reports fewer changed files than really changed, so an attribution
    check would pass on work it never saw.
    """


def rebase(path: str, prefix: str) -> str:
    """Re-express a repository-root-relative path relative to the project root.

    ``git diff`` reports paths from the repository root; everything else in this
    mechanism is project-root-relative. When a Shipwright project sits in a
    subdirectory of a larger repo the two disagree, and comparing them directly
    matched nothing at all. Returns ``""`` for a path outside the project.
    """
    if not prefix:
        return path
    if path == prefix:
        return ""
    return path[len(prefix) + 1:] if path.startswith(f"{prefix}/") else ""


def parse(stdout: str, prefix: str = "") -> dict[str, list[str]]:
    """Split the stream into ``added_modified`` / ``deleted`` / ``renamed``.

    Renames and copies carry TWO paths and are treated asymmetrically: the
    **destination** joins ``added_modified`` because it is a path that now exists
    and somebody is answerable for, while only the **source** is recorded as
    ``renamed``. Bucketing both as "renamed" (and then not checking renamed
    paths) let a ``git mv`` plus a rewrite of a shared file escape entirely —
    git reports exactly that as a single ``R`` record with a low similarity score.
    """
    buckets: dict[str, list[str]] = {"added_modified": [], "deleted": [], "renamed": []}
    fields = [f for f in stdout.split("\0") if f != ""]
    index = 0
    while index < len(fields):
        code = fields[index].strip()
        index += 1
        if not code:
            continue
        letter = code[0].upper()
        # R100 / C075 consume a source AND a destination field.
        if letter in ("R", "C"):
            if index + 1 >= len(fields):
                raise NameStatusError("truncated rename/copy record in git diff output")
            old = rebase(to_repo_relative_posix(fields[index]), prefix)
            new = rebase(to_repo_relative_posix(fields[index + 1]), prefix)
            index += 2
            if old:
                buckets["renamed"].append(old)
            if new:
                buckets["added_modified"].append(new)
            continue
        if index >= len(fields):
            raise NameStatusError(f"truncated {letter!r} record in git diff output")
        path = rebase(to_repo_relative_posix(fields[index]), prefix)
        index += 1
        if not path:
            continue
        if letter == "D":
            buckets["deleted"].append(path)
        else:
            buckets["added_modified"].append(path)
    return buckets
