#!/usr/bin/env python3
"""Fail-open cache repair serialized across 12 SessionStart hook copies."""
from __future__ import annotations
import hashlib, json, os, re, secrets, shutil, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from cache_repair_lock import CACHE_LOCK_NAME, CLAIM_TTL_SECONDS, COMPLETION_CLOCK_SKEW_SECONDS, acquire_cache_lock, observe_completion, read_claim_token, read_completion_age, session_event_key, session_repair_state, unlock_cache_lock
except (ImportError, OSError, SyntaxError):
    CLAIM_TTL_SECONDS = 30.0
    COMPLETION_CLOCK_SKEW_SECONDS = 1.0
    CACHE_LOCK_NAME = ".sessionstart-cache-repair.lock"
    acquire_cache_lock = observe_completion = read_claim_token = read_completion_age = None
    session_event_key = session_repair_state = unlock_cache_lock = None
_SHARED_SENTINEL = ("scripts", "lib", "project_root.py")
_IGNORE_NAMES = ("__pycache__", "*.pyc", "*.pyo", ".venv", ".pytest_cache",
                 ".git", "node_modules", ".in_use", ".orphaned_at",
                 ".python-version")
_IGNORE = shutil.ignore_patterns(*_IGNORE_NAMES)
_CLAIM_DIRNAME = ".sessionstart-claims"
_CLAIM_TTL_SECONDS = CLAIM_TTL_SECONDS
_CLAIM_WAIT_SECONDS = 5.0
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
def _claim_session(cache_root: Path, session_id: object, *,
                   wait_seconds: float = _CLAIM_WAIT_SECONDS,
                   token: str | None = None,
                   observer: str = "") -> Path | bool | None:
    """Return done-path(owner), False(completed by peer), or None(fail-open)."""
    if not isinstance(session_id, str):
        return None
    sid = session_id.strip()
    if not sid or sid == "unknown":
        return None
    directory = cache_root / _CLAIM_DIRNAME
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.is_symlink():
            return None
    except OSError:
        return None
    key = hashlib.sha256(sid.encode("utf-8")).hexdigest()[:32]
    prefix = f"ensure-shared-cache-{key}"
    claim = directory / f"{prefix}.claim"
    own = token or secrets.token_hex(16); observed_here = False
    deadline = time.monotonic() + max(0.0, wait_seconds)
    while True:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(claim, flags, 0o600)
        except FileExistsError:
            current = read_claim_token(claim) if read_claim_token else None
            if current is False:
                continue
            if current is None:
                return None
            if not current:
                if time.monotonic() >= deadline:
                    return None
                time.sleep(0.01)
                continue
            if not _TOKEN_RE.fullmatch(current):
                return None
            done = directory / f"{prefix}-{current}.done"
            age = read_completion_age(done) if read_completion_age else None
            if age is None: return None
            if age is not False:
                if -COMPLETION_CLOCK_SKEW_SECONDS <= age < _CLAIM_TTL_SECONDS:
                    if not observer or observed_here: return False
                claim = directory / f"{prefix}-{current}.next"; observed_here = False
                continue
            if observer and not observed_here and observe_completion:
                seen = observe_completion(done, observer)
                if seen is None: return None
                observed_here = seen
            if time.monotonic() >= deadline:
                print("shipwright: cache healer owner timed out; recovering under "
                      "the global cache lock", file=sys.stderr)
                return done
            time.sleep(0.01)
            continue
        except OSError:
            return None
        try:
            os.write(fd, own.encode("ascii"))
            os.fsync(fd)
        except OSError:
            os.close(fd)
            return None
        os.close(fd)
        return directory / f"{prefix}-{own}.done"
def _complete_session(done: Path) -> bool:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(done, flags, 0o600)
    except FileExistsError:
        return True
    except OSError:
        return False
    os.close(fd)
    return True
def _shared_healthy(shared_dir: Path) -> bool:
    return shared_dir.is_dir() and shared_dir.joinpath(*_SHARED_SENTINEL).is_file()
def _delivered(root: Path) -> set[str] | None:
    if not root.is_dir():
        return None
    out: set[str] = set()
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            return None
        ignored = _IGNORE(str(current), [e.name for e in entries])
        for entry in entries:
            if entry.name in ignored:
                continue
            try:
                if entry.is_dir():
                    stack.append(entry)
                elif entry.is_file():
                    rel = entry.relative_to(root).as_posix()
                    out.add(rel.lower() if os.name == "nt" else rel)
            except OSError:
                return None
    return out
def _incomplete(src: Path, dst: Path) -> bool | None:
    want = _delivered(src)
    if want is None:
        return None
    if not dst.is_dir():
        return True
    have = _delivered(dst)
    if have is None:
        return None
    return bool(want - have)
def _symlink_matches(src: Path, dst: Path) -> bool:
    try:
        return dst.is_symlink() and dst.resolve(strict=True) == src.resolve(strict=True)
    except OSError:
        return False
def _same_name_shared(cache_marketplace_root: Path) -> Path | None:
    same = cache_marketplace_root.parent.parent / "marketplaces" / \
        cache_marketplace_root.name / "shared"
    return same if _shared_healthy(same) else None
def _find_marketplace_shared(cache_marketplace_root: Path) -> Path | None:
    plugins_root = cache_marketplace_root.parent.parent  # cache/<name> -> cache -> plugins
    marketplaces = plugins_root / "marketplaces"
    if not marketplaces.is_dir():
        return None
    same = _same_name_shared(cache_marketplace_root)
    if same is not None:
        return same
    try:
        entries = sorted(marketplaces.iterdir())
    except OSError:
        return None
    for entry in entries:
        candidate = entry / "shared"
        if _shared_healthy(candidate):
            return candidate
    return None
