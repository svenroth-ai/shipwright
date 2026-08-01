"""A green from the cache-sync check must mean exactly the trees it read.

``scripts/check_plugin_cache_sync.py`` compared only ``plugins/shipwright-*``
while its own docstring promised ``shared/scripts/`` too. The runtime cache
carries three trees, not one:

- ``cache/<plugin>/<version>/``  — the installed plugins (was compared);
- ``cache/shared/``             — reached as ``{plugin_root}/../../shared``,
  and the home of the F11 finalization verifier (was NOT compared — this is
  what the iterate closes);
- ``cache/plugins/<plugin>/``   — the cross-plugin mirror (still NOT compared,
  on purpose; see the companion file).

Measured on 2026-08-01: deleting all 55 modules under
``shared/scripts/tools/verifiers/`` from the cache made the F11 verifier die
with ``ModuleNotFoundError: No module named 'tools.verifiers'``, left the
SessionStart self-heal hook a no-op (its sentinel ``scripts/lib/project_root.py``
survives a partial reap), and still printed
``plugin-cache-sync: ok - all 14 plugin(s) in sync`` with ``--strict`` exit 0.

This file pins WHAT is compared. ``test_plugin_cache_sync_verdict.py`` pins
what the verdict is allowed to CLAIM about it.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.append(str(_HERE))  # for the sibling cache_sync_fixtures module
if str(_SCRIPTS) not in sys.path:
    # APPEND, matching the module under test: prepending would let scripts/'s
    # top-level module names win resolution for the whole pytest process
    # (ADR-045 lib-collision, one directory over). Nothing here needs
    # precedence — no other `check_plugin_cache_sync` exists on any path.
    sys.path.append(str(_SCRIPTS))

from check_plugin_cache_sync import check_sync, main  # noqa: E402
from cache_sync_fixtures import seed_repo_and_cache as _seed  # noqa: E402
from cache_sync_fixtures import write_tree as _write  # noqa: E402


class TestSharedTreeIsCompared:
    """The cache's ``shared/`` tree is in scope, not merely copied."""

    def test_in_sync_shared_tree_is_reported_ok_with_a_count(self, tmp_path: Path):
        files = {"scripts/tools/verify_iterate_finalization.py": "x = 1\n",
                 "constitution.md": "# rules\n"}
        repo, cache = _seed(tmp_path, shared=files, cache_shared=files)
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "ok"
        assert result["shared"]["state"] == "ok"
        # A count proves the tree was actually walked, not skipped.
        assert result["shared"]["tracked_count"] == 2

    def test_stale_shared_file_is_drift(self, tmp_path: Path):
        repo, cache = _seed(
            tmp_path,
            shared={"scripts/tools/f11.py": "new = 1\n"},
            cache_shared={"scripts/tools/f11.py": "old = 1\n"},
        )
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "drift"
        assert result["shared"]["state"] == "drift"
        assert "scripts/tools/f11.py" in result["shared"]["sample"]

    def test_partial_reap_of_the_verifier_tree_is_drift(self, tmp_path: Path):
        """The measured failure: verifier modules reaped, sentinel intact.

        ``scripts/lib/project_root.py`` is the self-heal hook's health
        sentinel. It survives here exactly as it did in the real reap, so the
        hook stays a no-op — which is precisely why this gate has to be the
        one that notices.
        """
        repo, cache = _seed(
            tmp_path,
            shared={
                "scripts/lib/project_root.py": "sentinel = 1\n",
                "scripts/tools/verifiers/common.py": "c = 1\n",
                "scripts/tools/verifiers/ci_supplychain.py": "s = 1\n",
            },
            cache_shared={"scripts/lib/project_root.py": "sentinel = 1\n"},
        )
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "drift"
        assert result["shared"]["missing_in_cache_count"] == 2
        rc = main(["--repo-root", str(repo), "--cache-root", str(cache), "--strict"])
        assert rc == 1

    def test_shared_absent_from_cache_is_drift(self, tmp_path: Path):
        repo, cache = _seed(tmp_path, shared={"scripts/lib/a.py": "a = 1\n"})
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "drift"
        assert result["shared"]["state"] == "not_in_cache"

    def test_repo_without_a_shared_dir_reports_na_not_drift(self, tmp_path: Path):
        """Only the monorepo has ``shared/``; its absence is not a finding."""
        repo, cache = _seed(tmp_path)
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "ok"
        assert result["shared"]["state"] == "n/a"


class TestTheTreeIsDefinedByExclusion:
    """"In sync" must mean what ``update-marketplace.sh`` actually syncs.

    A seven-suffix allowlist left 44 of 1005 cached ``shared/`` files
    invisible (33 ``.template``, 8 extensionless, 3 ``.ts``) — 3/37 verified
    under ``shared/templates/`` and 3/9 under ``shared/prompts/``, both read
    from the cache at runtime and both able to vanish under a green.
    """

    def test_a_template_file_missing_from_the_cache_is_drift(self, tmp_path: Path):
        repo, cache = _seed(
            tmp_path,
            shared={"templates/github-actions/security.yml.template": "on: push\n"},
            cache_shared={},
        )
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "drift"
        assert result["shared"]["missing_in_cache_count"] == 1

    def test_an_extensionless_prompt_body_is_compared(self, tmp_path: Path):
        """``shared/prompts/code_reviewer/system`` has no suffix at all."""
        repo, cache = _seed(
            tmp_path,
            shared={"prompts/code_reviewer/system": "You are a reviewer.\n"},
            cache_shared={"prompts/code_reviewer/system": "STALE\n"},
        )
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "drift"
        assert "prompts/code_reviewer/system" in result["shared"]["sample"]

    def test_crlf_is_normalized_for_files_outside_any_suffix_list(
            self, tmp_path: Path):
        """Content, not suffix, decides text — or every .template false-drifts.

        A Windows checkout stores these with CRLF and the Linux-synced cache
        with LF; a suffix-based rule would have reported all 33 of them as
        drifted forever the moment the walk started including them.
        """
        repo, cache = _seed(tmp_path)
        for root, eol in ((repo / "shared", b"\r\n"), (cache / "shared", b"\n")):
            for rel in ("templates/rules/migrations.md.template",
                        "prompts/code_reviewer/system"):
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"line one" + eol + b"line two" + eol)
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "ok"
        assert result["shared"]["tracked_count"] == 2

    def test_a_directory_named_build_is_not_treated_as_build_output(
            self, tmp_path: Path):
        """``plugins/shipwright-build/skills/build/`` is 29 tracked files.

        A bare ``build`` in the component-matched skip set dropped every one
        of them — ``SKILL.md`` and the whole ``references/`` tree — from both
        sides, so the most-edited plugin-side file in the repo could never
        drift. Measured 2026-08-01: 0 of 29 walked.
        """
        repo, cache = _seed(tmp_path)
        _write(repo / "plugins" / "shipwright-foo",
               {"skills/build/SKILL.md": "# new\n"})
        _write(cache / "shipwright-foo" / "0.1.0",
               {"skills/build/SKILL.md": "# stale\n"})
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "drift"
        assert "skills/build/SKILL.md" in result["plugins"][0]["sample"]

    def test_build_artifacts_stay_excluded_on_both_sides(self, tmp_path: Path):
        repo, cache = _seed(
            tmp_path,
            shared={"scripts/lib/a.py": "a = 1\n",
                    "scripts/__pycache__/a.cpython-312.pyc": "junk",
                    "scripts/a.pyc": "junk"},
            cache_shared={"scripts/lib/a.py": "a = 1\n"},
        )
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "ok"
        assert result["shared"]["tracked_count"] == 1
