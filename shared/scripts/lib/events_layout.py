"""Event-log LAYOUT: legacy single file vs per-run drop files (issue 978, S0).

DORMANT by default. ``legacy`` (the one tracked ``shipwright_events.jsonl``) stays
the layout everywhere until the campaign's flip unit; this module only lands the
``drops`` path (``shipwright_events.d/<key>--<wt8>--<nonce8>.jsonl``) behind a
switch so the harness and the standing replay gate can exercise it.

Layout precedence (campaign BRIEF section 2):

1. ``SHIPWRIGHT_EVENTS_LAYOUT`` env var -- a TEST-ONLY override, honoured ONLY when
   ``SHIPWRIGHT_EVENTS_LAYOUT_TEST=1`` is also set. The plain env var without the
   test flag changes nothing. Set by the test harness and this repo's own replay
   step; never by plugins or consumer CI templates.
2. ``events_layout`` in ``shipwright_sync_config.json``, read at runtime on every
   call (no cache). Absent / unknown value = ``legacy``, forever.
3. Default ``legacy``.

Format changes are drops-only: nothing here changes the bytes the legacy path
writes. ``resolve_events_write_path`` returns the literal legacy file under
``legacy``.

Append / rotation sequence and recovery (drops): under ``events_lock_path``'s lock
the writer (1) chooses the open drop of its key and worktree -- one not in HEAD's
tree -- or a fresh name, (2) appends one complete line with ``fsync``. A commit
"closes" a file simply by putting it into HEAD; the next write sees it there and
starts a new file, so a closed file is never edited. A crash between (1) and (2)
leaves at most a name that does not exist yet (files appear on the first complete
write; the folder alone is invisible to git); a torn line is recovered by
``read_jsonl_records`` exactly as in the legacy file. Same-key concurrent writers
serialize on the lock, so they share the one open file and every recorded event is
readable exactly once.

Not in S0 (owned by later units, see the BRIEF): the ``run`` stamp and 16-hex ids
(S4), the single live key-precedence writer module (S4), per-file read status
(S2), fold/archive tooling (S6). The key rule below is the minimum a dormant
writer needs. The advisory lock is ``events_lock_path`` -- the SAME untracked file
the legacy path already locks, so it lives OUTSIDE the tracked drops folder.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .jsonl_records import RecordRead, read_jsonl_records

EVENT_FILE = "shipwright_events.jsonl"  # same literal as lib.events_log.EVENT_FILE
DROPS_DIR = "shipwright_events.d"
ARCHIVE_DIR = "shipwright_events.archive"
SYNC_CONFIG = "shipwright_sync_config.json"
LAYOUTS = ("legacy", "drops")

ENV_LAYOUT = "SHIPWRIGHT_EVENTS_LAYOUT"
ENV_LAYOUT_TEST = "SHIPWRIGHT_EVENTS_LAYOUT_TEST"

KEY_MAX = 80
_BAD_KEY_CHARS = re.compile(r"[^A-Za-z0-9._-]")
_DROP_NAME = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
_NONCE = re.compile(r"^[0-9a-f]{8}$")


def events_layout(project_root: Path | str) -> str:
    """Return ``"legacy"`` or ``"drops"`` for this tree (see module docstring)."""
    if os.environ.get(ENV_LAYOUT_TEST) == "1":
        forced = os.environ.get(ENV_LAYOUT, "").strip().lower()
        if forced in LAYOUTS:
            return forced
    try:
        cfg = json.loads((Path(project_root) / SYNC_CONFIG).read_text(encoding="utf-8-sig"))
        value = cfg.get("events_layout") if isinstance(cfg, dict) else None
    except (OSError, ValueError):
        return "legacy"
    return value if value in LAYOUTS else "legacy"


def events_lock_path(project_root: Path | str) -> Path:
    """The advisory lock file -- identical to the legacy ``<log>.lock``, untracked."""
    return Path(project_root) / (EVENT_FILE + ".lock")


def _git_identity(root: Path) -> tuple[str, bool, str]:
    """(absolute git dir, is main tree, branch name or ``HEAD`` when detached)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--absolute-git-dir",
             "--git-common-dir", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=15, check=True,
        ).stdout.splitlines()
        git_dir = os.path.realpath(out[0])
        common = Path(out[1])
        common = common if common.is_absolute() else root / common
        return git_dir, git_dir == os.path.realpath(common), out[2] if len(out) > 2 else "HEAD"
    except (OSError, subprocess.SubprocessError, IndexError):
        return os.path.realpath(root), True, ""