_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(.*)$")
def _version_key(name: str) -> tuple:
    m = _SEMVER_RE.match(name)
    if not m:
        return (-1, -1, -1, name)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4) or "")
def _plugin_mirrors(cache_marketplace_root: Path, plugins_target: Path,
                    enumeration: list[bool] | None = None):
    """Yield newest installed source + mirror; repo dev model yields none."""
    enumerable = True
    try:
        candidates = sorted(cache_marketplace_root.iterdir())
    except OSError:
        if enumeration is not None:
            enumeration.append(False)
        return
    for plugin_dir in candidates:
        if not plugin_dir.is_dir() or not plugin_dir.name.startswith("shipwright-"):
            continue
        try:
            versions = sorted((v for v in plugin_dir.iterdir() if v.is_dir()),
                              key=lambda v: _version_key(v.name))
        except OSError:
            enumerable = False
            continue
        if versions:
            yield versions[-1], plugins_target / plugin_dir.name
    if enumeration is not None:
        enumeration.append(enumerable)
def _heal_plugins(cache_marketplace_root: Path, plugins_target: Path,
                  readiness: list[bool] | None = None) -> bool:
    """Overlay partial mirrors; complete mirrors self-no-op."""
    healed = False
    ready = True
    enumeration: list[bool] = []
    for src, dst in _plugin_mirrors(
        cache_marketplace_root, plugins_target, enumeration,
    ):
        if dst.is_symlink():
            ready = ready and _symlink_matches(src, dst)
            continue
        state = _incomplete(src, dst)
        if state is not True:
            ready = ready and state is False
            continue
        try:
            shutil.copytree(src, dst, ignore=_IGNORE, dirs_exist_ok=True)
        except OSError:
            ready = False
            continue  # one unwritable mirror must not block the other thirteen
        healed = True
        ready = ready and _incomplete(src, dst) is False
    if readiness is not None:
        readiness.append(ready and enumeration == [True])
    return healed
def main(payload: object = None, participant: str = "") -> int:
    if payload is None:
        try: payload = json.load(sys.stdin)
        except Exception: payload = {}
    try:
        plugin_root = Path(__file__).resolve().parents[2]  # scripts/hooks/<f> -> plugin root
        cache_root = plugin_root.parent.parent             # cache/<name> (or the repo, in dev)
        shared_target = cache_root / "shared"
        plugins_target = cache_root / "plugins"
        # The repo is the --plugin-dir dev model; do not litter it with claims.
        dev_model = (cache_root / "scripts" / "update-marketplace.sh").is_file()
        event_key = "" if session_event_key is None else session_event_key(payload)
        plugin_id = plugin_root.name if plugin_root.name.startswith("shipwright-") else plugin_root.parent.name
        participant = participant or f"{plugin_id}:standalone"
        coordination = None if dev_model else _claim_session(cache_root, event_key, observer=participant)
        if coordination is False:
            return 0
        if isinstance(coordination, Path): time.sleep(0.1)
        cache_lock = None if dev_model or acquire_cache_lock is None else acquire_cache_lock(
            cache_root / CACHE_LOCK_NAME,
        )
        if not dev_model and cache_lock is None:
            print("shipwright: cache writer lock unavailable; repair skipped",
                  file=sys.stderr)
            return 0
        healed: list[str] = []; repair_ready = False
        try:
            if isinstance(coordination, Path) and session_repair_state and \
                    session_repair_state(cache_root, event_key) is True:
                repair_ready = True; return 0
            if not _shared_healthy(shared_target):
                source = _find_marketplace_shared(cache_root)
                shared_ready = False
            else:
                authoritative = _same_name_shared(cache_root)
                state = _incomplete(authoritative, shared_target) \
                    if authoritative is not None else None
                source = authoritative if state is True else None
                shared_ready = state is False
            if source is not None:
                try:
                    shutil.copytree(source, shared_target, ignore=_IGNORE, dirs_exist_ok=True)
                    healed.append("shared")
                    shared_ready = (authoritative := _same_name_shared(cache_root)) is not None and _incomplete(authoritative, shared_target) is False
                except OSError:
                    shared_ready = False
            plugin_ready: list[bool] = []
            if _heal_plugins(cache_root, plugins_target, plugin_ready):
                healed.append("plugins")
            if healed:
                print(f"shipwright: self-healed the plugin cache ({', '.join(healed)})", file=sys.stderr)
            if not _shared_healthy(shared_target):
                print("shipwright: shared/ is missing from the plugin cache and no "
                      "marketplace clone was found. Run `bash scripts/update-marketplace.sh`.",
                      file=sys.stderr)
            repair_ready = shared_ready and plugin_ready == [True]
        finally:
            if isinstance(coordination, Path):
                if repair_ready:
                    observed = observe_completion(coordination, participant) \
                        if observe_completion else None
                    if observed is not None:
                        _complete_session(coordination)
                    else:
                        print("shipwright: completion observer unavailable; "
                              "completion not published", file=sys.stderr)
                else:
                    print("shipwright: cache repair incomplete; completion not "
                          "published", file=sys.stderr)
            if isinstance(cache_lock, int):
                try:
                    unlock_cache_lock(cache_lock)
                finally:
                    os.close(cache_lock)
    except Exception as exc:  # never block a session
        print(f"shipwright: ensure_shared_cache skipped ({exc!r})", file=sys.stderr)
    return 0
if __name__ == "__main__":
    sys.exit(main())
