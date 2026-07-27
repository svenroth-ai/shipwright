"""The deploy-profile reader — one place that decides what a profile means.

The polling and data-rollback fields have been declared in every shipped
profile since they were written and nothing read them. These tests drive the
reader through the **real** shipped profiles rather than hand-written fixtures,
because a fixture only proves the reader agrees with the test author.
"""

import json

import pytest
from deploy_profile import (
    DEFAULT_MAX_WAIT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_TIMEOUT,
    ProfileError,
    data_rollback_strategy,
    load_profile,
    smoke_policy,
)

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent.parent
PROFILES_DIR = REPO_ROOT / "shared" / "profiles" / "deploy"
SHIPPED = sorted(PROFILES_DIR.glob("*.json"))


def test_there_are_profiles_to_read():
    """Guard: if the glob silently matched nothing, every test below is vacuous."""
    assert SHIPPED, f"no deploy profiles found under {PROFILES_DIR}"


# --------------------------------------------------------------------------
# Round-trip through the real shipped profiles (Boundary Probe)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.stem)
def test_every_shipped_profile_yields_a_usable_liveness_policy(path):
    profile = load_profile(path)
    policy = smoke_policy(profile)

    declared = json.loads(path.read_text(encoding="utf-8"))["smoke_test"]
    assert policy.timeout == declared["timeout_seconds"]
    assert policy.poll_interval == declared["poll_interval_seconds"]
    assert policy.max_wait == declared["max_wait_seconds"]
    assert policy.health_path == declared["health_path"]
    assert policy.polls is True
    assert set(policy.source.values()) == {f"profile:{profile['target_id']}"}


@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.stem)
def test_every_shipped_profile_declares_what_happens_to_stored_data(path):
    assert data_rollback_strategy(load_profile(path))


# --------------------------------------------------------------------------
# AC7 / AC8 — per-field precedence, and the single-attempt default
# --------------------------------------------------------------------------

def test_no_profile_means_one_attempt_with_todays_defaults():
    policy = smoke_policy()

    assert policy.timeout == DEFAULT_TIMEOUT
    assert policy.poll_interval == DEFAULT_POLL_INTERVAL
    assert policy.max_wait is DEFAULT_MAX_WAIT is None
    assert policy.polls is False
    assert set(policy.source.values()) == {"default"}


def test_an_explicit_flag_overrides_only_its_own_field():
    """AC7 — `--timeout 5` must not discard the target's polling deadline."""
    profile = load_profile(PROFILES_DIR / "jelastic.json")

    policy = smoke_policy(profile, timeout=5)

    assert policy.timeout == 5
    assert policy.source["timeout"] == "cli"
    assert policy.max_wait == 60
    assert policy.source["max_wait"] == "profile:jelastic"
    assert policy.poll_interval == 5
    assert policy.source["poll_interval"] == "profile:jelastic"


# --------------------------------------------------------------------------
# Malformed input fails loudly rather than silently defaulting
# --------------------------------------------------------------------------

def test_a_missing_profile_is_an_error_not_a_silent_default(tmp_path):
    with pytest.raises(ProfileError, match="not found"):
        load_profile(tmp_path / "nope.json")


def test_unparseable_json_is_an_error(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ProfileError, match="not readable JSON"):
        load_profile(broken)


def test_a_profile_without_a_target_id_is_rejected(tmp_path):
    anonymous = tmp_path / "anon.json"
    anonymous.write_text(json.dumps({"smoke_test": {}}), encoding="utf-8")
    with pytest.raises(ProfileError, match="target_id"):
        load_profile(anonymous)


@pytest.mark.parametrize("declared", [
    {"max_wait_seconds": -1},
    {"timeout_seconds": "thirty"},
    {"poll_interval_seconds": True},
])
def test_nonsensical_declared_durations_are_rejected(declared):
    with pytest.raises(ProfileError):
        smoke_policy({"target_id": "x", "smoke_test": declared})


def test_a_deadline_without_a_poll_interval_is_rejected():
    with pytest.raises(ProfileError, match="greater than zero"):
        smoke_policy({"target_id": "x",
                      "smoke_test": {"max_wait_seconds": 60, "poll_interval_seconds": 0}})


def test_a_target_with_no_rollback_block_reports_nothing_rather_than_guessing():
    assert data_rollback_strategy({"target_id": "x"}) is None
    assert data_rollback_strategy(None) is None
