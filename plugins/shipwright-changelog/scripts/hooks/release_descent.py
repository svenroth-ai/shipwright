"""The one rule "this tip is the release" shared by the release guard hook and ``release.py push-tag`` (unit P5). Stdlib only.

``tip`` is the release commit, or descends from it through event-only commits: ``commit`` is an ancestor of ``tip``, no merge commit lies
between them, and every commit between them touches at least one path and only the paths ``record-event`` commits (the event file and
the event drops). An amended release commit, a change and its revert, a merge commit and an empty commit are therefore not the release.

The caller supplies ``git(*args) -> (exit_code, stdout)`` so the hook (``git -C <root>``, own timeouts) and the CLI (its recorded runner,
which the tests replace) run the same questions. Loaded by ``release_guard.py`` from its own directory and by ``lib/release_push.py`` by path.
"""

from __future__ import annotations

from typing import Callable

EVENT_FILE = "shipwright_events.jsonl"
EVENT_DROPS = ".shipwright/events/drops/"  # what record-event commits
Git = Callable[..., "tuple[int, str]"]


def event_only(paths: list[str]) -> bool:
    return bool(paths) and all(p == EVENT_FILE or p.startswith(EVENT_DROPS) for p in paths)


def is_the_release(git: Git, commit: str, tip: str) -> bool:
    if tip == commit:
        return True
    if not tip or git("merge-base", "--is-ancestor", commit, tip)[0] != 0:
        return False
    if git("rev-list", "--merges", f"{commit}..{tip}")[1].strip():
        return False
    code, out = git("log", "--no-renames", "--name-only", "--format=%x01", f"{commit}..{tip}")  # each commit's own paths
    blocks = out.split("\x01")[1:]
    return code == 0 and bool(blocks) and all(event_only([n.strip() for n in b.splitlines() if n.strip()]) for b in blocks)