def _wt8(git_dir: str) -> str:
    return hashlib.sha256(os.path.normcase(git_dir).encode("utf-8")).hexdigest()[:8]


def worktree_id(project_root: Path | str) -> str:
    """``wt8``: first 8 hex of sha256 of the writing worktree's OWN git dir."""
    return _wt8(_git_identity(Path(project_root))[0])


def sanitize_key(raw: str) -> str:
    """Make ``raw`` a path-safe key (``[A-Za-z0-9._-]``, 1..80). Never empty."""
    key = _BAD_KEY_CHARS.sub("-", raw).lstrip(".") or "_run"
    return key[:KEY_MAX]


def drop_key(project_root: Path | str, identity: tuple[str, bool, str] | None = None) -> str:
    """The minimum S0 key rule: explicit run id, else branch, else detached/main."""
    explicit = os.environ.get("SHIPWRIGHT_RUN_ID", "").strip()
    if explicit:
        return sanitize_key(explicit)
    git_dir, is_main, branch = identity or _git_identity(Path(project_root))
    if is_main:
        return "_main"
    if branch and branch != "HEAD":
        return sanitize_key("_branch-" + branch)
    return "_detached-" + _wt8(git_dir)


def _names_in_head(root: Path) -> set[str] | None:
    """Drop file names already in HEAD's tree (``ls-tree``, never ``git status``).

    ``set()`` for an unborn HEAD / no repo (nothing is committed). ``None`` when the
    probe itself failed: the caller must then NOT reuse any existing file (a new
    file is always safe, a reused closed one is not).
    """
    try:
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", "HEAD"],
                              capture_output=True, text=True, timeout=15)
        if head.returncode != 0:
            return set()
        out = subprocess.run(
            ["git", "-C", str(root), "ls-tree", "--name-only", "HEAD", DROPS_DIR + "/"],
            capture_output=True, text=True, timeout=15, check=True,
        ).stdout
    except FileNotFoundError:
        return set()  # git not installed: not a repo, nothing committed
    except (OSError, subprocess.SubprocessError):
        return None
    return {line.rsplit("/", 1)[-1] for line in out.splitlines() if line}


def resolve_events_write_path(project_root: Path | str) -> Path:
    """Where the next event is appended. Call it INSIDE ``events_lock_path``'s lock.

    ``legacy``: the literal ``project_root / EVENT_FILE`` (today's behaviour).
    ``drops``: rotate-on-commit -- the open drop of this key and worktree (one NOT
    yet in HEAD's tree), else a fresh file name with a new nonce. The file itself
    comes into existence on the first complete write; the folder alone is invisible
    to git, so no empty file is ever committed.
    """
    root = Path(project_root)
    if events_layout(root) != "drops":
        return root / EVENT_FILE
    git_dir, is_main, branch = _git_identity(root)
    key, wt8 = drop_key(root, (git_dir, is_main, branch)), _wt8(git_dir)
    prefix = f"{key}--{wt8}--"
    drops = root / DROPS_DIR
    drops.mkdir(exist_ok=True)
    committed = _names_in_head(root)
    for path in sorted(drops.iterdir()) if committed is not None else ():
        name = path.name
        if (name.startswith(prefix) and name.endswith(".jsonl")
                and _NONCE.match(name[len(prefix):-len(".jsonl")])
                and name not in committed and not path.is_symlink()):
            return path
    name = f"{prefix}{uuid.uuid4().hex[:8]}.jsonl"
    if not _DROP_NAME.match(name):  # structurally impossible after sanitize_key
        raise ValueError(f"refusing unsafe drop file name: {name!r}")
    return drops / name


def _instant(ts: object) -> datetime:
    """Parsed UTC instant; unparseable sorts first (a total order is all we need)."""
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def read_events_assembled(project_root: Path | str) -> RecordRead:
    """Legacy file in FILE order, then archive + drops by (parsed instant, id).

    Byte-for-byte the plain legacy read when no drops/archive folder exists.
    """
    root = Path(project_root)
    result = read_jsonl_records(root / EVENT_FILE)
    folders = [root / d for d in (ARCHIVE_DIR, DROPS_DIR) if (root / d).is_dir()]
    if not folders:
        return result
    extra: list[dict] = []
    corrupt = list(result.corrupt)
    for folder in folders:
        for path in sorted(folder.glob("*.jsonl")):
            part = read_jsonl_records(path)
            extra.extend(part.records)
            corrupt.extend(part.corrupt)
    extra.sort(key=lambda e: (_instant(e.get("ts")), str(e.get("id", ""))))
    return RecordRead(records=list(result.records) + extra, corrupt=corrupt)
