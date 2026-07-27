"""Has the stored data moved past the version we are rolling back to?

Driven against real temporary git repositories — the question is entirely about
what git reports, so a mocked subprocess would only prove the test author's
assumptions about git's output.
"""

import subprocess

import pytest
from data_drift import detect, gate, is_valid_ref


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )


@pytest.fixture
def repo(tmp_path):
    """A repo with a migrations dir and one commit tagged `v1`."""
    root = tmp_path / "app"
    (root / "supabase" / "migrations").mkdir(parents=True)
    _git(root.parent, "init", "-q", "app")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "test")
    (root / "supabase" / "migrations" / "0001_init.sql").write_text("create table t();")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "first")
    _git(root, "tag", "v1")
    return root


def _add_migration(repo, name, commit=True):
    (repo / "supabase" / "migrations" / name).write_text("alter table t add c int;")
    if commit:
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", name)


# --------------------------------------------------------------------------
# AC4 — the states that refuse, and the ones that do not
# --------------------------------------------------------------------------

def test_no_new_migrations_is_clean(repo):
    report = detect(repo, "v1")
    assert report["status"] == "clean"
    assert report["drifted"] is False
    assert report["migrations"] == []


def test_a_committed_migration_added_since_the_ref_is_drift(repo):
    _add_migration(repo, "0002_add_column.sql")

    report = detect(repo, "v1")

    assert report["status"] == "drifted"
    assert report["drifted"] is True
    assert report["migrations"] == ["supabase/migrations/0002_add_column.sql"]


def test_an_uncommitted_migration_still_counts_as_drift(repo):
    """A migration nobody committed yet is still a schema that moved on."""
    _add_migration(repo, "0003_untracked.sql", commit=False)

    report = detect(repo, "v1")

    assert report["status"] == "drifted"
    assert "supabase/migrations/0003_untracked.sql" in report["migrations"]


def test_an_unresolvable_ref_is_unknown_not_clean(repo):
    """Being unable to answer is not permission to proceed."""
    report = detect(repo, "v99")

    assert report["status"] == "unknown"
    assert report["drifted"] is None
    assert "cannot resolve" in report["reason"]


def test_a_project_without_migrations_is_not_applicable(tmp_path):
    report = detect(tmp_path, "v1")
    assert report["status"] == "not-applicable"
    assert report["drifted"] is False


def test_a_non_git_directory_is_unknown(tmp_path):
    (tmp_path / "supabase" / "migrations").mkdir(parents=True)
    report = detect(tmp_path, "v1")
    assert report["status"] == "unknown"
    assert "not a git repository" in report["reason"]


def test_no_project_root_reports_not_checked_rather_than_clean():
    report = detect(None, "v1")
    assert report["status"] == "not-checked"
    assert report["drifted"] is None


def test_a_migrations_dir_outside_the_default_is_honoured(tmp_path):
    root = tmp_path / "app"
    (root / "db" / "migrate").mkdir(parents=True)
    _git(root.parent, "init", "-q", "app")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "test")
    (root / "db" / "migrate" / "0001.sql").write_text("create table t();")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "first")
    _git(root, "tag", "v1")

    assert detect(root, "v1", migrations_dir="db/migrate")["status"] == "clean"
    assert detect(root, "v1")["status"] == "not-applicable"


# --------------------------------------------------------------------------
# AC13 — the ref crosses into argv, so its shape is checked first
# --------------------------------------------------------------------------

@pytest.mark.parametrize("ref", ["v1.2.3", "main", "release-1", "refs/heads/main", "a_b.c"])
def test_valid_refs_are_accepted(ref):
    assert is_valid_ref(ref) is True


@pytest.mark.parametrize("ref", [
    "", "HEAD; rm -rf /", "-oProxyCommand=x", "a..b", "with space", "a//b",
    "tip@{2}", "ends/", "ends.", "branch.lock", "c:\\win", "a^b", "a~1", "a?b", "a*b", "a[b",
    "@",
    # git's rules apply per slash-separated component, not to the whole string
    "feature/.hidden", "release.lock/tip", "a/b.", "a/.b/c",
])
def test_dangerous_or_malformed_refs_are_rejected(ref):
    assert is_valid_ref(ref) is False


def test_a_shell_metacharacter_ref_never_reaches_git(repo):
    """It is rejected at the shape check, before any subprocess is built."""
    report = detect(repo, "v1; touch pwned")

    assert report["status"] == "unknown"
    assert "invalid ref" in report["reason"]
    assert not (repo / "pwned").exists()


# --------------------------------------------------------------------------
# The gate — what the target's own declared strategy does to the question
# --------------------------------------------------------------------------

def test_drift_refuses_and_names_the_targets_strategy(repo):
    _add_migration(repo, "0002_add_column.sql")

    report, refusal = gate(repo, "v1", strategy="down-migration", target_id="jelastic")

    assert report["status"] == "drifted"
    assert "down-migration" in refusal
    assert "0002_add_column.sql" in refusal


def test_an_unresolvable_ref_refuses_rather_than_guessing(repo):
    report, refusal = gate(repo, "v99", strategy="down-migration")

    assert report["status"] == "unknown"
    assert "cannot tell" in refusal


def test_acknowledging_the_drift_lifts_the_refusal(repo):
    _add_migration(repo, "0002_add_column.sql")

    report, refusal = gate(repo, "v1", strategy="down-migration", ack=True)

    assert report["status"] == "drifted"
    assert refusal is None


def test_a_target_whose_data_never_moves_skips_the_question(repo):
    """`none-app-only` means there is no data tier to meet — do not refuse."""
    _add_migration(repo, "0002_add_column.sql")

    report, refusal = gate(repo, "v99", strategy="none-app-only", target_id="vercel")

    assert refusal is None
    assert report["status"] == "not-applicable"
    assert "vercel" in report["reason"]


def test_an_undeclared_strategy_still_refuses_and_says_it_is_undeclared(repo):
    _add_migration(repo, "0002_add_column.sql")

    _, refusal = gate(repo, "v1", strategy=None)

    assert "not declared by the target" in refusal
