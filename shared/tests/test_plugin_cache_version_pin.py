"""The producer and the checker must resolve the cache target from the SAME facts.

`update-marketplace.sh` finds a plugin's live directory with `_install_path` — a Python
heredoc reading `~/.claude/plugins/installed_plugins.json`. `scripts/cache_install_resolve.py`
reads the identical file, key and entry from the other side. Nothing but this module connects
them, and a rename on either side is silent in the worst way: the sync keeps writing where it
always did while the check looks for a key nothing writes, falls back to the highest cached
version, and stays GREEN over a directory runtime does not load.

That is not hypothetical — it is the shape of the `.python-version` regression that preceded
this one (`test_marketplace_excludes_python_version.py`), where the sync gained an exclusion
the comparator was never taught. That module pins the exclusion; this one pins the target
directory. Both exist because one contract has two independent implementations.

Split from `test_plugin_cache_version_resolution.py` (which pins the BEHAVIOUR) so neither
module has to trade reasoning away to stay under 300 lines.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    # APPEND, matching the sibling cache modules: prepending would let scripts/'s top-level
    # names win resolution for the whole pytest process (ADR-045).
    sys.path.append(str(_SCRIPTS))

from cache_install_resolve import (  # noqa: E402
    INSTALL_PATH_KEY,
    MARKETPLACE_NAME,
    PLUGINS_KEY,
    default_cache_root,
    default_installed_plugins_path,
    plugin_key,
)

UPDATE_SH = _REPO_ROOT / "scripts" / "update-marketplace.sh"
PLUGIN = "shipwright-foo"

_INSTALL_PATH_FN = re.compile(r"_install_path\(\)\s*\{(.*?)\n\}", re.DOTALL)


def _body() -> str:
    match = _INSTALL_PATH_FN.search(UPDATE_SH.read_text(encoding="utf-8"))
    assert match, "`_install_path()` not found — the sync's shape changed, re-check this guard"
    return match.group(1)


def test_the_sync_reads_the_manifest_this_module_reads():
    """DERIVED from the Python side, never spelled out twice.

    A literal expectation here would pin the shell to a constant and leave the Python free to
    drift — half a pin, and the half that fails silently. Anchored at ``~`` because an
    absolute path passes on one machine and fails everywhere else.
    """
    expected = "~/" + default_installed_plugins_path().relative_to(Path.home()).as_posix()
    assert expected in _body(), (
        f"the sync does not read {expected}, which is where "
        f"cache_install_resolve.default_installed_plugins_path() looks")


def test_the_sync_reads_the_keys_this_module_reads():
    body = _body()
    assert f"'{PLUGINS_KEY}'" in body, f"sync no longer reads data[{PLUGINS_KEY!r}]: {body}"
    assert f"'{INSTALL_PATH_KEY}'" in body, (
        f"sync no longer reads entries[0][{INSTALL_PATH_KEY!r}], so cache_install_resolve "
        f"reads a key nothing writes: {body}")
    assert "entries[0]" in body, "sync no longer takes the FIRST entry"


def test_the_lookup_key_is_built_the_same_way():
    """Both halves of the key: the marketplace literal AND the ``@`` that joins it.

    Derived too — ``plugin_key()`` is rebuilt from the name the SHELL declares, so a change
    to either the separator or the name breaks this, in either direction.
    """
    text = UPDATE_SH.read_text(encoding="utf-8")
    shell_name = re.search(r'MARKETPLACE_NAME="([^"]+)"', text)
    assert shell_name, "MARKETPLACE_NAME not found in the sync"
    assert shell_name.group(1) == MARKETPLACE_NAME
    assert plugin_key(PLUGIN) == f"{PLUGIN}@{shell_name.group(1)}", (
        "plugin_key() no longer produces the <plugin>@<marketplace> key the sync writes")
    assert '"${plugin}@${MARKETPLACE_NAME}"' in text, (
        "the sync no longer builds its lookup key as <plugin>@<marketplace>, so "
        "cache_install_resolve.plugin_key() would look up a key that is never written")


def test_the_copy_target_is_the_pinned_function_s_output():
    """Pinning `_install_path`'s BODY is not enough — it has to still decide the copy target.

    Step 5 already re-reads the manifest for `entries[0]['version']`. Consolidating Step 2 to
    `cache_target="$cache_base/$installed_version"` would leave `_install_path` defined and
    still used by the symlink loop, so every literal the other tests look for survives — while
    the producer starts targeting `version` and the checker keeps targeting the basename of
    `installPath`. Those are the same string today and nothing requires them to stay so.
    """
    text = UPDATE_SH.read_text(encoding="utf-8")
    copy_block = text.split("Step 2:", 1)[-1].split("Step 3:", 1)[0]
    assert 'cache_target=$(_install_path' in copy_block, (
        "the copy target no longer comes from _install_path(), so pinning that function no "
        "longer pins where the sync actually writes")


def test_the_sync_copies_every_plugin_the_check_inspects():
    """The two sides enumerate plugins differently: a hardcoded array vs a glob of the repo.

    Nothing else connects them, and the gap has already cost once — shipwright-grade sat
    `not_in_cache` forever (decision_log.md:4112). A plugin added to the repo and forgotten
    here is drift no re-sync can clear, which is the failure mode this whole family exists to
    prevent: a permanently-wrong signal is worse than no signal.
    """
    text = UPDATE_SH.read_text(encoding="utf-8")
    array = re.search(r"PLUGINS=\(\s*(.*?)\)", text, re.DOTALL)
    assert array, "PLUGINS=(...) not found — the sync's shape changed, re-check this guard"
    synced = set(array.group(1).split())
    in_repo = {d.name for d in (_REPO_ROOT / "plugins").iterdir()
               if d.is_dir() and d.name.startswith("shipwright-")}
    assert synced == in_repo, (
        f"the sync copies {sorted(synced - in_repo)} that the repo does not have, and misses "
        f"{sorted(in_repo - synced)} that check_plugin_cache_sync.py will report as drift "
        f"forever — add it to PLUGINS=() in scripts/update-marketplace.sh")


def test_both_sides_agree_on_where_the_cache_lives():
    """The cache root is the marketplace name, on both sides.

    `default_cache_root()` derives it from `MARKETPLACE_NAME` rather than repeating the
    literal, so this asserts a fact about the code instead of a claim in a comment.
    """
    text = UPDATE_SH.read_text(encoding="utf-8")
    assert default_cache_root().name == MARKETPLACE_NAME
    assert 'SHARED_TARGET="$HOME/.claude/plugins/cache/shipwright/shared"' in text, (
        "the sync's cache root moved; cache_install_resolve.default_cache_root() still "
        "points at ~/.claude/plugins/cache/<marketplace>")
