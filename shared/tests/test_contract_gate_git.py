"""The git-anchored half of the contract gate, against a real git repository.

This is the load-bearing half. The bump-check is only a mechanism because its baseline
lives somewhere the pull request cannot rewrite: a pin inside the PR can be edited to
match the change, which empties the diff and lets any version pass. So these tests prove
the two git-backed pieces actually compose against a repo — a unit test of the algebra
alone would leave the enforcement itself unverified (a gate that no-ops is a false green,
which is worse than no gate).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.contract_baseline import (  # noqa: E402
    any_published_contract,
    frozen_fixture_diff,
    published_baseline,
    published_fixtures,
)
from lib.contract_skeleton import ContractViolation, require_bump  # noqa: E402

CONTRACTS = "plugins/demo/tests/contracts"
STEM = "demo-report"


def _require_git() -> None:
    if shutil.which("git") is None:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail("git is required in CI — install git on the runner")
        pytest.skip("git not available on this machine")


def _git(repo: Path, *args: str) -> None:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True,
        check=False, env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull,
                          "GIT_CONFIG_SYSTEM": os.devnull},
    )
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr}")


def _fixture(version: str, skeleton: dict) -> str:
    return json.dumps(
        {"schema_version": version, "contract": {"skeleton": skeleton}}, indent=2) + "\n"


def _write(repo: Path, relpath: str, text: str) -> None:
    path = repo / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def published(tmp_path: Path) -> Path:
    """A repo whose ``origin/main`` publishes contract 1.0 — the immutable baseline."""
    _require_git()
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "T")
    _git(repo, "config", "commit.gpgsign", "false")
    _write(repo, f"{CONTRACTS}/{STEM}-1.0.json",
           _fixture("1.0", {"grade": "string", "score": "number|null"}))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-gpg-sign", "-m", "publish contract 1.0")
    # Stand in for the remote-tracking ref the gate reads. A PR branch cannot rewrite
    # this, which is the entire point.
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


class TestPublishedBaseline:
    def test_reads_the_contract_main_published(self, published: Path):
        baseline = published_baseline(published, CONTRACTS, STEM)
        assert baseline is not None
        version, fixture = baseline
        assert version == "1.0"
        assert fixture["contract"]["skeleton"]["grade"] == "string"

    def test_takes_the_highest_version_not_the_alphabetical_one(self, published: Path):
        # "1.10" sorts BEFORE "1.2" as a string; the baseline must be the newest
        # contract main actually published, not whichever name sorts last.
        for version in ("1.2", "1.10"):
            _write(published, f"{CONTRACTS}/{STEM}-{version}.json",
                   _fixture(version, {"grade": "string"}))
        _git(published, "add", "-A")
        _git(published, "commit", "-q", "--no-gpg-sign", "-m", "more contracts")
        _git(published, "update-ref", "refs/remotes/origin/main", "HEAD")

        version, _ = published_baseline(published, CONTRACTS, STEM)
        assert version == "1.10"

    def test_no_published_contract_means_no_baseline(self, tmp_path: Path):
        # The bootstrap commit that introduces a contract: nothing can be broken yet,
        # so the gate stands down rather than inventing a baseline to compare against.
        _require_git()
        repo = tmp_path / "empty"
        repo.mkdir()
        _git(repo, "init", "-q")
        assert published_baseline(repo, CONTRACTS, STEM) is None


class TestFrozenFixture:
    """The check that closes the hole: you cannot green a break by editing the pin."""

    def test_an_untouched_fixture_passes(self, published: Path):
        assert frozen_fixture_diff(published, f"{CONTRACTS}/{STEM}-1.0.json") is None

    def test_editing_a_published_fixture_is_caught(self, published: Path):
        # The exact circumvention the design exists to stop: rename a field in the
        # producer, then quietly rewrite the pin so the diff comes out empty.
        _write(published, f"{CONTRACTS}/{STEM}-1.0.json",
               _fixture("1.0", {"verdict": "string", "score": "number|null"}))
        reason = frozen_fixture_diff(published, f"{CONTRACTS}/{STEM}-1.0.json")
        assert reason is not None
        assert "PUBLISHED contract fixture" in reason
        assert "bump schema_version" in reason

    def test_a_brand_new_version_is_not_frozen(self, published: Path):
        # Adding 2.0 is the sanctioned path and must not trip the immutability check.
        _write(published, f"{CONTRACTS}/{STEM}-2.0.json",
               _fixture("2.0", {"verdict": "string"}))
        assert frozen_fixture_diff(published, f"{CONTRACTS}/{STEM}-2.0.json") is None

    def test_reformatting_a_fixture_is_not_a_modification(self, published: Path):
        # Compared as parsed JSON, so re-indentation or a CRLF flip is not a "break".
        path = published / CONTRACTS / f"{STEM}-1.0.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps(data, indent=4), encoding="utf-8")
        assert frozen_fixture_diff(published, f"{CONTRACTS}/{STEM}-1.0.json") is None


class TestEndToEndGate:
    """Baseline from git + live shape → the bump the diff obliges, enforced."""

    def _baseline(self, repo: Path):
        version, fixture = published_baseline(repo, CONTRACTS, STEM)
        return fixture["contract"]["skeleton"], version

    def test_a_rename_against_the_published_baseline_demands_a_major(self, published):
        base, base_version = self._baseline(published)
        live = {"verdict": "string", "score": "number|null"}  # grade -> verdict
        with pytest.raises(ContractViolation, match="major"):
            require_bump(base, live, base_version, "1.1", consumer="the WebUI")
        # ...and passes once the major is actually performed.
        require_bump(base, live, base_version, "2.0", consumer="the WebUI")

    def test_an_unchanged_shape_needs_nothing(self, published: Path):
        base, base_version = self._baseline(published)
        require_bump(base, dict(base), base_version, base_version,
                     consumer="the WebUI")


class TestDeletionIsNotAnEscapeHatch:
    """Superseding a version does not retract it — the consumer may still look it up."""

    def test_deleting_a_published_fixture_is_caught(self, published: Path):
        # A working-tree glob would iterate the files that still EXIST and pass
        # vacuously. The published set has to come from git.
        (published / CONTRACTS / f"{STEM}-1.0.json").unlink()

        reason = frozen_fixture_diff(published, f"{CONTRACTS}/{STEM}-1.0.json")

        assert reason is not None and "DELETED" in reason

    def test_the_published_set_is_read_from_git_not_the_working_tree(self, published):
        (published / CONTRACTS / f"{STEM}-1.0.json").unlink()
        assert published_fixtures(published, CONTRACTS, STEM) == ["1.0"]


class TestBootstrapStandDownCannotBeAbused:
    """`published_baseline is None` means "nothing to break" — or a disarmed gate."""

    def test_a_repo_with_no_contracts_at_all_reports_none(self, tmp_path: Path):
        _require_git()
        repo = tmp_path / "virgin"
        repo.mkdir()
        _git(repo, "init", "-q")
        assert any_published_contract(repo) is False

    def test_a_renamed_contracts_dir_does_not_look_like_a_bootstrap(self, published):
        # The disarm: point the gate's constants at a directory main does not carry.
        # published_baseline goes None (looks like "nothing published yet"), but the
        # repo demonstrably DOES publish a contract — so the constants are stale, not
        # the world, and the caller must fail rather than stand down.
        assert published_baseline(published, "plugins/demo/tests/contract", STEM) is None
        assert any_published_contract(published) is True
