"""Tests for the coded release entry point's auto-rollback (FR-01.08
criterion 5) — split out of ``test_release.py`` once it crossed the 300-line
guideline.

Criterion 5 — a smoke-test failure automatically restores the previous
version. Before ``release.py`` this was pure SKILL.md agent prose with no
coded artifact a test could drive; these tests are that artifact.
"""

import json

import release
import release_rollback


def _write_test_results(project_root, *, unit_status="passed", e2e_status="passed"):
    (project_root / "shipwright_test_results.json").write_text(
        json.dumps({"unit": {"status": unit_status}, "e2e": {"status": e2e_status}}),
        encoding="utf-8",
    )


def test_smoke_success_never_triggers_a_rollback(client, tmp_path, monkeypatch):
    client()
    _write_test_results(tmp_path)
    monkeypatch.setattr(
        release_rollback.smoke_test, "run_smoke_test",
        lambda *a, **k: {"success": True, "url": "http://x"},
    )

    result = release.release(
        "dev-demo", "https://example.invalid/app.git", "feature-branch",
        target="dev", project_root=tmp_path, smoke_url="http://x",
    )

    assert result["released"] is True
    assert result["smoke_checked"] is True
    assert "rollback_triggered" not in result


def test_smoke_failure_automatically_rolls_back_to_the_previous_ref(client, tmp_path, monkeypatch):
    """AC05: the previously-live ref (``main``, from the fixture's default
    project) is restored WITHOUT any agent deciding to invoke rollback.py —
    the trigger is coded, and the audit trail records it as automatic.
    """
    recording = client()  # fixture project starts pinned to "main"
    _write_test_results(tmp_path)
    monkeypatch.setattr(
        release_rollback.smoke_test, "run_smoke_test",
        lambda *a, **k: {"success": False, "url": "http://x", "error": "connection refused"},
    )

    result = release.release(
        "dev-demo", "https://example.invalid/app.git", "feature-branch",
        target="dev", project_root=tmp_path, smoke_url="http://x",
        smoke_max_wait=10,
    )

    assert result["released"] is False
    assert result["failure_stage"] == "smoke"
    assert result["rollback_triggered"] is True
    assert result["rollback"]["success"] is True
    assert result["rollback"]["target_ref"] == "main"
    assert recording.params_for("editproject")[-1]["branch"] == "main"
    # The mock keeps reporting failure, so the post-rollback recheck (doubt
    # review finding #5) must say the restored ref is NOT confirmed healthy —
    # a ref pin alone is not the same claim as "serving traffic again".
    assert result["rollback_verified_healthy"] is False

    history = (tmp_path / ".shipwright" / "deploy" / "rollback-history.jsonl").read_text(encoding="utf-8")
    entry = json.loads(history.strip().splitlines()[-1])
    assert entry["invocation"] == "auto"
    assert entry["target_ref"] == "main"


def test_a_recovered_rollback_is_confirmed_healthy_by_the_recheck(client, tmp_path, monkeypatch):
    """Once the restored ref is actually serving traffic again, the recheck
    (doubt review finding #5) says so — not just that the pin was accepted.
    """
    client()  # fixture project starts pinned to "main"
    _write_test_results(tmp_path)
    calls = {"n": 0}

    def _flaky_then_healthy(*a, **k):
        calls["n"] += 1
        # First call is the initial post-deploy smoke check (fails); second
        # is the post-rollback recheck against the restored ref (succeeds).
        return {"success": calls["n"] > 1, "url": "http://x"}

    monkeypatch.setattr(release_rollback.smoke_test, "run_smoke_test", _flaky_then_healthy)

    result = release.release(
        "dev-demo", "https://example.invalid/app.git", "feature-branch",
        target="dev", project_root=tmp_path, smoke_url="http://x",
        smoke_max_wait=10,
    )

    assert result["rollback_triggered"] is True
    assert result["rollback_verified_healthy"] is True
    assert calls["n"] == 2


