"""Regression: the interpreter pin is a MONOREPO fact and must not be distributed.

`iterate-2026-08-01-pin-python-311` put a `.python-version` in each plugin directory
so a contributor's `cd plugins/<name> && uv run pytest tests/` runs the 3.11 this
repo's CI judges pushes with. `update-marketplace.sh` copies plugin trees into
`~/.claude/plugins/cache/shipwright/` with a `find -type f` that includes dotfiles, and
skills invoke `uv run --project {plugin_root}` (shipwright-plan/skills/plan/SKILL.md,
five call sites). uv honours a version file in the `--project` directory — measured
3.12.13 -> 3.11.15 — so shipping those files would force 3.11 onto every end user of
the plugins, who only ever agreed to `requires-python = ">=3.11"`, and would break them
outright where interpreter downloads are blocked.

Raised by the Stage-3 doubt reviewer: the adopted-project objection failed against the
F0 runner (monorepo-shaped, opt-in) and landed here instead, through the plugin payload.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
UPDATE_SH = REPO_ROOT / "scripts" / "update-marketplace.sh"

_SCRIPTS = REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    # APPEND, matching the sibling modules: prepending would let scripts/'s top-level
    # names win resolution for the whole pytest process (ADR-045, one directory over).
    sys.path.append(str(_SCRIPTS))

from cache_tree_compare import NOT_DISTRIBUTED, repo_tracked_files  # noqa: E402

_FIND_BLOCK = re.compile(r"find \"\$(\w+)\" -type f(.*?)-print0", re.DOTALL)
#: The shell vars naming a SOURCE tree that gets copied into the cache. The sibling
#: blocks scan a TARGET tree to prune what source no longer has — those must NOT carry
#: the exclusion, or a `.python-version` synced before this change would be immortal in
#: every existing cache.
_COPY_SOURCES = {"src_dir", "SHARED_SRC", "src"}


def test_every_copy_path_excludes_the_version_file():
    """Asserted per BLOCK, not once over the file.

    A single `".python-version" in text` check passes while one of the three copy paths
    still ships it — which is the only way this regression can actually occur.
    """
    blocks = _FIND_BLOCK.findall(UPDATE_SH.read_text(encoding="utf-8"))
    assert blocks, "no `find -type f ... -print0` block found — has the sync been rewritten?"
    copies = [(var, body) for var, body in blocks if var in _COPY_SOURCES]
    assert len(copies) == len(_COPY_SOURCES), (
        f"expected a copy block for each of {sorted(_COPY_SOURCES)}, found "
        f"{sorted(v for v, _ in copies)} — the sync's shape changed, re-check this guard")
    leaky = [var for var, body in copies if '-not -name ".python-version"' not in body]
    assert not leaky, (
        f"copy path(s) {leaky} would sync .python-version into the plugin cache. Skills "
        "run `uv run --project {plugin_root}`, and uv honours a version file there, so "
        "this forces the monorepo's 3.11 pin onto end users who only declared >=3.11 — "
        "and hard-fails them where uv cannot download 3.11.")


def test_the_comparator_knows_exactly_what_the_sync_refuses_to_copy():
    """The two lists are one fact with two owners, so they get pinned to each other.

    Shipping the exclusion WITHOUT teaching `cache_tree_compare` cost a real regression
    on 2026-08-01: every one of the 14 plugin trees reported `drift` because the repo
    side listed a tracked `.python-version` the cache is correct not to have, and
    `check_plugin_cache_sync.py --strict` exited 1 into a Stop-hook reminder that no
    re-sync could ever clear. A permanently-wrong drift signal is worse than none: the
    next REAL drift arrives as a fifteenth identical-looking line.

    Direction matters, and the consequences are NOT symmetric. Anything the shell
    refuses to copy MUST be in NOT_DISTRIBUTED, or the comparator reports unclearable
    drift — that is the regression above and it is asserted here.

    The reverse is deliberately not asserted, but the honest cost of an OVER-broad
    NOT_DISTRIBUTED entry is worse than "under-reporting": `diffs` iterates the repo
    hashes, so a filtered name can never be a diff; it lands in `cache_only`, which
    does not feed `state` and does not fail `--strict`. A cached copy that DIFFERS in
    content would therefore silently drop from a blocking `drift` to an advisory count.
    Present on both sides is not identical on both sides. (Corrected after review — an
    earlier draft claimed the reverse direction was harmless.)

    Scoped to the COPY blocks, not the whole file: a `-not -name` in a target-side
    PRUNE block would otherwise force that name into NOT_DISTRIBUTED and produce
    exactly the over-broad entry described above.
    """
    blocks = _FIND_BLOCK.findall(UPDATE_SH.read_text(encoding="utf-8"))
    copy_bodies = [body for var, body in blocks if var in _COPY_SOURCES]
    assert copy_bodies, "no copy block found — the sync's shape changed, re-check this guard"
    shell_excluded = set(re.findall(r'-not -name "([^"]+)"', "\n".join(copy_bodies)))
    # Only the literal names; `*`-globs are SKIP_SUFFIXES' business (pinned below).
    named = {n for n in shell_excluded if not n.startswith("*")}
    missing = sorted(named - set(NOT_DISTRIBUTED))
    assert not missing, (
        f"update-marketplace.sh refuses to copy {missing}, but cache_tree_compare."
        f"NOT_DISTRIBUTED does not list them, so every plugin tree carrying one will "
        f"report drift that no re-sync can clear. Add them to NOT_DISTRIBUTED.")


def test_repo_side_only_filtering(tmp_path):
    """The load-bearing asymmetry, which nothing else pins.

    Both branches of `repo_tracked_files` carry the same predicate, which makes hoisting
    it into `walk_tracked_files` the obvious DRY refactor — and that would blind the
    CACHE side, so a stale cached pin would become invisible forever while every
    existing cache-sync test stayed green. Raised by review; asserted here instead.
    """
    name = sorted(NOT_DISTRIBUTED)[0]
    (tmp_path / "keep.txt").write_text("x", encoding="utf-8")
    (tmp_path / name).write_text("3.11\n", encoding="utf-8")

    # Walk-fallback branch (no git repo here): the repo side drops it...
    hashes, basis, _ = repo_tracked_files(tmp_path)
    assert basis.startswith("walk"), basis
    assert "keep.txt" in hashes
    assert name not in hashes, f"{name} must not count as a file the cache is missing"

    # ...while the CACHE-side walk still sees it, so a stale copy stays visible.
    from cache_tree_compare import walk_tracked_files
    assert name in walk_tracked_files(tmp_path), (
        "the cache side must NOT be filtered — a pin synced before the exclusion "
        "existed has to surface as cache_only, or nothing can ever report it")


def test_a_filter_that_empties_the_listing_refuses_instead_of_reporting_ok(monkeypatch, tmp_path):
    """A zero must never read as agreement — the rule this module already applies twice.

    Unreachable while every plugin tracks a SKILL.md, so it is asserted by widening
    NOT_DISTRIBUTED rather than by contriving a repo: an entry broad enough to filter
    everything would otherwise yield tracked_count 0 and state `ok`.
    """
    import cache_tree_compare as ctc

    (tmp_path / "only.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(ctc, "_git_listing", lambda root: (["only.txt"], "git"))
    monkeypatch.setattr(ctc, "NOT_DISTRIBUTED", frozenset({"only.txt"}))

    hashes, basis, unhashable = ctc.repo_tracked_files(tmp_path)
    assert hashes == {}
    assert "filtered every tracked file" in basis, basis
    assert unhashable == 1, "the refusal must keep the pre-filter count, not report 0"


def test_a_tracked_pin_absent_from_the_cache_is_not_drift(tmp_path):
    """End-to-end over `compare_tree`: the verdict, not just the basis.

    This is the regression in its observable form — 14 plugin trees reporting `drift`
    that no re-sync could clear, into a Stop-hook reminder.
    """
    from cache_tree_compare import compare_tree

    name = sorted(NOT_DISTRIBUTED)[0]
    repo_dir, cache_dir = tmp_path / "repo", tmp_path / "cache"
    for d in (repo_dir, cache_dir):
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("# x\n", encoding="utf-8")
    (repo_dir / name).write_text("3.11\n", encoding="utf-8")  # repo only, by design

    result = compare_tree(repo_dir, cache_dir)
    assert result["state"] == "ok", result
    assert result["missing_in_cache_count"] == 0, result

    # And the converse: a cache-side copy is still counted, so it can be reported.
    (cache_dir / name).write_text("3.11\n", encoding="utf-8")
    assert compare_tree(repo_dir, cache_dir)["cache_only_count"] == 1


def test_the_prune_paths_do_not_exclude_it():
    """The other half of the contract, and the reason this is not a whole-file check.

    The target-side scans are how a `.python-version` copied into a cache BEFORE this
    change gets removed. Excluding it there too would leave every already-synced cache
    permanently pinned, with no code path able to clean it up.
    """
    blocks = _FIND_BLOCK.findall(UPDATE_SH.read_text(encoding="utf-8"))
    prunes = [(var, body) for var, body in blocks if var not in _COPY_SOURCES]
    assert prunes, "no target-side prune block found — stale cache entries would never be removed"
    over_excluded = [var for var, body in prunes if '-not -name ".python-version"' in body]
    assert not over_excluded, (
        f"prune path(s) {over_excluded} skip .python-version, so a copy synced before "
        "iterate-2026-08-01-pin-python-311 can never be cleaned out of an existing cache")
