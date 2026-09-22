"""Config-layer Codex hooks sync (R1b — AC2/AC3/AC5).

R1 (PR #781) inlines every Shipwright plugin's hooks into the Codex bundle's
own ``.codex-plugin/plugin.json``. Live probing found Codex CLI never
executes a plugin-bundled ``hooks`` key at all (openai/codex#16430,
#39895) — the one confirmed-working path is a **config-layer** hooks file:
``~/.codex/hooks.json``, global and trust-independent (see the iterate
spec's Design Notes for why global, not project-local). This module is the
producer: it reads the bundle's already-computed, already-deduplicated
``hooks`` key and merges it into ``codex_home / "hooks.json"``.

Per-hook **launcher-script** generation (the fix for a Windows ``cmd.exe /C``
double-quoting bug in Codex's own hook executor) lives in
``codex_hooks_launcher.py``, imported below — see that module's docstring
for the full mechanism.

Ownership detection uses a simpler signal than an exact
``(event, matcher, command)`` triple match (external review, glm + openai:
an operator's own identical entry could collide, and losing the sidecar
orphaned every prior entry permanently): a ``hooks.json`` entry is
Shipwright's if-and-only-if its command resolves inside the launcher
directory — self-evident from the entry alone.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from atomic_write import durable_atomic_write  # noqa: E402
from codex_runtime import is_codex_runtime  # noqa: E402
from file_lock import LockTimeout, file_lock  # noqa: E402
from plugin_root import PluginRootUnresolvedError, resolve_plugin_root  # noqa: E402

from codex_hooks_launcher import (  # noqa: E402
    CodexHooksSyncError,
    _PLACEHOLDER,
    _command_to_launcher_path,
    _materialize,
)

_LAUNCHER_DIR_NAME = "shipwright-hooks"
_HOOKS_FILENAME = "hooks.json"
_SIDECAR_FILENAME = ".shipwright-hooks-managed.json"
_LOCK_FILENAME = ".shipwright-hooks-sync.lock"


@dataclass
class SyncResult:
    applied: bool
    reason: str | None = None
    hooks_written: int = 0
    path: Path | None = None


def sync_codex_hooks(
    bundle_root: Path, *, codex_home: Path, allow_empty: bool = False
) -> SyncResult:
    """Merge *bundle_root*'s Codex-bundled hooks into
    ``codex_home / "hooks.json"``, relocating every command behind a
    launcher script (see module docstring). No-ops when *bundle_root* is
    not a real Codex bundle (AC5).

    Raises :class:`CodexHooksSyncError` unless *allow_empty* if the bundle
    yields zero hooks — a bundle with genuinely no hooks is not a real
    Shipwright bundle, so this is far more likely a corrupt or partial
    ``build_codex_plugin.py`` run than a legitimate "no hooks" state; syncing
    it anyway would silently strip every Shipwright entry that a prior,
    healthy sync wrote (doubt-reviewer, medium)."""
    if not is_codex_runtime(bundle_root):
        return SyncResult(applied=False, reason="not a Codex bundle")

    # Absolute regardless of caller-supplied relative paths or invocation
    # CWD: a relative codex_home would bake a relative launcher path into
    # hooks.json, which Codex may resolve against a different working
    # directory at hook-fire time — silently reproducing the exact
    # "hook registered but never fires" failure class this module exists
    # to eliminate (code review).
    bundle_root = bundle_root.resolve()
    codex_home = codex_home.resolve()

    bundle_hooks = _read_bundle_hooks(bundle_root)
    launcher_dir = codex_home / _LAUNCHER_DIR_NAME
    lock_path = codex_home / _LOCK_FILENAME

    try:
        with file_lock(lock_path, timeout_seconds=0):
            hooks_doc = _load_hooks_json(codex_home / _HOOKS_FILENAME)
            _validate_sidecar_if_present(codex_home / _SIDECAR_FILENAME)

            try:
                hooks_doc["hooks"] = _strip_shipwright_entries(
                    hooks_doc.get("hooks", {}), launcher_dir
                )
            except (AttributeError, TypeError, KeyError) as exc:
                raise CodexHooksSyncError(
                    f"{codex_home / _HOOKS_FILENAME} has an unexpected inner shape: {exc}"
                ) from exc

            launcher_dir.mkdir(parents=True, exist_ok=True)

            # Write the NEW launcher set first, then publish hooks.json
            # pointing at it, and only THEN delete stale launchers no
            # longer referenced — never delete-before-replace. Any crash
            # mid-write leaves the OLD, still-working hooks.json/launcher
            # pair intact rather than a hooks.json pointing at files that
            # were already removed (code review, high severity).
            try:
                new_hooks, manifest_entries = _materialize(
                    bundle_hooks, bundle_root, launcher_dir
                )
            except (AttributeError, TypeError, KeyError) as exc:
                raise CodexHooksSyncError(
                    f"bundle hooks at {bundle_root} have an unexpected shape: {exc}"
                ) from exc

            if not manifest_entries and not allow_empty:
                raise CodexHooksSyncError(
                    f"bundle at {bundle_root} produced zero hooks — likely a "
                    "corrupt or partial build, not a genuine 'no hooks' bundle; "
                    "pass allow_empty=True (--allow-empty on the CLI) to sync anyway"
                )

            for event, groups in new_hooks.items():
                hooks_doc["hooks"].setdefault(event, [])
                hooks_doc["hooks"][event].extend(groups)

            durable_atomic_write(
                codex_home / _HOOKS_FILENAME, json.dumps(hooks_doc, indent=2) + "\n"
            )
            durable_atomic_write(
                codex_home / _SIDECAR_FILENAME,
                json.dumps({"entries": manifest_entries}, indent=2) + "\n",
            )

            # hooks.json and the sidecar are already durably published above, so a
            # failure here is cosmetic (an orphaned launcher, cleaned up on the next
            # successful sync), never a lost write — it must not crash the process.
            # This tool is designed to be re-run while OTHER Codex sessions on the
            # machine are still active, so a concurrently-running session can hold a
            # stale launcher open (mid ``cmd.exe /C`` execution) exactly when this
            # loop tries to remove it: on Windows that raises a sharing-violation
            # PermissionError, which is neither malformed input nor an absence
            # signal, so it is logged and skipped rather than wrapped as
            # CodexHooksSyncError (doubt-reviewer, high).
            # manifest_entries["command"] is shlex-quoted on POSIX (module
            # docstring) — .name off the raw string would keep the
            # trailing quote char and never match a real launcher filename.
            wanted_names = {
                path.name
                for e in manifest_entries
                if (path := _command_to_launcher_path(e["command"])) is not None
            }
            for existing in launcher_dir.iterdir():
                if existing.name not in wanted_names:
                    try:
                        existing.unlink()
                        print(f"removed stale launcher: {existing}", file=sys.stderr)
                    except FileNotFoundError:
                        pass
                    except OSError as exc:
                        print(
                            f"warning: could not remove stale launcher {existing} "
                            f"({exc}) — will retry on next sync",
                            file=sys.stderr,
                        )
    except LockTimeout as exc:
        raise CodexHooksSyncError(
            f"another codex_hooks_sync run holds {lock_path} — try again shortly"
        ) from exc

    return SyncResult(
        applied=True,
        hooks_written=len(manifest_entries),
        path=codex_home / _HOOKS_FILENAME,
    )


def _read_bundle_hooks(bundle_root: Path) -> dict:
    """``plugin.json["hooks"]`` is `build_hook_inventory`'s own return value,
    which is ALREADY shaped ``{"hooks": {<event>: [group, ...]}}`` (see that
    function's docstring) — `build_codex_plugin.py` assigns it verbatim to
    the manifest's own ``"hooks"`` key, so the real on-disk shape is
    double-wrapped: ``plugin.json["hooks"]["hooks"]`` is the actual event
    map. Found live against a real built bundle — a hand-written test
    fixture using the flat shape does not catch this, so `_SAMPLE_HOOKS` in
    the test file mirrors the real double-wrap too."""
    plugin_json_path = bundle_root / ".codex-plugin" / "plugin.json"
    try:
        manifest = json.loads(plugin_json_path.read_text(encoding="utf-8"))
        return manifest["hooks"]["hooks"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CodexHooksSyncError(
            f"cannot read bundle hooks from {plugin_json_path}: {exc}"
        ) from exc


def _load_hooks_json(path: Path) -> dict:
    if not path.is_file():
        return {"hooks": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CodexHooksSyncError(f"cannot read existing {path}: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("hooks", {}), dict):
        raise CodexHooksSyncError(f"{path} is not a valid Codex hooks document")
    doc.setdefault("hooks", {})
    return doc


def _validate_sidecar_if_present(path: Path) -> None:
    if not path.is_file():
        return
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CodexHooksSyncError(f"cannot read existing {path}: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("entries"), list):
        raise CodexHooksSyncError(f"{path} is not a valid Shipwright sidecar manifest")


def _is_shipwright_entry(command: str, launcher_dir: Path) -> bool:
    """``.resolve()`` on the candidate, not just a lexical ``relative_to``
    against the already-absolute *launcher_dir* — closes a path-variant
    mismatch and a ``../``-traversal/symlink escape (external review,
    medium)."""
    candidate = _command_to_launcher_path(command)
    if candidate is None:
        return False
    try:
        candidate = candidate.resolve(strict=False)
        candidate.relative_to(launcher_dir)
    except (OSError, ValueError):
        return False
    return True


def _strip_shipwright_entries(hooks: dict, launcher_dir: Path) -> dict:
    stripped: dict = {}
    for event, groups in hooks.items():
        kept_groups = []
        for group in groups:
            kept_handlers = [
                handler
                for handler in group.get("hooks", [])
                if not _is_shipwright_entry(handler.get("command", ""), launcher_dir)
            ]
            if kept_handlers:
                kept_groups.append({**group, "hooks": kept_handlers})
        if kept_groups:
            stripped[event] = kept_groups
    return stripped


def _describe_bundle_hooks(bundle_hooks: dict, bundle_root: Path) -> str:
    """Human-readable preview of exactly what a confirmed sync would merge
    into ``~/.codex/hooks.json`` — the resolved (placeholder-substituted)
    command a launcher script would actually run, not the raw bundle text,
    so the operator reviews what will execute, not what is on disk."""
    lines = []
    for event, groups in bundle_hooks.items():
        for group in groups:
            matcher = group.get("matcher")
            suffix = f" (matcher={matcher})" if matcher else ""
            for handler in group.get("hooks", []):
                command = (handler.get("command") or "").replace(
                    _PLACEHOLDER, str(bundle_root)
                )
                lines.append(f"  {event}{suffix}: {command}")
    return "\n".join(lines) if lines else "  (no hooks)"


def _confirm_sync(bundle_root: Path, codex_home: Path, bundle_hooks: dict) -> bool:
    """Interactive checkpoint before ``main()`` writes to the GLOBAL,
    cross-session ``~/.codex/hooks.json`` — a cheap mitigation, not an
    authenticity check (see the ADR's Accepted Risk section): it gives the
    operator one more chance to notice an unexpected bundle path or an
    unfamiliar command before anything is written. Declines on anything
    other than an explicit y/yes, including EOF (a piped/non-interactive
    stdin with no answer must never be read as consent)."""
    print(f"About to merge hooks from bundle: {bundle_root}", file=sys.stderr)
    print(f"into: {codex_home / _HOOKS_FILENAME}", file=sys.stderr)
    print(_describe_bundle_hooks(bundle_hooks, bundle_root), file=sys.stderr)
    try:
        answer = input("Proceed? [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle-root",
        default=None,
        help="Codex bundle root (default: resolved via SHIPWRIGHT_PLUGIN_ROOT / "
        "CLAUDE_PLUGIN_ROOT / PLUGIN_ROOT)",
    )
    parser.add_argument(
        "--codex-home",
        default=None,
        help="Codex config-layer home (default: ~/.codex — NEVER pass this in "
        "tests or a scratch live-proof run without an explicit override)",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Sync even if the bundle yields zero hooks (default: refuse, since "
        "this is almost always a corrupt or partial build, not a real bundle)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive y/N confirmation before writing to the "
        "global ~/.codex/hooks.json (for scripted/test use). A future "
        "automated caller should only pass this once it has established "
        "equivalent trust some other way.",
    )
    args = parser.parse_args(argv)

    if args.bundle_root is not None:
        bundle_root = Path(args.bundle_root)
    else:
        try:
            bundle_root = resolve_plugin_root()
        except PluginRootUnresolvedError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    codex_home = Path(args.codex_home) if args.codex_home is not None else Path.home() / ".codex"

    if not args.yes and is_codex_runtime(bundle_root):
        try:
            bundle_hooks = _read_bundle_hooks(bundle_root)
        except CodexHooksSyncError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if not _confirm_sync(bundle_root.resolve(), codex_home, bundle_hooks):
            print("aborted: sync declined", file=sys.stderr)
            return 1

    try:
        result = sync_codex_hooks(
            bundle_root, codex_home=codex_home, allow_empty=args.allow_empty
        )
    except CodexHooksSyncError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not result.applied:
        print(f"no-op: {result.reason}")
        return 0

    print(f"Synced {result.hooks_written} Shipwright hook(s) into {result.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