def test_smoke_failure_skips_rollback_when_no_deadline_is_configured(client, tmp_path, monkeypatch):
    """A single fixed-timeout attempt with no polling deadline (neither
    --profile nor --smoke-max-wait) is not trusted to trigger a host
    mutation on its own (doubt review finding #2) — the failure is still
    reported, but auto-rollback is skipped rather than fired on one attempt.
    """
    recording = client()  # fixture project starts pinned to "main"
    _write_test_results(tmp_path)
    monkeypatch.setattr(
        release_rollback.smoke_test, "run_smoke_test",
        lambda *a, **k: {"success": False, "url": "http://x", "error": "connection refused"},
    )

    result = release.release(
        "dev-demo", "https://example.invalid/app.git", "feature-branch",
        target="dev", project_root=tmp_path, smoke_url="http://x",
    )

    assert result["released"] is False
    assert result["rollback_triggered"] is False
    assert "deadline" in result["rollback_skipped_reason"]
    assert "editproject" not in recording.endpoints


def test_smoke_failure_with_no_previous_ref_skips_rollback(client, tmp_path, monkeypatch):
    """A brand-new environment has nothing to restore — auto-rollback must
    not guess, it must skip and say why.
    """
    recording = client(fail_on={"getprojects"})
    _write_test_results(tmp_path)
    monkeypatch.setattr(
        release_rollback.smoke_test, "run_smoke_test",
        lambda *a, **k: {"success": False, "url": "http://x", "error": "connection refused"},
    )

    result = release.release(
        "dev-demo", "https://example.invalid/app.git", "feature-branch",
        target="dev", project_root=tmp_path, smoke_url="http://x",
        smoke_max_wait=10,
    )

    assert result["released"] is False
    assert result["rollback_triggered"] is False
    assert "rollback_skipped_reason" in result
    assert "editproject" not in recording.endpoints


def test_a_failed_audit_write_never_crashes_the_auto_rollback(client, tmp_path, monkeypatch):
    """Mirrors rollback.py's own main(): a lock timeout writing the audit
    trail must not crash a rollback that already mutated the host — it
    degrades to the durable marker instead (Tier-3 PR review round 4).
    """
    client()
    _write_test_results(tmp_path)
    monkeypatch.setattr(
        release_rollback.smoke_test, "run_smoke_test",
        lambda *a, **k: {"success": False, "url": "http://x", "error": "connection refused"},
    )

    def _boom(*a, **k):
        raise release_rollback.LockTimeout("locked")

    monkeypatch.setattr(release_rollback.rollback_audit, "record", _boom)

    result = release.release(
        "dev-demo", "https://example.invalid/app.git", "feature-branch",
        target="dev", project_root=tmp_path, smoke_url="http://x",
        smoke_max_wait=10,
    )

    assert result["rollback_triggered"] is True
    marker = tmp_path / ".shipwright" / "deploy" / "rollback-audit-degraded.jsonl"
    assert marker.exists()


def test_an_invalid_smoke_poll_interval_is_reported_not_raised(client, tmp_path):
    """A bad --smoke-poll-interval only surfaces once smoke verification is
    reached (the policy is resolved lazily) — after the deploy already
    happened. It must degrade to a structured result, not an uncaught
    ``ValueError`` traceback.
    """
    client()
    _write_test_results(tmp_path)

    result = release.release(
        "dev-demo", "https://example.invalid/app.git", "main",
        target="dev", project_root=tmp_path, smoke_url="http://x",
        smoke_max_wait=10, smoke_poll_interval=0,
    )

    assert result["released"] is False
    assert result["failure_stage"] == "smoke_config"
    assert "poll_interval" in result["reason"]


def test_smoke_failure_skips_rollback_when_deployed_ref_matches_previous(client, tmp_path, monkeypatch):
    """Redeploying the same ref that was already live has nothing to roll
    back TO — this is not a regression to restore away from.
    """
    recording = client()  # fixture project starts pinned to "main"
    _write_test_results(tmp_path)
    monkeypatch.setattr(
        release_rollback.smoke_test, "run_smoke_test",
        lambda *a, **k: {"success": False, "url": "http://x", "error": "connection refused"},
    )

    result = release.release(
        "dev-demo", "https://example.invalid/app.git", "main",
        target="dev", project_root=tmp_path, smoke_url="http://x",
        smoke_max_wait=10,
    )

    assert result["rollback_triggered"] is False
    assert "editproject" not in recording.endpoints
